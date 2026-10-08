"""#91 PR B2: conservative background-separated external profile silhouette.

Never use PR A internal Hough line proposals for contour estimation, and never
turn photographic contours into identified physical facet planes or 3-D angles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_profile_feasibility as feasibility

SCHEMA = "diamond360-asscher-profile-outer-contour/1"
POLICY = {
    "source_model": "upper_corner_rgb_background_vs_smoothed_pixel_color",
    "background_corner_width_fraction": 0.09,
    "background_corner_top_fraction": [0.03, 0.16],
    "background_color_variability_limit_rgb": 14.0,
    "smooth_sigma_px": 1.4,
    "rgb_distance_thresholds": [14.0, 22.0, 30.0],
    "morphology_close_radius_px": 3,
    "minimum_component_area_fraction": 0.035,
    "analyzable_height_fraction": [0.12, 0.84],
    "profile_row_start_fraction": 0.16,
    "profile_row_end_fraction": 0.81,
    "minimum_row_width_fraction": 0.08,
    "maximum_row_width_fraction": 0.91,
    "cross_threshold_spread_review_px": 8.0,
    "max_review_rows_fraction": 0.28,
    "candidate_upper_rows_fraction": [0.18, 0.34],
    "candidate_outer_width_rows_fraction": [0.48, 0.79],
    "landmark_policy": "candidate_regions_only_never_automatically_verified_table_girdle",
    "shadow_policy": "exclude_bottom_band_from_automatic_contour",
    "semantic_facet_policy": "no P1_P2_P3_C1_from_silhouette_without_3D_projection_model",
}


def _corners(rgb):
    h, w, _ = rgb.shape
    xlim = max(8, int(w * POLICY["background_corner_width_fraction"]))
    lo, hi = POLICY["background_corner_top_fraction"]
    y0, y1 = int(h * lo), int(h * hi)
    sample = np.concatenate([
        rgb[y0:y1, 3:xlim].reshape(-1, 3),
        rgb[y0:y1, w-xlim:w-3].reshape(-1, 3),
    ])
    median = np.median(sample, axis=0)
    spread = float(np.percentile(np.linalg.norm(sample - median, axis=1), 95))
    return median, spread


def _segment_foreground(rgb, background, threshold):
    """Largest connected background-different mass; not physical recognition."""
    h, w, _ = rgb.shape
    smooth = ndi.gaussian_filter(rgb.astype(float), sigma=(POLICY["smooth_sigma_px"], POLICY["smooth_sigma_px"], 0))
    distance = np.linalg.norm(smooth - background, axis=2)
    start = int(h * POLICY["analyzable_height_fraction"][0])
    stop = int(h * POLICY["analyzable_height_fraction"][1])
    mask = distance >= threshold
    # Never learn from border or the surface/reflection/shadow below the stone.
    mask[:start] = False
    mask[stop:] = False
    mask[:, :3] = False
    mask[:, -3:] = False
    radius = POLICY["morphology_close_radius_px"]
    mask = ndi.binary_closing(mask, structure=np.ones((2*radius+1, 2*radius+1), bool))
    labels, n = ndi.label(mask)
    if not n:
        return np.zeros((h, w), bool), distance
    count = np.bincount(labels.ravel())
    count[0] = 0
    chosen = int(np.argmax(count))
    selected = labels == chosen
    if count[chosen] < POLICY["minimum_component_area_fraction"] * w * h:
        return np.zeros((h, w), bool), distance
    selected = ndi.binary_fill_holes(selected)
    return selected, distance


def _row_span(mask, y):
    xs = np.flatnonzero(mask[y])
    return None if not len(xs) else (int(xs[0]), int(xs[-1]))


def _candidate_window(rows, low, high, height, key):
    subset = [
        row for row in rows
        if int(height * low) <= row["y_px"] <= int(height * high)
        and row["status"] == "supported_candidate"
    ]
    if not subset:
        return {
            "status": "unavailable",
            "reason": "no_cross_threshold_stable_outer_rows",
            "region_xyxy_px": None,
            "contour_row_count": 0,
        }
    if key == "max_width":
        peak = max(row["width_px"] for row in subset)
        qualified = [row for row in subset if row["width_px"] >= peak * 0.96]
    else:
        narrowest = min(row["width_px"] for row in subset)
        qualified = [row for row in subset if row["width_px"] <= narrowest * 1.20]
    x0 = min(row["left_x_px"] for row in qualified)
    x1 = max(row["right_x_px"] for row in qualified)
    return {
        "status": "candidate_only",
        "reason": "external_profile_row_band_not_verified_anatomical_junction",
        "region_xyxy_px": [int(x0), min(row["y_px"] for row in qualified),
                           int(x1), max(row["y_px"] for row in qualified)],
        "contour_row_count": len(qualified),
    }


def analyse_image(image_path, expected_sha256=None):
    """Return conservative projected outer-contour evidence only."""
    path = Path(image_path)
    source_sha256 = feasibility._hash_file(path)
    if expected_sha256 and source_sha256 != expected_sha256:
        raise ValueError("archived profile source SHA-256 mismatch")
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    if min(w, h) < 64:
        raise ValueError("source is too small for external-profile diagnostics")
    background, background_spread = _corners(rgb)
    masks = []
    if background_spread <= POLICY["background_color_variability_limit_rgb"]:
        for threshold in POLICY["rgb_distance_thresholds"]:
            mask, _ = _segment_foreground(rgb, background, threshold)
            masks.append(mask)
    rows = []
    lo = int(h * POLICY["profile_row_start_fraction"])
    hi = int(h * POLICY["profile_row_end_fraction"])
    for y in range(lo, hi):
        spans = [_row_span(mask, y) for mask in masks]
        if not spans or any(s is None for s in spans):
            rows.append({"y_px": y, "status": "unavailable", "reason": "missing_foreground_across_thresholds"})
            continue
        xleft = [s[0] for s in spans]
        xright = [s[1] for s in spans]
        spread = max(max(xleft)-min(xleft), max(xright)-min(xright))
        width = int(round(float(np.median(xright)) - float(np.median(xleft)) + 1))
        if (min(xleft) <= 4 or max(xright) >= w-5
                or width < POLICY["minimum_row_width_fraction"] * w
                or width > POLICY["maximum_row_width_fraction"] * w):
            rows.append({"y_px": y, "status": "unavailable", "reason": "background_bleed_or_unplausible_width",
                         "cross_threshold_max_spread_px": int(spread)})
            continue
        row = {
            "y_px": y,
            "left_x_px": int(round(np.median(xleft))),
            "right_x_px": int(round(np.median(xright))),
            "width_px": width,
            "cross_threshold_max_spread_px": int(spread),
            "status": "supported_candidate" if spread <= POLICY["cross_threshold_spread_review_px"] else "review",
        }
        if row["status"] != "supported_candidate":
            row["reason"] = "outer_contour_sensitive_to_background_distance_threshold"
        rows.append(row)
    supported = [row for row in rows if row["status"] == "supported_candidate"]
    disputed = [row for row in rows if row["status"] == "review"]
    proportion = float(len(disputed) / max(1, len(supported) + len(disputed)))
    usable = bool(
        len(supported) >= max(15, 0.28*(hi-lo))
        and proportion <= POLICY["max_review_rows_fraction"]
        and background_spread <= POLICY["background_color_variability_limit_rgb"]
    )
    windows = {
        "upper_profile_width_region": _candidate_window(
            rows, *POLICY["candidate_upper_rows_fraction"], h, key="min_width"
        ),
        "maximum_outer_width_region": _candidate_window(
            rows, *POLICY["candidate_outer_width_rows_fraction"], h, key="max_width"
        ),
    }
    # These are source-image silhouette support intervals, not the table or
    # the girdle. In particular, the maximum projected width does not prove
    # the viewer is square to the stone or the camera is orthographic.
    return {
        "schema_version": SCHEMA,
        "source": {
            "sha256": source_sha256,
            "width_px": w,
            "height_px": h,
            "original_verified": source_sha256 == feasibility.ORIGINAL_PROFILE_SHA256 and (w, h) == feasibility.ORIGINAL_PROFILE_SIZE,
        },
        "policy": POLICY,
        "policy_sha256": feasibility.canonical_sha256(POLICY),
        "status": "review" if usable else "unavailable",
        "reason": (
            "external_contour_candidate_requires_anatomical_review"
            if usable else "external_contour_not_stably_supported"
        ),
        "background": {
            "reference_rgb": [float(round(x, 3)) for x in background],
            "corner_spread_95_rgb": round(background_spread, 3),
            "status": "candidate_background" if background_spread <= POLICY["background_color_variability_limit_rgb"] else "unavailable",
        },
        "outer_rows": rows,
        "qc": {
            "supported_row_count": len(supported),
            "sensitive_row_count": len(disputed),
            "analyzed_row_count": hi-lo,
            "sensitive_fraction_among_detected_rows": round(proportion, 5),
        },
        "anatomical_candidates": windows,
        "physical_landmark_status": {
            key: {"status": "unavailable", "reason": "no_independent_anatomical_correspondence"}
            for key in ("table", "girdle", "culet")
        },
        "projection_suitability": {
            "status": "not_assessed",
            "side_facets_visible": "unknown",
            "table_reference_calibrated": False,
            "camera_model": None,
        },
        "semantic_measurements": {
            side: {
                family: {"status": "unavailable", "apparent_angle_deg": None,
                         "physical_angle_deg": None,
                         "reason": "physical_facet_junction_not_established"}
                for family in feasibility.SLOTS
            }
            for side in feasibility.SIDES
        },
        "interpretation": (
            "Background-separated outer shape proposals only. Internal "
            "optical and virtual-facet lines play no part in this fit. "
            "No physical facet angles or verified table/girdle landmarks."
        ),
    }, rgb


def write_qc(image_path, output, expected_sha256=None):
    output = Path(output)
    payload, rgb = analyse_image(image_path, expected_sha256)
    output.mkdir(parents=True, exist_ok=True)
    (output / "outer-contour.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    overlay = Image.fromarray(rgb)
    draw = ImageDraw.Draw(overlay)
    left, right = [], []
    for row in payload["outer_rows"]:
        if row["status"] not in ("supported_candidate", "review"):
            continue
        color = (20, 210, 75) if row["status"] == "supported_candidate" else (255, 158, 28)
        y = row["y_px"]
        draw.point((row["left_x_px"], y), fill=color)
        draw.point((row["right_x_px"], y), fill=color)
    for name, item in payload["anatomical_candidates"].items():
        if item["region_xyxy_px"]:
            draw.rectangle(tuple(item["region_xyxy_px"]), outline=(45, 120, 255), width=1)
    overlay.save(output / "outer-contour-candidates.png")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-original", action="store_true")
    args = parser.parse_args()
    result = write_qc(
        args.image, args.output,
        feasibility.ORIGINAL_PROFILE_SHA256 if args.require_original else None
    )
    print(json.dumps({
        "status": result["status"],
        "verified_original": result["source"]["original_verified"],
        "qc": result["qc"],
        "anatomical_candidates": result["anatomical_candidates"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
