"""Adjacent-tier tonal separation derived from retained regional activation traces."""
from __future__ import annotations

import math

import numpy as np

_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def summarise(values):
    finite = [_finite(value) for value in values]
    finite = [value for value in finite if value is not None]
    result = {
        "finite_frames": len(finite),
        "q10": None,
        "q50": None,
        "q90": None,
        "status": "ok" if len(finite) >= 3 else "unavailable",
        "reasons": [] if len(finite) >= 3 else ["insufficient_finite_frames"],
    }
    if len(finite) < 3:
        return result
    data = np.asarray(finite, float)
    result.update(
        q10=float(np.quantile(data, 0.1)),
        q50=float(np.quantile(data, 0.5)),
        q90=float(np.quantile(data, 0.9)),
    )
    return result


def contrast_trace(values_a, values_b, source_indices):
    """Framewise signed and absolute log contrast between aligned band traces."""
    if len(values_a) != len(values_b) or len(values_a) != len(source_indices):
        raise ValueError("paired traces and source indices must have equal length")
    frames = []
    separation = []
    for position, (left, right, source_index) in enumerate(
        zip(values_a, values_b, source_indices)
    ):
        left = _finite(left)
        right = _finite(right)
        item = {
            "position": position,
            "source_index": source_index,
            "status": "ok",
            "left_value": left,
            "right_value": right,
            "signed_log_contrast": None,
            "separation": None,
        }
        if left is None or right is None:
            item["status"] = "gap"
            frames.append(item)
            separation.append(None)
            continue
        signed = float(left - right)
        distance = abs(signed)
        item["signed_log_contrast"] = signed
        item["separation"] = distance
        frames.append(item)
        separation.append(distance)
    return {
        "frame_trace": frames,
        "separation_values": separation,
        "summary": summarise(separation),
    }


def brightness_contrast_trace(inside_values, outside_values, source_indices):
    """Signed/absolute log contrast from positive brightness medians.

    This is the boundary-local primitive used by issue #57. Invalid,
    non-positive, or missing brightness values remain explicit gaps rather
    than being epsilon-adjusted.
    """
    if len(inside_values) != len(outside_values) or len(inside_values) != len(source_indices):
        raise ValueError("paired brightness traces and source indices must have equal length")

    def _logs(values):
        result = []
        for value in values:
            value = _finite(value)
            result.append(
                float(math.log(value))
                if value is not None and value > 0 else None
            )
        return result

    result = contrast_trace(_logs(inside_values), _logs(outside_values), source_indices)
    for row, inside, outside in zip(result["frame_trace"], inside_values, outside_values):
        inside = _finite(inside)
        outside = _finite(outside)
        row["inside_brightness"] = inside if inside is not None and inside > 0 else None
        row["outside_brightness"] = outside if outside is not None and outside > 0 else None
    return result

def robust_fractional_spread(values):
    """1.4826*MAD/median on finite positive encoded-brightness samples."""
    data = np.asarray(values, float).ravel()
    data = data[np.isfinite(data)]
    if data.size < 3:
        return None
    median = float(np.median(data))
    if median <= 0:
        return None
    mad = float(np.median(np.abs(data - median)))
    return float(1.4826 * mad / median)


def standardized_trace(frame_trace, spread_a, spread_b):
    """Scale absolute separation by RMS within-band robust fractional spread."""
    if len(frame_trace) != len(spread_a) or len(frame_trace) != len(spread_b):
        raise ValueError("contrast and spread traces must have equal length")
    frames = []
    values = []
    for item, left_spread, right_spread in zip(frame_trace, spread_a, spread_b):
        value = _finite(item.get("separation"))
        left_spread = _finite(left_spread)
        right_spread = _finite(right_spread)
        row = {
            "position": item["position"],
            "source_index": item["source_index"],
            "status": "ok",
            "separation": value,
            "left_fractional_spread": left_spread,
            "right_fractional_spread": right_spread,
            "scale": None,
            "standardized_separation": None,
        }
        if value is None or left_spread is None or right_spread is None:
            row["status"] = "gap"
            frames.append(row)
            values.append(None)
            continue
        if left_spread < 0 or right_spread < 0:
            raise ValueError("spread values must be nonnegative")
        scale = math.sqrt((left_spread ** 2 + right_spread ** 2) / 2.0)
        row["scale"] = float(scale)
        if scale <= 0:
            row["status"] = "zero_spread_scale"
            frames.append(row)
            values.append(None)
            continue
        standardized = float(value / scale)
        row["standardized_separation"] = standardized
        frames.append(row)
        values.append(standardized)
    return {
        "frame_trace": frames,
        "values": values,
        "summary": summarise(values),
    }


def _nearest_event(frame_trace, key, target):
    finite = [
        item for item in frame_trace
        if _finite(item.get(key)) is not None
    ]
    if not finite:
        return None
    return min(
        finite,
        key=lambda item: (abs(float(item[key]) - target), item["position"]),
    )


