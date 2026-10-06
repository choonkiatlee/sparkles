"""Pairwise opposing-region coordination for Asscher activation traces."""
from __future__ import annotations

import math

import numpy as np

PAIR_DEFINITIONS = {
    "side_E_W": ("side_E", "side_W"),
    "side_N_S": ("side_N", "side_S"),
    "corner_NE_SW": ("corner_NE", "corner_SW"),
    "corner_NW_SE": ("corner_NW", "corner_SE"),
}


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _is_adjacent(left, right, wrap=False):
    return right == left + 1 or (wrap and right == 0 and left > 0)


def _metric(value, status="ok", reason=None, **extra):
    result = {"value": value, "status": status}
    if reason:
        result["reason"] = reason
    result.update(extra)
    return result


def pair_trace(left_values, right_values, source_indices, wrap=False):
    """Compare two activation traces without bridging gaps."""
    if len(left_values) != len(right_values) or len(left_values) != len(source_indices):
        raise ValueError("left/right traces and source indices must have equal length")

    frames = []
    paired = []
    for position, (left, right) in enumerate(zip(left_values, right_values)):
        left = _finite(left)
        right = _finite(right)
        item = {
            "position": position,
            "source_index": source_indices[position],
            "left": left,
            "right": right,
            "signed_difference": None,
            "absolute_difference": None,
            "status": "ok" if left is not None and right is not None else "gap",
        }
        if left is not None and right is not None:
            difference = left - right
            item["signed_difference"] = float(difference)
            item["absolute_difference"] = float(abs(difference))
            paired.append((left, right, difference))
        frames.append(item)

    paired_frames = len(paired)
    if paired_frames:
        left = np.asarray([item[0] for item in paired], float)
        right = np.asarray([item[1] for item in paired], float)
        difference = np.asarray([item[2] for item in paired], float)
        median_abs = float(np.median(np.abs(difference)))
        median_signed = float(np.median(difference))
    else:
        left = right = np.asarray([], float)
        median_abs = median_signed = None

    if paired_frames < 3:
        correlation = _metric(
            None, "unavailable", "fewer_than_three_paired_frames",
            paired_frames=paired_frames,
        )
    elif float(np.std(left)) == 0.0 or float(np.std(right)) == 0.0:
        correlation = _metric(
            None, "unavailable", "zero_variance_component_trace",
            paired_frames=paired_frames,
        )
    else:
        correlation = _metric(
            float(np.corrcoef(left, right)[0, 1]),
            paired_frames=paired_frames,
        )

    absolute_difference = (
        _metric(median_abs, paired_frames=paired_frames)
        if paired_frames
        else _metric(None, "unavailable", "no_paired_frames", paired_frames=0)
    )

    adjacent = []
    same_direction = 0
    opposite_direction = 0
    flat = 0
    for right_position in range(1, len(frames)):
        left_position = right_position - 1
        item = {
            "left_position": left_position,
            "right_position": right_position,
            "left_source_index": source_indices[left_position],
            "right_source_index": source_indices[right_position],
            "left_delta": None,
            "right_delta": None,
            "direction": None,
            "coordination_strength": None,
            "divergence_strength": None,
            "movement_strength": None,
            "status": "ok",
        }
        if not _is_adjacent(
            source_indices[left_position],
            source_indices[right_position],
            wrap,
        ):
            item["status"] = "non_adjacent_source_steps"
            adjacent.append(item)
            continue
        a0, a1 = frames[left_position]["left"], frames[right_position]["left"]
        b0, b1 = frames[left_position]["right"], frames[right_position]["right"]
        if None in (a0, a1, b0, b1):
            item["status"] = "gap"
            adjacent.append(item)
            continue
        da = float(a1 - a0)
        db = float(b1 - b0)
        item["left_delta"] = da
        item["right_delta"] = db
        item["coordination_strength"] = float(min(abs(da), abs(db)))
        item["divergence_strength"] = float(abs(da - db))
        item["movement_strength"] = float(max(abs(da), abs(db)))
        if da == 0.0 or db == 0.0:
            item["direction"] = "flat"
            flat += 1
        elif da * db > 0:
            item["direction"] = "same"
            same_direction += 1
        else:
            item["direction"] = "opposite"
            opposite_direction += 1
        adjacent.append(item)

    directional_pairs = same_direction + opposite_direction
    if directional_pairs:
        sign_agreement = _metric(
            float(same_direction / directional_pairs),
            observed_adjacent_pairs=same_direction + opposite_direction + flat,
            directional_pairs=directional_pairs,
            same_direction_pairs=same_direction,
            opposite_direction_pairs=opposite_direction,
            flat_pairs=flat,
        )
    else:
        sign_agreement = _metric(
            None, "unavailable", "no_nonflat_adjacent_pairs",
            observed_adjacent_pairs=flat,
            directional_pairs=0,
            same_direction_pairs=0,
            opposite_direction_pairs=0,
            flat_pairs=flat,
        )

    pair_status = "ok" if paired_frames >= 3 else "unavailable"
    pair_reasons = [] if pair_status == "ok" else ["fewer_than_three_paired_frames"]
    return {
        "frame_trace": frames,
        "adjacent_trace": adjacent,
        "paired_frames": paired_frames,
        "median_signed_difference": median_signed,
        "metrics": {
            "correlation": correlation,
            "median_absolute_difference": absolute_difference,
            "sign_agreement": sign_agreement,
        },
        "status": pair_status,
        "reasons": pair_reasons,
    }


def select_evidence(pair_result):
    """Select deterministic coordinated/divergent/typical adjacent events."""
    observed = [
        (position, item)
        for position, item in enumerate(pair_result.get("adjacent_trace", []))
        if item.get("status") == "ok"
    ]
    coordinated = [
        entry for entry in observed
        if entry[1].get("direction") == "same"
    ]
    strongest_coordinated = (
        max(
            coordinated,
            key=lambda entry: (entry[1]["coordination_strength"], -entry[0]),
        )
        if coordinated else None
    )
    strongest_divergent = (
        max(
            observed,
            key=lambda entry: (entry[1]["divergence_strength"], -entry[0]),
        )
        if observed else None
    )

    typical = None
    if observed:
        values = np.asarray(
            [entry[1]["movement_strength"] for entry in observed],
            float,
        )
        target = float(np.median(values))
        typical = min(
            observed,
            key=lambda entry: (
                abs(entry[1]["movement_strength"] - target),
                entry[0],
            ),
        )

    def encode(entry):
        if entry is None:
            return None
        position, item = entry
        return {"pair_position": position, **item}

    return {
        "strongest_coordinated": encode(strongest_coordinated),
        "strongest_divergent": encode(strongest_divergent),
        "typical": encode(typical),
    }
