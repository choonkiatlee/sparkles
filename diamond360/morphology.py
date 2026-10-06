"""Bright-flash spatial morphology for registered Asscher 360 frames."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

MAD_SCALE = 1.4826


def validate_bright_threshold(threshold):
    """Validate a global threshold in robust fixed-support contrast units."""
    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("bright threshold must be finite and positive")
    return threshold


def robust_bright_scale(brightness, support, whole_stone_value):
    """Return 1.4826*MAD around G_t on the fixed reference support."""
    brightness = np.asarray(brightness, float)
    support = np.asarray(support, bool) & np.isfinite(brightness)
    if brightness.shape != support.shape:
        raise ValueError("brightness and support must have matching shapes")
    if whole_stone_value is None or not support.any():
        return None
    reference = float(whole_stone_value)
    if not math.isfinite(reference):
        return None
    values = brightness[support]
    scale = float(MAD_SCALE * np.median(np.abs(values - reference)))
    return scale if math.isfinite(scale) and scale > 1e-12 else None


def relative_bright_state(brightness, whole_stone_value, robust_scale, threshold):
    """Return pixels strictly above G_t + k*S_t, or None for an invalid reference."""
    threshold = validate_bright_threshold(threshold)
    if whole_stone_value is None or robust_scale is None:
        return None
    reference = float(whole_stone_value)
    scale = float(robust_scale)
    if not math.isfinite(reference) or not math.isfinite(scale) or scale <= 0:
        return None
    return np.asarray(brightness, float) > reference + threshold * scale


def _structure(connectivity):
    if connectivity == 8:
        return np.ones((3, 3), dtype=bool)
    if connectivity == 4:
        return np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    raise ValueError("connectivity must be 4 or 8")


def frame_morphology(active, support, connectivity=8):
    """Measure connected active structure inside one declared support mask."""
    active = np.asarray(active, bool)
    support = np.asarray(support, bool)
    if active.shape != support.shape or active.ndim != 2:
        raise ValueError("active and support must be matching 2D masks")
    active = active & support
    support_pixels = int(support.sum())
    active_pixels = int(active.sum())
    result = {
        "status": "ok" if active_pixels else "unavailable",
        "reason": None if active_pixels else "no_active_pixels",
        "support_pixels": support_pixels,
        "active_pixels": active_pixels,
        "active_fraction": float(active_pixels / support_pixels) if support_pixels else None,
        "component_count": 0,
        "largest_component_pixels": None,
        "largest_component_fraction": None,
        "largest_component_support_fraction": None,
        "effective_component_count": None,
        "boundary_active_pixels": None,
        "boundary_active_fraction": None,
        "components_touching_support_boundary": None,
    }
    if support_pixels == 0:
        result["status"] = "unavailable"
        result["reason"] = "no_support"
        return result
    if active_pixels == 0:
        return result

    structure = _structure(connectivity)
    labels, count = ndimage.label(active, structure=structure)
    sizes = np.bincount(labels.ravel())[1:].astype(float)
    largest = int(sizes.max())
    shares = sizes / active_pixels

    eroded = ndimage.binary_erosion(support, structure=structure, border_value=0)
    support_boundary = support & ~eroded
    boundary_active = active & support_boundary
    boundary_labels = np.unique(labels[boundary_active])
    boundary_labels = boundary_labels[boundary_labels > 0]

    result.update(
        component_count=int(count),
        largest_component_pixels=largest,
        largest_component_fraction=float(largest / active_pixels),
        largest_component_support_fraction=float(largest / support_pixels),
        effective_component_count=float(1.0 / np.sum(shares * shares)),
        boundary_active_pixels=int(boundary_active.sum()),
        boundary_active_fraction=float(boundary_active.sum() / active_pixels),
        components_touching_support_boundary=int(len(boundary_labels)),
    )
    return result


def _validate_arrays(brightness, valid_masks, stone_masks, observed):
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    stone_masks = np.asarray(stone_masks, bool)
    observed = np.asarray(observed, bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape or stone_masks.shape != brightness.shape:
        raise ValueError("brightness, valid masks and stone masks must be matching frame-height-width arrays")
    if observed.shape != (len(brightness),):
        raise ValueError("observed flags must match frames")
    valid_masks = valid_masks & np.isfinite(brightness)
    return brightness, valid_masks, stone_masks, observed


def _persistent_support(valid_masks, stone_masks, observed):
    if not observed.any():
        return np.zeros(valid_masks.shape[1:], bool)
    return np.all((valid_masks & stone_masks)[observed], axis=0)


def _summary(frames):
    active = [frame for frame in frames if frame["status"] == "ok"]
    result = {
        "status": "ok" if active else "unavailable",
        "observed_frames": sum(frame["status"] != "gap" for frame in frames),
        "active_frames": len(active),
        "active_frame_fraction": None,
        "median_active_fraction": None,
        "median_largest_component_fraction": None,
        "q10_largest_component_fraction": None,
        "q90_largest_component_fraction": None,
        "median_effective_component_count": None,
        "q90_effective_component_count": None,
        "median_boundary_active_fraction": None,
        "median_reference_scale": None,
    }
    observed = result["observed_frames"]
    if observed:
        result["active_frame_fraction"] = float(len(active) / observed)
    if not active:
        return result

    def values(key):
        return np.asarray([frame[key] for frame in active if frame[key] is not None], float)

    af = values("active_fraction")
    lcf = values("largest_component_fraction")
    eff = values("effective_component_count")
    baf = values("boundary_active_fraction")
    scales = values("reference_scale")
    result.update(
        median_active_fraction=float(np.median(af)),
        median_largest_component_fraction=float(np.median(lcf)),
        q10_largest_component_fraction=float(np.quantile(lcf, 0.1)),
        q90_largest_component_fraction=float(np.quantile(lcf, 0.9)),
        median_effective_component_count=float(np.median(eff)),
        q90_effective_component_count=float(np.quantile(eff, 0.9)),
        median_boundary_active_fraction=float(np.median(baf)),
        median_reference_scale=float(np.median(scales)),
    )
    return result


def morphology_trace(
    brightness,
    valid_masks,
    stone_masks,
    whole_stone_values,
    observed,
    support_mode,
    threshold,
    connectivity=8,
):
    """Measure per-frame bright-flash morphology on fixed or frame-local whole-stone support."""
    brightness, valid_masks, stone_masks, observed = _validate_arrays(
        brightness, valid_masks, stone_masks, observed
    )
    if support_mode not in {"fixed", "dynamic"}:
        raise ValueError('support_mode must be "fixed" or "dynamic"')
    threshold = validate_bright_threshold(threshold)
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")
    _structure(connectivity)

    common = _persistent_support(valid_masks, stone_masks, observed)
    union = (
        np.any(stone_masks[observed], axis=0)
        if observed.any()
        else np.zeros(stone_masks.shape[1:], bool)
    )
    frames = []
    for position, (frame, valid, stone, whole, ok) in enumerate(
        zip(brightness, valid_masks, stone_masks, whole_stone_values, observed)
    ):
        if not ok:
            frames.append({
                "position": position,
                "status": "gap",
                "reason": "unobserved_frame",
                "support_pixels": None,
                "active_pixels": None,
                "active_fraction": None,
                "component_count": None,
                "largest_component_pixels": None,
                "largest_component_fraction": None,
                "largest_component_support_fraction": None,
                "effective_component_count": None,
                "boundary_active_pixels": None,
                "boundary_active_fraction": None,
                "components_touching_support_boundary": None,
                "reference_scale": None,
                "active_threshold_value": None,
            })
            continue
        support = common if support_mode == "fixed" else (valid & stone)
        scale = robust_bright_scale(frame, common, whole)
        state = relative_bright_state(frame, whole, scale, threshold)
        if state is None:
            item = frame_morphology(np.zeros_like(support), support, connectivity)
            item["status"] = "unavailable"
            item["reason"] = "no_support" if not common.any() else "invalid_or_zero_reference_scale"
        else:
            item = frame_morphology(state & support, support, connectivity)
        item["reference_scale"] = scale
        item["active_threshold_value"] = (
            float(whole) + threshold * scale
            if whole is not None and scale is not None and math.isfinite(float(whole))
            else None
        )
        item["position"] = position
        frames.append(item)

    return {
        "threshold": threshold,
        "threshold_boundary": "strict_greater_than",
        "normalization": "G_t + k * (1.4826 * MAD(Y_t - G_t) on fixed common support)",
        "support_mode": support_mode,
        "connectivity": connectivity,
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / union.sum()) if union.any() else None,
        "frames": frames,
        "summary": _summary(frames),
    }


def threshold_sweep(
    brightness,
    valid_masks,
    stone_masks,
    whole_stone_values,
    observed,
    support_mode,
    thresholds=(0.75, 1.00, 1.25),
    connectivity=8,
):
    thresholds = tuple(float(value) for value in thresholds)
    if len(thresholds) != len(set(thresholds)):
        raise ValueError("thresholds must be unique")
    return {
        f"{threshold:.2f}": morphology_trace(
            brightness,
            valid_masks,
            stone_masks,
            whole_stone_values,
            observed,
            support_mode,
            threshold,
            connectivity,
        )
        for threshold in thresholds
    }


def select_frame_evidence(frames, source_indices, matched_area_tolerance=0.02):
    """Select deterministic broad, fragmented and matched-active-area evidence."""
    if len(frames) != len(source_indices):
        raise ValueError("frames and source indices must have equal length")
    finite = [(i, frame) for i, frame in enumerate(frames) if frame.get("status") == "ok"]
    if not finite:
        return {"broadest": None, "most_fragmented": None, "matched_active_area_pair": None}

    broadest = max(
        finite,
        key=lambda entry: (
            entry[1]["largest_component_support_fraction"],
            entry[1]["largest_component_fraction"],
            -entry[0],
        ),
    )
    fragmented = max(
        finite,
        key=lambda entry: (
            entry[1]["effective_component_count"],
            -entry[1]["largest_component_fraction"],
            -entry[0],
        ),
    )

    pair_candidates = []
    for left in range(len(finite)):
        for right in range(left + 1, len(finite)):
            ia, a = finite[left]
            ib, b = finite[right]
            area_diff = abs(a["active_fraction"] - b["active_fraction"])
            morphology_diff = abs(a["largest_component_fraction"] - b["largest_component_fraction"])
            pair_candidates.append((area_diff, -morphology_diff, ia, ib, a, b))
    close = [item for item in pair_candidates if item[0] <= matched_area_tolerance]
    pool = close if close else pair_candidates
    matched = min(pool, key=lambda item: (item[1], item[0], item[2], item[3])) if pool else None

    def encode(entry):
        if entry is None:
            return None
        position, frame = entry
        return {"position": position, "source_index": source_indices[position], **frame}

    matched_encoded = None
    if matched is not None:
        area_diff, neg_morphology_diff, ia, ib, a, b = matched
        matched_encoded = {
            "area_difference": float(area_diff),
            "largest_component_fraction_difference": float(-neg_morphology_diff),
            "within_tolerance": bool(area_diff <= matched_area_tolerance),
            "left": {"position": ia, "source_index": source_indices[ia], **a},
            "right": {"position": ib, "source_index": source_indices[ib], **b},
        }
    return {
        "broadest": encode(broadest),
        "most_fragmented": encode(fragmented),
        "matched_active_area_pair": matched_encoded,
    }


def select_threshold_sensitivity(sweep, source_indices, baseline="1.00"):
    """Select the frame whose largest-component fraction moves most across thresholds."""
    if baseline not in sweep:
        raise ValueError("baseline threshold missing from sweep")
    keys = list(sweep)
    frame_count = len(sweep[baseline]["frames"])
    best = None
    for position in range(frame_count):
        values = []
        for key in keys:
            frame = sweep[key]["frames"][position]
            value = frame.get("largest_component_fraction")
            if value is not None and math.isfinite(float(value)):
                values.append((key, float(value), frame.get("effective_component_count")))
        if len(values) < 2:
            continue
        span = max(value[1] for value in values) - min(value[1] for value in values)
        candidate = (span, -position, values)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    span, neg_position, values = best
    position = -neg_position
    return {
        "position": position,
        "source_index": source_indices[position],
        "largest_component_fraction_range": float(span),
        "threshold_values": [
            {
                "threshold": key,
                "largest_component_fraction": lcf,
                "effective_component_count": effective,
            }
            for key, lcf, effective in values
        ],
    }


def select_support_disagreement(fixed_frames, dynamic_frames, source_indices):
    """Select strongest and weakest finite fixed-vs-dynamic morphology disagreements."""
    if len(fixed_frames) != len(dynamic_frames) or len(fixed_frames) != len(source_indices):
        raise ValueError("support traces and source indices must have equal length")
    finite = []
    for position, (fixed, dynamic) in enumerate(zip(fixed_frames, dynamic_frames)):
        a = fixed.get("largest_component_fraction")
        b = dynamic.get("largest_component_fraction")
        if a is None or b is None:
            continue
        delta = abs(float(a) - float(b))
        finite.append((delta, position, float(a), float(b)))
    if not finite:
        return {"strongest": None, "control": None}
    strongest = max(finite, key=lambda item: (item[0], -item[1]))
    control = min(finite, key=lambda item: (item[0], item[1]))

    def encode(item):
        delta, position, fixed, dynamic = item
        return {
            "position": position,
            "source_index": source_indices[position],
            "absolute_difference": float(delta),
            "fixed_largest_component_fraction": fixed,
            "dynamic_largest_component_fraction": dynamic,
        }

    return {"strongest": encode(strongest), "control": encode(control)}
