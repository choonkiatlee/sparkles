"""Concentric-band coordination derived from retained activation traces."""
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


def level_correlation(values_a, values_b):
    """Pearson correlation on aligned finite observations."""
    if len(values_a) != len(values_b):
        raise ValueError("paired traces must have equal length")
    paired = []
    for left, right in zip(values_a, values_b):
        left = _finite(left)
        right = _finite(right)
        if left is not None and right is not None:
            paired.append((left, right))
    result = {
        "aligned_finite_frames": len(paired),
        "pearson_r": None,
        "status": "unavailable",
        "reasons": [],
    }
    if len(paired) < 3:
        result["reasons"].append("insufficient_aligned_finite_frames")
        return result
    a = np.asarray([item[0] for item in paired], float)
    b = np.asarray([item[1] for item in paired], float)
    if float(np.ptp(a)) == 0.0 or float(np.ptp(b)) == 0.0:
        result["reasons"].append("constant_component_trace")
        return result
    result["pearson_r"] = float(np.corrcoef(a, b)[0, 1])
    result["status"] = "ok"
    return result


def adjacent_change_coordination(values_a, values_b, source_indices, wrap=False):
    """Compare the directions of aligned adjacent activation changes.

    Zero change in either component is a tie rather than forced into same/opposite.
    No magnitude threshold is introduced.
    """
    if len(values_a) != len(values_b) or len(values_a) != len(source_indices):
        raise ValueError("paired traces and source indices must have equal length")
    events = []
    same = opposite = ties = 0
    for right in range(1, len(source_indices)):
        left = right - 1
        event = {
            "left_position": left,
            "right_position": right,
            "left_source_index": source_indices[left],
            "right_source_index": source_indices[right],
            "status": "ok",
            "delta_a": None,
            "delta_b": None,
            "relationship": None,
            "joint_move_strength": None,
        }
        if not _is_adjacent(source_indices[left], source_indices[right], wrap):
            event["status"] = "non_adjacent_source_steps"
            events.append(event)
            continue
        a0, a1 = _finite(values_a[left]), _finite(values_a[right])
        b0, b1 = _finite(values_b[left]), _finite(values_b[right])
        if None in (a0, a1, b0, b1):
            event["status"] = "gap"
            events.append(event)
            continue
        da = float(a1 - a0)
        db = float(b1 - b0)
        product = da * db
        if product > 0:
            relationship = "same"
            same += 1
        elif product < 0:
            relationship = "opposite"
            opposite += 1
        else:
            relationship = "tie"
            ties += 1
        event.update(
            delta_a=da,
            delta_b=db,
            relationship=relationship,
            joint_move_strength=float(min(abs(da), abs(db))),
        )
        events.append(event)

    directional = same + opposite
    observed = directional + ties
    summary = {
        "requested_adjacent_pairs": max(0, len(source_indices) - 1),
        "observed_adjacent_pairs": observed,
        "directional_pairs": directional,
        "same_direction_pairs": same,
        "opposite_direction_pairs": opposite,
        "tie_pairs": ties,
        "same_direction_fraction": float(same / directional) if directional else None,
        "opposite_direction_fraction": float(opposite / directional) if directional else None,
        "status": "ok" if directional else "unavailable",
        "reasons": [] if directional else ["no_directional_adjacent_pairs"],
    }
    return {"event_trace": events, "summary": summary}


def select_event_evidence(event_trace):
    """Select deterministic coordinated, divergent and typical directional events."""
    finite = [
        (position, item)
        for position, item in enumerate(event_trace)
        if item.get("relationship") in {"same", "opposite"}
        and item.get("joint_move_strength") is not None
        and math.isfinite(float(item["joint_move_strength"]))
    ]

    def strongest(kind):
        candidates = [entry for entry in finite if entry[1]["relationship"] == kind]
        if not candidates:
            return None
        return max(candidates, key=lambda entry: (entry[1]["joint_move_strength"], -entry[0]))

    typical = None
    if finite:
        values = np.asarray([entry[1]["joint_move_strength"] for entry in finite], float)
        median = float(np.median(values))
        typical = min(
            finite,
            key=lambda entry: (abs(entry[1]["joint_move_strength"] - median), entry[0]),
        )

    def encode(entry):
        if entry is None:
            return None
        position, item = entry
        return {"event_position": position, **item}

    return {
        "strongest_coordinated": encode(strongest("same")),
        "strongest_divergent": encode(strongest("opposite")),
        "typical_directional": encode(typical),
    }


def compose_validity(component_validities, local):
    """Monotone validity composition; disposition remains separate provenance."""
    worst = "ok"
    reasons = []
    for source in [*(component_validities or []), local or {}]:
        status = source.get("status", "ok")
        if status not in _STATUS_RANK:
            raise ValueError(f"unknown validity status: {status}")
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
        for reason in [source.get("reason"), *(source.get("reasons") or [])]:
            if reason and reason not in reasons:
                reasons.append(reason)
    return {"status": worst, "reasons": reasons}


def measure_pair(values_a, values_b, source_indices, validity_a, validity_b, wrap=False):
    levels = level_correlation(values_a, values_b)
    changes = adjacent_change_coordination(values_a, values_b, source_indices, wrap=wrap)
    return {
        "values_a": list(values_a),
        "values_b": list(values_b),
        "level_correlation": levels,
        "level_validity": compose_validity([validity_a, validity_b], levels),
        "change_coordination": changes,
        "change_validity": compose_validity([validity_a, validity_b], changes["summary"]),
        "evidence": select_event_evidence(changes["event_trace"]),
    }
