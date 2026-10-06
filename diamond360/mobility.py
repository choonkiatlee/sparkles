"""Contrast-mobility measurements derived from retained activation traces."""
from __future__ import annotations

import math

import numpy as np


_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _is_adjacent(left, right, wrap=False):
    return right == left + 1 or (wrap and right == 0 and left > 0)


def mobility_trace(values, source_indices, wrap=False):
    """Measure absolute adjacent-step change without bridging gaps.

    The returned pair trace is aligned to requested neighboring positions. A pair is
    only observed when source indices are adjacent and both activation values are
    finite. Missing/rejected values therefore break adjacency rather than being
    interpolated.
    """
    if len(values) != len(source_indices):
        raise ValueError("values and source indices must have equal length")

    pairs = []
    observed = []
    for right in range(1, len(values)):
        left = right - 1
        item = {
            "left_position": left,
            "right_position": right,
            "left_source_index": source_indices[left],
            "right_source_index": source_indices[right],
            "status": "ok",
            "left_value": None,
            "right_value": None,
            "signed_delta": None,
            "mobility": None,
        }
        if not _is_adjacent(source_indices[left], source_indices[right], wrap):
            item["status"] = "non_adjacent_source_steps"
            pairs.append(item)
            continue
        left_value = _finite(values[left])
        right_value = _finite(values[right])
        item["left_value"] = left_value
        item["right_value"] = right_value
        if left_value is None or right_value is None:
            item["status"] = "gap"
            pairs.append(item)
            continue
        delta = right_value - left_value
        mobility = abs(delta)
        item["signed_delta"] = float(delta)
        item["mobility"] = float(mobility)
        pairs.append(item)
        observed.append(float(mobility))

    summary = {
        "requested_adjacent_pairs": max(0, len(values) - 1),
        "observed_adjacent_pairs": len(observed),
        "median": None,
        "q90": None,
        "status": "ok" if observed else "unavailable",
    }
    if observed:
        data = np.asarray(observed, float)
        summary["median"] = float(np.median(data))
        summary["q90"] = float(np.quantile(data, 0.9))
    return {"pair_trace": pairs, "summary": summary}


def select_pair_evidence(pair_trace):
    """Select deterministic largest, typical, Q90 and lowest non-zero events."""
    finite = [
        (position, item)
        for position, item in enumerate(pair_trace)
        if item.get("mobility") is not None
        and math.isfinite(float(item["mobility"]))
    ]
    if not finite:
        return {
            "largest": None,
            "median": None,
            "q90": None,
            "lowest_nonzero": None,
        }

    values = np.asarray([item["mobility"] for _, item in finite], float)
    median = float(np.median(values))
    q90 = float(np.quantile(values, 0.9))

    def nearest(target):
        return min(
            finite,
            key=lambda entry: (abs(float(entry[1]["mobility"]) - target), entry[0]),
        )

    largest = max(finite, key=lambda entry: (entry[1]["mobility"], -entry[0]))
    nonzero = [entry for entry in finite if entry[1]["mobility"] > 0]
    lowest = min(nonzero, key=lambda entry: (entry[1]["mobility"], entry[0])) if nonzero else None

    def encode(entry):
        if entry is None:
            return None
        position, item = entry
        return {"pair_position": position, **item}

    return {
        "largest": encode(largest),
        "median": encode(nearest(median)),
        "q90": encode(nearest(q90)),
        "lowest_nonzero": encode(lowest),
    }


def mobility_validity(upstream_validity, summary):
    """Inherit #26 validity and add only mobility-specific availability failures."""
    upstream_validity = dict(upstream_validity or {})
    upstream_status = upstream_validity.get("status", "ok")
    if upstream_status not in _STATUS_RANK:
        raise ValueError(f"unknown validity status: {upstream_status}")
    reasons = list(upstream_validity.get("reasons") or [])
    local_status = summary.get("status", "unavailable")
    if local_status not in _STATUS_RANK:
        raise ValueError(f"unknown validity status: {local_status}")
    if local_status == "unavailable" and "no_observed_adjacent_pairs" not in reasons:
        reasons.append("no_observed_adjacent_pairs")
    status = (
        upstream_status
        if _STATUS_RANK[upstream_status] >= _STATUS_RANK[local_status]
        else local_status
    )
    return {"status": status, "reasons": reasons}
