"""Image-only table-cap and terminal pavilion-contour hypotheses for #91.

The existing joint crown/pavilion changepoint model covers the long outline.
This *separate* endpoint experiment handles two regions its fixed ROI omits:
the tiny top silhouette cap, and the faint terminal pavilion beside the
photographic platform. Missing/shadow-contaminated endpoints FAIL CLOSED.
No physical facet identities or Sergey angles are assigned.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_auto_exterior as exterior
from . import asscher_profile_auto_changepoints as joint

SCHEMA = "diamond360-asscher-profile-endpoints/1"
POLICY = {
    "upper_source_column_fraction": [0.44, 0.56],
    "upper_search_rows_px": [40, 85],
    "upper_rgb_thresholds": [7.0, 9.0, 12.0],
    "upper_contact_pixels_of_seven": 5,
    "upper_max_threshold_spread_px": 2,
    "upper_flat_cap_height_tolerance_px": 1,
    "upper_min_flat_run_width_px": 5,
    "lower_seed_min_supported_points": 8,
    "lower_start_row_px": 277,
    "lower_end_row_exclusive_px": 292,
    "lower_max_inward_step_px": 7,
    "lower_max_outward_step_px": 1,
    "lower_foreground_cross_separation_min_rgb": 15.0,
    "lower_outside_distance_max_rgb": 20.0,
    "lower_max_consecutive_missing_rows": 2,
    "terminal_joint_min_span_y_px": 10,
    "terminal_joint_min_slope_change_dx_dy": 0.38,
    "terminal_joint_min_residual_improvement_px2": 200.0,
    "terminal_joint_penalty_sensitivity_px2": [40.0, 100.0, 250.0],
    "terminal_break_search_near_end_rows_px": 24,
    "top_edge_identity": "outside_cap_candidate_not_verified_polished_table",
    "terminal_edge_identity": "outside_projection_candidate_not_verified_pavilion_facet",
    "do_not_fill_missing_side_from_symmetry": True,
    "no_internal_virtual_facets_or_expert_angles": True,
}


def _signals(rgb):
    smooth = ndi.gaussian_filter(np.asarray(rgb, float), (1.0, 1.0, 0.0))
    h, w = smooth.shape[:2]
    reference = np.median(np.concatenate(
        [smooth[:, 4:26], smooth[:, w - 26:w - 4]], axis=1), axis=1)
    distance = np.linalg.norm(smooth - reference[:, None, :], axis=2)
    return distance


def _top_cap(distance):
    h, w = distance.shape
    x0 = int(round(w * POLICY["upper_source_column_fraction"][0]))
    x1 = int(round(w * POLICY["upper_source_column_fraction"][1]))
    start, end = POLICY["upper_search_rows_px"]
    source = []
    for x in range(x0, x1 + 1):
        origins = []
        for threshold in POLICY["upper_rgb_thresholds"]:
            mask = distance[start:end, x] >= threshold
            count = sum(mask[i:len(mask) - 6 + i] for i in range(7))
            valid = np.flatnonzero(count >= POLICY["upper_contact_pixels_of_seven"])
            if len(valid):
                origins.append(int(start + valid[0]))
        if (len(origins) == len(POLICY["upper_rgb_thresholds"])
                and max(origins) - min(origins) <= POLICY["upper_max_threshold_spread_px"]):
            source.append([x, int(round(np.median(origins)))])
    if not source:
        return {"status": "unavailable", "reason": "no_stable_top_background_contact", "source_xy_px": []}
    min_y = min(y for _, y in source)
    plateau = [p for p in source if p[1] <= min_y + POLICY["upper_flat_cap_height_tolerance_px"]]
    runs = []
    for pt in plateau:
        if not runs or pt[0] > runs[-1][-1][0] + 1:
            runs.append([pt])
        else:
            runs[-1].append(pt)
    valid = [run for run in runs if len(run) >= POLICY["upper_min_flat_run_width_px"]]
    if not valid:
        return {"status": "unavailable", "reason": "top_is_not_a_supported_flat_cap",
                "source_xy_px": plateau}
    central = min(valid, key=lambda run: abs((run[0][0]+run[-1][0])/2-(w-1)/2))
    return {
        "status": "candidate_only",
        "kind": "short_horizontal_top_silhouette_cap_not_verified_table",
        "source_xy_px": central,
        "left_endpoint_xy_px": central[0],
        "right_endpoint_xy_px": central[-1],
        "observed_width_px": central[-1][0] - central[0][0] + 1,
        "top_source_y_px": min_y,
        "physical_table_identity": "not_established",
        "reason": "first_sustained_source_background_contact_from_top",
    }


def _source_supported(record, side):
    return {
        int(p["xy_px"][1]): int(p["xy_px"][0])
        for p in record["paths"][side + "_pavilion"]["points"]
        if p["xy_px"] is not None and p["support"] == "edge_supported_candidate"
    }


def _lower_trace(distance, record, side):
    h, w = distance.shape
    known = _source_supported(record, side)
    seed_ys = sorted(y for y in known if y < POLICY["lower_start_row_px"])[-10:]
    if len(seed_ys) < POLICY["lower_seed_min_supported_points"]:
        return {"status": "unavailable", "reason": "missing_supported_lower_pavilion_seed", "points": []}
    seed_y = seed_ys[-1]
    seed_x = float(known[seed_y])
    velocity = float(np.polyfit(seed_ys, [known[y] for y in seed_ys], 1)[0])
    sign = 1 if side == "left" else -1
    if velocity * sign < 0:
        return {"status": "unavailable", "reason": "last_supported_pavilion_is_not_inward", "points": []}
    velocity = float(np.clip(velocity, -3.5, 3.5))
    prev, misses = seed_x, 0
    points = []
    for y in range(seed_y + 1, min(h, POLICY["lower_end_row_exclusive_px"])):
        options = []
        lo = int(round(prev - (POLICY["lower_max_outward_step_px"] if sign > 0 else POLICY["lower_max_inward_step_px"])))
        hi = int(round(prev + (POLICY["lower_max_inward_step_px"] if sign > 0 else POLICY["lower_max_outward_step_px"])))
        for x in range(lo, hi + 1):
            if not 12 <= x < w - 12:
                continue
            dv = sign * (x - prev)
            if not -POLICY["lower_max_outward_step_px"] <= dv <= POLICY["lower_max_inward_step_px"]:
                continue
            inside, outside = x + sign * 5, x - sign * 5
            cross = float(distance[y, inside] - distance[y, outside])
            short_cross = float(distance[y, x + sign * 2] - distance[y, x - sign * 2])
            outside_rgb = float(distance[y, outside])
            # Geometry only limits search to the neighboring EXTERIOR edge;
            # no bright inner feature can be jumped to across the stone.
            score = (0.45*cross + 0.55*short_cross
                     - 0.6*max(outside_rgb - 13, 0)
                     - 0.3*((x-prev)-velocity)**2)
            options.append((score, x, cross, outside_rgb))
        if not options:
            break
        score, x, cross, outside_rgb = max(options)
        accepted = (
            cross >= POLICY["lower_foreground_cross_separation_min_rgb"]
            and outside_rgb <= POLICY["lower_outside_distance_max_rgb"]
        )
        points.append({
            "xy_px": [int(x), int(y)],
            "status": "candidate_only" if accepted else "weak_or_shadow_contaminated",
            "outside_background_distance_rgb": round(outside_rgb, 3),
            "inside_outside_separation_rgb": round(cross, 3),
            "reason": "local_exterior_continuation" if accepted else "outside_background_unreliable",
        })
        if accepted:
            velocity = float(np.clip(0.5*velocity + 0.5*(x-prev), -3.5, 3.5))
            prev = x
            misses = 0
        else:
            misses += 1
            if misses > POLICY["lower_max_consecutive_missing_rows"]:
                break
    accepted = [row for row in points if row["status"] == "candidate_only"]
    return {
        "status": "review" if len(accepted) >= POLICY["terminal_joint_min_span_y_px"] else "unavailable",
        "provenance": "automatic_local_exterior_continuation_not_verified",
        "source_seed_xy_px": [int(seed_x), int(seed_y)],
        "points": points,
        "supported_extension_count": len(accepted),
        "ending_at_shadow": True,
    }


def _terminal_bend(record, extension, side):
    base = _source_supported(record, side)
    augmented = dict(base)
    for p in extension["points"]:
        if p["status"] == "candidate_only":
            augmented[p["xy_px"][1]] = p["xy_px"][0]
    pts = sorted((y, x) for y, x in augmented.items() if y >= 225)
    if len(pts) < 30 or extension["status"] != "review":
        return {"status": "unavailable", "reason": "insufficient_independent_terminal_contour_support"}
    y, x = np.array(pts, dtype=float).T
    design = np.stack([np.ones(len(y)), y], axis=1)
    linear = np.linalg.lstsq(design, x, rcond=None)[0]
    baseline = float(np.sum((design @ linear-x)**2))
    proposals = []
    for penalty in POLICY["terminal_joint_penalty_sensitivity_px2"]:
        best = None
        for knot in range(int(y[0])+POLICY["terminal_joint_min_span_y_px"],
                          int(y[-1])-POLICY["terminal_joint_min_span_y_px"]+1):
            if knot < extension["source_seed_xy_px"][1]-POLICY["terminal_break_search_near_end_rows_px"]:
                continue
            matrix = np.stack([np.ones(len(y)), y, np.maximum(y-knot, 0)], axis=1)
            coeff = np.linalg.lstsq(matrix, x, rcond=None)[0]
            slope_diff = abs(coeff[2])
            if slope_diff < POLICY["terminal_joint_min_slope_change_dx_dy"]:
                continue
            squared = float(np.sum((matrix @ coeff-x)**2))
            if best is None or squared < best["squared"]:
                best = {"y": int(knot), "squared": squared, "coeff": coeff}
        if best and baseline - best["squared"] > max(
            POLICY["terminal_joint_min_residual_improvement_px2"], penalty
        ):
            proposals.append(best)
    if not proposals:
        return {"status": "unavailable",
                "reason": "no_supported_new_terminal_slope_change_beyond_current_outline_fit"}
    knots = [v["y"] for v in proposals]
    if max(knots)-min(knots)>4 or len(proposals)!=len(POLICY["terminal_joint_penalty_sensitivity_px2"]):
        return {"status": "ambiguous",
                "reason": "terminal_breakpoint_changes_with_penalty",
                "breakpoint_y_candidates_px": knots}
    y0 = int(round(np.median(knots)))
    x0 = float(np.interp(y0, y, x))
    return {
        "status": "candidate_only",
        "xy_px": [round(x0, 2), y0],
        "breakpoint_y_candidates_px": knots,
        "reason": "image_only_terminal_slope_change_cross_penalty_support",
        "physical_pavilion_facet_identity": "not_established",
    }


def analyse(rgb, contour, joint_report):
    if contour.get("schema_version") != exterior.SCHEMA or (
        contour.get("policy_sha256") != feasibility.canonical_sha256(exterior.POLICY)
    ):
        raise ValueError("endpoint tool requires frozen background-first auto contour v2")
    if contour.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("wrong source hash")
    if joint_report.get("schema_version") != joint.SCHEMA or (
        joint_report.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
    ):
        raise ValueError("incorrect source or joint changepoint report")
    if contour.get("comparison_targets_loaded") is not False or joint_report.get("comparison_targets_loaded") is not False:
        raise ValueError("Sergey angle targets are forbidden")
    rgb = np.asarray(rgb)
    if rgb.shape[:2] != (319, 410):
        raise ValueError("only full original 410x319 source is supported")
    dist = _signals(rgb)
    top = _top_cap(dist)
    lower = {side: _lower_trace(dist, contour, side) for side in ("left", "right")}
    bends = {side: _terminal_bend(contour, lower[side], side) for side in ("left", "right")}
    return {
        "schema_version": SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "top_cap_candidate": top,
        "terminal_contours": lower,
        "last_pavilion_changepoint_candidates": bends,
        "comparison_targets_loaded": False,
        "physical_facet_angle_status": "all_unavailable",
        "interpretation": "Original-photo boundary candidates only; the outer top cap need not be the verified polished table, and bottom shadows may hide pavilion steps.",
    }


def render_overlay(base_image, result):
    image = base_image.copy()
    draw = ImageDraw.Draw(image)
    top = result["top_cap_candidate"]
    if top["status"] == "candidate_only":
        pts = [(x*3, y*3) for x,y in top["source_xy_px"]]
        draw.line(pts, fill=(0, 240, 226), width=5)
        for p in (top["left_endpoint_xy_px"], top["right_endpoint_xy_px"]):
            x, y = p
            draw.ellipse((3*x-8,3*y-8,3*x+8,3*y+8),
                         fill=(252,220,0), outline=(0,0,0),width=2)
    for side, row in result["terminal_contours"].items():
        for p in row["points"]:
            x,y = p["xy_px"]
            color = (28,225,115) if p["status"]=="candidate_only" else (248,145,34)
            draw.ellipse((3*x-3,3*y-3,3*x+3,3*y+3),fill=color)
    for side, bend in result["last_pavilion_changepoint_candidates"].items():
        if bend["status"]=="candidate_only":
            x,y = bend["xy_px"]
            draw.ellipse((3*x-9,3*y-9,3*x+9,3*y+9),
                         fill=(255,210,0),outline=(32,37,41),width=3)
    return image


def write_report(image_path, auto_json, joint_json, output):
    path = Path(image_path)
    if feasibility._hash_file(path) != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("source photo SHA mismatch")
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"))
    contour = json.loads(Path(auto_json).read_text(encoding="utf-8"))
    primary = json.loads(Path(joint_json).read_text(encoding="utf-8"))
    result = analyse(rgb, contour, primary)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/"endpoint-candidates.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    render_overlay(joint.render_overlay(path, primary), result).save(output/"endpoint-review-overlay.png")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",required=True,type=Path)
    parser.add_argument("--auto-json",required=True,type=Path)
    parser.add_argument("--joint-json",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    result = write_report(args.image,args.auto_json,args.joint_json,args.output)
    print(json.dumps({
        "top_cap":result["top_cap_candidate"]["status"],
        "last_pavilion_bends":{side:row["status"] for side,row in result["last_pavilion_changepoint_candidates"].items()},
        "physical_angles":"unavailable",
    },sort_keys=True))


if __name__=="__main__":
    main()
