"""Diagonal-arm / windmill legibility prototype for normalized Asscher frames.

The descriptor samples four predeclared diagonal corridors. Edge magnitude is
used only to locate/support a structure; outputs describe visibility,
orientation coherence, trajectory straightness and stability rather than raw
edge amplitude.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

from .normalized_geometry import effective_diameter

SCHEMA = "diamond360-diagonal-arms/1"
ARM_NAMES = ("SE", "SW", "NW", "NE")
ARM_ANGLES = (
    math.pi/4,
    3*math.pi/4,
    5*math.pi/4,
    7*math.pi/4,
)
DEFAULT_LOW_CONFIDENCE = 0.35


def _median(values):
    data = np.asarray(
        [
            float(v)
            for v in values
            if v is not None and math.isfinite(float(v))
        ],
        float,
    )
    return float(np.median(data)) if data.size else None


def _mad(values):
    data = np.asarray(
        [
            float(v)
            for v in values
            if v is not None and math.isfinite(float(v))
        ],
        float,
    )
    if not data.size:
        return None
    med = float(np.median(data))
    return float(
        1.4826 * np.median(np.abs(data - med))
    )


def longest_linear_gap_fraction(flags):
    flags = np.asarray(flags, bool)
    if flags.ndim != 1 or flags.size == 0:
        raise ValueError(
            "flags must be a non-empty 1-D boolean array"
        )
    best = run = 0
    for value in ~flags:
        run = run + 1 if value else 0
        best = max(best, run)
    return float(best / len(flags))


def _centroid(mask):
    yy, xx = np.nonzero(mask)
    if len(xx) < 64:
        raise ValueError(
            "mask must contain at least 64 pixels"
        )
    return float(np.mean(yy)), float(np.mean(xx))


def _angle_distance_axis(a, b):
    """Unsigned line-orientation difference modulo pi."""
    delta = (
        (a - b + math.pi/2) % math.pi
        - math.pi/2
    )
    return abs(float(delta))


def measure_arm(
    brightness,
    mask,
    valid_mask,
    angle,
    *,
    radial_samples=64,
    corridor_fraction=0.08,
    low_confidence=DEFAULT_LOW_CONFIDENCE,
    include_trace=True,
):
    brightness = np.asarray(brightness, float)
    mask = np.asarray(mask, bool)
    valid_mask = np.asarray(valid_mask, bool)
    if (
        brightness.ndim != 2
        or brightness.shape != mask.shape
        or mask.shape != valid_mask.shape
    ):
        raise ValueError(
            "brightness, mask and valid_mask must be "
            "matching 2-D arrays"
        )

    cy, cx = _centroid(mask)
    radius = effective_diameter(mask) / 2.0
    gy = ndi.sobel(
        brightness, axis=0, mode="nearest"
    )
    gx = ndi.sobel(
        brightness, axis=1, mode="nearest"
    )
    magnitude = np.hypot(gx, gy)

    radii = np.linspace(
        0.18*radius,
        0.84*radius,
        radial_samples,
    )
    offsets = np.linspace(
        -corridor_fraction*radius,
        corridor_fraction*radius,
        25,
    )
    ca, sa = math.cos(angle), math.sin(angle)
    px, py = -sa, ca

    yy = (
        cy
        + sa*radii[:, None]
        + py*offsets[None, :]
    )
    xx = (
        cx
        + ca*radii[:, None]
        + px*offsets[None, :]
    )
    mag = ndi.map_coordinates(
        magnitude,
        [yy, xx],
        order=1,
        mode="constant",
        cval=0.0,
    )
    sx = ndi.map_coordinates(
        gx,
        [yy, xx],
        order=1,
        mode="constant",
        cval=0.0,
    )
    sy = ndi.map_coordinates(
        gy,
        [yy, xx],
        order=1,
        mode="constant",
        cval=0.0,
    )
    support = (
        ndi.map_coordinates(
            valid_mask.astype(np.uint8),
            [yy, xx],
            order=0,
            mode="constant",
            cval=0,
        )
        > 0
    )
    support &= (
        ndi.map_coordinates(
            mask.astype(np.uint8),
            [yy, xx],
            order=0,
            mode="constant",
            cval=0,
        )
        > 0
    )

    trace = []
    for i, r in enumerate(radii):
        ok = support[i]
        if ok.sum() < 5:
            trace.append(None)
            continue
        row = mag[i].copy()
        row[~ok] = -np.inf
        j = int(np.argmax(row))
        peak = float(mag[i, j])
        background = float(
            np.median(mag[i, ok])
        )
        edge_support = peak / (
            peak + 2.0*background + 1e-9
        )
        if peak <= 1e-12:
            alignment = 0.0
        else:
            alignment = (
                abs(
                    float(
                        sx[i, j]*px
                        + sy[i, j]*py
                    )
                )
                / (peak + 1e-9)
            )
            alignment = float(
                np.clip(alignment, 0.0, 1.0)
            )
        confidence = float(
            np.clip(
                edge_support * alignment,
                0.0,
                1.0,
            )
        )
        off = float(offsets[j] / radius)
        angular_offset = float(
            math.atan2(offsets[j], r)
        )
        trace.append(
            {
                "radius_fraction": float(
                    r/radius
                ),
                "offset_radius_fraction": off,
                "angular_offset_deg": float(
                    math.degrees(angular_offset)
                ),
                "confidence": confidence,
                "orientation_alignment":
                    alignment,
                "peak_gradient": peak,
            }
        )

    finite = [
        row for row in trace
        if row is not None
    ]
    if len(finite) < radial_samples * 0.4:
        status = "unavailable"
    elif len(finite) < radial_samples * 0.75:
        status = "review"
    else:
        status = "ok"

    confidence = np.asarray(
        [
            0.0
            if row is None
            else row["confidence"]
            for row in trace
        ],
        float,
    )
    available = np.asarray(
        [row is not None for row in trace],
        bool,
    )
    good = available & (confidence > 0.05)
    straightness = None
    if good.sum() >= 10:
        rr = np.asarray(
            [r/radius for r in radii],
            float,
        )[good]
        oo = np.asarray(
            [
                np.nan
                if row is None
                else row[
                    "offset_radius_fraction"
                ]
                for row in trace
            ],
            float,
        )[good]
        ww = confidence[good]
        design = np.column_stack(
            [np.ones_like(rr), rr]
        )
        root_w = np.sqrt(ww)
        coef, *_ = np.linalg.lstsq(
            design * root_w[:, None],
            oo * root_w,
            rcond=None,
        )
        residual = oo - design @ coef
        straightness = _mad(residual)

    result = {
        "status": status,
        "available_fraction": float(
            available.mean()
        ),
        "median_confidence": float(
            np.median(confidence)
        ),
        "mean_confidence": float(
            np.mean(confidence)
        ),
        "longest_low_confidence_gap_fraction":
            longest_linear_gap_fraction(
                confidence >= low_confidence
            ),
        "median_orientation_alignment": _median(
            [
                None
                if row is None
                else row[
                    "orientation_alignment"
                ]
                for row in trace
            ]
        ),
        "trajectory_straightness_mad_radius":
            straightness,
        "median_angular_offset_deg": _median(
            [
                None
                if row is None
                else row["angular_offset_deg"]
                for row in trace
            ]
        ),
        "angular_offset_mad_deg": _mad(
            [
                None
                if row is None
                else row["angular_offset_deg"]
                for row in trace
            ]
        ),
        "low_confidence_threshold": float(
            low_confidence
        ),
    }
    if include_trace:
        result["trace"] = trace
    return result


def measure_frame(
    brightness,
    mask,
    valid_mask,
    *,
    include_trace=True,
):
    arm_rows = {
        name: measure_arm(
            brightness,
            mask,
            valid_mask,
            angle,
            include_trace=include_trace,
        )
        for name, angle in zip(
            ARM_NAMES, ARM_ANGLES
        )
    }
    effective = []
    for name, expected in zip(
        ARM_NAMES, ARM_ANGLES
    ):
        offset = arm_rows[name][
            "median_angular_offset_deg"
        ]
        effective.append(
            None
            if offset is None
            else expected + math.radians(offset)
        )
    opposing = {}
    for label, a, b in (
        ("SE_NW", 0, 2),
        ("SW_NE", 1, 3),
    ):
        if (
            effective[a] is None
            or effective[b] is None
        ):
            opposing[label] = None
        else:
            opposing[label] = float(
                math.degrees(
                    _angle_distance_axis(
                        effective[a],
                        effective[b],
                    )
                )
            )
    spacing_error = []
    if all(v is not None for v in effective):
        ordered = np.unwrap(
            np.asarray(effective, float)
        )
        gaps = np.diff(
            np.r_[
                ordered,
                ordered[0] + 2*math.pi,
            ]
        )
        spacing_error = [
            float(
                math.degrees(
                    abs(g - math.pi/2)
                )
            )
            for g in gaps
        ]
    return {
        "arms": arm_rows,
        "opposing_axis_misalignment_deg":
            opposing,
        "four_arm_spacing_error_mad_deg":
            _mad(spacing_error),
    }


def summarize_frames(frames):
    output = {
        "arms": {},
        "frame_count": len(frames),
    }
    for name in ARM_NAMES:
        rows = [
            frame["arms"][name]
            for frame in frames
        ]
        offsets = [
            row["median_angular_offset_deg"]
            for row in rows
        ]
        output["arms"][name] = {
            "median_visibility_confidence":
                _median(
                    [
                        row["median_confidence"]
                        for row in rows
                    ]
                ),
            "median_orientation_alignment":
                _median(
                    [
                        row[
                            "median_orientation_alignment"
                        ]
                        for row in rows
                    ]
                ),
            "median_straightness_mad_radius":
                _median(
                    [
                        row[
                            "trajectory_straightness_mad_radius"
                        ]
                        for row in rows
                    ]
                ),
            "median_longest_gap_fraction":
                _median(
                    [
                        row[
                            "longest_low_confidence_gap_fraction"
                        ]
                        for row in rows
                    ]
                ),
            "angular_offset_frame_mad_deg":
                _mad(offsets),
        }
    for pair in ("SE_NW", "SW_NE"):
        output.setdefault(
            "opposing_axis_misalignment_deg",
            {},
        )[pair] = _median(
            [
                frame[
                    "opposing_axis_misalignment_deg"
                ][pair]
                for frame in frames
            ]
        )
    output[
        "median_four_arm_spacing_error_mad_deg"
    ] = _median(
        [
            frame[
                "four_arm_spacing_error_mad_deg"
            ]
            for frame in frames
        ]
    )
    return output
