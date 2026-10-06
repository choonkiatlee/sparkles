"""Normalized static tier-edge primitives for issue #55.

Semantic boundary identity is inherited from #19's declared radial windows.
Each held-out frame is only allowed to estimate a local transition position
inside that predeclared zone. The headline quantity is transition width in
silhouette-normalized radius units; gradient magnitude is QC only.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

from . import asscher_steps as steps

SCHEMA = "diamond360-normalized-tier-edges/1"
BOUNDARIES = steps.BOUNDARIES
BOUNDARY_WINDOWS = steps.BOUNDARY_WINDOWS
DEFAULT_LOW_CONFIDENCE = 0.35


def _finite(values):
    return np.asarray(
        [
            float(v)
            for v in values
            if v is not None and math.isfinite(float(v))
        ],
        float,
    )


def _median(values):
    data = _finite(values)
    return float(np.median(data)) if data.size else None


def _weighted_quantile(x, weights, q):
    x = np.asarray(x, float)
    weights = np.asarray(weights, float)
    good = np.isfinite(x) & np.isfinite(weights) & (weights > 0)
    if good.sum() < 2:
        return None
    x, weights = x[good], weights[good]
    order = np.argsort(x)
    x, weights = x[order], weights[order]
    cumulative = np.cumsum(weights)
    target = q * cumulative[-1]
    return float(np.interp(target, cumulative, x))


def measure_transition_ray(profile, support, u, semantic_window):
    """Measure one transition without allowing the ray to redefine semantics."""
    profile = np.asarray(profile, float)
    support = np.asarray(support, bool)
    u = np.asarray(u, float)
    if profile.shape != support.shape or profile.shape != u.shape:
        raise ValueError("profile, support and u must have matching shapes")
    lo, hi = map(float, semantic_window)
    zone = (
        support
        & np.isfinite(profile)
        & (u >= lo)
        & (u <= hi)
    )
    if zone.sum() < 8:
        return None

    filled = profile.copy()
    idx = np.arange(len(profile))
    good = support & np.isfinite(profile)
    if good.sum() < 8:
        return None
    filled[~good] = np.interp(
        idx[~good], idx[good], profile[good]
    )
    smooth = ndi.gaussian_filter1d(
        filled, 1.0, mode="nearest"
    )
    derivative = np.abs(np.gradient(smooth, u))
    zone_indices = np.flatnonzero(zone)
    peak_idx = int(
        zone_indices[
            int(np.argmax(derivative[zone_indices]))
        ]
    )
    peak_u = float(u[peak_idx])

    mass_zone = zone & (np.abs(u - peak_u) <= 0.065)
    local_d = derivative[mass_zone]
    if local_d.size < 5:
        return None
    baseline = float(np.median(derivative[zone]))
    weights = np.maximum(local_d - baseline, 0.0)
    local_u = u[mass_zone]
    q10 = _weighted_quantile(local_u, weights, 0.10)
    q90 = _weighted_quantile(local_u, weights, 0.90)
    width = (
        None
        if q10 is None or q90 is None
        else float(max(0.0, q90 - q10))
    )

    du = float(np.median(np.diff(u)))
    plateau = max(
        2, int(round(0.018 / max(du, 1e-9)))
    )
    gap = max(1, int(round(0.008 / max(du, 1e-9))))
    left = smooth[
        max(0, peak_idx-gap-plateau):
        max(0, peak_idx-gap)
    ]
    right = smooth[
        min(len(smooth), peak_idx+gap):
        min(len(smooth), peak_idx+gap+plateau)
    ]
    contrast = (
        float(abs(np.median(right) - np.median(left)))
        if left.size and right.size
        else 0.0
    )
    noise = float(
        1.4826
        * np.median(
            np.abs(
                smooth[zone] - np.median(smooth[zone])
            )
        )
    )
    contrast_score = contrast / (
        contrast + noise + 1e-9
    )
    peak = float(derivative[peak_idx])
    concentration = peak / (
        peak + 2.0 * baseline + 1e-9
    )
    local_support = float(np.mean(support[mass_zone]))
    confidence = float(
        np.clip(
            local_support
            * contrast_score
            * concentration,
            0.0,
            1.0,
        )
    )

    return {
        "position_u": peak_u,
        "transition_width_u": width,
        "confidence": confidence,
        "local_contrast": contrast,
        "peak_gradient": peak,
        "gradient_baseline": baseline,
        "local_support_fraction": local_support,
    }


def longest_circular_gap_fraction(flags):
    flags = np.asarray(flags, bool)
    if flags.ndim != 1 or flags.size == 0:
        raise ValueError(
            "flags must be a non-empty 1-D boolean array"
        )
    missing = ~flags
    if not missing.any():
        return 0.0
    if missing.all():
        return 1.0
    doubled = np.r_[missing, missing]
    best = run = 0
    for value in doubled:
        run = run + 1 if value else 0
        best = max(best, run)
    return float(
        min(best, len(flags)) / len(flags)
    )


def circular_component_count(flags):
    """Number of circular True components."""
    flags = np.asarray(flags, bool)
    if flags.ndim != 1 or flags.size == 0:
        raise ValueError(
            "flags must be a non-empty 1-D boolean array"
        )
    if not flags.any():
        return 0
    if flags.all():
        return 1
    return int(
        sum(
            bool(flags[i] and not flags[i-1])
            for i in range(len(flags))
        )
    )


def periodic_position_residual_mad(
    angles, positions, confidence
):
    angles = np.asarray(angles, float)
    positions = np.asarray(positions, float)
    confidence = np.asarray(confidence, float)
    good = (
        np.isfinite(positions)
        & np.isfinite(confidence)
        & (confidence > 0.05)
    )
    if good.sum() < 10:
        return None
    a = angles[good]
    y = positions[good]
    w = confidence[good]
    design = np.column_stack(
        [
            np.ones_like(a),
            np.cos(4*a),
            np.sin(4*a),
            np.cos(8*a),
            np.sin(8*a),
        ]
    )
    root_w = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(
        design * root_w[:, None],
        y * root_w,
        rcond=None,
    )
    residual = y - design @ coef
    med = float(np.median(residual))
    return float(
        1.4826
        * np.median(np.abs(residual - med))
    )


def measure_boundary_frame(
    ray_profiles,
    ray_support,
    u,
    angles,
    semantic_window,
    *,
    low_confidence=DEFAULT_LOW_CONFIDENCE,
    include_rays=True,
):
    ray_profiles = np.asarray(ray_profiles, float)
    ray_support = np.asarray(ray_support, bool)
    u = np.asarray(u, float)
    angles = np.asarray(angles, float)
    if (
        ray_profiles.shape != ray_support.shape
        or ray_profiles.ndim != 2
    ):
        raise ValueError(
            "ray_profiles and ray_support must be "
            "matching ray x radius arrays"
        )
    if ray_profiles.shape != (
        len(angles), len(u)
    ):
        raise ValueError(
            "angles/u must match ray profiles"
        )

    rays = [
        measure_transition_ray(
            ray_profiles[i],
            ray_support[i],
            u,
            semantic_window,
        )
        for i in range(len(angles))
    ]
    confidence = np.asarray(
        [
            0.0 if row is None else row["confidence"]
            for row in rays
        ],
        float,
    )
    positions = np.asarray(
        [
            np.nan
            if row is None
            else row["position_u"]
            for row in rays
        ],
        float,
    )
    widths = [
        None
        if row is None
        else row["transition_width_u"]
        for row in rays
    ]
    low = confidence < low_confidence
    available = np.isfinite(positions)
    result = {
        "status": (
            "ok"
            if available.mean() >= 0.75
            else "review"
            if available.mean() >= 0.40
            else "unavailable"
        ),
        "ray_count": int(len(angles)),
        "available_fraction": float(
            available.mean()
        ),
        "median_transition_width_u": _median(
            widths
        ),
        "median_confidence": float(
            np.median(confidence)
        ),
        "mean_confidence": float(
            np.mean(confidence)
        ),
        "low_confidence_fraction": float(
            np.mean(low)
        ),
        "longest_low_confidence_gap_fraction":
            longest_circular_gap_fraction(~low),
        "low_confidence_component_count":
            circular_component_count(low),
        "position_residual_mad_u":
            periodic_position_residual_mad(
                angles,
                positions,
                confidence,
            ),
        "median_local_contrast": _median(
            [
                None
                if row is None
                else row["local_contrast"]
                for row in rays
            ]
        ),
        "median_peak_gradient": _median(
            [
                None
                if row is None
                else row["peak_gradient"]
                for row in rays
            ]
        ),
        "low_confidence_threshold": float(
            low_confidence
        ),
    }
    if include_rays:
        result["rays"] = rays
    return result


def measure_frame(
    ray_profiles,
    ray_support,
    u,
    angles,
    *,
    include_rays=True,
):
    return {
        name: measure_boundary_frame(
            ray_profiles,
            ray_support,
            u,
            angles,
            window,
            include_rays=include_rays,
        )
        for name, window in zip(
            BOUNDARIES, BOUNDARY_WINDOWS
        )
    }


def summarize_frames(frames):
    summary = {}
    for boundary in BOUNDARIES:
        rows = [
            frame[boundary]
            for frame in frames
            if frame is not None
        ]
        summary[boundary] = {
            "frame_count": len(rows),
            "median_transition_width_u": _median(
                [
                    r["median_transition_width_u"]
                    for r in rows
                ]
            ),
            "median_confidence": _median(
                [
                    r["median_confidence"]
                    for r in rows
                ]
            ),
            "median_longest_gap_fraction": _median(
                [
                    r[
                        "longest_low_confidence_gap_fraction"
                    ]
                    for r in rows
                ]
            ),
            "median_fragment_count": _median(
                [
                    r[
                        "low_confidence_component_count"
                    ]
                    for r in rows
                ]
            ),
            "median_position_residual_mad_u": _median(
                [
                    r["position_residual_mad_u"]
                    for r in rows
                ]
            ),
            "median_local_contrast": _median(
                [
                    r["median_local_contrast"]
                    for r in rows
                ]
            ),
            "median_peak_gradient": _median(
                [
                    r["median_peak_gradient"]
                    for r in rows
                ]
            ),
        }
    return summary
