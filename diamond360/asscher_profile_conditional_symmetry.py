"""Conditional, explicitly model-inferred left/right symmetry for #91 profile.

A head-on view does NOT follow from a symmetric-looking outline alone. An
externally reviewed pose AND an explicit stone-mirror-symmetry assumption are
required to enable modeled symmetry. Without them, produce only a counter-
factual visual preview. Never overwrite observed silhouette evidence or
assert physical P1/P2/P3 angles.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_auto_exterior as auto
from . import asscher_profile_auto_changepoints as joint
from . import asscher_profile_endpoint_candidates as endpoint

SCHEMA = "diamond360-asscher-conditional-profile-symmetry/2"
POSE_SCHEMA = "diamond360-asscher-pose-review/1"
POLICY = {
    "source": "independent_left_and_right_outer_silhouette_image_only",
    "symmetry_axis": "midpoint_of_left_and_right_width_band_edge_midpoints",
    "pose_proxy_is_not_pose_proof": True,
    "max_pavilion_median_mirror_axis_offset_px": 7.0,
    "max_pavilion_p90_mirror_axis_offset_px": 14.0,
    "minimum_paired_supported_pavilion_rows": 30,
    "max_top_apex_offset_from_axis_px": 12.0,
    "mirror_scope": "only_missing_or_unavailable_right_lower_crown_terminal_bend",
    "do_not_overwrite_observed_right_breaks": True,
    "pose_confirmation": "explicit_independent_human_or_calibrated_review_required",
    "stone_mirror_symmetry_assumption": "must_be_declared_separately_from_pose",
    "uncertainty": "mirror_prediction_conditional_not_pixel_confidence_or_physical_angle",
    "target_angle_data": "not_permitted",
    "source_orientation": "pointed_upper_pavilion_broad_lower_crown",
}


def pose_template():
    return {
        "schema_version": POSE_SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "status": "unreviewed",
        "head_on_pose_confirmed": False,
        "stone_mirror_symmetry_assumed": False,
        "review_basis": "",
        "reviewed_by": "",
        "target_angles_used": False,
    }


def _validate_pose(review):
    if review is None:
        return {"status": "not_confirmed", "reason": "no_independent_pose_review"}
    if set(review) != set(pose_template()):
        raise ValueError("pose review must preserve exact schema; no target or extra fields")
    if (review.get("schema_version") != POSE_SCHEMA
        or review.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
        or review.get("target_angles_used") is not False):
        raise ValueError("pose review source mismatch or expert-target contamination")
    if review["status"] == "unreviewed":
        if review != pose_template():
            raise ValueError("unreviewed pose may not assert assumptions")
        return {"status": "not_confirmed", "reason": "head_on_view_not_verified"}
    if review["status"] not in {"reviewed_head_on", "reviewed_not_head_on"}:
        raise ValueError("invalid pose review state")
    if not isinstance(review["review_basis"], str) or len(review["review_basis"].strip()) < 35:
        raise ValueError("pose review requires independent visual/calibrated rationale")
    if not isinstance(review["reviewed_by"], str) or not review["reviewed_by"].strip():
        raise ValueError("pose review requires provenance")
    if review["status"] == "reviewed_not_head_on" or not review["head_on_pose_confirmed"]:
        return {"status": "not_confirmed", "reason": "review_does_not_confirm_head_on"}
    if review["stone_mirror_symmetry_assumed"] is not True:
        return {"status": "not_confirmed", "reason": "stone_mirror_symmetry_not_assumed"}
    return {"status": "confirmed_conditional", "reason": "explicit_pose_review_plus_symmetry_assumption"}


def _supported(record, side, phase):
    return {
        p["xy_px"][1]: p["xy_px"][0]
        for p in record["paths"][f"{side}_{phase}"]["points"]
        if p["support"] == "edge_supported_candidate" and p["xy_px"] is not None
    }


def _outline_symmetry_proxy(contour, report, endpoints):
    band = report.get("widest_band_candidate", {})
    if band.get("status") != "candidate_only":
        return {"status": "unavailable", "reason": "shared_external_width_band_missing"}
    required = ("left_edge_x_range_px", "right_edge_x_range_px")
    if not all(isinstance(band.get(k), list) and len(band[k]) == 2 for k in required):
        return {"status": "unavailable", "reason": "missing_external_width_support"}
    left = float(np.mean(band["left_edge_x_range_px"]))
    right = float(np.mean(band["right_edge_x_range_px"]))
    axis = (left + right) / 2
    lrows = _supported(contour, "left", "pavilion")
    rrows = _supported(contour, "right", "pavilion")
    shared = sorted(set(lrows) & set(rrows))
    if len(shared) < POLICY["minimum_paired_supported_pavilion_rows"]:
        return {
            "status": "unavailable",
            "reason": "insufficient_independently_supported_pavilion_pairs",
            "paired_rows": len(shared),
            "axis_x_px": round(axis, 3),
        }
    offsets = np.abs(
        (np.array([lrows[y] for y in shared]) +
         np.array([rrows[y] for y in shared])) / 2.0 - axis
    )
    top = endpoints.get("top_pavilion_tip_candidate", {})
    apex_xy = top.get("projected_pavilion_tip_xy_px") if top.get("status") == "candidate_only" else None
    apex_offset = abs(float(apex_xy[0]) - axis) if apex_xy is not None else None
    median = float(np.median(offsets))
    p90 = float(np.percentile(offsets, 90))
    plausible = (
        median <= POLICY["max_pavilion_median_mirror_axis_offset_px"]
        and p90 <= POLICY["max_pavilion_p90_mirror_axis_offset_px"]
        and (apex_offset is None or
             apex_offset <= POLICY["max_top_apex_offset_from_axis_px"])
    )
    return {
        "status": "image_only_compatible_not_pose_proof" if plausible else "image_only_inconsistent",
        "axis_x_px": round(axis, 3),
        "paired_pavilion_rows": len(shared),
        "median_axis_offset_px": round(median, 3),
        "p90_axis_offset_px": round(p90, 3),
        "apex_axis_offset_px": None if apex_offset is None else round(apex_offset, 3),
        "reason": "2d_outline_symmetry_neither_proves_head_on_pose_nor_stone_symmetry",
    }


def analyse(contour, report, endpoints, pose_review=None):
    if contour.get("policy", {}).get("source_orientation") != POLICY["source_orientation"]:
        raise ValueError("source orientation mismatch")
    if (contour.get("schema_version") != auto.SCHEMA
        or report.get("schema_version") != joint.SCHEMA
        or endpoints.get("schema_version") != endpoint.SCHEMA):
        raise ValueError("requires matching pinned exterior/joint/endpoint schemas")
    if any(row.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
           for row in (contour, report, endpoints)):
        raise ValueError("symmetry inputs must use the archived original source")
    if (contour.get("policy_sha256") != feasibility.canonical_sha256(auto.POLICY)
        or report.get("policy_sha256") != feasibility.canonical_sha256(joint.POLICY)
        or endpoints.get("policy_sha256") != feasibility.canonical_sha256(endpoint.POLICY)):
        raise ValueError("symmetry requires unchanged source-only method revisions")
    if any(row.get("comparison_targets_loaded") is not False
           for row in (contour, report, endpoints)):
        raise ValueError("expert-angle targets cannot enter symmetry assistance")
    pose = _validate_pose(pose_review)
    proxy = _outline_symmetry_proxy(contour, report, endpoints)
    left = endpoints.get("last_crown_changepoint_candidates", {}).get("left", {})
    right = endpoints.get("last_crown_changepoint_candidates", {}).get("right", {})
    mirror = {
        "status": "unavailable",
        "reason": "requires_observed_left_terminal_and_shared_width_axis",
        "xy_px": None,
        "provenance": "no_right_physical_measurement",
        "semantic_facet_id": None,
        "physical_angle_deg": None,
    }
    if left.get("status") == "candidate_only" and "axis_x_px" in proxy:
        x, y = left["xy_px"]
        projected = [round(2 * proxy["axis_x_px"] - x, 2), float(y)]
        mirror = {
            "status": "counterfactual_mirror_preview_not_applied",
            "reason": "head_on_pose_and_stone_symmetry_not_independently_established",
            "xy_px": projected,
            "source_side": "left",
            "destination_side": "right",
            "original_left_xy_px": [float(x), float(y)],
            "axis_x_px": proxy["axis_x_px"],
            "provenance": "MODEL_INFERRED_from_left_NOT_observed_right",
            "right_independent_observation": right.get("status", "unavailable"),
            "semantic_facet_id": None,
            "physical_angle_deg": None,
        }
        if right.get("status") == "candidate_only":
            mirror["reason"] = "right_already_has_independent_candidate_keep_separate"
        elif pose["status"] == "confirmed_conditional" and proxy["status"] == "image_only_compatible_not_pose_proof":
            mirror["status"] = "conditional_symmetry_model_inferred"
            mirror["reason"] = "separately_confirmed_head_on_and_explicit_stone_symmetry_assumption"
        elif pose["status"] == "confirmed_conditional":
            mirror["reason"] = "2d_outline_or_apex_consistency_gate_not_met"
    return {
        "schema_version": SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "top_shape_interpretation": "upper_pointed_pavilion_tip_culet_region_not_verified_culet_facet",
        "source_orientation": POLICY["source_orientation"],
        "pose_review": pose,
        "image_only_symmetry_diagnostic": proxy,
        "independent_crown_terminal_candidates": {"left": left, "right": right},
        "right_crown_terminal_symmetry_hypothesis": mirror,
        "status": (
            "conditional_model_inference" if mirror["status"] == "conditional_symmetry_model_inferred"
            else "preview_only_not_adopted"
        ),
        "comparison_targets_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "interpretation": (
            "Mirroring is a geometrical conditional model, not a right-side observation. "
            "The pointed upper pavilion outline cannot itself verify camera pose or physical mirror symmetry. This mirror predicts the LOWER CROWN, not the pavilion. "
            "Never overwrite the right observed silhouette or create P1/P2/P3 angles."
        ),
    }


def render_overlay(base, result):
    overlay = base.copy()
    d = ImageDraw.Draw(overlay)
    mirror = result["right_crown_terminal_symmetry_hypothesis"]
    proxy = result["image_only_symmetry_diagnostic"]
    axis = proxy.get("axis_x_px")
    if axis is not None:
        x = round(axis * 3)
        for y in range(60, 885, 18):
            d.line((x, y, x, min(y+8, 885)), fill=(50, 160, 205), width=2)
    if mirror["xy_px"] is not None:
        x, y = mirror["xy_px"]
        cx, cy = round(x*3), round(y*3)
        c = (35, 223, 245) if mirror["status"] == "conditional_symmetry_model_inferred" else (190, 90, 240)
        d.ellipse((cx-10,cy-10,cx+10,cy+10), fill=None, outline=c, width=4)
        for delta in (-1,1):
            d.line((cx+delta*13,cy,cx+delta*18,cy),fill=c,width=3)
    return overlay


def write_report(photo, auto_json, joint_json, endpoint_json, output, pose_json=None):
    photo = Path(photo)
    if feasibility._hash_file(photo) != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("source photograph SHA-256 mismatch")
    contour = json.loads(Path(auto_json).read_text(encoding="utf-8"))
    joined = json.loads(Path(joint_json).read_text(encoding="utf-8"))
    endpoints = json.loads(Path(endpoint_json).read_text(encoding="utf-8"))
    review = json.loads(Path(pose_json).read_text(encoding="utf-8")) if pose_json else None
    result = analyse(contour, joined, endpoints, review)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "conditional-symmetry.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "pose-review-template.json").write_text(
        json.dumps(pose_template(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    base = endpoint.render_overlay(joint.render_overlay(photo, joined), endpoints)
    render_overlay(base, result).save(output / "conditional-symmetry-preview.png")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--auto-json", type=Path, required=True)
    parser.add_argument("--joint-json", type=Path, required=True)
    parser.add_argument("--endpoint-json", type=Path, required=True)
    parser.add_argument("--pose-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    r = write_report(args.image, args.auto_json, args.joint_json, args.endpoint_json,
                     args.output, args.pose_review)
    print(json.dumps({
        "status": r["status"],
        "pose": r["pose_review"]["status"],
        "image_only_symmetry_proxy": r["image_only_symmetry_diagnostic"]["status"],
        "right_mirrored": r["right_crown_terminal_symmetry_hypothesis"]["status"],
        "mirror_xy_px": r["right_crown_terminal_symmetry_hypothesis"]["xy_px"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
