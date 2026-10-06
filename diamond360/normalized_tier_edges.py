"""Normalized static tier-edge primitives for issue #55.

Semantic boundary identity is inherited from #19's declared radial windows.
Each held-out frame first estimates an eight-sector boundary locus inside the
predeclared semantic zone, then each ray can refine that position only in a
small local neighbourhood. The frame therefore localises a known semantic
boundary without being allowed to invent a different one.

The headline quantity is transition width in silhouette-normalized radius
units. Gradient magnitude and local contrast are retained only as QC signals.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

from . import asscher_steps as steps

SCHEMA = "diamond360-normalized-tier-edges/2"
BOUNDARIES = steps.BOUNDARIES
BOUNDARY_WINDOWS = steps.BOUNDARY_WINDOWS
DEFAULT_LOW_CONFIDENCE = 0.35
DEFAULT_LOCAL_SEARCH_RADIUS = 0.035


def _finite(values):
    return np.asarray(
        [
            float(v)
            for v in values
            if v is not None
            and math.isfinite(float(v))
        ],
        float,
    )


def _median(values):
    data = _finite(values)
    return (
        float(np.median(data))
        if data.size
        else None
    )


def _weighted_quantile(
    x, weights, q
):
    x = np.asarray(x, float)
    weights = np.asarray(weights, float)
    good = (
        np.isfinite(x)
        & np.isfinite(weights)
        & (weights > 0)
    )
    if good.sum() < 2:
        return None
    x, weights = (
        x[good],
        weights[good],
    )
    order = np.argsort(x)
    x, weights = (
        x[order],
        weights[order],
    )
    cumulative = np.cumsum(weights)
    target = q * cumulative[-1]
    return float(
        np.interp(
            target,
            cumulative,
            x,
        )
    )


def _smooth_derivative(
    profile, support, u
):
    profile = np.asarray(
        profile, float
    )
    support = np.asarray(
        support, bool
    )
    u = np.asarray(u, float)
    if (
        profile.shape != support.shape
        or profile.shape != u.shape
    ):
        raise ValueError(
            "profile, support and u "
            "must have matching shapes"
        )
    good = (
        support
        & np.isfinite(profile)
    )
    if good.sum() < 8:
        return None, None

    filled = profile.copy()
    idx = np.arange(len(profile))
    filled[~good] = np.interp(
        idx[~good],
        idx[good],
        profile[good],
    )
    smooth = ndi.gaussian_filter1d(
        filled,
        1.0,
        mode="nearest",
    )
    derivative = np.abs(
        np.gradient(smooth, u)
    )
    derivative[~support] = np.nan
    return smooth, derivative


def _sector_boundary_targets(
    ray_profiles,
    ray_support,
    u,
    angles,
    semantic_window,
):
    """Estimate one coherent held-out boundary locus inside the #19 zone."""
    profiles = np.asarray(
        ray_profiles, float
    )
    supports = np.asarray(
        ray_support, bool
    )
    u = np.asarray(u, float)
    angles = np.asarray(
        angles, float
    )

    derivatives = []
    for profile, support in zip(
        profiles, supports
    ):
        _, derivative = (
            _smooth_derivative(
                profile,
                support,
                u,
            )
        )
        derivatives.append(
            np.full_like(
                u, np.nan
            )
            if derivative is None
            else derivative
        )
    derivatives = np.asarray(
        derivatives
    )

    lo, hi = map(
        float, semantic_window
    )
    zone = (
        (u >= lo)
        & (u <= hi)
    )
    ids = steps._sector_ids(
        angles
    )

    with np.errstate(
        all="ignore"
    ):
        global_consensus = (
            np.nanmedian(
                derivatives,
                axis=0,
            )
        )
    global_consensus = (
        ndi.gaussian_filter1d(
            np.nan_to_num(
                global_consensus,
                nan=0.0,
            ),
            0.8,
            mode="nearest",
        )
    )
    candidates = np.flatnonzero(
        zone
        & np.isfinite(
            global_consensus
        )
    )
    if not len(candidates):
        return None
    global_idx = int(
        candidates[
            int(
                np.argmax(
                    global_consensus[
                        candidates
                    ]
                )
            )
        ]
    )
    global_u = float(
        u[global_idx]
    )

    sector_u = np.full(
        8, global_u, float
    )
    sector_support = np.zeros(
        8, float
    )
    for sector in range(8):
        rows = derivatives[
            ids == sector
        ]
        if not len(rows):
            continue
        with np.errstate(
            all="ignore"
        ):
            consensus = (
                np.nanmedian(
                    rows,
                    axis=0,
                )
            )
        consensus = (
            ndi.gaussian_filter1d(
                np.nan_to_num(
                    consensus,
                    nan=0.0,
                ),
                0.8,
                mode="nearest",
            )
        )
        local_candidates = (
            np.flatnonzero(zone)
        )
        if not len(
            local_candidates
        ):
            continue
        j = int(
            local_candidates[
                int(
                    np.argmax(
                        consensus[
                            local_candidates
                        ]
                    )
                )
            ]
        )
        if (
            consensus[j]
            <= 0
        ):
            continue
        sector_u[sector] = (
            float(u[j])
        )
        sector_support[sector] = (
            float(
                np.mean(
                    np.isfinite(
                        rows[:, j]
                    )
                )
            )
        )

    targets = (
        steps._periodic_boundary(
            angles,
            sector_u,
        )
    )
    return {
        "global_u": global_u,
        "sector_u": sector_u,
        "sector_support":
            sector_support,
        "targets_u": targets,
    }


