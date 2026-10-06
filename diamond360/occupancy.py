"""Relative-dark occupancy traces for registered Asscher 360 sequences."""
from __future__ import annotations

import math

import numpy as np

_SUMMARY_KEYS = ("mean", "median", "q10", "q50", "q90")


def _finite_values(values):
    out = []
    for value in values:
        if value is None:
            continue
        value = float(value)
        if math.isfinite(value):
            out.append(value)
    return out


def summarise_occupancy(values):
    """Summarise the finite occupancy trace without inventing missing values."""
    finite = _finite_values(values)
    result = {
        "status": "ok" if finite else "unavailable",
        "finite_frames": len(finite),
    }
    if not finite:
        result.update({key: None for key in _SUMMARY_KEYS})
        return result
    data = np.asarray(finite, float)
    q10, q50, q90 = (float(np.quantile(data, q)) for q in (0.1, 0.5, 0.9))
    result.update(
        mean=float(np.mean(data)),
        median=float(np.median(data)),
        q10=q10,
        q50=q50,
        q90=q90,
    )
    return result


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


def _persistent_support(valid_masks, region_masks, observed):
    if not observed.any():
        return np.zeros(valid_masks.shape[1:], bool)
    return np.all((valid_masks & region_masks)[observed], axis=0)


def _valid_reference(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def validate_relative_dark_threshold(threshold):
    """Validate the shared #27 relative-dark threshold."""
    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    return threshold


def relative_dark_state(brightness, whole_stone_value, threshold):
    """Return the #27 relative-dark state field, or None for an invalid reference.

    Support is deliberately not applied here. Callers must intersect this state field
    with their declared fixed/frame/pair support so mask motion cannot become state.
    """
    reference = _valid_reference(whole_stone_value)
    if reference is None:
        return None
    threshold = validate_relative_dark_threshold(threshold)
    return np.asarray(brightness, float) < threshold * reference


def occupancy_trace(
    brightness,
    valid_masks,
    region_masks,
    whole_stone_values,
    observed,
    support_mode,
    threshold,
):
    """Measure the fraction of supported pixels strictly below threshold * G_t.

    Missing/unobserved frames remain null. Fixed support is the intersection over
    observed frames only; dynamic support uses each frame's valid regional support.
    """
    brightness, valid_masks, region_masks, observed = _validate_arrays(
        brightness, valid_masks, region_masks, observed
    )
    if support_mode not in {"fixed", "dynamic"}:
        raise ValueError('support_mode must be "fixed" or "dynamic"')
    threshold = validate_relative_dark_threshold(threshold)
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")

    common = _persistent_support(valid_masks, region_masks, observed)
    values = []
    dark_counts = []
    support_counts = []
    support_fractions = []

    for frame, valid, region, whole, ok in zip(
        brightness, valid_masks, region_masks, whole_stone_values, observed
    ):
        nominal = int(region.sum())
        dynamic = valid & region
        support_fractions.append(float(dynamic.sum() / nominal) if ok and nominal else None)
        support = common if support_mode == "fixed" else dynamic

        if not ok:
            values.append(None)
            dark_counts.append(None)
            support_counts.append(None)
            continue

        denominator = int(support.sum())
        support_counts.append(denominator)
        state = relative_dark_state(frame, whole, threshold)
        if denominator == 0 or state is None:
            values.append(None)
            dark_counts.append(None)
            continue

        dark = int(np.count_nonzero(state & support))
        dark_counts.append(dark)
        values.append(float(dark / denominator))

    nominal_union = (
        np.any(region_masks[observed], axis=0)
        if observed.any()
        else np.zeros(region_masks.shape[1:], bool)
    )
    return {
        "threshold": threshold,
        "support_mode": support_mode,
        "values": values,
        "dark_pixel_counts": dark_counts,
        "supported_pixel_counts": support_counts,
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / nominal_union.sum()) if nominal_union.any() else None,
        "per_frame_support_fraction": support_fractions,
        "summary": summarise_occupancy(values),
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
    """Run a predeclared global threshold sweep without per-stone tuning."""
    thresholds = tuple(float(value) for value in thresholds)
    if len(thresholds) != len(set(thresholds)):
        raise ValueError("thresholds must be unique")
    return {
        f"{threshold:.2f}": occupancy_trace(
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
