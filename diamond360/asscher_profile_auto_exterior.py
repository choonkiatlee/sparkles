"""Automated *proposals* for the outside of an Asscher profile (issue #91).

Use the background/interior transition, a weak framed-profile path prior and
left/right path continuity; never use PR A Hough peaks, internal facet labels
or expert target angles. A traced silhouette is not automatically a physical
pavilion plane. This fixture-focused v1 is deliberately not a general 360
profile recognizer: normalized framing assumptions are serialized as policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_profile_feasibility as feasibility
from . import asscher_profile_outline_changepoints as changepoints

SCHEMA = "diamond360-asscher-auto-exterior/1"
POLICY = {
    "expected_framing": "centered_approximately_side_on_profile_with_horizontal_girdle",
    "prior_role": "soft_symmetric_top_girdle_bottom_kite_envelope_not_measured_facet_angles",
    "top_y_fraction": 0.188,
    "girdle_y_fraction": 0.665,
    "lower_y_fraction": 0.906,
    "top_left_x_fraction": 0.490,
    "top_right_x_fraction": 0.510,
    "girdle_left_x_fraction": 0.105,
    "girdle_right_x_fraction": 0.895,
    "lower_left_x_fraction": 0.435,
    "lower_right_x_fraction": 0.565,
    "corridor_halfwidth_px": 28,
    "smooth_sigma_px": 1.3,
    "inside_outside_sample_px": 7,
    "gradient_span_px": 3,
    "prior_penalty_per_px2": 0.10,
    "tangent_change_penalty": 2.0,
    "max_dx_per_y_px": 5,
    "minimum_local_cross_gradient_rgb": 3.0,
    "minimum_local_separation_rgb": 3.0,
    "uncertainty_variants": [[0.45, 0.70, 0.30], [0.70, 0.50, 0.50], [0.40, 1.00, 0.20]],
    "spread_review_px": 6.0,
    "max_unsupported_fraction_for_review": 0.70,
    "min_supported_contiguous_run_for_exploratory_changepoints": 18,
    "trace_status_policy": "all_paths_proposals_even_when_review",
    "angle_policy": "all_physical_facet_angles_unavailable",
    "internal_optical_data_policy": "not_read",
}
SIDES = ("left", "right")
PHASES = ("crown", "pavilion")


def _signals(rgb):
    h, w = rgb.shape[:2]
    smooth = ndi.gaussian_filter(
        rgb.astype(float),
        sigma=(POLICY["smooth_sigma_px"], POLICY["smooth_sigma_px"], 0),
    )
    radius = POLICY["gradient_span_px"]
    cross = np.linalg.norm(
        np.roll(smooth, -radius, axis=1) - np.roll(smooth, radius, axis=1), axis=2
    )
    background = np.stack([
        np.median(
            np.concatenate((
                smooth[y, 4:max(5, int(0.065 * w))],
                smooth[y, min(w-5, int(0.94*w)):w-4],
            )), axis=0,
        )
        for y in range(h)
    ])
    distance = np.linalg.norm(smooth - background[:, None, :], axis=2)
    return cross, distance


def _geometry(side, phase, h, w):
    top = round(h * POLICY["top_y_fraction"])
    girdle = round(h * POLICY["girdle_y_fraction"])
    lower = round(h * POLICY["lower_y_fraction"])
    y0, y1 = (top, girdle) if phase == "crown" else (girdle, lower)
    start = ("top_" if phase == "crown" else "girdle_") + side + "_x_fraction"
    end = ("girdle_" if phase == "crown" else "lower_") + side + "_x_fraction"
    x0, x1 = POLICY[start] * w, POLICY[end] * w
    ys = np.arange(y0, y1 + 1, dtype=int)
    prior = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
    return ys, prior, float((x1 - x0) / (y1 - y0))


def _path(cross, dist, side, phase, weights):
    h, w = cross.shape
    ys, prior, slope = _geometry(side, phase, h, w)
    inner_sign = 1 if side == "left" else -1
    radius = POLICY["inside_outside_sample_px"]
    margin = radius + POLICY["gradient_span_px"] + 2
    xs = np.arange(margin, w - margin)
    emission = []
    for i, y in enumerate(ys):
        inner = xs + inner_sign * radius
        outside = xs - inner_sign * radius
        evidence = (
            weights[0] * cross[y, xs]
            + weights[1] * np.maximum(dist[y, inner] - dist[y, outside], 0)
            - weights[2] * np.clip(dist[y, outside] - 8, 0, 60)
        )
        local = np.where(
            np.abs(xs - prior[i]) <= POLICY["corridor_halfwidth_px"],
            -evidence + POLICY["prior_penalty_per_px2"] * (xs - prior[i]) ** 2,
            np.inf,
        )
        emission.append(local)
    costs = emission[0].copy()
    backwards = []
    for i in range(1, len(ys)):
        best = np.full_like(costs, np.inf)
        back = np.full(len(xs), -1, dtype=int)
        for dx in range(-POLICY["max_dx_per_y_px"], POLICY["max_dx_per_y_px"] + 1):
            old = np.arange(len(xs)) - dx
            allowed = (old >= 0) & (old < len(xs))
            candidate = np.full_like(costs, np.inf)
            candidate[allowed] = (
                costs[old[allowed]]
                + POLICY["tangent_change_penalty"] * (dx - slope) ** 2
            )
            better = candidate < best
            best[better], back[better] = candidate[better], old[better]
        costs = best + emission[i]
        backwards.append(back)
    if not np.isfinite(costs).any():
        return None
    index = int(np.argmin(costs))
    chosen = [index]
    for back in reversed(backwards):
        index = int(back[index])
        chosen.append(index)
    return ys, xs[np.asarray(chosen[::-1])]


def _supported_runs(points):
    """Never fit a straight stretch across ambiguous/missing edge intervals."""
    runs, current = [], []
    for point in points:
        if point["support"] == "edge_supported_candidate":
            current.append(point["xy_px"])
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    result = []
    for run in runs:
        if len(run) < POLICY["min_supported_contiguous_run_for_exploratory_changepoints"]:
            continue
        # Shape-change fits are only to *supported* source outline points,
        # and are clearly not reviewer-confirmed physical facet identities.
        fitted = changepoints.fit_stroke(run)
        if fitted["status"] == "unavailable":
            continue
        result.append({
            "first_xy_px": run[0],
            "last_xy_px": run[-1],
            "point_count": len(run),
            "status": "exploratory_contiguous_image_slope_only",
            "fitted": fitted,
        })
    return result


def analyse_array(rgb):
    rgb = np.asarray(rgb, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("expected RGB source image")
    h, w = rgb.shape[:2]
    if min(w, h) < 160:
        raise ValueError("source too small for framed-profile soft-prior experiment")
    cross, dist = _signals(rgb)
    paths = {}
    for side in SIDES:
        for phase in PHASES:
            name = f"{side}_{phase}"
            variations = [
                _path(cross, dist, side, phase, weights)
                for weights in POLICY["uncertainty_variants"]
            ]
            if any(value is None for value in variations):
                paths[name] = {
                    "status": "unavailable",
                    "reason": "no_continuous_guided_path",
                    "points": [],
                    "supported_runs": [],
                }
                continue
            ys = variations[0][0]
            stack = np.stack([value[1] for value in variations])
            x = np.rint(np.median(stack, axis=0)).astype(int)
            direction = 1 if side == "left" else -1
            radius = POLICY["inside_outside_sample_px"]
            inner = np.clip(x + direction * radius, 0, w - 1)
            outside = np.clip(x - direction * radius, 0, w - 1)
            gradient = cross[ys, x]
            separation = dist[ys, inner] - dist[ys, outside]
            spread = np.ptp(stack, axis=0)
            supported = (
                (gradient >= POLICY["minimum_local_cross_gradient_rgb"])
                & (separation >= POLICY["minimum_local_separation_rgb"])
                & (spread <= POLICY["spread_review_px"])
            )
            points = [
                {
                    "xy_px": [int(px), int(y)],
                    "support": "edge_supported_candidate" if ok else "weak_or_ambiguous",
                    "cross_gradient_rgb": round(float(contrast), 3),
                    "in_out_background_separation_rgb": round(float(delta), 3),
                    "variant_disagreement_px": int(disagreement),
                }
                for y, px, ok, contrast, delta, disagreement in zip(
                    ys, x, supported, gradient, separation, spread
                )
            ]
            fraction = float(np.mean(supported))
            paths[name] = {
                "status": (
                    "review"
                    if fraction >= 1.0 - POLICY["max_unsupported_fraction_for_review"]
                    else "unavailable"
                ),
                "provenance": "automated_guided_exterior_candidate_not_human_confirmed",
                "supported_fraction": round(fraction, 4),
                "candidate_model": "background_transition_continuous_kite_guided_path",
                "points": points,
                "supported_runs": _supported_runs(points),
                "physical_facet_correspondence": "not_established",
                "named_facet_angles": "unavailable",
            }
    return {
        "schema_version": SCHEMA,
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "source_dimensions_xy_px": [w, h],
        "status": (
            "review" if all(path["status"] == "review" for path in paths.values())
            else "partial_or_unavailable"
        ),
        "paths": paths,
        "comparison_targets_loaded": False,
        "semantic_measurements": {
            side: {
                facet: {"status": "unavailable", "physical_angle_deg": None}
                for facet in feasibility.SLOTS
            }
            for side in SIDES
        },
        "interpretation": (
            "Contour proposals guided by image-only outside/background evidence. "
            "Normalized framing is an explicit soft prior, not measured geometry; "
            "internal virtual-facet gradients and Sergey target angles are not used."
        ),
    }


def render_overlay(result, rgb):
    image = Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    draw = ImageDraw.Draw(image)
    for row in result["paths"].values():
        previous = None
        for point in row["points"]:
            xy = tuple(point["xy_px"])
            color = (
                (20, 211, 80)
                if point["support"] == "edge_supported_candidate"
                else (250, 135, 30)
            )
            draw.point(xy, fill=color)
            if previous and previous[1] == point["support"]:
                draw.line((previous[0], xy), fill=color, width=2)
            previous = (xy, point["support"])
    return image


def write_qc(image_path, output, expected_sha256=None):
    image_path, output = Path(image_path), Path(output)
    source_sha = feasibility._hash_file(image_path)
    if expected_sha256 and source_sha != expected_sha256:
        raise ValueError("original profile source SHA-256 mismatch")
    with Image.open(image_path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    result = analyse_array(rgb)
    result["source_sha256"] = source_sha
    result["original_verified"] = (
        source_sha == feasibility.ORIGINAL_PROFILE_SHA256
        and rgb.shape[:2][::-1] == feasibility.ORIGINAL_PROFILE_SIZE
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "auto-exterior.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    render_overlay(result, rgb).save(output / "auto-exterior-overlay.png")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-original", action="store_true")
    args = parser.parse_args()
    result = write_qc(
        args.image, args.output,
        feasibility.ORIGINAL_PROFILE_SHA256 if args.require_original else None,
    )
    print(json.dumps({
        "status": result["status"],
        "original_verified": result["original_verified"],
        "paths": {
            name: {
                "status": record["status"],
                "supported_fraction": record.get("supported_fraction"),
                "exploratory_supported_runs": len(record.get("supported_runs", [])),
            }
            for name, record in result["paths"].items()
        },
    }, sort_keys=True))


if __name__ == "__main__":
    main()
