"""Outer-octagon-first geometry anchoring for Asscher wireframes.

The silhouette is the strongest physical image boundary in a vendor 360: it
separates the stone from the background and is much less ambiguous than the
interior bright/dark structure.  This module therefore treats the fitted outer
cut-corner octagon as the first geometry gate and the coordinate anchor for
later crown/table inference.

It intentionally makes no 3-D camera or facet-angle claim.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import fit_asscher_outline

SCHEMA = "diamond360-asscher-outer-octagon/1"

MIN_EDGE_VISIBILITY_SCORE = 0.72
MAX_NORMALIZED_Q90_RESIDUAL = 0.040
MAX_CARDINAL_PARALLELISM_DEG = 6.0
MAX_ABS_LOG_ASPECT = 0.10
FACE_ON_ASPECT_SCALE = 0.050
FACE_ON_PARALLELISM_SCALE_DEG = 3.0
PREFERRED_FACE_ON_CORE_FRAMES = 5
MIN_CONSENSUS_DISTANCE = 0.012
CONSENSUS_MAD_MULTIPLIER = 2.5

# geometry.fit_asscher_outline vertex i is the intersection of side-normal
# families i and i+1.  Reorder those vertices into asscher_topology's ring
# order: top-left, top-right, right-top, right-bottom, bottom-right,
# bottom-left, left-bottom, left-top.
_GEOMETRY_TO_TOPOLOGY_VERTEX_ORDER = (5, 6, 7, 0, 1, 2, 3, 4)


def specification():
    return {
        "schema_version": SCHEMA,
        "purpose": (
            "fit and validate the physical silhouette before using any "
            "interior optical edge as semantic geometry"
        ),
        "selection_thresholds": {
            "minimum_edge_visibility_score": MIN_EDGE_VISIBILITY_SCORE,
            "maximum_normalized_q90_boundary_residual": (
                MAX_NORMALIZED_Q90_RESIDUAL
            ),
            "maximum_cardinal_parallelism_error_deg": (
                MAX_CARDINAL_PARALLELISM_DEG
            ),
            "maximum_abs_log_aspect": MAX_ABS_LOG_ASPECT,
            "face_on_aspect_scale": FACE_ON_ASPECT_SCALE,
            "face_on_parallelism_scale_deg": FACE_ON_PARALLELISM_SCALE_DEG,
            "preferred_face_on_core_frames": PREFERRED_FACE_ON_CORE_FRAMES,
        },
        "consensus_policy": (
            "outline residual and edge visibility are reliability gates; "
            "among reliable silhouettes, face-onness is ranked from explicit "
            "octagon foreshortening (aspect) and opposite-cardinal convergence; "
            "a robust medoid/MAD gate separately removes shape outliers"
        ),
        "stone_outline_policy": (
            "the stone-level GIRDLE_OUTLINE is the coordinate-wise median of "
            "the selected per-frame fitted octagons after centre/scale "
            "normalization in the stable sequence gauge"
        ),
        "physical_geometry_claim": (
            "2-D observed silhouette only; no physical camera angle or "
            "projective rectification is inferred"
        ),
    }


def _component_score(assessment, name, default=0.0):
    row = (assessment.get("components") or {}).get(name) or {}
    value = row.get("score")
    return float(default if value is None else value)


def _cardinal_parallelism(outline):
    values = [
        float(value)
        for name, value in (outline.get("parallelism_error_deg") or {}).items()
        if name.startswith("cardinal_") and value is not None
    ]
    return max(values) if values else float("inf")


def _shape_vector(outline):
    diameter = max(float(outline.get("effective_diameter_px") or 0.0), 1e-12)
    sides = outline.get("side_lines") or []
    if len(sides) != 8:
        return None
    values = [
        float(side["offset_from_centre_px"]) / diameter
        for side in sides
    ]
    result = np.asarray(values, float)
    if result.shape != (8,) or not np.isfinite(result).all():
        return None
    return result


def _quarter_turn_distance(first, second):
    """RMS silhouette-shape distance, invariant to the 90-degree gauge branch."""
    a = np.asarray(first, float)
    b = np.asarray(second, float)
    if a.shape != (8,) or b.shape != (8,):
        raise ValueError("outer-octagon shape vectors must have eight sides")
    return float(min(
        np.sqrt(np.mean((a - np.roll(b, 2 * turns)) ** 2))
        for turns in range(4)
    ))


def assess_record(record):
    """Return an outer-silhouette-only diagnostic for one #73 pose record."""
    assessment = record.get("assessment") or {}
    outline = assessment.get("outline")
    diagnostic = {
        "source_index": record.get("source_index"),
        "position": record.get("position"),
        "rank": record.get("rank"),
        "face_role": record.get("face_role"),
        "status": "rejected",
        "hard_usable": False,
        "quality": 0.0,
        "reasons": [],
    }
    if not outline:
        diagnostic["reasons"] = ["outer_outline_unavailable"]
        return diagnostic

    residual = float(
        outline.get("normalized_q90_boundary_residual", float("inf"))
    )
    aspect = max(float(outline.get("aspect_ratio", 0.0)), 1e-12)
    aspect_error = float(abs(math.log(aspect)))
    parallelism = _cardinal_parallelism(outline)
    projection = _component_score(
        assessment, "projection_consistency", default=0.0
    )
    edge_visibility = _component_score(
        assessment, "edge_visibility", default=0.0
    )
    fit_score = _component_score(assessment, "outline_fit", default=0.0)
    # Detection quality answers "can we trust this outline?".
    # Projection-consistency remains diagnostic because its centre/corner terms
    # can penalize a genuinely asymmetric stone. Face-onness is instead an
    # explicit, narrow geometric measure from the outer octagon itself.
    quality = float(
        max(0.0, fit_score) * max(0.0, edge_visibility)
    ) ** 0.5
    face_on_error = float(math.sqrt(
        (aspect_error / FACE_ON_ASPECT_SCALE) ** 2
        + (parallelism / FACE_ON_PARALLELISM_SCALE_DEG) ** 2
    ))
    shape = _shape_vector(outline)

    reasons = []
    if shape is None:
        reasons.append("invalid_outer_octagon")
    if residual > MAX_NORMALIZED_Q90_RESIDUAL:
        reasons.append("outer_outline_residual")
    if parallelism > MAX_CARDINAL_PARALLELISM_DEG:
        reasons.append("outer_projection_parallelism")
    if aspect_error > MAX_ABS_LOG_ASPECT:
        reasons.append("outer_projection_aspect")
    if edge_visibility < MIN_EDGE_VISIBILITY_SCORE:
        reasons.append("outer_edge_visibility")

    diagnostic.update(
        status="candidate" if not reasons else "rejected",
        hard_usable=not reasons,
        quality=quality,
        face_on_error=face_on_error,
        normalized_q90_boundary_residual=residual,
        abs_log_aspect=aspect_error,
        max_cardinal_parallelism_error_deg=parallelism,
        projection_consistency_score=projection,
        edge_visibility_score=edge_visibility,
        outline_fit_score=fit_score,
        shape_vector=None if shape is None else shape.tolist(),
        reasons=reasons,
    )
    return diagnostic


