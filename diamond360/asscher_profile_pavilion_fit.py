"""Pavilion-first, target-blind silhouette model (issue #91 / draft PR B).

Keeps source-observed left/right pavilion contour points and missing spans
separate from a conditional symmetric *model*. A mirror model is permitted
only with independent head-on pose review + explicit stone symmetry, and
cannot overwrite actual observations or recover physical facet angles.
No internal virtual-facet lines or Sergey values are input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_auto_exterior as exterior
from . import asscher_profile_auto_changepoints as changepoints
from . import asscher_profile_endpoint_candidates as endpoints
from . import asscher_profile_conditional_symmetry as symmetry

SCHEMA = "diamond360-asscher-pavilion-profile-fit/1"
POLICY = {
    "start_after_joint_maximum_width_band": True,
    "max_segments_per_pavilion_side": 3,
    "minimum_observed_rows_per_side": 25,
    "minimum_paired_rows": 25,
    "paired_pavilion_median_midpoint_offset_px_max": 7.0,
    "paired_pavilion_p90_midpoint_offset_px_max": 12.0,
    "model_penalties_px2": [40.0, 60.0, 110.0, 150.0],
    "default_penalty_px2": 60.0,
    "lower_extension_weight": "one_source_row_one_weight_only_if_endpoint_QC_supported",
    "right_model_mirrored_where_unobserved": True,
    "do_not_predict_below_last_left_supported_y": True,
    "do_not_force_3_physical_steps": True,
    "continuous_fit": "hinge_x_of_y_on_all_source_supported_rows",
    "paired_fit": "one_median_half_width_per_y_plus_left_only_supported_terminal",
    "observed_point_provenance": "background_first_photo_edge_or_local_terminal_extension",
    "inferred_point_provenance": "MODEL_ONLY_NOT_PIXEL_OBSERVED",
    "pose_requirement": "independent_head_on_review_plus_explicit_mirror_stone_assumption",
    "no_angle_target_or_inside_optical_inputs": True,
}


def _observed_points(contour, terminal, side, y_start):
    observed = {}
    for point in contour["paths"][side + "_pavilion"]["points"]:
        xy = point.get("xy_px")
        if (xy is not None and point.get("support") == "edge_supported_candidate"
                and xy[1] > y_start):
            observed[int(xy[1])] = {
                "xy_px": [int(xy[0]), int(xy[1])],
                "provenance": "first_outside_background_contact",
                "physical_facet_id": None,
            }
    tail = terminal.get("terminal_contours", {}).get(side, {})
    for point in tail.get("points", []):
        xy = point.get("xy_px")
        if xy is not None and xy[1] > y_start and point.get("status") == "candidate_only":
            observed[int(xy[1])] = {
                "xy_px": [int(xy[0]), int(xy[1])],
                "provenance": "source_supported_terminal_extension_not_verified",
                "physical_facet_id": None,
            }
    return [observed[y] for y in sorted(observed)]


def _selection(point_rows):
    if len(point_rows) < POLICY["minimum_observed_rows_per_side"]:
        return {"status": "unavailable", "reason": "insufficient_pavilion_contour_support"}
    xy = [row["xy_px"] for row in point_rows]
    choices = {}
    for penalty in POLICY["model_penalties_px2"]:
        options = changepoints._piecewise_models(xy, penalty)
        if options:
            chosen = min(options, key=lambda v: (v["score"], v["segments"]))
            choices[str(int(penalty))] = chosen
    selected = choices.get(str(int(POLICY["default_penalty_px2"])))
    if selected is None:
        return {"status": "unavailable", "reason": "no_defensible_continuous_pavilion_profile"}
    variations = [
        {"penalty_px2": int(k), "segments": v["segments"],
         "break_y_px": v["break_y_px"], "objective_px2": v["score"]}
        for k, v in choices.items()
    ]
    breakpoints = []
    for y in selected["break_y_px"]:
        found = sum(any(abs(y - b) <= 7 for b in v["break_y_px"]) for v in choices.values())
        breakpoints.append({
            "source_image_y_px": int(y),
            "status": "image_slope_change_candidate_only",
            "model_variant_support": found,
            "model_variant_total": len(choices),
            "stability": "stable" if found == len(choices) else "model_dependent",
            "physical_facet_junction": "not_established",
        })
    return {
        "status": "review",
        "observed_row_count": len(point_rows),
        "observed_y_first": int(xy[0][1]),
        "observed_y_last": int(xy[-1][1]),
        "selected_segment_count": selected["segments"],
        "selected_breakpoints": breakpoints,
        "image_tangent_dx_per_dy": selected["slope_dx_per_dy"],
        "fit_coefficients_x_of_y": selected["coefficients_x_of_y"],
        "orthogonal_physical_angle_deg": None,
        "squared_pixel_residual": selected["squared_residual_px2"],
        "penalty_sensitivity": variations,
        "source_observed_points": point_rows,
        "physical_facet_correspondence": "not_established",
    }


def _paired_diagnostic(left, right, axis):
    l = {row["xy_px"][1]: row["xy_px"][0] for row in left}
    r = {row["xy_px"][1]: row["xy_px"][0] for row in right}
    common = sorted(set(l) & set(r))
    if len(common) < POLICY["minimum_paired_rows"]:
        return {"status": "insufficient_joint_pavilion_support",
                "paired_rows": len(common)}
    offsets = np.array([(l[y] + r[y])/2.0-axis for y in common])
    median_abs = float(np.median(np.abs(offsets)))
    p90_abs = float(np.percentile(np.abs(offsets), 90))
    compatible = (
        median_abs <= POLICY["paired_pavilion_median_midpoint_offset_px_max"]
        and p90_abs <= POLICY["paired_pavilion_p90_midpoint_offset_px_max"]
    )
    return {
        "status": "compatible_2d_only" if compatible else "inconsistent_2d",
        "paired_rows": len(common),
        "median_absolute_midpoint_offset_px": round(median_abs, 4),
        "p90_absolute_midpoint_offset_px": round(p90_abs, 4),
        "reason": "paired_image_midpoints_cannot_certify_camera_pose_or_physical_symmetry",
        "mean_signed_midpoint_offset_px": round(float(np.mean(offsets)), 4),
    }


def _paired_half_width(left, right, axis):
    l = {row["xy_px"][1]: row["xy_px"][0] for row in left}
    r = {row["xy_px"][1]: row["xy_px"][0] for row in right}
    paired = sorted(set(l) & set(r))
    if len(paired) < POLICY["minimum_paired_rows"]:
        return [], []
    # One source y carries one unit of model weight. On rows with two sides,
    # use their midpoint width; on the terminal where the right edge is lost,
    # use left alone. The implied right edge is explicitly *inferred*.
    sample = []
    inferred = []
    for y in sorted(set(l) | set(r)):
        if y in l and y in r:
            radius = (r[y] - l[y]) / 2.0
            origin = "paired_observed_half_width"
        elif y in l and y > max(paired):
            radius = axis - l[y]
            origin = "left_observed_right_missing"
            inferred.append({"xy_px": [round(float(axis + radius), 3), int(y)],
                             "source_left_xy_px": [float(l[y]), int(y)],
                             "provenance": POLICY["inferred_point_provenance"],
                             "status": "counterfactual_not_applied"})
        else:
            continue
        sample.append({"xy_px": [round(float(radius), 5), int(y)],
                       "radius_definition": origin})
    return sample, inferred


def _symmetry_preview_status(pose, crown_proxy, pavilion_proxy, independent_right):
    if pavilion_proxy.get("status") != "compatible_2d_only":
        return "counterfactual_not_adopted", "pavilion_2d_mismatch_or_missing_pairs"
    if crown_proxy.get("status") != "image_only_compatible_not_pose_proof":
        return "counterfactual_not_adopted", "crown_proxy_is_inconsistent_or_unavailable"
    if pose.get("status") != "confirmed_conditional":
        return "counterfactual_not_adopted", "pose_and_stone_symmetry_not_independently_confirmed"
    if independent_right.get("status") != "unavailable":
        # Do not erase an independently detected last right changepoint.
        return "counterfactual_not_adopted", "independent_right_terminal_not_missing"
    return "conditional_symmetry_model_inferred", "head_on_review_plus_stone_symmetry_declaration"


def analyse(contour, joint_report, terminal, pose_review=None):
    if contour.get("schema_version") != exterior.SCHEMA or (
        contour.get("policy_sha256") != feasibility.canonical_sha256(exterior.POLICY)
    ):
        raise ValueError("expected frozen v2 background-first contour")
    if joint_report.get("schema_version") != changepoints.SCHEMA or (
        joint_report.get("policy_sha256") != feasibility.canonical_sha256(changepoints.POLICY)
    ):
        raise ValueError("expected frozen joint image-only contour")
    if terminal.get("schema_version") != endpoints.SCHEMA or (
        terminal.get("policy_sha256") != feasibility.canonical_sha256(endpoints.POLICY)
    ):
        raise ValueError("expected frozen endpoint evidence")
    if any(row.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
           for row in (contour, joint_report, terminal)):
        raise ValueError("input source provenance does not match original photo")
    if any(row.get("comparison_targets_loaded") is not False
           for row in (contour, joint_report, terminal)):
        raise ValueError("external facet-angle target leakage")
    pose = symmetry._validate_pose(pose_review)
    crown_proxy = symmetry._outline_symmetry_proxy(contour, joint_report, terminal)
    band = joint_report["widest_band_candidate"]
    if band.get("status") != "candidate_only":
        return {"schema_version": SCHEMA, "status": "unavailable",
                "reason": "no_joint_outer_width_band",
                "physical_facet_angles": "all_unavailable",
                "comparison_targets_loaded": False}
    axis = crown_proxy.get("axis_x_px")
    if axis is None:
        return {"schema_version": SCHEMA, "status": "unavailable",
                "reason": "no_independently_supported_axis",
                "physical_facet_angles": "all_unavailable",
                "comparison_targets_loaded": False}
    start = int(band["y_last_px"])
    left = _observed_points(contour, terminal, "left", start)
    right = _observed_points(contour, terminal, "right", start)
    independent = {"left": _selection(left), "right": _selection(right)}
    pavilion_proxy = _paired_diagnostic(left, right, axis)
    samples, missing_right = _paired_half_width(left, right, axis)
    shared = _selection(samples)
    if shared["status"] == "review":
        # Shared half-width is measured inward from the image-axis,
        # not an independent, observed physical surface.
        shared["fit_coordinate"] = "radius_half_width_px"
        shared["status"] = "counterfactual_model_preview"
    terminal_right = terminal["last_pavilion_changepoint_candidates"]["right"]
    status, reason = _symmetry_preview_status(pose, crown_proxy, pavilion_proxy, terminal_right)
    if shared.get("status") != "counterfactual_model_preview":
        status, reason = "unavailable", "shared_profile_not_sufficiently_supported"
    predicted_bends = []
    if shared.get("status") == "counterfactual_model_preview":
        for br in shared["selected_breakpoints"]:
            y = int(br["source_image_y_px"])
            # Model proposal is NOT the local physical facet identity and
            # does not replace the direct independent right analysis.
            predicted_bends.append({
                "y_px": y,
                "stability": br["stability"],
                "status": status,
                "provenance": POLICY["inferred_point_provenance"],
                "physical_facet_junction": "not_established",
            })
    for p in missing_right:
        p["status"] = status
    return {
        "schema_version": SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "widest_outer_profile_band": band,
        "symmetry_axis_x_px": axis,
        "pose_assessment": pose,
        "image_only_crown_alignment": crown_proxy,
        "pavilion_paired_alignment": pavilion_proxy,
        "independent_pavilion_models": independent,
        "observed_terminal_changepoints": terminal["last_pavilion_changepoint_candidates"],
        "shared_symmetry_model": {
            "status": status,
            "reason": reason,
            "coordinate": "radius_inward_from_axis_x",
            "fit": shared,
            "inferred_right_points_only_where_no_right_source_support": missing_right,
            "inferred_shared_break_y_candidates": predicted_bends,
        },
        "shadow_unresolved_region": {
            "status": "unavailable",
            "last_supported_left_y_px": left[-1]["xy_px"][1] if left else None,
            "last_supported_right_y_px": right[-1]["xy_px"][1] if right else None,
            "tip_or_culet_xy_px": None,
            "reason": "background_and_platform_shadow_no_unambiguous_tip_evidence",
        },
        "status": "review" if all(x["status"] == "review" for x in independent.values())
                         else "partial_or_unavailable",
        "comparison_targets_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "interpretation": (
            "Observed external pavilion traces, observed independent slope candidates, "
            "and symmetry-inferred contour points are disjoint evidence categories. "
            "Even conditionally symmetric x(y) is not physical P1/P2/P3 recovery."
        ),
    }


def _draw_observations(draw, model, box, color):
    points = model.get("source_observed_points", [])
    prev = None
    for row in points:
        x, y = row["xy_px"]
        xy = (round((x-box[0])*3), round((y-box[1])*3))
        if prev is not None and y - prev[1] <= 3:
            draw.line((prev[0], xy), fill=color, width=3)
        prev = (xy, y)
    for mark in model.get("selected_breakpoints", []):
        y = mark["source_image_y_px"]
        points_xy = [p["xy_px"] for p in points]
        near = min(points_xy, key=lambda v: abs(v[1]-y)) if points_xy else None
        if near:
            x = round((near[0]-box[0])*3)
            yy = round((near[1]-box[1])*3)
            fill = (255,215,20) if mark["stability"] == "stable" else (255,142,20)
            draw.ellipse((x-8,yy-8,x+8,yy+8),fill=fill,outline=(20,23,26),width=2)


def render_pavilion_panel(photo, report):
    """Enlarged photo-crop with observed vs symmetry-inferred evidence styling."""
    with Image.open(photo) as source:
        rgb = source.convert("RGB")
    # Excludes most crown; retain maximum width band and the shadow margin.
    box = (18, 191, 392, 307)
    image = rgb.crop(box).resize(((box[2]-box[0])*3,(box[3]-box[1])*3))
    d = ImageDraw.Draw(image)
    band = report["widest_outer_profile_band"]
    if band.get("status") == "candidate_only":
        for y in (band["y_first_px"], band["y_last_px"]):
            yy=round((y-box[1])*3)
            d.line((0,yy,image.width,yy),fill=(230,164,30),width=2)
    for side, c in (("left",(0,225,75)),("right",(28,121,240))):
        _draw_observations(d,report["independent_pavilion_models"][side],box,c)
    sym = report["shared_symmetry_model"]
    for row in sym.get("inferred_right_points_only_where_no_right_source_support", []):
        x, y = row["xy_px"]
        xx, yy = round((x-box[0])*3),round((y-box[1])*3)
        c=(34,239,244) if sym["status"]=="conditional_symmetry_model_inferred" else (185,75,230)
        d.ellipse((xx-3,yy-3,xx+3,yy+3),fill=c)
    mirror = report["observed_terminal_changepoints"]["left"]
    if mirror.get("status")=="candidate_only":
        x, y = mirror["xy_px"]
        xx, yy = round((x-box[0])*3),round((y-box[1])*3)
        d.ellipse((xx-10,yy-10,xx+10,yy+10),fill=(255,226,10),outline=(17,17,17),width=3)
        xx=round((2*report["symmetry_axis_x_px"]-x-box[0])*3)
        d.ellipse((xx-10,yy-10,xx+10,yy+10),outline=(190,65,237),width=4)
    cutoff = report["shadow_unresolved_region"].get("last_supported_left_y_px")
    if cutoff is not None and cutoff < box[3]-1:
        y=round((cutoff+1-box[1])*3)
        d.line((0,y,image.width,y),fill=(200,120,40),width=2)
    return image


def write_report(photo, auto_json, joint_json, terminal_json, output, pose_json=None):
    photo=Path(photo)
    if feasibility._hash_file(photo) != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("pavilion fit requires exact source photo SHA-256")
    record=json.loads(Path(auto_json).read_text(encoding="utf-8"))
    widths=json.loads(Path(joint_json).read_text(encoding="utf-8"))
    ends=json.loads(Path(terminal_json).read_text(encoding="utf-8"))
    pose=json.loads(Path(pose_json).read_text(encoding="utf-8")) if pose_json else None
    result=analyse(record,widths,ends,pose)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    (output/"pavilion-fit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if result["status"] in {"review","partial_or_unavailable"}:
        render_pavilion_panel(photo,result).save(output/"pavilion-only-overlay.png")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",required=True,type=Path)
    parser.add_argument("--auto-json",required=True,type=Path)
    parser.add_argument("--joint-json",required=True,type=Path)
    parser.add_argument("--endpoint-json",required=True,type=Path)
    parser.add_argument("--pose-review",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    r=write_report(args.image,args.auto_json,args.joint_json,args.endpoint_json,
                   args.output,args.pose_review)
    print(json.dumps({
        "status":r["status"],
        "independent_segments":{k:v.get("selected_segment_count") for k,v in r["independent_pavilion_models"].items()},
        "shared_symmetry_status":r["shared_symmetry_model"]["status"],
        "shared_break_y_candidates":r["shared_symmetry_model"]["inferred_shared_break_y_candidates"],
        "paired_alignment":r["pavilion_paired_alignment"],
        "tip":r["shadow_unresolved_region"]["tip_or_culet_xy_px"],
    },sort_keys=True))


if __name__=="__main__":
    main()