def measure_transition_ray(
    profile,
    support,
    u,
    semantic_window,
    *,
    target_u=None,
    search_radius=
        DEFAULT_LOCAL_SEARCH_RADIUS,
):
    """Measure one local transition around a predeclared semantic target."""
    smooth, derivative = (
        _smooth_derivative(
            profile,
            support,
            u,
        )
    )
    if smooth is None:
        return None

    support = np.asarray(
        support, bool
    )
    u = np.asarray(u, float)
    lo, hi = map(
        float, semantic_window
    )
    zone = (
        support
        & np.isfinite(derivative)
        & (u >= lo)
        & (u <= hi)
    )
    if target_u is not None:
        zone &= (
            np.abs(
                u - float(target_u)
            )
            <= search_radius
        )
    if zone.sum() < 5:
        return None

    zone_indices = np.flatnonzero(
        zone
    )
    peak_idx = int(
        zone_indices[
            int(
                np.nanargmax(
                    derivative[
                        zone_indices
                    ]
                )
            )
        ]
    )
    peak_u = float(
        u[peak_idx]
    )

    broad_zone = (
        support
        & np.isfinite(
            derivative
        )
        & (u >= lo)
        & (u <= hi)
    )
    baseline = float(
        np.nanmedian(
            derivative[
                broad_zone
            ]
        )
    )
    local_d = derivative[
        zone
    ]
    weights = np.maximum(
        local_d - baseline,
        0.0,
    )
    local_u = u[zone]
    q10 = _weighted_quantile(
        local_u,
        weights,
        0.10,
    )
    q90 = _weighted_quantile(
        local_u,
        weights,
        0.90,
    )
    width = (
        None
        if (
            q10 is None
            or q90 is None
        )
        else float(
            max(
                0.0,
                q90 - q10,
            )
        )
    )

    du = float(
        np.median(
            np.diff(u)
        )
    )
    plateau = max(
        2,
        int(
            round(
                0.018
                / max(
                    du, 1e-9
                )
            )
        ),
    )
    gap = max(
        1,
        int(
            round(
                0.008
                / max(
                    du, 1e-9
                )
            )
        ),
    )
    left = smooth[
        max(
            0,
            peak_idx
            - gap
            - plateau,
        ):
        max(
            0,
            peak_idx-gap,
        )
    ]
    right = smooth[
        min(
            len(smooth),
            peak_idx+gap,
        ):
        min(
            len(smooth),
            peak_idx
            + gap
            + plateau,
        )
    ]
    contrast = (
        float(
            abs(
                np.median(right)
                - np.median(left)
            )
        )
        if (
            left.size
            and right.size
        )
        else 0.0
    )
    noise = float(
        1.4826
        * np.nanmedian(
            np.abs(
                smooth[broad_zone]
                - np.nanmedian(
                    smooth[
                        broad_zone
                    ]
                )
            )
        )
    )
    contrast_score = (
        contrast
        / (
            contrast
            + noise
            + 1e-9
        )
    )
    peak = float(
        derivative[peak_idx]
    )
    concentration = (
        peak
        / (
            peak
            + 2.0*baseline
            + 1e-9
        )
    )
    local_support = float(
        np.mean(
            support[zone]
        )
    )
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
        "target_u": (
            None
            if target_u is None
            else float(
                target_u
            )
        ),
        "position_u":
            peak_u,
        "transition_width_u":
            width,
        "confidence":
            confidence,
        "local_contrast":
            contrast,
        "peak_gradient":
            peak,
        "gradient_baseline":
            baseline,
        "local_support_fraction":
            local_support,
    }