def select_records(records, *, max_frames=7, min_frames=3):
    """Select compatible geometry views using the outer octagon before rank.

    The method deliberately does not fill the quota with lower-quality edge
    frames.  A stone may use fewer than max_frames when the crown lobe contains
    only a small face-on core.
    """
    records = list(records)
    diagnostics = [assess_record(record) for record in records]
    hard = [
        index for index, row in enumerate(diagnostics)
        if row["hard_usable"]
    ]

    result = {
        "schema_version": SCHEMA,
        "candidate_count": len(records),
        "hard_usable_count": len(hard),
        "selected_count": 0,
        "medoid_source_index": None,
        "consensus_distance_threshold": None,
        "quality_threshold": None,
        "frames": diagnostics,
    }
    if len(hard) < int(min_frames):
        for row in diagnostics:
            if row["hard_usable"]:
                row["reasons"] = ["insufficient_compatible_outer_views"]
        return [], result

    shapes = {
        index: np.asarray(diagnostics[index]["shape_vector"], float)
        for index in hard
    }
    pairwise = {
        (i, j): _quarter_turn_distance(shapes[i], shapes[j])
        for i in hard for j in hard if i != j
    }
    medoid = min(
        hard,
        key=lambda index: float(np.median([
            pairwise[(index, other)]
            for other in hard if other != index
        ])),
    )
    distances = {
        index: _quarter_turn_distance(shapes[index], shapes[medoid])
        for index in hard
    }
    distance_values = np.asarray(list(distances.values()), float)
    distance_median = float(np.median(distance_values))
    distance_mad = float(
        np.median(np.abs(distance_values - distance_median))
    )
    robust_scale = max(1.4826 * distance_mad, 1e-6)
    distance_threshold = max(
        MIN_CONSENSUS_DISTANCE,
        distance_median + CONSENSUS_MAD_MULTIPLIER * robust_scale,
    )

    consensus_pool = [
        index for index in hard
        if distances[index] <= distance_threshold
    ]
    effective_max = min(
        int(max_frames),
        int(PREFERRED_FACE_ON_CORE_FRAMES),
    )
    selected_indices = sorted(
        consensus_pool,
        key=lambda index: (
            diagnostics[index]["face_on_error"],
            -diagnostics[index]["quality"],
            distances[index],
            int(records[index].get("rank", 10**9)),
            int(records[index].get("position", 10**9)),
        ),
    )[: effective_max]
    selected_set = set(selected_indices)

    for index in hard:
        row = diagnostics[index]
        row["consensus_distance"] = float(distances[index])
        if index in selected_set:
            row["status"] = "selected"
            row["selected"] = True
            row["reasons"] = []
        else:
            row["selected"] = False
            if distances[index] > distance_threshold:
                row["status"] = "rejected"
                row["reasons"] = ["outer_octagon_consensus_outlier"]
            else:
                row["status"] = "not_selected"
                row["reasons"] = ["outside_face_on_outer_core"]
    for index, row in enumerate(diagnostics):
        if index not in hard:
            row["selected"] = False

    result.update(
        selected_count=len(selected_indices),
        medoid_source_index=records[medoid].get("source_index"),
        consensus_distance_threshold=float(distance_threshold),
        consensus_distance_median=distance_median,
        consensus_distance_mad=distance_mad,
        preferred_face_on_core_frames=int(PREFERRED_FACE_ON_CORE_FRAMES),
        frames=diagnostics,
    )
    return [records[index] for index in selected_indices], result