def _extreme_event(frame_trace, key, largest):
    finite = [
        item for item in frame_trace
        if _finite(item.get(key)) is not None
    ]
    if not finite:
        return None
    if largest:
        return max(finite, key=lambda item: (float(item[key]), -item["position"]))
    return min(finite, key=lambda item: (float(item[key]), item["position"]))


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def select_evidence(simple_trace, standardized=None):
    """Select weak/median/strong simple frames plus maximal formulation disagreement."""
    summary = summarise([item.get("separation") for item in simple_trace])
    evidence = {
        "weakest": _extreme_event(simple_trace, "separation", False),
        "median": (
            _nearest_event(simple_trace, "separation", summary["q50"])
            if summary["q50"] is not None else None
        ),
        "strongest": _extreme_event(simple_trace, "separation", True),
        "strongest_formulation_disagreement": None,
    }
    if standardized is None:
        return evidence
    aligned = []
    for simple, scaled in zip(simple_trace, standardized):
        left = _finite(simple.get("separation"))
        right = _finite(scaled.get("standardized_separation"))
        if left is not None and right is not None:
            aligned.append((simple["position"], left, right, simple, scaled))
    if len(aligned) < 2:
        return evidence
    simple_ranks = _average_ranks([item[1] for item in aligned])
    scaled_ranks = _average_ranks([item[2] for item in aligned])
    denom = max(1.0, len(aligned) - 1.0)
    candidates = []
    for index, item in enumerate(aligned):
        disagreement = abs(simple_ranks[index] - scaled_ranks[index]) / denom
        candidates.append((disagreement, -item[0], item))
    disagreement, _, item = max(candidates)
    evidence["strongest_formulation_disagreement"] = {
        **item[3],
        "standardized_separation": item[4]["standardized_separation"],
        "rank_disagreement": float(disagreement),
    }
    return evidence


def strongest_rank_disagreement(left_trace, left_key, right_trace, right_key):
    """Return the aligned frame whose two formulations disagree most in rank."""
    if len(left_trace) != len(right_trace):
        raise ValueError("compared traces must have equal length")
    aligned = []
    for position, (left, right) in enumerate(zip(left_trace, right_trace)):
        if left.get("source_index") != right.get("source_index"):
            raise ValueError("compared traces must share source-index alignment")
        left_value = _finite(left.get(left_key))
        right_value = _finite(right.get(right_key))
        if left_value is None or right_value is None:
            continue
        aligned.append((
            position, left["source_index"], left_value, right_value
        ))
    if len(aligned) < 2:
        return None
    left_ranks = _average_ranks([row[2] for row in aligned])
    right_ranks = _average_ranks([row[3] for row in aligned])
    denom = max(1.0, len(aligned) - 1.0)
    candidates = []
    for index, row in enumerate(aligned):
        disagreement = abs(left_ranks[index] - right_ranks[index]) / denom
        candidates.append((disagreement, -row[0], row))
    disagreement, _, row = max(candidates)
    return {
        "position": row[0],
        "source_index": row[1],
        "left_value": row[2],
        "right_value": row[3],
        "rank_disagreement": float(disagreement),
    }

def compose_validity(component_validities, local_summary):
    """Monotone validity composition; usefulness/disposition stays separate."""
    worst = "ok"
    reasons = []
    for source in [*(component_validities or []), local_summary or {}]:
        status = source.get("status", "ok")
        if status not in _STATUS_RANK:
            raise ValueError(f"unknown validity status: {status}")
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
        for reason in [source.get("reason"), *(source.get("reasons") or [])]:
            if reason and reason not in reasons:
                reasons.append(reason)
    return {"status": worst, "reasons": reasons}


def sectorized_contrast_trace(left_sector_values, right_sector_values, source_indices):
    """Preserve matched directional-sector contrast, then summarize typical local separation.

    Inputs map sector name -> positive brightness-median trace. The calculation
    uses log ratios directly, so common multiplicative scene brightness cancels.
    Sector labels are image-axis locations only, not facet identities.
    """
    if set(left_sector_values) != set(right_sector_values) or not left_sector_values:
        raise ValueError("left/right sector sets must match and be non-empty")
    sectors = tuple(sorted(left_sector_values))
    per_sector = {}
    for sector in sectors:
        left = left_sector_values[sector]
        right = right_sector_values[sector]
        if len(left) != len(source_indices) or len(right) != len(source_indices):
            raise ValueError("sector traces must align with source indices")
        per_sector[sector] = brightness_contrast_trace(
            left, right, source_indices
        )

    frame_trace = []
    median_values = []
    q75_values = []
    for position, source_index in enumerate(source_indices):
        values = {
            sector: per_sector[sector]["frame_trace"][position]["separation"]
            for sector in sectors
        }
        signed_values = {
            sector: per_sector[sector]["frame_trace"][position]["signed_log_contrast"]
            for sector in sectors
        }
        finite = {
            sector: float(value)
            for sector, value in values.items()
            if _finite(value) is not None
        }
        row = {
            "position": position,
            "source_index": source_index,
            "status": "ok" if finite else "gap",
            "sector_separations": values,
            "sector_signed_log_contrasts": signed_values,
            "finite_sectors": len(finite),
            "median_separation": None,
            "q75_separation": None,
            "strongest_sector": None,
            "strongest_sector_separation": None,
        }
        if finite:
            data = np.asarray(list(finite.values()), float)
            row["median_separation"] = float(np.median(data))
            row["q75_separation"] = float(np.quantile(data, .75))
            strongest = max(finite, key=lambda sector: (finite[sector], sector))
            row["strongest_sector"] = strongest
            row["strongest_sector_separation"] = finite[strongest]
        frame_trace.append(row)
        median_values.append(row["median_separation"])
        q75_values.append(row["q75_separation"])

    return {
        "sectors": list(sectors),
        "per_sector": per_sector,
        "frame_trace": frame_trace,
        "median_summary": summarise(median_values),
        "q75_summary": summarise(q75_values),
    }


