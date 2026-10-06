"""Declared common spatial-transfer function for static Asscher geometry work.

This module does not enhance source imagery. It maps every already-registered
frame to a fixed effective diamond diameter, then applies one fixed Gaussian
low-pass in normalized output pixels. The policy is deliberately simple and
fully serialized so downstream research can distinguish source content from the
measurement transfer function.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

SCHEMA = "diamond360-normalized-geometry/1"
DEFAULT_TARGET_DIAMETER = 256
DEFAULT_MARGIN_FRACTION = 0.12
DEFAULT_LOWPASS_SIGMA_PX = 1.0


def specification(
    target_diameter=DEFAULT_TARGET_DIAMETER,
    margin_fraction=DEFAULT_MARGIN_FRACTION,
    lowpass_sigma_px=DEFAULT_LOWPASS_SIGMA_PX,
):
    if target_diameter < 64:
        raise ValueError("target_diameter must be at least 64 pixels")
    if not 0 <= margin_fraction <= 0.5:
        raise ValueError("margin_fraction must be between 0 and 0.5")
    if lowpass_sigma_px < 0:
        raise ValueError("lowpass_sigma_px must be non-negative")
    canvas_size = int(math.ceil(target_diameter * (1 + 2 * margin_fraction)))
    if canvas_size % 2 == 0:
        canvas_size += 1
    return {
        "schema_version": SCHEMA,
        "target_effective_diameter_px": int(target_diameter),
        "canvas_size_px": int(canvas_size),
        "centering": "valid-mask centroid",
        "effective_diameter": "2*sqrt(mask_area/pi)",
        "resampling": "scipy.ndimage.map_coordinates order=1",
        "mask_resampling": "scipy.ndimage.map_coordinates order=0",
        "post_resample_lowpass": "gaussian",
        "lowpass_sigma_px": float(lowpass_sigma_px),
        "enhancement": "none",
    }


def effective_diameter(mask):
    mask = np.asarray(mask, bool)
    area = int(mask.sum())
    if mask.ndim != 2 or area < 64:
        raise ValueError("mask must be a non-trivial 2-D silhouette")
    return float(2.0 * math.sqrt(area / math.pi))


def _centroid(mask):
    yy, xx = np.nonzero(mask)
    if len(xx) < 64:
        raise ValueError("mask must contain at least 64 pixels")
    return float(np.mean(yy)), float(np.mean(xx))


def normalize_frame(
    brightness,
    mask,
    valid_mask,
    *,
    target_diameter=DEFAULT_TARGET_DIAMETER,
    margin_fraction=DEFAULT_MARGIN_FRACTION,
    lowpass_sigma_px=DEFAULT_LOWPASS_SIGMA_PX,
):
    """Normalize one registered frame onto the declared spatial transfer."""
    spec = specification(target_diameter, margin_fraction, lowpass_sigma_px)
    brightness = np.asarray(brightness, float)
    mask = np.asarray(mask, bool)
    valid_mask = np.asarray(valid_mask, bool)
    if (
        brightness.ndim != 2
        or brightness.shape != mask.shape
        or mask.shape != valid_mask.shape
    ):
        raise ValueError(
            "brightness, mask and valid_mask must be matching 2-D arrays"
        )
    if not np.isfinite(brightness[valid_mask]).all():
        raise ValueError(
            "brightness contains non-finite values on valid support"
        )

    source_diameter = effective_diameter(mask)
    scale = float(target_diameter / source_diameter)
    cy, cx = _centroid(mask)
    n = spec["canvas_size_px"]
    oc = (n - 1) / 2.0
    oy, ox = np.indices((n, n), dtype=float)
    iy = cy + (oy - oc) / scale
    ix = cx + (ox - oc) / scale

    sampled = ndi.map_coordinates(
        brightness,
        [iy, ix],
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    out_mask = (
        ndi.map_coordinates(
            mask.astype(np.uint8),
            [iy, ix],
            order=0,
            mode="constant",
            cval=0,
        )
        > 0
    )
    out_valid = (
        ndi.map_coordinates(
            valid_mask.astype(np.uint8),
            [iy, ix],
            order=0,
            mode="constant",
            cval=0,
        )
        > 0
    )
    out_valid &= out_mask

    if lowpass_sigma_px:
        weights = out_valid.astype(float)
        numerator = ndi.gaussian_filter(
            sampled * weights, lowpass_sigma_px, mode="nearest"
        )
        denominator = ndi.gaussian_filter(
            weights, lowpass_sigma_px, mode="nearest"
        )
        good = denominator > 0.25
        filtered = np.zeros_like(sampled)
        filtered[good] = numerator[good] / denominator[good]
        sampled = filtered
        out_valid &= good

    sampled[~out_valid] = 0.0
    return {
        "brightness": sampled,
        "mask": out_mask,
        "valid_mask": out_valid,
        "transform": {
            **spec,
            "source_effective_diameter_px": float(source_diameter),
            "isotropic_scale": scale,
            "source_centroid_yx": [cy, cx],
            "valid_fraction_of_mask": float(
                out_valid.sum() / max(1, out_mask.sum())
            ),
        },
    }
