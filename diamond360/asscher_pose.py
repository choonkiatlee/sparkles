"""Auditable Asscher frame suitability and canonical 2-D pose.

This module ranks whether a silhouette is useful for later semantic wireframe
fitting.  It intentionally stops at image-plane evidence: projection
inconsistency is measured and reported, never converted into a physical camera
tilt or corrected with a homography.
"""
from __future__ import annotations

import math

import numpy as np

from . import normalized_geometry
from .geometry import fit_asscher_outline

SCHEMA = "diamond360-asscher-pose/1"

_REJECT_MAX_PARALLELISM_DEG = 10.0
_REJECT_MAX_NORMALIZED_RESIDUAL = 0.055
_REJECT_MIN_VALID_FRACTION = 0.65
_REVIEW_MIN_SCORE = 0.78
_REVIEW_MIN_PROJECTION_SCORE = 0.70
_REVIEW_MIN_EDGE_VISIBILITY = 0.70
_REVIEW_MIN_MARGIN_FRACTION = 0.035


def specification():
    """Return the declared, fixture-independent v1 suitability policy."""
    return {
        "schema_version": SCHEMA,
        "coordinate_space": "2-D image plane",
        "physical_geometry_claim": "none",
        "canonical_transform": (
            "translation + rotation + isotropic scale only; "
            "no anisotropic/projective rectification"
        ),
        "orientation_period_deg": 90,
        "quarter_turn_policy": (
            "single-frame quarter-turn remains ambiguous; downstream sequence "
            "tracking may resolve equivalent branches by temporal continuity"
        ),
        "component_policy": {
            "clipping": "minimum image-edge margin / effective diameter",
            "outline_fit": "q90 boundary-to-eight-line residual / effective diameter",
            "squareness": "absolute log fitted width/height",
            "opposite_parallelism": "maximum observed opposite-side angle error",
            "centre_offset": "outline-centre to silhouette-centroid / effective diameter",
            "corner_balance": "maximum normalized opposite corner-side imbalance",
            "edge_visibility": "boundary support relative to fitted model-side length",
            "valid_support": "fraction of silhouette pixels on valid source support",
            "projection_consistency": (
                "geometric mean of squareness, opposite-parallelism, "
                "centre-offset and corner-balance scores"
            ),
        },
        "hard_reject_thresholds": {
            "image_edge_margin_px": 1.0,
            "max_opposite_parallelism_error_deg": _REJECT_MAX_PARALLELISM_DEG,
            "normalized_q90_outline_residual": _REJECT_MAX_NORMALIZED_RESIDUAL,
            "valid_fraction_of_mask": _REJECT_MIN_VALID_FRACTION,
        },
        "review_thresholds": {
            "overall_score": _REVIEW_MIN_SCORE,
            "projection_consistency_score": _REVIEW_MIN_PROJECTION_SCORE,
            "edge_visibility_score": _REVIEW_MIN_EDGE_VISIBILITY,
            "edge_margin_fraction": _REVIEW_MIN_MARGIN_FRACTION,
        },
        "score_note": (
            "Scores rank geometry usability only. Thresholds are declared v1 "
            "heuristics and are not fitted to DiaGem/Sergey facet-angle values."
        ),
    }


def _bounded(value):
    return float(np.clip(float(value), 0.0, 1.0))


def _gaussian_score(value, scale):
    return float(math.exp(-((float(value) / float(scale)) ** 2)))


def _component(value, score, unit=None):
    result = {
        "value": None if value is None else float(value),
        "score": _bounded(score),
    }
    if unit is not None:
        result["unit"] = unit
    return result


