"""#91: image-only changepoints in independently traced exterior profile strokes.

This is NOT a physical angle fitter. A three-tier Asscher pavilion provides
an upper bound on plausible *projected contour* stretches, not a requirement
that three facets or bends are visible. All P1/P2/P3/C1 slots remain unavailable.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_profile_feasibility as feasibility

SCHEMA = "diamond360-asscher-exterior-changepoints/1"
TRACE_SCHEMA = "diamond360-asscher-exterior-traces/1"
STROKES = ("left_crown", "right_crown", "left_pavilion", "right_pavilion")
POLICY = {
    "coordinate_system": "original_image_xy_top_left_pixel_centers",
    "source_type": "reviewed_image_only_exterior_contour_trace",
    "max_segments_per_side_region": 3,
    "min_points_per_segment": 6,
    "min_y_span_per_segment_px": 12.0,
    "minimum_trace_points": 8,
    "complexity_penalty_squared_px_per_added_segment": 40.0,
    "fit": "orthogonal_total_least_squares_piecewise_independent_each_side",
    "objective": "sum_squared_orthogonal_residual_plus_per_additional_segment_penalty",
    "angle_measurement": "image_tangent_only_not_physical_facet_inclination",
    "change_point": "midpoint_between_adjacent_source_trace_samples",
    "uncertainty": "fit_residual_and_model_selection_margin_not_calibrated_CI",
    "hidden_physical_facets": "zero_to_three_visible_straight_stretches_allowed",
    "missing_data": "never_interpolate_between_separate_strokes",
    "semantic_policy": "facet_identity_none; no_P1_P2_P3_C1_angles",
    "anti_leakage": "do_not_load_expert_targets_or_internal_gradient_bands",
}


def template():
    return {
        "schema_version": TRACE_SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "coordinate_system": POLICY["coordinate_system"],
        "strokes": {key: {
            "status": "unavailable",
            "provenance": "no_independently_reviewed_exterior_trace",
            "points_xy_px": [],
            "review_notes": "",
        } for key in STROKES},
        "target_values_loaded": False,
    }


def _validate_strokes(payload):
    if payload.get("schema_version") != TRACE_SCHEMA:
        raise ValueError("wrong exterior trace schema")
    if payload.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("trace must refer to original source SHA-256")
    if payload.get("coordinate_system") != POLICY["coordinate_system"]:
        raise ValueError("invalid image coordinate convention")
    if payload.get("target_values_loaded") is not False:
        raise ValueError("expert comparison values forbidden during silhouette fitting")
    strokes = payload.get("strokes")
    if not isinstance(strokes, dict) or set(strokes) != set(STROKES):
        raise ValueError("all four independent exterior stroke slots required")
    width, height = feasibility.ORIGINAL_PROFILE_SIZE
    for name, item in strokes.items():
        points = item.get("points_xy_px")
        if not isinstance(points, list) or len(points) > 180:
            raise ValueError("exterior stroke must be a list of up to 180 points")
        if item.get("status") == "unavailable":
            if points or item.get("provenance") != "no_independently_reviewed_exterior_trace":
                raise ValueError("unavailable stroke cannot contain invented points")
            continue
        if (item.get("status") != "reviewed_image_only"
            or item.get("provenance") != "human_traced_image_only"
            or len(points) < POLICY["minimum_trace_points"]
            or len(str(item.get("review_notes", "")).strip()) < 12):
            raise ValueError("fitted stroke requires source-image-only reviewed trace and notes")
        previous_y = -1.0
        for point in points:
            if (not isinstance(point, list) or len(point) != 2
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in point)
                or not 0 <= point[0] < width or not 0 <= point[1] < height):
                raise ValueError("nonfinite or out-of-image contour point")
            x, y = map(float, point)
            if y <= previous_y:
                raise ValueError("trace points must follow strictly increasing source y")
            previous_y = y
            if name.startswith("left") and x > width * .5 + 10:
                raise ValueError("left contour crosses far into right side")
            if name.startswith("right") and x < width * .5 - 10:
                raise ValueError("right contour crosses far into left side")
    return True


def _tls_fit(points):
    """2-D orthogonal line residual, so nearly vertical spans fit safely."""
    center = np.mean(points, axis=0)
    singular = np.linalg.svd(points - center, full_matrices=False)[2][0]
    v = singular / np.linalg.norm(singular)
    residual = (points - center) @ np.array([-v[1], v[0]])
    squared = float(np.dot(residual, residual))
    # Choose the signed tangent consistently with increasing image y.
    if v[1] < 0 or (abs(v[1]) < 1e-12 and v[0] < 0):
        v = -v
    return squared, float(np.sqrt(np.mean(residual ** 2))), v, center


def fit_stroke(points):
    """Penalized DP: 1/2/3 independently evidenced contour stretches."""
    arr = np.asarray(points, dtype=float)
    n = len(arr)
    if arr.ndim != 2 or arr.shape[1:] != (2,) or n < POLICY["minimum_trace_points"]:
        return {"status": "unavailable", "reason": "insufficient_exterior_trace_points"}
    if not np.isfinite(arr).all() or np.any(np.diff(arr[:, 1]) <= 0):
        return {"status": "unavailable", "reason": "nonmonotonic_or_invalid_trace"}
    m = POLICY["min_points_per_segment"]
    minspan = POLICY["min_y_span_per_segment_px"]
    penalty = POLICY["complexity_penalty_squared_px_per_added_segment"]
    maxseg = POLICY["max_segments_per_side_region"]
    # Fit pieces on [i,j), with no interpolation across missing stroke regions.
    fits = {}
    for i in range(n):
        for j in range(i + m, n + 1):
            if arr[j-1, 1] - arr[i, 1] < minspan:
                continue
            fits[i, j] = _tls_fit(arr[i:j])
    dp = [{(0, 0): (0.0, [])}]
    for k in range(1, maxseg + 1):
        row = {}
        for j in range(k*m, n+1):
            best = None
            for i in range((k-1)*m, j-m+1):
                prev = dp[k-1].get((k-1, i))
                if prev is None or (i, j) not in fits:
                    continue
                cost = prev[0] + fits[i, j][0] + (penalty if k > 1 else 0.0)
                boundaries = prev[1] + [(i, j)]
                if best is None or cost < best[0]:
                    best = (cost, boundaries)
            if best is not None:
                row[k, j] = best
        dp.append(row)
    choices = [(k, dp[k][(k, n)]) for k in range(1, maxseg+1) if (k, n) in dp[k]]
    if not choices:
        return {"status": "unavailable", "reason": "no_supported_contiguous_piecewise_model"}
    choices.sort(key=lambda x: (x[1][0], x[0]))
    k, (cost, boundaries) = choices[0]
    next_score = float(choices[1][1][0]) if len(choices)>1 else None
    rows = []
    for a, b in boundaries:
        residual, rms, v, center = fits[a, b]
        rows.append({
            "first_source_point_index": int(a),
            "last_source_point_index": int(b - 1),
            "source_point_count": int(b - a),
            "start_xy_px": [float(x) for x in arr[a]],
            "end_xy_px": [float(x) for x in arr[b-1]],
            "orthogonal_rms_residual_px": round(rms, 5),
            "orthogonal_sum_squared_residual_px2": round(residual, 5),
            "image_tangent_angle_deg": round(math.degrees(math.atan2(v[1], v[0])), 5),
            "semantic_facet_id": None,
            "status": "candidate_only_not_verified_physical_facet",
        })
    changes = []
    for prev, current in zip(boundaries, boundaries[1:]):
        i = prev[1]
        changes.append({
            "xy_px": [round(float(x), 3) for x in (arr[i-1]+arr[i])/2],
            "between_source_indices": [int(i-1), int(i)],
            "status": "contour_slope_changepoint_candidate_only",
        })
    return {
        "status": "review",
        "reason": "image_contour_segments_not_physical_facet_identity",
        "selected_segment_count": k,
        "selected_internal_changepoint_count": k-1,
        "selected_objective_px2": round(float(cost), 5),
        "runner_up_model_objective_px2": None if next_score is None else round(next_score, 5),
        "model_selection_margin_px2": None if next_score is None else round(next_score-cost, 5),
        "model_comparison_note": "margin_not_probability_or_calibrated_angle_uncertainty",
        "segments": rows,
        "changepoints": changes,
        "physical_facet_correspondence": "not_established",
    }


def analyse_trace_record(payload):
    _validate_strokes(payload)
    return {
        "schema_version": SCHEMA,
        "source_sha256": payload["source_sha256"],
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "contours": {
            name: (fit_stroke(item["points_xy_px"]) if item["status"] == "reviewed_image_only"
                   else {"status": "unavailable", "reason": "no_reviewed_exterior_trace"})
            for name, item in payload["strokes"].items()
        },
        "status": "review" if any(x["status"] == "reviewed_image_only" for x in payload["strokes"].values()) else "unavailable",
        "observation_kind": "projected_exterior_changepoints_only",
        "semantic_measurements": {
            side: {facet: {
                "status": "unavailable", "physical_angle_deg": None,
                "reason": "no_assigned_physical_facet_or_projection_model"
            } for facet in feasibility.SLOTS}
            for side in feasibility.SIDES
        },
        "comparison_targets_loaded": False,
    }


def write_result(image_path, output, traces=None):
    image_path, output = Path(image_path), Path(output)
    with Image.open(image_path) as im:
        image = im.convert("RGB")
    if feasibility._hash_file(image_path) != feasibility.ORIGINAL_PROFILE_SHA256 or image.size != feasibility.ORIGINAL_PROFILE_SIZE:
        raise ValueError("original profile JPEG is required")
    doc = template() if traces is None else json.loads(Path(traces).read_text(encoding="utf-8"))
    result = analyse_trace_record(doc)
    output.mkdir(parents=True, exist_ok=True)
    (output / "exterior-changepoints.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "exterior-trace-template.json").write_text(
        json.dumps(template(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    draw = ImageDraw.Draw(image)
    colors = {
        "left_crown": (30, 190, 70), "right_crown": (20, 130, 225),
        "left_pavilion": (245, 140, 25), "right_pavilion": (200, 55, 165),
    }
    for name, item in doc["strokes"].items():
        if item["status"] != "reviewed_image_only":
            continue
        points = [tuple(x) for x in item["points_xy_px"]]
        draw.line(points, fill=colors[name], width=2)
        for change in result["contours"][name].get("changepoints", []):
            x, y = change["xy_px"]
            draw.ellipse((x-3, y-3, x+3, y+3), fill=(255, 235, 0), outline=(0, 0, 0))
    image.save(output / "exterior-changepoints-overlay.png")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--traces", type=Path, help="Original-image-only independent exterior traces")
    args = parser.parse_args()
    r = write_result(args.image, args.output, args.traces)
    print(json.dumps({
        "status": r["status"],
        "contours": {k: v["status"] for k,v in r["contours"].items()},
        "physical_angles": "all_unavailable",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
