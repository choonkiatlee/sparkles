"""Within-inner-region tonal articulation for registered Asscher frames."""
from __future__ import annotations

import math

import numpy as np

MEASURES = (
    "raw_spread",
    "relative_to_whole_median",
    "log_spread",
    "relative_to_whole_contrast",
)


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


def frame_articulation(values, whole_median=None, whole_spread=None):
    """Robust within-region spread plus scale-normalized challengers."""
    data = np.asarray(values, float).ravel()
    data = data[np.isfinite(data)]
    result = {
        "status": "ok" if data.size >= 3 else "unavailable",
        "reasons": [] if data.size >= 3 else ["insufficient_supported_pixels"],
        "supported_pixels": int(data.size),
        "pixel_q10": None,
        "pixel_q50": None,
        "pixel_q90": None,
        **{measure: None for measure in MEASURES},
    }
    if data.size < 3:
        return result

    q10, q50, q90 = (float(np.quantile(data, q)) for q in (0.1, 0.5, 0.9))
    raw = float(q90 - q10)
    result.update(
        pixel_q10=q10,
        pixel_q50=q50,
        pixel_q90=q90,
        raw_spread=raw,
    )

    whole_median = _finite(whole_median)
    if whole_median is not None and whole_median > 0:
        result["relative_to_whole_median"] = float(raw / whole_median)
    if q10 > 0 and q90 > 0:
        result["log_spread"] = float(math.log(q90) - math.log(q10))

    whole_spread = _finite(whole_spread)
    if whole_spread is not None and whole_spread > 0:
        result["relative_to_whole_contrast"] = float(raw / whole_spread)
    return result


def articulation_trace(frames, source_indices, whole_medians=None, whole_spreads=None):
    """Measure aligned per-frame articulation without interpolation."""
    frames = list(frames)
    source_indices = list(source_indices)
    if len(frames) != len(source_indices):
        raise ValueError("frames and source indices must have equal length")
    n = len(frames)
    whole_medians = [None] * n if whole_medians is None else list(whole_medians)
    whole_spreads = [None] * n if whole_spreads is None else list(whole_spreads)
    if len(whole_medians) != n or len(whole_spreads) != n:
        raise ValueError("whole-stone references must align with frames")

    rows = []
    for position, (pixels, source_index, whole_median, whole_spread) in enumerate(
        zip(frames, source_indices, whole_medians, whole_spreads)
    ):
        if pixels is None:
            measured = {
                "status": "gap",
                "reasons": ["unobserved_frame"],
                "supported_pixels": 0,
                "pixel_q10": None,
                "pixel_q50": None,
                "pixel_q90": None,
                **{measure: None for measure in MEASURES},
            }
        else:
            measured = frame_articulation(pixels, whole_median, whole_spread)
        rows.append(
            {
                "position": position,
                "source_index": source_index,
                "whole_median": _finite(whole_median),
                "whole_spread": _finite(whole_spread),
                **measured,
            }
        )

    return {
        "frame_trace": rows,
        "summaries": {
            measure: summarise([row[measure] for row in rows])
            for measure in MEASURES
        },
    }


def _finite_rows(frame_trace, key):
    return [
        row for row in frame_trace
        if _finite(row.get(key)) is not None
    ]


def _extreme(frame_trace, key, largest):
    rows = _finite_rows(frame_trace, key)
    if not rows:
        return None
    if largest:
        return max(rows, key=lambda row: (float(row[key]), -row["position"]))
    return min(rows, key=lambda row: (float(row[key]), row["position"]))


def _nearest(frame_trace, key, target):
    rows = _finite_rows(frame_trace, key)
    if not rows or target is None:
        return None
    return min(rows, key=lambda row: (abs(float(row[key]) - target), row["position"]))


def matched_brightness_pair(
    frame_trace,
    key="raw_spread",
    max_brightness_ratio=1.02,
):
    """Find a brightness-matched counterexample with maximally different articulation.

    A pair is considered brightness-matched when the larger whole-stone median is
    no more than `max_brightness_ratio` times the smaller one. Within that fixed
    tolerance, choose the largest articulation gap. If no pair meets the tolerance,
    fall back to the closest-brightness pair and mark the fallback explicitly.
    """
    if max_brightness_ratio <= 1:
        raise ValueError("max_brightness_ratio must be greater than 1")
    rows = [
        row for row in frame_trace
        if _finite(row.get(key)) is not None
        and _finite(row.get("whole_median")) is not None
        and float(row["whole_median"]) > 0
    ]
    if len(rows) < 2:
        return None

    tolerance = math.log(float(max_brightness_ratio))
    candidates = []
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1:]:
            brightness_gap = abs(
                math.log(float(right["whole_median"]))
                - math.log(float(left["whole_median"]))
            )
            articulation_gap = abs(float(right[key]) - float(left[key]))
            candidates.append(
                {
                    "first": left,
                    "second": right,
                    "articulation_gap": float(articulation_gap),
                    "whole_log_brightness_gap": float(brightness_gap),
                }
            )

    matched = [
        item for item in candidates
        if item["whole_log_brightness_gap"] <= tolerance
    ]
    if matched:
        chosen = max(
            matched,
            key=lambda item: (
                item["articulation_gap"],
                -item["whole_log_brightness_gap"],
                -min(item["first"]["position"], item["second"]["position"]),
            ),
        )
        selection = (
            f"largest articulation gap among pairs within "
            f"{(max_brightness_ratio - 1.0) * 100:.1f}% whole-stone median brightness"
        )
        fallback = False
    else:
        chosen = min(
            candidates,
            key=lambda item: (
                item["whole_log_brightness_gap"],
                -item["articulation_gap"],
                min(item["first"]["position"], item["second"]["position"]),
            ),
        )
        selection = (
            f"no pair within {(max_brightness_ratio - 1.0) * 100:.1f}% brightness; "
            "closest whole-brightness pair used"
        )
        fallback = True

    return {
        **chosen,
        "max_brightness_ratio": float(max_brightness_ratio),
        "brightness_matched": not fallback,
        "matched_candidate_count": len(matched),
        "selection": selection,
    }


def select_evidence(frame_trace, primary="raw_spread"):
    if primary not in MEASURES:
        raise ValueError(f"unknown articulation measure: {primary}")
    summary = summarise([row.get(primary) for row in frame_trace])
    return {
        "primary_measure": primary,
        "lowest": _extreme(frame_trace, primary, False),
        "median": _nearest(frame_trace, primary, summary.get("q50")),
        "highest": _extreme(frame_trace, primary, True),
        "matched_brightness_pair": matched_brightness_pair(frame_trace, primary),
    }


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


def rank_agreement(frame_trace, baseline="raw_spread"):
    """Diagnostic Spearman rank agreement between baseline and normalization candidates."""
    if baseline not in MEASURES:
        raise ValueError(f"unknown articulation measure: {baseline}")
    result = {}
    for challenger in MEASURES:
        if challenger == baseline:
            continue
        pairs = [
            (float(row[baseline]), float(row[challenger]))
            for row in frame_trace
            if _finite(row.get(baseline)) is not None
            and _finite(row.get(challenger)) is not None
        ]
        rho = None
        if len(pairs) >= 3:
            left = np.asarray(_average_ranks([item[0] for item in pairs]), float)
            right = np.asarray(_average_ranks([item[1] for item in pairs]), float)
            if np.std(left) > 0 and np.std(right) > 0:
                rho = float(np.corrcoef(left, right)[0, 1])
        result[challenger] = {
            "paired_frames": len(pairs),
            "spearman_vs_baseline": rho,
        }
    return result