def assess_frame(mask, valid_mask=None):
    """Assess one candidate frame from its segmented silhouette/support."""
    mask = np.asarray(mask, bool)
    if mask.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    if valid_mask is not None:
        valid_mask = np.asarray(valid_mask, bool)
        if valid_mask.shape != mask.shape:
            raise ValueError("valid_mask must match mask shape")

    try:
        outline = fit_asscher_outline(mask)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA,
            "status": "failed",
            "score": 0.0,
            "reasons": ["outline_fit_failed"],
            "failure_detail": str(exc),
            "components": {},
            "outline": None,
        }

    height, width = mask.shape
    yy, xx = np.nonzero(mask)
    margin_px = float(
        min(
            xx.min(),
            yy.min(),
            width - 1 - xx.max(),
            height - 1 - yy.max(),
        )
    )
    diameter = max(float(outline["effective_diameter_px"]), 1e-12)
    margin_fraction = float(margin_px / diameter)
    clipping_score = _bounded(margin_fraction / _REVIEW_MIN_MARGIN_FRACTION)

    fit_residual = float(outline["normalized_q90_boundary_residual"])
    fit_score = _gaussian_score(fit_residual, 0.025)

    log_aspect_error = float(abs(math.log(max(outline["aspect_ratio"], 1e-12))))
    squareness_score = _gaussian_score(log_aspect_error, 0.12)

    parallel_errors = [
        float(value)
        for value in outline["parallelism_error_deg"].values()
        if value is not None
    ]
    max_parallelism = max(parallel_errors) if parallel_errors else 90.0
    parallelism_score = _gaussian_score(max_parallelism, 6.0)

    centre_offset = float(
        np.linalg.norm(
            np.asarray(outline["centre_xy"], float)
            - np.asarray(outline["silhouette_centroid_xy"], float)
        )
        / diameter
    )
    centre_score = _gaussian_score(centre_offset, 0.03)

    corner_imbalance = float(max(outline["opposite_corner_imbalance"]))
    corner_score = _gaussian_score(corner_imbalance, 0.20)

    support_ratios = [
        _bounded(side["support_ratio_to_model_length"])
        for side in outline["side_lines"]
    ]
    edge_visibility_score = float(np.mean(support_ratios))

    if valid_mask is None:
        valid_fraction = None
        valid_support_score = 1.0
    else:
        valid_fraction = float((valid_mask & mask).sum() / max(1, mask.sum()))
        valid_support_score = _bounded(
            (valid_fraction - _REJECT_MIN_VALID_FRACTION)
            / (0.95 - _REJECT_MIN_VALID_FRACTION)
        )

    projection_score = float(
        (
            squareness_score
            * parallelism_score
            * centre_score
            * corner_score
        )
        ** 0.25
    )

    components = {
        "clipping": _component(margin_fraction, clipping_score, "diameter_fraction"),
        "outline_fit": _component(fit_residual, fit_score, "diameter_fraction"),
        "squareness": _component(log_aspect_error, squareness_score, "abs_log_ratio"),
        "opposite_parallelism": _component(
            max_parallelism,
            parallelism_score,
            "degrees",
        ),
        "centre_offset": _component(
            centre_offset,
            centre_score,
            "diameter_fraction",
        ),
        "corner_balance": _component(
            corner_imbalance,
            corner_score,
            "normalized_difference",
        ),
        "edge_visibility": _component(
            edge_visibility_score,
            edge_visibility_score,
            "relative_support",
        ),
        "valid_support": _component(
            valid_fraction,
            valid_support_score,
            "fraction_of_mask",
        ),
        "projection_consistency": _component(
            None,
            projection_score,
        ),
    }

    overall = float(
        np.mean(
            [
                clipping_score,
                fit_score,
                projection_score,
                edge_visibility_score,
                valid_support_score,
            ]
        )
    )

    reject_reasons = []
    review_reasons = []
    if margin_px <= 1.0:
        reject_reasons.append("outline_clipped_or_at_image_edge")
    elif margin_fraction < _REVIEW_MIN_MARGIN_FRACTION:
        review_reasons.append("low_image_edge_margin")

    if max_parallelism > _REJECT_MAX_PARALLELISM_DEG:
        reject_reasons.append("severe_projection_parallelism")
    elif projection_score < _REVIEW_MIN_PROJECTION_SCORE:
        review_reasons.append("projection_inconsistency")

    if fit_residual > _REJECT_MAX_NORMALIZED_RESIDUAL:
        reject_reasons.append("outline_model_mismatch")
    elif fit_score < 0.70:
        review_reasons.append("weak_outline_fit")

    if edge_visibility_score < _REVIEW_MIN_EDGE_VISIBILITY:
        review_reasons.append("weak_edge_visibility")

    if valid_fraction is not None:
        if valid_fraction < _REJECT_MIN_VALID_FRACTION:
            reject_reasons.append("insufficient_valid_support")
        elif valid_support_score < 0.80:
            review_reasons.append("reduced_valid_support")

    if reject_reasons:
        status = "rejected"
        reasons = reject_reasons + review_reasons
    else:
        if overall < _REVIEW_MIN_SCORE:
            review_reasons.append("low_overall_suitability")
        status = "review" if review_reasons else "ok"
        reasons = review_reasons

    return {
        "schema_version": SCHEMA,
        "status": status,
        "score": overall,
        "reasons": reasons,
        "components": components,
        "outline": outline,
        "source_support": {
            "image_shape_yx": [int(height), int(width)],
            "minimum_image_edge_margin_px": margin_px,
            "valid_fraction_of_mask": valid_fraction,
        },
    }


def canonicalise_frame(
    brightness,
    mask,
    valid_mask,
    *,
    target_diameter=normalized_geometry.DEFAULT_TARGET_DIAMETER,
    margin_fraction=normalized_geometry.DEFAULT_MARGIN_FRACTION,
    lowpass_sigma_px=normalized_geometry.DEFAULT_LOWPASS_SIGMA_PX,
):
    """Assess and similarity-normalize one frame into canonical Asscher pose."""
    assessment = assess_frame(mask, valid_mask)
    if assessment["status"] == "failed":
        return {
            "assessment": assessment,
            "brightness": None,
            "mask": None,
            "valid_mask": None,
            "transform": None,
        }

    outline = assessment["outline"]
    normalized = normalized_geometry.normalize_frame(
        brightness,
        mask,
        valid_mask,
        target_diameter=target_diameter,
        margin_fraction=margin_fraction,
        lowpass_sigma_px=lowpass_sigma_px,
        centre_xy=outline["centre_xy"],
        rotation_deg=outline["orientation_deg_mod_90"],
    )
    transform = {
        **normalized["transform"],
        "pose_schema_version": SCHEMA,
        "orientation_period_deg": 90,
        "quarter_turn_ambiguous": bool(outline["quarter_turn_ambiguous"]),
        "rectification": "none",
    }
    return {
        "assessment": assessment,
        "brightness": normalized["brightness"],
        "mask": normalized["mask"],
        "valid_mask": normalized["valid_mask"],
        "transform": transform,
    }


def rank_assessments(assessments):
    """Return indices ordered by geometry usability, then descending score."""
    order = {"ok": 0, "review": 1, "rejected": 2, "failed": 3}
    return sorted(
        range(len(assessments)),
        key=lambda index: (
            order.get(assessments[index].get("status"), 4),
            -float(assessments[index].get("score", 0.0)),
            index,
        ),
    )