def _normalized_fitted_vertices(mask):
    """Fit one silhouette and express its octagon in topology ring order."""
    outline = fit_asscher_outline(np.asarray(mask, bool))
    points = np.asarray(outline["vertices_xy"], float)
    centre = np.asarray(outline["centre_xy"], float)
    points = points - centre[None, :]
    points = points[list(_GEOMETRY_TO_TOPOLOGY_VERTEX_ORDER)]
    scale = float(np.max(np.abs(points)))
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("outer octagon has invalid normalization scale")
    points = points / scale
    return points, outline


def fit_consensus(masks, frame_metadata=None):
    """Fit one fixed stone-level outer octagon from selected silhouette masks."""
    masks = [np.asarray(mask, bool) for mask in masks]
    if len(masks) < 3:
        raise ValueError("outer-octagon consensus requires at least three masks")
    metadata = (
        list(frame_metadata)
        if frame_metadata is not None
        else [{"source_index": i, "position": i} for i in range(len(masks))]
    )
    if len(metadata) != len(masks):
        raise ValueError("frame_metadata must match masks")

    per_frame = []
    vertices = []
    for mask, meta in zip(masks, metadata):
        points, outline = _normalized_fitted_vertices(mask)
        vertices.append(points)
        per_frame.append({
            "source_index": meta.get("source_index"),
            "position": meta.get("position"),
            "normalized_q90_boundary_residual": float(
                outline["normalized_q90_boundary_residual"]
            ),
            "aspect_ratio": float(outline["aspect_ratio"]),
            "vertices_topology_order": points.tolist(),
        })

    array = np.asarray(vertices, float)
    consensus = np.median(array, axis=0)
    scale = float(np.max(np.abs(consensus)))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("outer-octagon consensus has invalid scale")
    consensus = consensus / scale

    residuals = np.sqrt(
        np.mean((array - consensus[None, :, :]) ** 2, axis=(1, 2))
    )
    for row, residual in zip(per_frame, residuals):
        row["consensus_vertex_rms"] = float(residual)

    median_residual = float(np.median(residuals))
    # Confidence is intentionally simple and auditable: agreement of the
    # independently fitted silhouettes, not any interior optical evidence.
    confidence = float(np.clip(
        math.exp(-((median_residual / 0.060) ** 2)),
        0.0,
        1.0,
    ))
    return {
        "schema_version": SCHEMA,
        "vertices_topology_order": consensus.tolist(),
        "confidence": confidence,
        "median_vertex_rms": median_residual,
        "max_vertex_rms": float(np.max(residuals)),
        "frame_count": len(masks),
        "per_frame": per_frame,
    }
