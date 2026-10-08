"""Automatic Asscher profile OUTSIDE edge proposals from background-first evidence.

Do not maximize brightness or gradient magnitude: brilliant virtual facets
are often a stronger *interior* edge than the physical outside silhouette.
Find the first sustained foreground contact from each constant-color exterior
image margin, separately on left/right. A soft medoid filter only removes
row-level glitches. It may NEVER select a stronger interior edge to fix
an unstable outline. All source-derived paths remain unverified.
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

SCHEMA = "diamond360-asscher-auto-exterior/2"
POLICY = {
    "source_type": "approximately_side_on_centered_profile_on_nearly_constant_background",
    "edge_selection": "FIRST_PERSISTENT_FOREGROUND_CONTACT_FROM_IMAGE_MARGIN",
    "outside_background_model": "independent_row_median_from_both_horizontal_image_margins",
    "background_smoothing_sigma_px": 1.0,
    "left_right_background_probe_width_px": 22,
    "min_border_inset_px": 22,
    "first_contact_thresholds_rgb": [7.0, 9.0, 12.0],
    "persistent_contact_window_px": 7,
    "persistent_contact_required_px": 5,
    "median_contour_smoothing_rows": 5,
    "max_threshold_endpoint_spread_px": 7.0,
    "max_smoothed_vs_raw_offset_px": 5.0,
    "bottom_shadow_unreliable_at_y_fraction": 0.868,
    "crown_first_y_fraction": 0.188,
    "crown_last_y_fraction": 0.665,
    "pavilion_first_y_fraction": 0.665,
    "pavilion_last_y_fraction": 0.878,
    "phase_break_is_candidate": "the fixed crown_pavilion_phase_split is NOT a verified girdle",
    "minimum_supported_fraction_for_review": 0.45,
    "min_contiguous_support_for_exploratory_slope_fit": 18,
    "uncertainty_policy": "threshold_variant_disagreement_and_missing_source_evidence_not_calibrated_interval",
    "prior_policy": "NO_INTERNAL_OPTICAL_GRADIENTS_NO_BRIGHTEST_LINE_NO_ANGLE_TARGET_PRIORS",
    "semantic_policy": "all_physical_P1_P2_P3_C1_angles_unavailable",
}
SIDES = ("left", "right")
PHASES = ("crown", "pavilion")


def _background_distance(rgb):
    h, w = rgb.shape[:2]
    smooth = ndi.gaussian_filter(
        rgb.astype(float), sigma=(POLICY["background_smoothing_sigma_px"],)*2 + (0,)
    )
    width = POLICY["left_right_background_probe_width_px"]
    left = smooth[:, 4:width + 4]
    right = smooth[:, w - width - 4:w - 4]
    # The background is sampled OUTSIDE, never from the bright central face.
    reference = np.median(np.concatenate((left, right), axis=1), axis=1)
    difference = np.linalg.norm(smooth - reference[:, None, :], axis=2)
    return difference, reference


def _outside_first_contact(distance, side, threshold):
    """First persistent deviation from background, not the strongest edge.

    A sustained contact condition removes isolated background JPEG pixels.
    Searching only from each extreme toward the center prevents bright,
    internal reflection boundaries from winning a stronger-gradient contest.
    """
    h, w = distance.shape
    rows = distance[:, :w // 2] if side == "left" else distance[:, w // 2:][:, ::-1]
    margin = POLICY["min_border_inset_px"]
    limit = rows.shape[1] - POLICY["persistent_contact_window_px"]
    if margin >= limit:
        raise ValueError("source too narrow for first-contact tracing")
    above = (rows >= threshold).astype(np.int16)
    # Explicit forward count enforces the first inward contact. A symmetric
    # convolution would risk shifting an exterior edge toward the interior.
    counts = sum(
        above[:, margin + shift:limit + shift]
        for shift in range(POLICY["persistent_contact_window_px"])
    )
    eligible = counts >= POLICY["persistent_contact_required_px"]
    any_contact = np.any(eligible, axis=1)
    first = margin + np.argmax(eligible, axis=1)
    x = first if side == "left" else (w - 1 - first)
    return np.where(any_contact, x, np.nan).astype(float)


def _phase_rows(height, phase):
    lo, hi = (
        (POLICY["crown_first_y_fraction"], POLICY["crown_last_y_fraction"])
        if phase == "crown" else
        (POLICY["pavilion_first_y_fraction"], POLICY["pavilion_last_y_fraction"])
    )
    return np.arange(round(lo * height), round(hi * height) + 1, dtype=int)


def _supported_runs(points):
    runs, current = [], []
    for item in points:
        if item["support"] == "edge_supported_candidate" and item["xy_px"] is not None:
            current.append(item["xy_px"])
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    output = []
    for points_in_run in runs:
        if len(points_in_run) < POLICY["min_contiguous_support_for_exploratory_slope_fit"]:
            continue
        fitted = changepoints.fit_stroke(points_in_run)
        if fitted["status"] != "review":
            continue
        output.append({
            "status": "exploratory_contiguous_image_slope_only",
            "first_xy_px": points_in_run[0],
            "last_xy_px": points_in_run[-1],
            "point_count": len(points_in_run),
            "fitted": fitted,
        })
    return output


def analyse_array(rgb):
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[-1] != 3:
        raise ValueError("expected RGB source image")
    h, w = arr.shape[:2]
    if min(w, h) < 160:
        raise ValueError("source too small for outside-background profile experiment")
    distance, background = _background_distance(arr)
    paths = {}
    for side in SIDES:
        variants = np.vstack([
            _outside_first_contact(distance, side, threshold)
            for threshold in POLICY["first_contact_thresholds_rgb"]
        ])
        for phase in PHASES:
            name = f"{side}_{phase}"
            ys = _phase_rows(h, phase)
            values = variants[:, ys]
            finite = np.isfinite(values)
            enough = np.count_nonzero(finite, axis=0) >= 2
            # Median prioritizes the earliest consistent background departure;
            # disagreement with the more conservative threshold is disclosed.
            raw = np.full(len(ys), np.nan)
            for i in np.flatnonzero(enough):
                raw[i] = np.median(values[finite[:, i], i])
            # Short filter suppresses background JPEG grains; it cannot cross
            # a missing row or convert it into a physical contour observation.
            valid_indices = np.flatnonzero(np.isfinite(raw))
            smoothed = raw.copy()
            for i in valid_indices:
                neighbors = raw[max(0, i - 2):min(len(raw), i + 3)]
                smoothed[i] = np.median(neighbors[np.isfinite(neighbors)])
            spreads = np.full(len(ys), np.inf)
            for i in valid_indices:
                candidates = values[finite[:, i], i]
                spreads[i] = float(np.max(candidates) - np.min(candidates))
            bottom_safe = ys < int(round(h * POLICY["bottom_shadow_unreliable_at_y_fraction"]))
            supported = (
                enough & (spreads <= POLICY["max_threshold_endpoint_spread_px"])
                & (np.abs(smoothed - raw) <= POLICY["max_smoothed_vs_raw_offset_px"])
                & bottom_safe
            )
            points = []
            for i, y in enumerate(ys):
                x = int(np.rint(smoothed[i])) if np.isfinite(smoothed[i]) else None
                points.append({
                    "xy_px": [x, int(y)] if x is not None else None,
                    "support": "edge_supported_candidate" if supported[i] else "weak_or_ambiguous",
                    "threshold_disagreement_px": round(float(spreads[i]), 3) if np.isfinite(spreads[i]) else None,
                    "first_contact_count": int(finite[:, i].sum()),
                    "reason": (
                        "persistent_source_background_transition"
                        if supported[i] else
                        ("lower_platform_shadow_proximity" if not bottom_safe[i]
                         else "missing_or_inconsistent_background_contact")
                    ),
                })
            fraction = float(np.mean(supported))
            paths[name] = {
                "status": "review" if fraction >= POLICY["minimum_supported_fraction_for_review"] else "unavailable",
                "provenance": "automated_first_background_contact_not_human_verified",
                "supported_fraction": round(fraction, 4),
                "candidate_model": "exterior_margin_connected_background_contact",
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
        "status": "review" if all(row["status"] == "review" for row in paths.values()) else "partial_or_unavailable",
        "paths": paths,
        "comparison_targets_loaded": False,
        "semantic_measurements": {
            side: {facet: {"status": "unavailable", "physical_angle_deg": None}
                   for facet in feasibility.SLOTS}
            for side in SIDES
        },
        "interpretation": (
            "Outermost sustained deviation from row-wise measured background, NOT the "
            "strongest photo gradient. No interior virtual-feature detection, named "
            "facet identity, physical angle, or expert comparison. The fixed phase "
            "split does not establish physical girdle location."
        ),
    }


def render_overlay(result, rgb):
    image = Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    draw = ImageDraw.Draw(image)
    for row in result["paths"].values():
        previous = None
        for point in row["points"]:
            if point["xy_px"] is None:
                previous = None
                continue
            xy = tuple(point["xy_px"])
            color = ((15, 224, 75) if point["support"] == "edge_supported_candidate"
                     else (250, 132, 22))
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
        "paths": {key: {"status": row["status"],
                        "supported_fraction": row.get("supported_fraction")}
                  for key, row in result["paths"].items()},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