def multiscale_sector_consensus(scale_results):
    """Median a small declared scale family while preserving sector/frame detail.

    ``scale_results`` maps a scale label to a sectorized_contrast_trace result.
    This aggregates only over measurement scale; it does not collapse the eight
    spatial sectors into a production descriptor.
    """
    if not scale_results:
        raise ValueError("at least one scale result is required")
    labels = tuple(sorted(scale_results))
    first = scale_results[labels[0]]
    sectors = tuple(first.get("sectors") or [])
    frame_count = len(first.get("frame_trace") or [])
    if not sectors or frame_count == 0:
        raise ValueError("scale results must contain sectorized frame traces")
    for label in labels[1:]:
        item = scale_results[label]
        if tuple(item.get("sectors") or []) != sectors:
            raise ValueError("scale results must share sectors")
        if len(item.get("frame_trace") or []) != frame_count:
            raise ValueError("scale results must share frame alignment")

    frame_trace = []
    median_values = []
    q75_values = []
    scale_spread_values = []
    for position in range(frame_count):
        source_index = first["frame_trace"][position]["source_index"]
        sector_sep = {}
        sector_signed = {}
        sector_scale_spread = {}
        for sector in sectors:
            separations = []
            signed = []
            for label in labels:
                row = scale_results[label]["frame_trace"][position]
                if row["source_index"] != source_index:
                    raise ValueError("scale results must share source-index alignment")
                value = _finite((row.get("sector_separations") or {}).get(sector))
                if value is not None:
                    separations.append(float(value))
                signed_value = _finite(
                    (row.get("sector_signed_log_contrasts") or {}).get(sector)
                )
                if signed_value is not None:
                    signed.append(float(signed_value))
            sector_sep[sector] = float(np.median(separations)) if separations else None
            sector_signed[sector] = float(np.median(signed)) if signed else None
            sector_scale_spread[sector] = (
                float(max(separations) - min(separations))
                if len(separations) >= 2 else None
            )

        finite = {k: v for k, v in sector_sep.items() if v is not None}
        finite_spread = [v for v in sector_scale_spread.values() if v is not None]
        row = {
            "position": position,
            "source_index": source_index,
            "status": "ok" if finite else "gap",
            "sector_separations": sector_sep,
            "sector_signed_log_contrasts": sector_signed,
            "sector_scale_spread": sector_scale_spread,
            "finite_sectors": len(finite),
            "median_separation": None,
            "q75_separation": None,
            "median_scale_spread": (
                float(np.median(finite_spread)) if finite_spread else None
            ),
            "strongest_sector": None,
            "strongest_sector_separation": None,
        }
        if finite:
            data = np.asarray(list(finite.values()), float)
            row["median_separation"] = float(np.median(data))
            row["q75_separation"] = float(np.quantile(data, .75))
            strongest = max(finite, key=lambda sector: (finite[sector], sector))
            row["strongest_sector"] = strongest
            row["strongest_sector_separation"] = finite[strongest]
        frame_trace.append(row)
        median_values.append(row["median_separation"])
        q75_values.append(row["q75_separation"])
        scale_spread_values.append(row["median_scale_spread"])

    return {
        "scale_labels": list(labels),
        "sectors": list(sectors),
        "frame_trace": frame_trace,
        "median_summary": summarise(median_values),
        "q75_summary": summarise(q75_values),
        "scale_spread_summary": summarise(scale_spread_values),
    }

def select_sectorized_evidence(frame_trace):
    """Weak/typical/strong frames using median matched-sector separation."""
    pseudo = [
        {
            "position": item["position"],
            "source_index": item["source_index"],
            "status": item["status"],
            "separation": item.get("median_separation"),
            "finite_sectors": item.get("finite_sectors"),
            "strongest_sector": item.get("strongest_sector"),
            "strongest_sector_separation": item.get("strongest_sector_separation"),
            "sector_separations": item.get("sector_separations"),
        }
        for item in frame_trace
    ]
    return select_evidence(pseudo)
