"""Descriptive activation traces for registered Asscher 360 sequences."""
from __future__ import annotations

import math

import numpy as np

_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}
_SUMMARY_KEYS = (
    "q10", "q50", "q90", "bright_excursion", "dark_excursion",
    "total_excursion", "mad_scale",
)


def _finite_values(values):
    out = []
    for value in values:
        if value is None:
            continue
        value = float(value)
        if math.isfinite(value):
            out.append(value)
    return out


def summarise_activation(values):
    finite = _finite_values(values)
    result = {"status": "ok" if len(finite) >= 3 else "unavailable", "finite_frames": len(finite)}
    if len(finite) < 3:
        result.update({key: None for key in _SUMMARY_KEYS})
        return result
    data = np.asarray(finite, float)
    q10, q50, q90 = (float(np.quantile(data, q)) for q in (.1, .5, .9))
    bright = q90 - q50
    dark = q50 - q10
    result.update(
        q10=q10,
        q50=q50,
        q90=q90,
        bright_excursion=bright,
        dark_excursion=dark,
        total_excursion=bright + dark,
        mad_scale=float(1.4826 * np.median(np.abs(data - q50))),
    )
    return result


def _validate_arrays(brightness, valid_masks, masks, observed):
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    masks = np.asarray(masks, bool)
    observed = np.asarray(observed, bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape or masks.shape != brightness.shape:
        raise ValueError("brightness, valid masks and masks must be matching frame-height-width arrays")
    if observed.shape != (len(brightness),):
        raise ValueError("observed flags must match frames")
    valid_masks = valid_masks & np.isfinite(brightness)
    return brightness, valid_masks, masks, observed


def _persistent_support(valid_masks, masks, observed):
    if not observed.any():
        return np.zeros(valid_masks.shape[1:], bool)
    return np.all((valid_masks & masks)[observed], axis=0)


def whole_stone_trace(brightness, valid_masks, stone_masks, observed):
    brightness, valid_masks, stone_masks, observed = _validate_arrays(
        brightness, valid_masks, stone_masks, observed
    )
    common = _persistent_support(valid_masks, stone_masks, observed)
    values = []
    dynamic_support = []
    for frame, valid, stone, ok in zip(brightness, valid_masks, stone_masks, observed):
        nominal = int(stone.sum())
        supported = valid & stone
        dynamic_support.append(float(supported.sum() / nominal) if ok and nominal else None)
        values.append(float(np.median(frame[common])) if ok and common.any() else None)
    return {
        "values": values,
        "persistent_support_pixels": int(common.sum()),
        "per_frame_support_fraction": dynamic_support,
        "summary": summarise_activation(values),
    }


def regional_trace(brightness, valid_masks, region_masks, whole_stone_values, observed, support_mode):
    brightness, valid_masks, region_masks, observed = _validate_arrays(
        brightness, valid_masks, region_masks, observed
    )
    if support_mode not in {"fixed", "dynamic"}:
        raise ValueError('support_mode must be "fixed" or "dynamic"')
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")

    common = _persistent_support(valid_masks, region_masks, observed)
    raw = []
    relative = []
    support_fractions = []
    for frame, valid, region, whole, ok in zip(
        brightness, valid_masks, region_masks, whole_stone_values, observed
    ):
        nominal = int(region.sum())
        dynamic = valid & region
        support_fractions.append(float(dynamic.sum() / nominal) if ok and nominal else None)
        support = common if support_mode == "fixed" else dynamic
        if not ok or not support.any():
            raw.append(None)
            relative.append(None)
            continue
        regional = float(np.median(frame[support]))
        raw.append(regional)
        if whole is None or regional <= 0 or not math.isfinite(regional):
            relative.append(None)
            continue
        whole = float(whole)
        relative.append(float(math.log(regional) - math.log(whole)) if whole > 0 and math.isfinite(whole) else None)

    nominal_union = np.any(region_masks[observed], axis=0) if observed.any() else np.zeros(region_masks.shape[1:], bool)
    return {
        "support_mode": support_mode,
        "raw_values": raw,
        "relative_values": relative,
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / nominal_union.sum()) if nominal_union.any() else None,
        "per_frame_support_fraction": support_fractions,
        "raw_summary": summarise_activation(raw),
        "relative_summary": summarise_activation(relative),
    }


def compose_validity(sources):
    worst = "ok"
    reasons = []
    for source in sources:
        status = source.get("status", "ok")
        if status not in _STATUS_RANK:
            raise ValueError(f"unknown validity status: {status}")
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
        reason = source.get("reason")
        if reason and reason not in reasons:
            reasons.append(reason)
        for item in source.get("reasons", []):
            if item and item not in reasons:
                reasons.append(item)
    return {"status": worst, "reasons": reasons}
