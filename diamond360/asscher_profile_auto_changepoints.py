"""Image-only global exterior silhouette changepoints for #91.

Fit left and right separately across short holes in *supported* source rows;
missing observations are never fabricated. Detect a candidate common widest
profile band before fitting crown/pavilion segments. None of the resulting
breaks proves a polished facet junction, a 3-D angle, or P1/P2/P3 identity.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_auto_exterior as auto_exterior

SCHEMA = "diamond360-asscher-auto-outline-changepoints/2"
INPUT_SCHEMA = auto_exterior.SCHEMA
POLICY = {
    "width_band_search_y_fraction": [0.54, 0.74],
    "source_orientation": "pointed_upper_pavilion_broad_lower_crown",
    "width_band_within_peak_px": 5.0,
    "maximum_gap_within_band_px": 2,
    "minimum_band_rows": 6,
    "max_linear_segments_per_crown_or_pavilion": 3,
    "minimum_span_per_segment_y_px": 18,
    "minimum_observed_points_per_segment": 12,
    "candidate_changepoint_step_y_px": 2,
    "minimum_slope_difference_dx_per_dy": 0.20,
    "default_complexity_penalty_px2": 60.0,
    "penalty_sensitivity_px2": [40.0, 60.0, 110.0, 150.0],
    "nearby_breakpoint_tolerance_y_px": 7,
    "plot_do_not_interpolate_gaps_larger_y_px": 4,
    "physical_identity": "not_established",
    "no_forced_mirror_symmetry": True,
    "no_internal_brightness_inputs": True,
    "no_expert_targets": True,
}


def _supported_points(record, side):
    data = {}
    for phase in ("pavilion", "crown"):
        path = record["paths"][f"{side}_{phase}"]
        for row in path["points"]:
            xy = row.get("xy_px")
            if xy is not None and row["support"] == "edge_supported_candidate":
                data[int(xy[1])] = int(xy[0])
    return data


def _candidate_widest_band(record):
    _, height = record["source_dimensions_xy_px"]
    left, right = (_supported_points(record, side) for side in ("left", "right"))
    low, high = POLICY["width_band_search_y_fraction"]
    spans = {
        y: right[y] - lx
        for y, lx in left.items()
        if y in right and int(low * height) <= y <= int(high * height)
    }
    if not spans:
        return {"status": "unavailable", "reason": "no_joint_supported_width"}
    max_width = max(spans.values())
    accepted = [
        y for y in sorted(spans)
        if spans[y] >= max_width - POLICY["width_band_within_peak_px"]
    ]
    groups = []
    for y in accepted:
        if not groups or y - groups[-1][-1] > POLICY["maximum_gap_within_band_px"]:
            groups.append([y])
        else:
            groups[-1].append(y)
    sufficient = [g for g in groups if len(g) >= POLICY["minimum_band_rows"]]
    if not sufficient:
        return {
            "status": "unavailable",
            "reason": "no_sustained_outermost_profile_width_band",
            "maximum_observed_width_px": max_width,
        }
    best = max(sufficient, key=lambda g: (len(g), -abs((g[0] + g[-1])/2 -
                  max(spans, key=spans.get))))
    return {
        "status": "candidate_only",
        "kind": "maximum_projected_left_right_width_band_not_verified_girdle",
        "y_first_px": int(best[0]),
        "y_last_px": int(best[-1]),
        "supported_row_count": len(best),
        "maximum_observed_width_px": int(max_width),
        "width_range_px": [min(spans[y] for y in best), max(spans[y] for y in best)],
        "left_edge_x_range_px": [min(left[y] for y in best), max(left[y] for y in best)],
        "right_edge_x_range_px": [min(right[y] for y in best), max(right[y] for y in best)],
        "reason": "image_width_extremum_only_no_anatomical_ground_truth",
    }


def _piecewise_models(xy, penalty):
    """Continuous x(y) hinge fits for one, two or three visible stretches."""
    xy = np.asarray(xy, float)
    if len(xy) < POLICY["minimum_observed_points_per_segment"]:
        return []
    ys, xs = xy[:, 1], xy[:, 0]
    minspan = POLICY["minimum_span_per_segment_y_px"]
    minpts = POLICY["minimum_observed_points_per_segment"]
    step = POLICY["candidate_changepoint_step_y_px"]
    candidates = np.arange(ys[0] + minspan, ys[-1] - minspan + 1, step)
    models = []
    for k in range(1, POLICY["max_linear_segments_per_crown_or_pavilion"] + 1):
        best = None
        for cuts in (itertools.combinations(candidates, k-1) if k > 1 else [()]):
            bounds = (ys[0],) + tuple(cuts) + (ys[-1],)
            if np.diff(bounds).min() < minspan:
                continue
            if any(
                np.count_nonzero((ys >= a) & (ys <= b)) < minpts
                for a, b in zip(bounds[:-1], bounds[1:])
            ):
                continue
            design = np.column_stack(
                [np.ones(len(ys)), ys] + [np.maximum(ys - t, 0) for t in cuts]
            )
            coeff = np.linalg.lstsq(design, xs, rcond=None)[0]
            slopes = np.cumsum(coeff[1:])
            if (len(slopes) > 1 and
                    np.min(np.abs(np.diff(slopes))) <
                    POLICY["minimum_slope_difference_dx_per_dy"]):
                continue
            squared_error = float(np.sum((design @ coeff - xs)**2))
            score = squared_error + (k - 1) * penalty
            if best is None or score < best["score"]:
                best = {
                    "segments": k,
                    "break_y_px": [int(t) for t in cuts],
                    "slope_dx_per_dy": [round(float(v), 5) for v in slopes],
                    "coefficients_x_of_y": [float(c) for c in coeff],
                    "squared_residual_px2": round(squared_error, 5),
                    "score": round(score, 5),
                }
        if best is not None:
            models.append(best)
    return models


def _region(record, band, side, phase):
    if band["status"] != "candidate_only":
        return {"status": "unavailable", "reason": "joint_maximum_width_unavailable"}
    full = _supported_points(record, side)
    if phase == "pavilion":
        ys = sorted(y for y in full if y < band["y_first_px"])
    else:
        ys = sorted(y for y in full if y > band["y_last_px"])
    xy = [[full[y], y] for y in ys]
    if len(xy) < POLICY["minimum_observed_points_per_segment"]:
        return {"status": "unavailable", "reason": "insufficient_supported_outer_rows"}
    alternatives = {}
    for penalty in POLICY["penalty_sensitivity_px2"]:
        models = _piecewise_models(xy, penalty)
        if models:
            alternatives[str(int(penalty))] = min(
                models, key=lambda d: (d["score"], d["segments"])
            )
    default = alternatives.get(str(int(POLICY["default_complexity_penalty_px2"])))
    if default is None:
        return {"status": "unavailable", "reason": "no_valid_piecewise_profile"}
    points = []
    for cut in default["break_y_px"]:
        matched = sum(
            any(abs(t - cut) <= POLICY["nearby_breakpoint_tolerance_y_px"]
                for t in model["break_y_px"])
            for model in alternatives.values()
        )
        coeff = default["coefficients_x_of_y"]
        fitted_x = (coeff[0] + coeff[1] * cut +
                    sum(c * max(cut - t, 0)
                        for c, t in zip(coeff[2:], default["break_y_px"])))
        points.append({
            "xy_px": [round(float(fitted_x), 3), int(cut)],
            "status": "candidate_only",
            "model_variant_support": matched,
            "model_variant_total": len(alternatives),
            "stability": (
                "stable_to_penalty_variants"
                if matched == len(alternatives) else "model_dependent"
            ),
            "meaning": "image_plane_contour_slope_change_not_polished_facet_junction",
        })
    return {
        "status": "review",
        "observed_point_count": len(xy),
        "supported_y_range_px": [ys[0], ys[-1]],
        "unsupported_rows_between_observations": ys[-1] - ys[0] + 1 - len(ys),
        "selected_segment_count": default["segments"],
        "candidate_breakpoints": points,
        "coefficients_x_of_y": default["coefficients_x_of_y"],
        "slope_dx_per_dy": default["slope_dx_per_dy"],
        "model_selection_by_penalty": {
            penalty: {
                "segments": model["segments"],
                "break_y_px": model["break_y_px"],
                "score": model["score"],
            }
            for penalty, model in alternatives.items()
        },
        "source_observations_xy_px": xy,
        "physical_facet_correspondence": "not_established",
    }


def analyse(record):
    if record.get("schema_version") != INPUT_SCHEMA:
        raise ValueError("requires oriented background-first auto-exterior/3")
    if record.get("comparison_targets_loaded") is not False:
        raise ValueError("expert angle targets must not enter extraction")
    if record.get("policy_sha256") != feasibility.canonical_sha256(auto_exterior.POLICY):
        raise ValueError("input contour method revision differs from pinned v2")
    if record.get("source_dimensions_xy_px") != [410, 319]:
        raise ValueError("expected source dimensions for archived profile")
    if record.get("policy", {}).get("source_orientation") != POLICY["source_orientation"]:
        raise ValueError("source orientation is missing or inverted")
    band = _candidate_widest_band(record)
    regions = {
        f"{side}_{phase}": _region(record, band, side, phase)
        for side in ("left", "right")
        for phase in ("crown", "pavilion")
    }
    return {
        "schema_version": SCHEMA,
        "source_sha256": record.get("source_sha256"),
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "widest_band_candidate": band,
        "source_orientation": POLICY["source_orientation"],
        "regions": regions,
        "status": (
            "review" if any(row["status"] == "review" for row in regions.values())
            else "unavailable"
        ),
        "comparison_targets_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "interpretation": (
            "Independent projected left/right silhouette slope changes only. "
            "Shared widest region is a candidate, not a verified girdle. "
            "Missing image support is retained; no calibrated physical angles."
        ),
    }


def render_overlay(image_path, result):
    with Image.open(image_path) as source:
        image = source.convert("RGB").resize((1230, 957))
    d = ImageDraw.Draw(image)
    scale = 3
    colors = {
        "left_pavilion": (5, 190, 220),
        "right_pavilion": (40, 75, 235),
        "left_crown": (160, 52, 238),
        "right_crown": (243, 45, 108),
    }
    band = result["widest_band_candidate"]
    if band["status"] == "candidate_only":
        for y in (band["y_first_px"], band["y_last_px"]):
            d.line((35*scale, y*scale, 375*scale, y*scale),
                   fill=(244, 150, 15), width=2)
    for name, region in result["regions"].items():
        if region["status"] != "review":
            continue
        points = region["source_observations_xy_px"]
        cuts = [p["xy_px"][1] for p in region["candidate_breakpoints"]]
        coeff = region["coefficients_x_of_y"]
        def fitted_x(y):
            return coeff[0] + coeff[1]*y + sum(
                c*max(y - t, 0) for c, t in zip(coeff[2:], cuts)
            )
        previous = None
        for x, y in points:
            if previous is not None and y - previous[1] <= POLICY["plot_do_not_interpolate_gaps_larger_y_px"]:
                d.line((previous[0]*scale, previous[1]*scale, x*scale, y*scale),
                       fill=colors[name], width=3)
                d.line((round(fitted_x(previous[1])*scale), previous[1]*scale,
                        round(fitted_x(y)*scale), y*scale),
                       fill=(255, 252, 252), width=2)
            previous = (x, y)
        for mark in region["candidate_breakpoints"]:
            x, y = mark["xy_px"]
            cx, cy = round(x*scale), round(y*scale)
            color = (
                (245, 221, 0) if mark["stability"] == "stable_to_penalty_variants"
                else (253, 108, 5)
            )
            d.ellipse((cx-8, cy-8, cx+8, cy+8),
                      fill=color, outline=(37, 39, 47), width=3)
    return image


def write_report(image_path, auto_json_path, output):
    image_path, output = Path(image_path), Path(output)
    if feasibility._hash_file(image_path) != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("original source hash mismatch")
    contour = json.loads(Path(auto_json_path).read_text(encoding="utf-8"))
    if contour.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("auto source hash mismatch")
    result = analyse(contour)
    output.mkdir(parents=True, exist_ok=True)
    (output / "joint-changepoints.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    render_overlay(image_path, result).save(output / "joint-changepoints-overlay.png")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--auto-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = write_report(args.image, args.auto_json, args.output)
    print(json.dumps({
        "status": output["status"],
        "widest_band": output["widest_band_candidate"],
        "segment_count": {
            name: row.get("selected_segment_count")
            for name, row in output["regions"].items()
        },
        "breaks": {
            name: [x["xy_px"] for x in row.get("candidate_breakpoints", [])]
            for name, row in output["regions"].items()
        },
    }, sort_keys=True))


if __name__ == "__main__":
    main()
