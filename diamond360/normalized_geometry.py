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
DEFAULT_TARGET_DIAMETER = 160
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
        "centering": "silhouette centroid",
        "effective_diameter": "2*sqrt(mask_area/pi)",
        "anti_aliasing": (
            "support-weighted Gaussian before downsampling; "
            "sigma_source_px=max(0,0.5*(1/scale-1))"
        ),
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
    centre_xy=None,
    rotation_deg=0.0,
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
    centroid_y, centroid_x = _centroid(mask)
    if centre_xy is None:
        cx, cy = centroid_x, centroid_y
        centering_applied = "silhouette centroid"
    else:
        centre_xy = np.asarray(centre_xy, float)
        if centre_xy.shape != (2,) or not np.isfinite(centre_xy).all():
            raise ValueError("centre_xy must be a finite [x, y] pair")
        cx, cy = map(float, centre_xy)
        centering_applied = "explicit image-plane centre"
    if not np.isfinite(rotation_deg):
        raise ValueError("rotation_deg must be finite")
    rotation_deg = float(rotation_deg)
    anti_alias_sigma = (
        max(0.0, 0.5 * (1.0 / scale - 1.0))
        if scale < 1.0
        else 0.0
    )
    source = brightness
    source_valid = valid_mask.copy()
    if anti_alias_sigma > 0:
        weights = source_valid.astype(float)
        numerator = ndi.gaussian_filter(
            source * weights,
            anti_alias_sigma,
            mode="nearest",
        )
        denominator = ndi.gaussian_filter(
            weights,
            anti_alias_sigma,
            mode="nearest",
        )
        good = denominator > 0.25
        filtered = np.zeros_like(source)
        filtered[good] = numerator[good] / denominator[good]
        source = filtered
        source_valid &= good

    n = spec["canvas_size_px"]
    oc = (n - 1) / 2.0

    # source -> canonical is a similarity transform only.  Rotation is
    # deliberately not allowed to introduce anisotropic scale, shear, or
    # projective rectification because those would hide projection evidence.
    angle = math.radians(-rotation_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    rotation = np.array(
        [[cosine, -sine], [sine, cosine]],
        dtype=float,
    )
    linear = scale * rotation
    centre = np.array([cx, cy], dtype=float)
    translation = np.array([oc, oc], dtype=float) - linear @ centre
    source_to_canonical = np.eye(3, dtype=float)
    source_to_canonical[:2, :2] = linear
    source_to_canonical[:2, 2] = translation
    canonical_to_source = np.linalg.inv(source_to_canonical)

    oy, ox = np.indices((n, n), dtype=float)
    homogeneous = np.stack(
        [ox.ravel(), oy.ravel(), np.ones(n * n, dtype=float)],
        axis=0,
    )
    source_xy = canonical_to_source @ homogeneous
    ix = source_xy[0].reshape(n, n)
    iy = source_xy[1].reshape(n, n)

    sampled = ndi.map_coordinates(
        source,
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
            source_valid.astype(np.uint8),
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
            "sampling_direction": (
                "downsample"
                if scale < 1.0
                else "upsample"
                if scale > 1.0
                else "native"
            ),
            "anti_alias_sigma_source_px": float(
                anti_alias_sigma
            ),
            "source_centroid_yx": [centroid_y, centroid_x],
            "source_centre_xy": [cx, cy],
            "centering_applied": centering_applied,
            "rotation_applied_deg": rotation_deg,
            "transform_type": "similarity: translation + rotation + isotropic scale",
            "source_to_canonical_xy": source_to_canonical.tolist(),
            "canonical_to_source_xy": canonical_to_source.tolist(),
            "valid_fraction_of_mask": float(
                out_valid.sum() / max(1, out_mask.sum())
            ),
        },
    }
