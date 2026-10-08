"""Actual upper-pavilion source-contour fitting, with separately gated symmetry.

Only the UPPER pointed source-image contour (physical pavilion region) enters
the fit. Lower shadow-affected rows are CROWN and excluded completely. No facet IDs, expert
photo-angle targets, or internal virtual-facet gradients enter this module.
A mirrored outline is a hypothetical/model-inferred geometry, NEVER a
right-side observation and never an unqualified physical facet angle.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_auto_exterior as exterior
from . import asscher_profile_auto_changepoints as joint
from . import asscher_profile_endpoint_candidates as endpoint
from . import asscher_profile_conditional_symmetry as symmetry

SCHEMA = "diamond360-asscher-profile-pavilion-refinement/2"
POLICY = {
    "roi": "pointed_upper_pavilion_above_joint_widest_width_band",
    "source_orientation": "pointed_upper_pavilion_broad_lower_crown",
    "main_source_weight": 1.0,
    "inferred_top_point_weight": 0.0,
    "point_like_tip_is_candidate_only": True,
    "minimum_points_per_straight_stretch": 10,
    "minimum_y_span_per_straight_stretch_px": 9.0,
    "maximum_apparent_stretches_per_side": 3,
    "candidate_break_step_y_px": 2,
    "minimum_change_in_dx_per_dy": 0.20,
    "segment_complexity_penalties_px2": [40.0, 80.0, 140.0, 220.0],
    "default_penalty_px2": 80.0,
    "changepoint_agreement_tolerance_y_px": 5.0,
    "maximum_visual_connected_gap_y_px": 3,
    "mirror_only_if_external_pose_review_and_symmetric_stone_assumption": True,
    "mirror_is_model_inferred_never_observed": True,
    "do_not_modify_independent_contours": True,
    "do_not_assign_physical_pavilion_facet_angles": True,
    "no_internal_optical_feature_or_expert_target_access": True,
}


def _points(contour, side, boundary_start_y):
    """Only UPPER source-supported physical-pavilion envelope; no lower crown."""
    raw = {}
    for row in contour["paths"][side + "_pavilion"]["points"]:
        xy = row.get("xy_px")
        if (xy and row["support"] == "edge_supported_candidate"
                and xy[1] < boundary_start_y):
            raw[int(xy[1])] = {
                "xy_px": [int(xy[0]), int(xy[1])],
                "weight": POLICY["main_source_weight"],
                "provenance": "automated_background_first_exterior_source",
            }
    return [raw[k] for k in sorted(raw)]


def _fit(points, penalty, max_stretches=3, mirrored_axis=None):
    """Weighted continuous x(y) hinge fit, predeclared 1–3 segment selection.

    If mirrored_axis is given, data rows include a 'side' label; x is
    transformed to *radial* distance from that axis and pooled, but each
    source side retains its distinct original observation and residual.
    """
    if len(points) < POLICY["minimum_points_per_straight_stretch"]:
        return None
    ys = np.array([float(p["xy_px"][1]) for p in points])
    xs = np.array([float(p["xy_px"][0]) for p in points])
    weights = np.array([float(p["weight"]) for p in points])
    if mirrored_axis is not None:
        xs = np.array([
            mirrored_axis - x if p["side"] == "left" else x - mirrored_axis
            for p, x in zip(points, xs)
        ])
    order = np.argsort(ys, kind="stable")
    ys, xs, weights = ys[order], xs[order], weights[order]
    bounds = [float(ys[0]), float(ys[-1])]
    min_span = POLICY["minimum_y_span_per_straight_stretch_px"]
    step = POLICY["candidate_break_step_y_px"]
    knots = np.arange(int(ys[0] + min_span), int(ys[-1] - min_span) + 1, step)
    candidates = []
    for count in range(1, max_stretches + 1):
        best = None
        for breaks in (itertools.combinations(knots, count - 1)
                       if count > 1 else [()]):
            boundaries = bounds[:1] + list(breaks) + bounds[1:]
            if min(np.diff(boundaries)) < min_span:
                continue
            if any(
                np.sum((ys >= left) & (ys <= right)) <
                POLICY["minimum_points_per_straight_stretch"]
                for left, right in zip(boundaries[:-1], boundaries[1:])
            ):
                continue
            design = np.column_stack(
                [np.ones(len(ys)), ys] +
                [np.maximum(ys - knot, 0) for knot in breaks]
            )
            basis = np.sqrt(weights)
            beta = np.linalg.lstsq(design * basis[:, None], xs * basis, rcond=None)[0]
            slopes = np.cumsum(beta[1:])
            if len(slopes) > 1 and np.min(np.abs(np.diff(slopes))) < POLICY["minimum_change_in_dx_per_dy"]:
                continue
            residual = float(np.sum(weights * (design @ beta - xs) ** 2))
            objective = residual + penalty * (count - 1)
            if best is None or objective < best["objective_px2"]:
                best = {
                    "segment_count": count,
                    "break_y_px": [int(k) for k in breaks],
                    "slope_dx_per_dy": [round(float(v), 5) for v in slopes],
                    "beta": [float(x) for x in beta],
                    "weighted_squared_residual_px2": round(residual, 5),
                    "objective_px2": round(float(objective), 5),
                }
        if best is not None:
            candidates.append(best)
    return min(candidates, key=lambda fit: (fit["objective_px2"], fit["segment_count"])) if candidates else None


def _piecewise_x(fit, y):
    return (fit["beta"][0] + fit["beta"][1] * y +
            sum(k * max(0.0, y - b)
                for k, b in zip(fit["beta"][2:], fit["break_y_px"])))


def _select(points):
    if len(points) < POLICY["minimum_points_per_straight_stretch"]:
        return {"status": "unavailable", "reason": "insufficient_supported_upper_pavilion_points"}
    candidates = {}
    for p in POLICY["segment_complexity_penalties_px2"]:
        model = _fit(points, p)
        if model is not None:
            candidates[str(int(p))] = model
    selected = candidates.get(str(int(POLICY["default_penalty_px2"])))
    if selected is None:
        return {"status": "unavailable", "reason": "no_valid_pavilion_piecewise_fit"}
    ys = sorted({p["xy_px"][1] for p in points})
    cuts = []
    for y in selected["break_y_px"]:
        supported_variants = sum(
            any(abs(v - y) <= POLICY["changepoint_agreement_tolerance_y_px"]
                for v in row["break_y_px"])
            for row in candidates.values()
        )
        cuts.append({
            "xy_px": [round(_piecewise_x(selected, y), 3), y],
            "status": "observed_source_changepoint_candidate_not_facet_junction",
            "penalty_variants_support": supported_variants,
            "penalty_variant_total": len(candidates),
            "stability": "stable_across_penalties" if supported_variants == len(candidates)
                         else "model_dependent",
        })
    gaps = [[a+1, b-1] for a, b in zip(ys, ys[1:]) if b > a+1]
    by_provenance = {}
    for item in points:
        key = item["provenance"]
        by_provenance[key] = by_provenance.get(key, 0) + 1
    return {
        "status": "review",
        "observed_point_count": len(points),
        "supported_y_range_px": [ys[0], ys[-1]],
        "unsupported_y_intervals_px": gaps,
        "support_counts": by_provenance,
        "selected_segment_count": selected["segment_count"],
        "selected_weighted_residual_px2": selected["weighted_squared_residual_px2"],
        "slope_dx_per_dy": selected["slope_dx_per_dy"],
        "breakpoints": cuts,
        "selected_model": selected,
        "penalty_models": {
            penalty: {
                "segments": model["segment_count"],
                "break_y_px": model["break_y_px"],
                "objective_px2": model["objective_px2"],
            }
            for penalty, model in candidates.items()
        },
        "physical_facet_identity": "not_established",
    }


def analyse(contour, joined, ends, pose_review=None):
    if contour.get("policy", {}).get("source_orientation") != POLICY["source_orientation"]:
        raise ValueError("inverted source orientation")
    if (contour.get("schema_version") != exterior.SCHEMA
        or joined.get("schema_version") != joint.SCHEMA
        or ends.get("schema_version") != endpoint.SCHEMA):
        raise ValueError("requires source-pinned exterior, joint and endpoint versions")
    if any(row.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
           for row in (contour, joined, ends)):
        raise ValueError("source SHA mismatch")
    if joined.get("source_orientation") != POLICY["source_orientation"]:
        raise ValueError("joint stage source orientation is inverted")
    if (contour.get("policy_sha256") != feasibility.canonical_sha256(exterior.POLICY)
        or joined.get("policy_sha256") != feasibility.canonical_sha256(joint.POLICY)
        or ends.get("policy_sha256") != feasibility.canonical_sha256(endpoint.POLICY)):
        raise ValueError("source geometry method revision mismatch")
    if any(row.get("comparison_targets_loaded") is not False for row in (contour, joined, ends)):
        raise ValueError("expert angle target data forbidden")
    band = joined.get("widest_band_candidate", {})
    if band.get("status") != "candidate_only":
        return {
            "schema_version": SCHEMA,
            "status": "unavailable",
            "reason": "no_independently_supported_maximum_width_band",
            "physical_facet_angles": "all_unavailable",
            "comparison_targets_loaded": False,
        }
    boundary_y = int(band["y_first_px"])
    separate = {side: _points(contour, side, boundary_y)
                for side in ("left", "right")}
    independent = {side: _select(separate[side]) for side in ("left", "right")}
    # The 2-D paired *upper pavilion* shape is a pose-consistency check, not
    # independent proof of head-on orientation or real facet mirror symmetry.
    pose = symmetry._validate_pose(pose_review)
    proxy = symmetry._outline_symmetry_proxy(contour, joined, ends)
    axis = proxy.get("axis_x_px")
    mirrored_right = [] if axis is None else [
        {
            "xy_px": [round(2 * axis - row["xy_px"][0], 3), row["xy_px"][1]],
            "provenance": "MODEL_ONLY_mirrored_left_pavilion_not_observed_right",
            "status": "counterfactual_only",
        }
        for row in separate["left"]
    ]
    model_allowed = (pose["status"] == "confirmed_conditional"
        and proxy["status"] == "image_only_compatible_not_pose_proof"
        and all(len(separate[side]) >= 15 for side in ("left", "right")))
    common = _select_mirror(
        [dict(item, side=side) for side in ("left","right") for item in separate[side]], axis
    ) if model_allowed else None
    modeled = {
        "status": "conditional_symmetry_model_inferred" if common and common["status"] != "unavailable"
                  else "not_adopted_pose_unconfirmed_or_inconsistent",
        "provenance": "head_on_and_stone_symmetry_model_not_independent_pixels",
        "axis_x_px": axis,
        "mirrored_right_pavilion_preview": mirrored_right,
        "common_model": common,
        "original_side_records_unchanged": True,
    }
    return {
        "schema_version": SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "status": "review",
        "source_orientation": POLICY["source_orientation"],
        "top_pavilion_tip_candidate": ends.get("top_pavilion_tip_candidate"),
        "widest_width_band_candidate": band,
        "independent_pavilion": independent,
        "observed_supported_points": separate,
        "symmetry_diagnostic": proxy,
        "pose_review": pose,
        "conditional_pavilion_model": modeled,
        "comparison_targets_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "interpretation": (
            "Upper pointed half is PAVILION; lower shadowed half is CROWN and "
            "excluded from pavilion fitting. Independently observed upper "
            "left/right source coordinates remain separate. Conditional symmetry "
            "is never an observed right contour. No physical P1/P2/P3 angles."
        ),
    }


def _select_mirror(points, axis):
    # Use a shared radial x(y) curve only when the external pose gate passed.
    variants = {}
    for penalty in POLICY["segment_complexity_penalties_px2"]:
        fit = _fit(points, penalty, mirrored_axis=axis)
        if fit:
            variants[str(int(penalty))] = fit
    chosen = variants.get(str(int(POLICY["default_penalty_px2"])))
    if chosen is None:
        return {"status": "unavailable", "reason": "insufficient_paired_pavilion_support"}
    return {
        "status": "conditional_model_inferred_not_observed",
        "selected_model": chosen,
        "model_variants": {
            p: {"segments": v["segment_count"], "break_y_px": v["break_y_px"]}
            for p, v in variants.items()
        },
        "right_side_observations_replaced": False,
        "physical_facet_angles": "unavailable",
    }


def _draw_line_dashed(draw, xy, fill, width=3):
    # Dashed means conditional mirror preview, *never* a detected edge.
    for a, b in zip(xy[::2], xy[1::2]):
        draw.line((a, b), fill=fill, width=width)


def render_comparison(photo, result):
    """Mobile-friendly vertically stacked pointed PAVILION-only comparison."""
    base = photo.convert("RGB")
    mag = 3
    crop = (20, 40, 390, 225)
    panel_w, panel_h = (crop[2]-crop[0])*mag, (crop[3]-crop[1])*mag
    head, foot, gutter = 42, 47, 22
    image = Image.new("RGB",(panel_w,2*(head+panel_h+foot+gutter)),(249,250,252))
    draw = ImageDraw.Draw(image)
    colors={"left":(20,205,75),"right":(25,128,240)}
    for p in (0,1):
        yoffset=p*(head+panel_h+foot+gutter)
        image.paste(base.crop(crop).resize((panel_w,panel_h)),(0,yoffset+head))
        draw.text((12,yoffset+11),(
            "UPPER PAVILION: independently observed outer geometry" if p==0
            else "UPPER PAVILION: purple mirror is MODEL ONLY (not observed)"
        ),fill=(30,39,52))
        def pos(x,y):
            return (round((x-crop[0])*mag), round((y-crop[1])*mag+yoffset+head))
        band=result["widest_width_band_candidate"]
        for y in (band["y_first_px"],band["y_last_px"]):
            draw.line((*pos(crop[0],y),*pos(crop[2],y)),
                      fill=(234,153,31),width=2)
        tip=result.get("top_pavilion_tip_candidate") or {}
        if tip.get("status")=="candidate_only":
            x,y=tip["projected_pavilion_tip_xy_px"]
            cx,cy=pos(x,y)
            draw.ellipse((cx-8,cy-8,cx+8,cy+8),
                         fill=(5,235,223),outline=(10,30,42),width=2)
        for side in ("left","right"):
            source=result["observed_supported_points"][side]
            prev=None
            for item in source:
                x,y=item["xy_px"];xy=pos(x,y)
                if prev and y-prev[1]<=POLICY["maximum_visual_connected_gap_y_px"]:
                    draw.line((*prev[0],*xy),fill=colors[side],width=3)
                prev=(xy,y)
            fit=result["independent_pavilion"][side]
            if fit["status"]!="review":
                continue
            line=fit["selected_model"]
            ys=range(fit["supported_y_range_px"][0],fit["supported_y_range_px"][-1]+1)
            poly=[pos(_piecewise_x(line,y),y) for y in ys]
            draw.line(poly,fill=(14,21,33),width=4)
            draw.line(poly,fill=(250,250,247),width=2)
            for ch in fit["breakpoints"]:
                x,y=ch["xy_px"];cx,cy=pos(x,y)
                c=(249,224,17) if ch["stability"]=="stable_across_penalties" else (247,116,21)
                draw.ellipse((cx-8,cy-8,cx+8,cy+8),
                             fill=c,outline=(20,29,40),width=2)
        if p==1:
            pred=result["conditional_pavilion_model"]["mirrored_right_pavilion_preview"]
            for a,b in zip(pred[::3],pred[1::3]):
                draw.line((*pos(*a["xy_px"]),*pos(*b["xy_px"])),
                          fill=(190,57,205),width=4)
        draw.text((12,yoffset+head+panel_h+12),
                  "GREEN/BLUE: independently observed upper outline; WHITE: fitted.",
                  fill=(38,48,62))
        draw.text((12,yoffset+head+panel_h+28),
                  "YELLOW stable bend; ORANGE model-dependent; CYAN culet-region tip.",
                  fill=(38,48,62))
    return image

def write_report(photo, auto_json, joint_json, endpoint_json, output, pose_json=None):
    photo = Path(photo)
    if feasibility._hash_file(photo) != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("must use original archived profile photo")
    contour = json.loads(Path(auto_json).read_text(encoding="utf-8"))
    joined = json.loads(Path(joint_json).read_text(encoding="utf-8"))
    endpoints = json.loads(Path(endpoint_json).read_text(encoding="utf-8"))
    review = json.loads(Path(pose_json).read_text(encoding="utf-8")) if pose_json else None
    result = analyse(contour, joined, endpoints, review)
    with Image.open(photo) as image:
        viz = render_comparison(image, result)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "pavilion-refinement.json").write_text(
        json.dumps(result, sort_keys=True, indent=2)+"\n", encoding="utf-8"
    )
    viz.save(output / "pavilion-observed-vs-symmetry.png")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--auto-json",type=Path,required=True)
    parser.add_argument("--joint-json",type=Path,required=True)
    parser.add_argument("--endpoint-json",type=Path,required=True)
    parser.add_argument("--pose-review",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=write_report(args.image,args.auto_json,args.joint_json,args.endpoint_json,
                        args.output,args.pose_review)
    print(json.dumps({
        "status":result["status"],
        "independent_pavilion": {
            side: {"segment_count":v.get("selected_segment_count"),
                   "breaks":[p["xy_px"] for p in v.get("breakpoints",[])]}
            for side,v in result["independent_pavilion"].items()
        },
        "symmetry":result["conditional_pavilion_model"]["status"],
        "physical_facet_angles":result["physical_facet_angles"],
    },sort_keys=True))


if __name__=="__main__":
    main()
