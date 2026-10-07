"""Silhouette geometry in camera coordinates, without inferring 3D geometry.

The generic :func:`measure` contract remains intentionally conservative.  Asscher
pose work uses :func:`fit_asscher_outline`, which fits a 2-D cut-corner outline
with eight fixed direction families.  The fit is an image-plane scaffold only:
it does not claim physical facet angles, lengths, or camera calibration.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

ASSCHER_OUTLINE_SCHEMA = "diamond360-asscher-outline/1"


def measure(mask):
    y,x = np.nonzero(mask)
    if len(x) < 3:
        raise ValueError('Cannot measure empty/degenerate mask')
    points = np.column_stack([x,y]).astype(float)
    centre = points.mean(axis=0)
    covariance = np.cov(points-centre, rowvar=False, bias=True)
    values,vectors = np.linalg.eigh(covariance)
    values,vectors = values[::-1],vectors[:,::-1]
    ratio = float(values[0]/max(values[1],1e-12))
    major = vectors[:,0]
    angle = float((np.degrees(np.arctan2(major[1],major[0]))+90)%180-90)
    ambiguous = ratio < 1.08
    return dict(centroid_xy=centre.tolist(),bbox_xyxy=[int(x.min()),int(y.min()),int(x.max()),int(y.max())],
                width_px=int(np.ptp(x)+1),height_px=int(np.ptp(y)+1),area_px=int(len(x)),
                principal_axes_xy=vectors.T.tolist(),eigenvalues_px2=values.tolist(),
                eigenvalue_ratio=ratio,orientation_deg=None if ambiguous else angle,
                orientation_ambiguous=ambiguous,orientation_period_deg=180,
                principal_axis_lengths_px=(4*np.sqrt(values)).tolist(),
                corner_estimation='omitted: hull vertices are not validated Asscher corners')


def _as_mask(mask):
    mask = np.asarray(mask, bool)
    if mask.ndim != 2 or int(mask.sum()) < 64:
        raise ValueError("mask must be a non-trivial 2-D silhouette")
    return mask


def _rotate_points(points, angle_deg):
    """Rotate row-vector xy points around the origin."""
    angle = math.radians(float(angle_deg))
    c, s = math.cos(angle), math.sin(angle)
    matrix = np.array([[c, -s], [s, c]], dtype=float)
    return np.asarray(points, float) @ matrix.T


def _boundary_points(mask):
    boundary = mask & ~ndi.binary_erosion(mask)
    yy, xx = np.nonzero(boundary)
    if len(xx) < 16:
        raise ValueError("silhouette boundary is too small for Asscher outline fitting")
    return np.column_stack([xx, yy]).astype(float)


def _orientation_support(points, centroid, angle_deg):
    q = _rotate_points(points - centroid, -angle_deg)
    xmin, ymin = q.min(axis=0)
    xmax, ymax = q.max(axis=0)
    extent = max(xmax - xmin, ymax - ymin, 1.0)
    tolerance = max(0.75, 0.015 * extent)
    distance = np.minimum.reduce(
        [
            np.abs(q[:, 0] - xmin),
            np.abs(q[:, 0] - xmax),
            np.abs(q[:, 1] - ymin),
            np.abs(q[:, 1] - ymax),
        ]
    )
    return float(np.mean(distance <= tolerance))


def _canonical_orientation(points, centroid):
    """Return the Asscher cardinal-axis angle modulo 90 degrees.

    A cut-corner square has four long cardinal sides and four shorter corner
    sides.  The correct cardinal orientation therefore maximises boundary
    support on an oriented bounding box.  Searching only one 90-degree period
    makes the unavoidable fourfold ambiguity explicit.
    """
    coarse = np.arange(-45.0, 45.0, 0.5)
    scores = np.array(
        [_orientation_support(points, centroid, angle) for angle in coarse]
    )
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(best - 0.6, best + 0.6001, 0.05)
    fine = ((fine + 45.0) % 90.0) - 45.0
    fine_scores = np.array(
        [_orientation_support(points, centroid, angle) for angle in fine]
    )
    index = int(np.argmax(fine_scores))
    return float(fine[index]), float(fine_scores[index])


def _line_direction_deg(points):
    points = np.asarray(points, float)
    if len(points) < 3:
        return None
    centred = points - points.mean(axis=0)
    covariance = np.cov(centred, rowvar=False, bias=True)
    values, vectors = np.linalg.eigh(covariance)
    if values[-1] <= 1e-9:
        return None
    direction = vectors[:, -1]
    return float(
        (np.degrees(np.arctan2(direction[1], direction[0])) + 90.0)
        % 180.0
        - 90.0
    )


def _angle_difference_180(a, b):
    return float(abs((float(a) - float(b) + 90.0) % 180.0 - 90.0))


def fit_asscher_outline(mask):
    """Fit a constrained 2-D cut-corner-square outline to a silhouette.

    The model has eight outward-normal direction families at 45-degree
    intervals.  Their offsets are fit independently so corner sizes and
    opposing sides may differ.  Direction families are used to establish a
    stable image-plane pose; local observed side directions are also reported
    so projection/asymmetry can be audited rather than rectified away.

    Returns only image-plane geometry.  In particular, side lengths and angles
    in this record are *not* physical polished-facet measurements.
    """
    mask = _as_mask(mask)
    yy, xx = np.nonzero(mask)
    silhouette_centroid = np.array([xx.mean(), yy.mean()], dtype=float)
    boundary = _boundary_points(mask)

    orientation, orientation_support = _canonical_orientation(
        boundary, silhouette_centroid
    )
    q = _rotate_points(boundary - silhouette_centroid, -orientation)

    normal_angles = np.arange(0.0, 360.0, 45.0)
    normals = np.column_stack(
        [
            np.cos(np.radians(normal_angles)),
            np.sin(np.radians(normal_angles)),
        ]
    )

    # A high quantile is more robust than one extreme pixel while still
    # following the eroded segmentation boundary closely.
    projections = q @ normals.T
    offsets = np.quantile(projections, 0.9975, axis=0)

    # Cardinal support lines define the outline centre without imposing equal
    # side lengths or perfect fourfold symmetry.
    centre_q = np.array(
        [
            (offsets[0] - offsets[4]) / 2.0,
            (offsets[2] - offsets[6]) / 2.0,
        ]
    )
    centre_xy = (
        silhouette_centroid
        + _rotate_points(centre_q[None, :], orientation)[0]
    )

    q_centre = q - centre_q
    centred_offsets = offsets - normals @ centre_q

    vertices_q = []
    for index in range(8):
        nxt = (index + 1) % 8
        matrix = np.vstack([normals[index], normals[nxt]])
        rhs = np.array([centred_offsets[index], centred_offsets[nxt]])
        vertices_q.append(np.linalg.solve(matrix, rhs))
    vertices_q = np.asarray(vertices_q)
    vertices_xy = (
        centre_xy
        + _rotate_points(vertices_q, orientation)
    )

    # Vertex i is the intersection of line i and line i+1, so line i
    # spans vertex i-1 -> vertex i.
    line_lengths = np.linalg.norm(
        vertices_q - np.roll(vertices_q, 1, axis=0),
        axis=1,
    )
    perimeter = float(line_lengths.sum())

    residuals = centred_offsets[None, :] - q_centre @ normals.T
    abs_residuals = np.abs(residuals)
    assignments = np.argmin(abs_residuals, axis=1)
    nearest = abs_residuals[np.arange(len(boundary)), assignments]

    effective_diameter = 2.0 * math.sqrt(float(mask.sum()) / math.pi)
    side_records = []
    observed_angles = []
    for index in range(8):
        chosen = assignments == index
        selected = boundary[chosen]
        observed_angle = _line_direction_deg(selected)
        observed_angles.append(observed_angle)
        expected_fraction = float(line_lengths[index] / max(perimeter, 1e-12))
        observed_fraction = float(np.mean(chosen))
        support_ratio = float(
            observed_fraction / max(expected_fraction, 1e-12)
        )
        side_records.append(
            {
                "index": index,
                "family": "cardinal" if index % 2 == 0 else "corner",
                "normal_angle_canonical_deg": float(normal_angles[index]),
                "offset_from_centre_px": float(centred_offsets[index]),
                "model_side_length_px": float(line_lengths[index]),
                "boundary_support_fraction": observed_fraction,
                "support_ratio_to_model_length": support_ratio,
                "observed_line_angle_image_deg": observed_angle,
                "median_model_residual_px": (
                    float(np.median(nearest[chosen])) if np.any(chosen) else None
                ),
                "q90_model_residual_px": (
                    float(np.quantile(nearest[chosen], 0.9))
                    if np.any(chosen)
                    else None
                ),
            }
        )

    parallelism = {}
    for name, first, second in [
        ("cardinal_0_4", 0, 4),
        ("corner_1_5", 1, 5),
        ("cardinal_2_6", 2, 6),
        ("corner_3_7", 3, 7),
    ]:
        a, b = observed_angles[first], observed_angles[second]
        parallelism[name] = (
            None if a is None or b is None else _angle_difference_180(a, b)
        )

    width = float(centred_offsets[0] + centred_offsets[4])
    height = float(centred_offsets[2] + centred_offsets[6])
    corner_lengths = line_lengths[1::2]
    opposite_corner_imbalance = []
    for a, b in [(0, 2), (1, 3)]:
        denom = max(float(corner_lengths[a] + corner_lengths[b]), 1e-12)
        opposite_corner_imbalance.append(
            float(2.0 * abs(corner_lengths[a] - corner_lengths[b]) / denom)
        )

    x_axis = _rotate_points(np.array([[1.0, 0.0]]), orientation)[0]
    y_axis = _rotate_points(np.array([[0.0, 1.0]]), orientation)[0]
    diagonals = np.array(
        [
            (x_axis + y_axis) / math.sqrt(2.0),
            (x_axis - y_axis) / math.sqrt(2.0),
        ]
    )

    return {
        "schema_version": ASSCHER_OUTLINE_SCHEMA,
        "coordinate_space": "source_image_xy_pixels",
        "interpretation": "2-D silhouette scaffold; not physical facet geometry",
        "silhouette_centroid_xy": silhouette_centroid.tolist(),
        "centre_xy": centre_xy.tolist(),
        "vertices_xy": vertices_xy.tolist(),
        "vertices_canonical_xy": vertices_q.tolist(),
        "cardinal_axes_xy": [x_axis.tolist(), y_axis.tolist()],
        "diagonals_xy": diagonals.tolist(),
        "orientation_deg_mod_90": float(orientation),
        "orientation_period_deg": 90,
        "quarter_turn_ambiguous": True,
        "orientation_boundary_support": float(orientation_support),
        "width_px": width,
        "height_px": height,
        "aspect_ratio": float(width / max(height, 1e-12)),
        "effective_diameter_px": float(effective_diameter),
        "side_lines": side_records,
        "parallelism_error_deg": parallelism,
        "corner_side_lengths_px": corner_lengths.tolist(),
        "opposite_corner_imbalance": opposite_corner_imbalance,
        "median_boundary_residual_px": float(np.median(nearest)),
        "q90_boundary_residual_px": float(np.quantile(nearest, 0.9)),
        "normalized_q90_boundary_residual": float(
            np.quantile(nearest, 0.9) / max(effective_diameter, 1e-12)
        ),
    }
