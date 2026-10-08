"""Pavilion-first source-contour fitting, with separately gated symmetry.

Only projected OUTER contours enter the fit. End-of-pavilion extensions have
less weight than independently supported main paths. No facet IDs, expert
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

SCHEMA = "diamond360-asscher-profile-pavilion-refinement/1"
POLICY = {
    "roi": "projected_pavilion_below_joint_widest_width_band",
    "main_source_weight": 1.0,
    "independently_source_supported_endpoint_weight": 0.55,
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


def _points(contour, ends, side, boundary_end_y):
    """Keep original and terminal support/provenance independent, no filling."""
    raw = {}
    for row in contour["paths"][side + "_pavilion"]["points"]:
        xy = row.get("xy_px")
        if (xy and row["support"] == "edge_supported_candidate"
                and xy[1] > boundary_end_y):
            raw[int(xy[1])] = {
                "xy_px": [int(xy[0]), int(xy[1])],
                "weight": POLICY["main_source_weight"],
                "provenance": "automated_background_first_exterior_source",
            }
    for row in ends["terminal_contours"][side]["points"]:
        xy = row.get("xy_px")
        if (xy and row["status"] == "candidate_only"
                and xy[1] > boundary_end_y and int(xy[1]) not in raw):
            raw[int(xy[1])] = {
                "xy_px": [int(xy[0]), int(xy[1])],
                "weight": POLICY["independently_source_supported_endpoint_weight"],
                "provenance": "automatic_shadow_limited_endpoint_extension",
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
        return {"status": "unavailable", "reason": "insufficient_supported_exterior_pavilion_points"}
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
    if (contour.get("schema_version") != exterior.SCHEMA
        or joined.get("schema_version") != joint.SCHEMA
        or ends.get("schema_version") != endpoint.SCHEMA):
        raise ValueError("requires source-pinned exterior, joint and endpoint versions")
    if any(row.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256
           for row in (contour, joined, ends)):
        raise ValueError("source SHA mismatch")
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
    boundary_y = int(band["y_last_px"])
    separate = {side: _points(contour, ends, side, boundary_y)
                for side in ("left", "right")}
    independent = {side: _select(separate[side]) for side in ("left", "right")}
    symmetrical = symmetry.analyse(contour, joined, ends, pose_review)
    hypothesis = symmetrical["right_terminal_symmetry_hypothesis"]
    proposal = None
    if hypothesis.get("xy_px") is not None:
        proposal = {
            **hypothesis,
            "status": hypothesis["status"],
            "reason": hypothesis["reason"],
            "important": "modeled_right_terminal_not_independent_image_evidence",
        }
    modeled = {
        "status": "not_adopted_pose_unconfirmed",
        "provenance": "counterfactual_illustration_not_observation",
        "right_terminal_candidate": proposal,
        "common_model": None,
    }
    if symmetrical["status"] == "conditional_model_inference":
        axis = symmetrical["image_only_symmetry_diagnostic"]["axis_x_px"]
        pooled = [dict(p, side=side) for side in ("left", "right")
                  for p in separate[side]]
        # A shared radial curve is a MODEL, not an alteration to independent
        # observations. It also requires each side to have some real support.
        if all(len(separate[side]) >= 15 for side in ("left", "right")):
            common = _select_mirror(pooled, axis)
            modeled = {
                "status": "conditional_symmetry_model_inferred",
                "provenance": "separately_confirmed_head_on_plus_stone_symmetry",
                "axis_x_px": axis,
                "right_terminal_candidate": proposal,
                "common_model": common,
                "original_side_records_unchanged": True,
            }
    return {
        "schema_version": SCHEMA,
        "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "status": "review",
        "widest_width_band_candidate": band,
        "independent_pavilion": independent,
        "observed_supported_points": separate,
        "symmetry_diagnostic": symmetrical["image_only_symmetry_diagnostic"],
        "pose_review": symmetrical["pose_review"],
        "conditional_pavilion_model": modeled,
        "comparison_targets_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "interpretation": (
            "Pavilion-first piecewise projected silhouette. Independently observed "
            "left/right source coordinates remain separate. Symmetry, when used, "
            "is an optional head-on-gated model inference, not observed data. "
            "No physical pavilion-tier identity or calibrated facet angles."
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
    """Two vertical, readable pavilion panels: observed vs conditional mirror.

    All actual image-source observations appear identically in both panels.
    Purple dotted paths are ONLY a modeled mirrored left extension and never
    become independent right-side measurements, irrespective of visual fit.
    """
    base = photo.convert("RGB")
    mag = 3
    crop = (20, 190, 390, 304)
    panel_width = (crop[2]-crop[0])*mag
    panel_height = (crop[3]-crop[1])*mag
    header_height, legend_height, gutter = 45, 46, 24
    full_height = 2*(header_height+panel_height+legend_height)+gutter+35
    image = Image.new("RGB", (panel_width, full_height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    colors = {"left": (5, 210, 64), "right": (20, 140, 240)}
    predicted = (195, 48, 210)
    titles = (
        "OBSERVED PAVILION: independent left and right outer edges",
        "OPTIONAL MIRROR: purple is NOT observed right-side evidence",
    )

    for panel in (0, 1):
        offset_y = panel*(header_height+panel_height+legend_height+gutter)
        image.paste(base.crop(crop).resize((panel_width, panel_height)),
                    (0, offset_y+header_height))
        draw.text((12,offset_y+13),titles[panel],fill=(27,38,55))

        def at(x,y):
            return (round((x-crop[0])*mag),round((y-crop[1])*mag+offset_y+header_height))

        band=result["widest_width_band_candidate"]
        for y in (band["y_first_px"],band["y_last_px"]):
            draw.line((*at(crop[0],y),*at(crop[2],y)),
                      fill=(224,143,28),width=2)

        for side in ("left","right"):
            source=result["observed_supported_points"][side]
            previous=None
            for row in source:
                x,y=row["xy_px"]
                this=at(x,y)
                color=(colors[side]
                       if row["provenance"]=="automated_background_first_exterior_source"
                       else (255,153,28))
                if previous is not None and y-previous[1] <= POLICY["maximum_visual_connected_gap_y_px"]:
                    draw.line((*previous[0],*this),fill=color,width=3)
                previous=(this,y)
            fit=result["independent_pavilion"][side]
            if fit["status"]!="review":
                continue
            line=fit["selected_model"]
            ys=range(fit["supported_y_range_px"][0],fit["supported_y_range_px"][-1]+1)
            smooth=[at(_piecewise_x(line,y),y) for y in ys]
            # Dark outline makes the actual straight-segment fit legible
            # against both luminous diamond facets and grey background.
            draw.line(smooth,fill=(15,26,40),width=4)
            draw.line(smooth,fill=(252,251,246),width=2)
            for change in fit["breakpoints"]:
                x,y=change["xy_px"];cx,cy=at(x,y)
                color=((251,230,25) if change["stability"]=="stable_across_penalties"
                       else (249,100,20))
                draw.ellipse((cx-8,cy-8,cx+8,cy+8),
                             fill=color,outline=(18,26,35),width=2)
        draw.text(
            (12,offset_y+header_height+panel_height+12),
            "GREEN left / BLUE right: source. ORANGE: shadow-limited extension.",
            fill=(33,48,56),
        )
        draw.text(
            (12,offset_y+header_height+panel_height+28),
            "YELLOW break: penalty-stable. ORANGE break: model-dependent.",
            fill=(33,48,56),
        )

        if panel==1:
            proposal=result["conditional_pavilion_model"].get("right_terminal_candidate")
            axis=result["symmetry_diagnostic"].get("axis_x_px")
            if proposal and proposal.get("xy_px") and axis is not None:
                pts=[at(2*axis-row["xy_px"][0],row["xy_px"][1])
                     for row in result["observed_supported_points"]["left"]
                     if row["xy_px"][1]>=248]
                # Every other short segment: conspicuously dashed model hypothesis.
                for a,b in zip(pts[::2],pts[1::2]):
                    draw.line((a,b),fill=predicted,width=4)
                x,y=proposal["xy_px"];cx,cy=at(x,y)
                draw.ellipse((cx-11,cy-11,cx+11,cy+11),
                             outline=predicted,width=4)
                draw.line((cx-15,cy,cx+15,cy),fill=predicted,width=2)
    draw.text((12,full_height-23),
              "IMAGE PROJECTION ONLY. No verified P1/P2/P3 physical angles.",
              fill=(33,48,56))
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