def longest_circular_gap_fraction(
    flags
):
    flags = np.asarray(
        flags, bool
    )
    if (
        flags.ndim != 1
        or flags.size == 0
    ):
        raise ValueError(
            "flags must be a "
            "non-empty 1-D "
            "boolean array"
        )
    missing = ~flags
    if not missing.any():
        return 0.0
    if missing.all():
        return 1.0
    doubled = np.r_[
        missing, missing
    ]
    best = run = 0
    for value in doubled:
        run = (
            run + 1
            if value
            else 0
        )
        best = max(
            best, run
        )
    return float(
        min(
            best,
            len(flags),
        )
        / len(flags)
    )


def circular_component_count(
    flags
):
    """Number of circular True components."""
    flags = np.asarray(
        flags, bool
    )
    if (
        flags.ndim != 1
        or flags.size == 0
    ):
        raise ValueError(
            "flags must be a "
            "non-empty 1-D "
            "boolean array"
        )
    if not flags.any():
        return 0
    if flags.all():
        return 1
    return int(
        sum(
            bool(
                flags[i]
                and not flags[i-1]
            )
            for i in range(
                len(flags)
            )
        )
    )


def periodic_position_residual_mad(
    angles,
    positions,
    confidence,
):
    angles = np.asarray(
        angles, float
    )
    positions = np.asarray(
        positions, float
    )
    confidence = np.asarray(
        confidence, float
    )
    good = (
        np.isfinite(
            positions
        )
        & np.isfinite(
            confidence
        )
        & (
            confidence
            > 0.05
        )
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
    coef, *_ = (
        np.linalg.lstsq(
            design
            * root_w[:, None],
            y * root_w,
            rcond=None,
        )
    )
    residual = (
        y - design @ coef
    )
    med = float(
        np.median(residual)
    )
    return float(
        1.4826
        * np.median(
            np.abs(
                residual - med
            )
        )
    )


def measure_boundary_frame(
    ray_profiles,
    ray_support,
    u,
    angles,
    semantic_window,
    *,
    low_confidence=
        DEFAULT_LOW_CONFIDENCE,
    local_search_radius=
        DEFAULT_LOCAL_SEARCH_RADIUS,
    include_rays=True,
):
    ray_profiles = np.asarray(
        ray_profiles, float
    )
    ray_support = np.asarray(
        ray_support, bool
    )
    u = np.asarray(u, float)
    angles = np.asarray(
        angles, float
    )
    if (
        ray_profiles.shape
        != ray_support.shape
        or ray_profiles.ndim
        != 2
    ):
        raise ValueError(
            "ray_profiles and "
            "ray_support must be "
            "matching ray x radius "
            "arrays"
        )
    if (
        ray_profiles.shape
        != (
            len(angles),
            len(u),
        )
    ):
        raise ValueError(
            "angles/u must match "
            "ray profiles"
        )

    locus = (
        _sector_boundary_targets(
            ray_profiles,
            ray_support,
            u,
            angles,
            semantic_window,
        )
    )
    if locus is None:
        return {
            "status":
                "unavailable",
            "reason":
                "no_frame_consensus_boundary",
            "ray_count":
                int(
                    len(angles)
                ),
        }

    rays = [
        measure_transition_ray(
            ray_profiles[i],
            ray_support[i],
            u,
            semantic_window,
            target_u=
                locus[
                    "targets_u"
                ][i],
            search_radius=
                local_search_radius,
        )
        for i in range(
            len(angles)
        )
    ]
    confidence = np.asarray(
        [
            0.0
            if row is None
            else row[
                "confidence"
            ]
            for row in rays
        ],
        float,
    )
    positions = np.asarray(
        [
            np.nan
            if row is None
            else row[
                "position_u"
            ]
            for row in rays
        ],
        float,
    )
    widths = [
        None
        if row is None
        else row[
            "transition_width_u"
        ]
        for row in rays
    ]
    low = (
        confidence
        < low_confidence
    )
    available = np.isfinite(
        positions
    )
    result = {
        "status": (
            "ok"
            if available.mean()
            >= 0.75
            else "review"
            if available.mean()
            >= 0.40
            else "unavailable"
        ),
        "ray_count":
            int(len(angles)),
        "available_fraction":
            float(
                available.mean()
            ),
        "frame_global_u":
            float(
                locus["global_u"]
            ),
        "sector_target_u": [
            float(v)
            for v in locus[
                "sector_u"
            ]
        ],
        "sector_target_support": [
            float(v)
            for v in locus[
                "sector_support"
            ]
        ],
        "local_search_radius_u":
            float(
                local_search_radius
            ),
        "median_transition_width_u":
            _median(widths),
        "median_confidence":
            float(
                np.median(
                    confidence
                )
            ),
        "mean_confidence":
            float(
                np.mean(
                    confidence
                )
            ),
        "low_confidence_fraction":
            float(
                np.mean(low)
            ),
        "longest_low_confidence_gap_fraction":
            longest_circular_gap_fraction(
                ~low
            ),
        "low_confidence_component_count":
            circular_component_count(
                low
            ),
        "position_residual_mad_u":
            periodic_position_residual_mad(
                angles,
                positions,
                confidence,
            ),
        "median_local_contrast":
            _median(
                [
                    None
                    if row is None
                    else row[
                        "local_contrast"
                    ]
                    for row in rays
                ]
            ),
        "median_peak_gradient":
            _median(
                [
                    None
                    if row is None
                    else row[
                        "peak_gradient"
                    ]
                    for row in rays
                ]
            ),
        "low_confidence_threshold":
            float(
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
        name:
            measure_boundary_frame(
                ray_profiles,
                ray_support,
                u,
                angles,
                window,
                include_rays=
                    include_rays,
            )
        for name, window
        in zip(
            BOUNDARIES,
            BOUNDARY_WINDOWS,
        )
    }


def summarize_frames(frames):
    summary = {}
    for boundary in BOUNDARIES:
        rows = [
            frame[boundary]
            for frame in frames
            if (
                frame is not None
                and frame[
                    boundary
                ].get(
                    "status"
                )
                != "unavailable"
            )
        ]
        summary[boundary] = {
            "frame_count":
                len(rows),
            "median_transition_width_u":
                _median(
                    [
                        r[
                            "median_transition_width_u"
                        ]
                        for r in rows
                    ]
                ),
            "median_confidence":
                _median(
                    [
                        r[
                            "median_confidence"
                        ]
                        for r in rows
                    ]
                ),
            "median_longest_gap_fraction":
                _median(
                    [
                        r[
                            "longest_low_confidence_gap_fraction"
                        ]
                        for r in rows
                    ]
                ),
            "median_fragment_count":
                _median(
                    [
                        r[
                            "low_confidence_component_count"
                        ]
                        for r in rows
                    ]
                ),
            "median_position_residual_mad_u":
                _median(
                    [
                        r[
                            "position_residual_mad_u"
                        ]
                        for r in rows
                    ]
                ),
            "median_local_contrast":
                _median(
                    [
                        r[
                            "median_local_contrast"
                        ]
                        for r in rows
                    ]
                ),
            "median_peak_gradient":
                _median(
                    [
                        r[
                            "median_peak_gradient"
                        ]
                        for r in rows
                    ]
                ),
        }
    return summary
