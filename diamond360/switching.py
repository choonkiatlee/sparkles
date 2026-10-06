"""Bright/dark switching measurements for registered Asscher 360 sequences."""
from __future__ import annotations

import math

import numpy as np

from . import occupancy as o


def _validate_arrays(brightness, valid_masks, region_masks, observed):
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    region_masks = np.asarray(region_masks, bool)
    observed = np.asarray(observed, bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape or region_masks.shape != brightness.shape:
        raise ValueError("brightness, valid masks and region masks must be matching frame-height-width arrays")
    if observed.shape != (len(brightness),):
        raise ValueError("observed flags must match frames")
    valid_masks = valid_masks & np.isfinite(brightness)
    return brightness, valid_masks, region_masks, observed


def _quantiles(values):
    data = np.asarray(values, float)
    if not len(data):
        return {"q10": None, "q50": None, "q90": None}
    q10, q50, q90 = (float(np.quantile(data, q)) for q in (0.1, 0.5, 0.9))
    return {"q10": q10, "q50": q50, "q90": q90}


def switching_trace(
    brightness,
    valid_masks,
    region_masks,
    whole_stone_values,
    observed,
    support_mode,
    threshold,
):
    """Measure relative-dark state switches between adjacent requested source steps.

    fixed uses pixels supported throughout the observed interval.
    pair_local uses only pixels supported on both sides of each adjacent pair.
    Missing/unobserved frames and invalid whole-stone references break adjacency.
    """
    brightness, valid_masks, region_masks, observed = _validate_arrays(
        brightness, valid_masks, region_masks, observed
    )
    if support_mode not in {"fixed", "pair_local"}:
        raise ValueError('support_mode must be "fixed" or "pair_local"')
    threshold = o.validate_relative_dark_threshold(threshold)
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")

    supported = valid_masks & region_masks
    common = (
        np.all(supported[observed], axis=0)
        if observed.any()
        else np.zeros(brightness.shape[1:], bool)
    )
    nominal_union = (
        np.any(region_masks[observed], axis=0)
        if observed.any()
        else np.zeros(brightness.shape[1:], bool)
    )

    eligible_counts = np.zeros(brightness.shape[1:], dtype=np.int32)
    switch_counts = np.zeros(brightness.shape[1:], dtype=np.int32)
    pair_trace = []
    total_eligible = 0
    total_switches = 0
    observed_pairs = 0
    valid_reference_pairs = 0

    for right in range(1, len(brightness)):
        left = right - 1
        item = {
            "left_position": left,
            "right_position": right,
            "status": "ok",
            "eligible_pixels": None,
            "switched_pixels": None,
            "switch_fraction": None,
        }
        if not (observed[left] and observed[right]):
            item["status"] = "gap"
            pair_trace.append(item)
            continue

        left_state = o.relative_dark_state(brightness[left], whole_stone_values[left], threshold)
        right_state = o.relative_dark_state(brightness[right], whole_stone_values[right], threshold)
        if left_state is None or right_state is None:
            item["status"] = "invalid_reference"
            pair_trace.append(item)
            continue
        valid_reference_pairs += 1

        pair_support = common if support_mode == "fixed" else (supported[left] & supported[right])
        denominator = int(pair_support.sum())
        if denominator == 0:
            item["status"] = "no_support"
            pair_trace.append(item)
            continue

        switched = pair_support & (left_state != right_state)
        numerator = int(switched.sum())
        item.update(
            eligible_pixels=denominator,
            switched_pixels=numerator,
            switch_fraction=float(numerator / denominator),
        )
        pair_trace.append(item)
        observed_pairs += 1
        total_eligible += denominator
        total_switches += numerator
        eligible_counts[pair_support] += 1
        switch_counts[switched] += 1

    finite_pixels = eligible_counts > 0
    if finite_pixels.any():
        rates = switch_counts[finite_pixels] / eligible_counts[finite_pixels]
        eligible_per_pixel = eligible_counts[finite_pixels].astype(float)
    else:
        rates = np.asarray([], float)
        eligible_per_pixel = np.asarray([], float)
    rate_q = _quantiles(rates)
    eligible_q = _quantiles(eligible_per_pixel)

    return {
        "threshold": threshold,
        "support_mode": support_mode,
        "requested_adjacent_pairs": max(0, len(brightness) - 1),
        "valid_reference_pairs": valid_reference_pairs,
        "observed_adjacent_pairs": observed_pairs,
        "pair_trace": pair_trace,
        "eligible_pixel_pairs": int(total_eligible),
        "switched_pixel_pairs": int(total_switches),
        "regional_switch_rate": float(total_switches / total_eligible) if total_eligible else None,
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / nominal_union.sum()) if nominal_union.any() else None,
        "per_pixel_rate": {
            "finite_pixels": int(finite_pixels.sum()),
            "q10": rate_q["q10"],
            "q50": rate_q["q50"],
            "q90": rate_q["q90"],
            "max": float(np.max(rates)) if len(rates) else None,
            "fraction_nonzero": float(np.mean(rates > 0)) if len(rates) else None,
        },
        "per_pixel_eligible_pairs": {
            "q10": eligible_q["q10"],
            "q50": eligible_q["q50"],
            "q90": eligible_q["q90"],
            "min": int(np.min(eligible_per_pixel)) if len(eligible_per_pixel) else None,
            "max": int(np.max(eligible_per_pixel)) if len(eligible_per_pixel) else None,
        },
        "status": "ok" if total_eligible else "unavailable",
    }


def threshold_sweep(
    brightness,
    valid_masks,
    region_masks,
    whole_stone_values,
    observed,
    support_mode,
    thresholds=(0.60, 0.65, 0.70),
):
    """Run switching under the same predeclared #27 threshold neighborhood."""
    thresholds = tuple(float(value) for value in thresholds)
    if len(thresholds) != len(set(thresholds)):
        raise ValueError("thresholds must be unique")
    return {
        f"{threshold:.2f}": switching_trace(
            brightness,
            valid_masks,
            region_masks,
            whole_stone_values,
            observed,
            support_mode,
            threshold,
        )
        for threshold in thresholds
    }


def select_pair_evidence(pair_trace):
    """Select deterministic high and low-nonzero pair events."""
    finite = [
        (position, item)
        for position, item in enumerate(pair_trace)
        if item.get("switch_fraction") is not None and math.isfinite(float(item["switch_fraction"]))
    ]
    if not finite:
        return {"highest": None, "lowest_nonzero": None}

    highest = max(finite, key=lambda entry: (entry[1]["switch_fraction"], -entry[0]))
    nonzero = [entry for entry in finite if entry[1]["switch_fraction"] > 0]
    lowest = min(nonzero, key=lambda entry: (entry[1]["switch_fraction"], entry[0])) if nonzero else None

    def encode(entry):
        if entry is None:
            return None
        position, item = entry
        return {
            "pair_position": position,
            "left_position": item["left_position"],
            "right_position": item["right_position"],
            "switch_fraction": item["switch_fraction"],
            "eligible_pixels": item["eligible_pixels"],
            "switched_pixels": item["switched_pixels"],
        }

    return {"highest": encode(highest), "lowest_nonzero": encode(lowest)}
