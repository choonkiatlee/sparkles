"""Target-blind profile-photo feasibility diagnostics for issue #91 / PR A.

This module intentionally DOES NOT infer facet identities or angles. Generic
line candidates and their visual evidence are the only fitted output. The
separate, future estimator may consume the frozen measurement contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

SCHEMA = "diamond360-asscher-profile-feasibility/1"
ORIGINAL_PROFILE_SHA256 = "0d0d87dfd9d4090dc21d03173b9260abe00556b40c6df05e19fad310fa0bd3a3"
ORIGINAL_PROFILE_SIZE = (410, 319)
SLOTS = ("P1", "P2", "P3", "C1")
SIDES = ("left", "right")

# Image-only specification. No reference/expert angle values or numeric targets.
POLICY = {
    "coordinate_system": "image_xy_origin_top_left_y_down",
    "geometry_coordinate_system": "pixels_centered_on_image",
    "input_color": "encoded_rgb_rec709_weighted_gray",
    "gaussian_sigma_px": 1.1,
    "roi_margin_fraction": 0.07,
    "edgel_percentile": 94.0,
    "hough_angle_min_deg": -75,
    "hough_angle_max_deg": 75,
    "hough_step_deg": 3,
    "hough_rho_bin_px": 1,
    "max_candidate_lines": 14,
    "peak_suppression_angle_deg": 6,
    "peak_suppression_rho_px": 9,
    "min_relative_vote": 0.23,
    "line_support_tolerance_px": 2.0,
    "max_connected_support_gap_px": 8.0,
    "min_connected_support_span_px": 18.0,
    "min_connected_support_edgels": 8,
    "landmark_policy": "proposals_only_no_semantic_assignment",
    "projection_policy": "not_assessed_until_side_facet_visibility_check",
    "ambiguity_policy": "all_facet_slots_unavailable_until_independent_extractor",
}


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _roi_bounds(width, height):
    margin = POLICY["roi_margin_fraction"]
    x0 = max(1, round(width * margin))
    y0 = max(1, round(height * margin))
    x1 = min(width - 1, round(width * (1.0 - margin)))
    y1 = min(height - 1, round(height * (1.0 - margin)))
    return x0, y0, x1, y1


def _edge_evidence(rgb):
    gray = np.asarray(rgb, np.float64) @ np.array([0.2126, 0.7152, 0.0722])
    smooth = ndi.gaussian_filter(gray, POLICY["gaussian_sigma_px"], mode="reflect")
    gx = ndi.sobel(smooth, axis=1, mode="reflect") / 8.0
    gy = ndi.sobel(smooth, axis=0, mode="reflect") / 8.0
    energy = np.hypot(gx, gy)
    h, w = gray.shape
    x0, y0, x1, y1 = _roi_bounds(w, h)
    roi = energy[y0:y1, x0:x1]
    cutoff = float(np.percentile(roi, POLICY["edgel_percentile"]))
    # A constant or extremely flat source must fail closed; never select
    # all pixels just because the quantile threshold happens to be zero.
    usable = bool(np.max(roi) > 1.0 / 255.0 and cutoff > 1e-8)
    mask = np.zeros((h, w), dtype=bool)
    if usable:
        mask[y0:y1, x0:x1] = roi >= cutoff
    return energy, mask, cutoff, [x0, y0, x1, y1]


def _line_segment(angle_deg, rho, width, height):
    """Clip -x*sin(a)+y*cos(a)=rho to the source image rectangle."""
    a = np.deg2rad(angle_deg)
    sin, cos = np.sin(a), np.cos(a)
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    candidates = []
    if abs(cos) > 1e-9:
        for x in (0.0, float(width - 1)):
            y = (rho + (x - cx) * sin) / cos + cy
            if -1e-8 <= y <= height - 1 + 1e-8:
                candidates.append((x, float(np.clip(y, 0, height - 1))))
    if abs(sin) > 1e-9:
        for y in (0.0, float(height - 1)):
            x = (cos * (y - cy) - rho) / sin + cx
            if -1e-8 <= x <= width - 1 + 1e-8:
                candidates.append((float(np.clip(x, 0, width - 1)), y))
    if len(candidates) < 2:
        return None
    # Pick farthest pair, avoiding duplicate intersections at corners.
    pairs = [
        (float(np.hypot(ax - bx, ay - by)), (ax, ay), (bx, by))
        for i, (ax, ay) in enumerate(candidates)
        for bx, by in candidates[i + 1:]
    ]
    _, p, q = max(pairs, key=lambda item: item[0])
    return [[round(float(v), 3) for v in p], [round(float(v), 3) for v in q]]


def _supported_segment(angle, rho, width, height, xs, ys, weights):
    """Return the strongest contiguous edge-supported portion of a Hough line.

    A Hough vote is global and may aggregate disconnected optical edges; an
    image-wide line is therefore not valid segment evidence. We use only
    measured nearby edgels and refuse candidates without sustained support.
    """
    theta = np.deg2rad(angle)
    tangent = np.array([np.cos(theta), np.sin(theta)])
    normal = np.array([-np.sin(theta), np.cos(theta)])
    centre = np.array([(width - 1) / 2.0, (height - 1) / 2.0])
    points = np.column_stack((xs, ys)).astype(float) - centre
    residual = np.abs(points @ normal - rho)
    supported = residual <= POLICY["line_support_tolerance_px"]
    if int(np.count_nonzero(supported)) < POLICY["min_connected_support_edgels"]:
        return None
    along = points[supported] @ tangent
    supported_weights = weights[supported]
    order = np.argsort(along, kind="stable")
    along, supported_weights = along[order], supported_weights[order]
    split = np.flatnonzero(np.diff(along) > POLICY["max_connected_support_gap_px"]) + 1
    groups = np.split(np.arange(len(along)), split)
    candidates = []
    for group in groups:
        if len(group) < POLICY["min_connected_support_edgels"]:
            continue
        lo, hi = float(along[group[0]]), float(along[group[-1]])
        span = hi - lo
        if span < POLICY["min_connected_support_span_px"]:
            continue
        candidates.append((float(np.sum(supported_weights[group])), span, len(group), lo, hi))
    if not candidates:
        return None
    strength, span, count, lo, hi = max(candidates)
    endpoints = []
    for t in (lo, hi):
        pt = centre + normal * rho + tangent * t
        endpoints.append([round(float(v), 3) for v in pt])
    if any(
        x < -2.1 or x > width + 1.1 or y < -2.1 or y > height + 1.1
        for x, y in endpoints
    ):
        return None
    endpoints = [
        [round(float(np.clip(x, 0, width - 1)), 3),
         round(float(np.clip(y, 0, height - 1)), 3)]
        for x, y in endpoints
    ]
    return {
        "supported_segment_xy_px": endpoints,
        "support_edgel_count": int(count),
        "support_span_px": round(span, 3),
        "support_vote_strength": round(strength, 6),
        "support_policy": "strongest_connected_run_not_full_hough_line",
    }


def _line_candidates(energy, mask):
    h, w = energy.shape
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    px = xs.astype(float) - cx
    py = ys.astype(float) - cy
    weights = energy[ys, xs]
    max_rho = int(np.ceil(np.hypot(w, h))) + 2
    angles = np.arange(
        POLICY["hough_angle_min_deg"],
        POLICY["hough_angle_max_deg"] + 1,
        POLICY["hough_step_deg"],
    )
    rows = []
    for angle in angles:
        theta = np.deg2rad(angle)
        rhos = np.rint(-px * np.sin(theta) + py * np.cos(theta)).astype(int)
        accumulator = np.bincount(
            np.clip(rhos + max_rho, 0, 2 * max_rho),
            weights=weights,
            minlength=2 * max_rho + 1,
        )
        peaks = np.flatnonzero(
            (accumulator == ndi.maximum_filter1d(accumulator, size=13))
            & (accumulator > 0)
        )
        for index in peaks:
            score = float(accumulator[index])
            rows.append((score, int(angle), int(index - max_rho)))
    if not rows:
        return []
    rows.sort(key=lambda item: (-item[0], item[1], item[2]))
    maximum = rows[0][0]
    selected = []
    for score, angle, rho in rows:
        if score < POLICY["min_relative_vote"] * maximum:
            break
        if any(
            abs(angle - old["image_line_angle_deg"]) <= POLICY["peak_suppression_angle_deg"]
            and abs(rho - old["signed_normal_offset_px"]) <= POLICY["peak_suppression_rho_px"]
            for old in selected
        ):
            continue
        segment = _supported_segment(angle, rho, w, h, xs, ys, weights)
        if segment is None:
            continue
        selected.append({
            "candidate_id": "line-%02d" % (len(selected) + 1),
            "status": "candidate_only",
            "image_line_angle_deg": int(angle),
            "signed_normal_offset_px": int(rho),
            "vote_strength": round(score, 6),
            "relative_vote": round(score / maximum, 6),
            **segment,
            "facet_identity": None,
            "evidence_type": "weighted_gradient_hough",
        })
        if len(selected) >= POLICY["max_candidate_lines"]:
            break
    return selected


def _horizontal_band_proposals(lines, width, height):
    """Image-coordinate hypotheses, not table/girdle identification.

    These are only centrally located horizontal edge runs at coarse height
    ranges. The geometry intervals are deliberately broad and no candidate
    is assigned a physical facet or final anatomical identity.
    """
    proposals = {}
    for name, lo, hi in (
        ("upper_central_band", 0.15, 0.38),
        ("lower_central_band", 0.60, 0.78),
    ):
        eligible = []
        for line in lines:
            if abs(line["image_line_angle_deg"]) > 3:
                continue
            (x0, y0), (x1, y1) = line["supported_segment_xy_px"]
            xmid, ymid = (x0 + x1) / 2, (y0 + y1) / 2
            if (
                lo * height <= ymid <= hi * height
                and 0.23 * width <= xmid <= 0.77 * width
                and line["support_span_px"] >= 0.10 * width
            ):
                eligible.append(line)
        best = max(eligible, key=lambda x: (x["support_span_px"], x["support_vote_strength"])) if eligible else None
        proposals[name] = {
            "status": "candidate_only" if best else "unavailable",
            "line_candidate_id": best["candidate_id"] if best else None,
            "reason": "coarse_vertical_position_only_anatomy_not_confirmed",
        }
    return proposals


def _empty_slots():
    return {
        side: {
            facet: {
                "status": "unavailable",
                "provenance": "not_measured_pr_a",
                "reason": "semantic_line_assignment_deferred_to_pr_b",
                "apparent_angle_deg": None,
                "uncertainty_deg": None,
                "image_support": [],
                "fit_residual_px": None,
            }
            for facet in SLOTS
        }
        for side in SIDES
    }


def analyse_image(image_path, expected_sha256=None):
    """Produce generic image evidence; never load expert comparison targets."""
    image_path = Path(image_path)
    image_sha = _hash_file(image_path)
    if expected_sha256 is not None and image_sha != expected_sha256:
        raise ValueError("source image SHA-256 differs from required original")
    with Image.open(image_path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    if min(width, height) < 64:
        raise ValueError("profile diagnostic requires at least 64 pixels per axis")
    energy, mask, cutoff, roi = _edge_evidence(rgb)
    lines = _line_candidates(energy, mask)
    edgels = np.column_stack(np.nonzero(mask))
    if len(edgels):
        ylo, xlo = np.percentile(edgels, 5, axis=0)
        yhi, xhi = np.percentile(edgels, 95, axis=0)
        activity_box = [round(float(v), 2) for v in (xlo, ylo, xhi, yhi)]
    else:
        activity_box = None
    status = "review" if lines else "unavailable"
    return {
        "schema_version": SCHEMA,
        "purpose": "image_only_profile_feasibility_not_facet_angle_extraction",
        "source": {
            "sha256": image_sha,
            "width_px": width,
            "height_px": height,
            "role": "candidate_profile_photo",
            "archived_original_match": (
                image_sha == ORIGINAL_PROFILE_SHA256
                and (width, height) == ORIGINAL_PROFILE_SIZE
            ),
        },
        "policy": POLICY,
        "policy_sha256": canonical_sha256(POLICY),
        "status": status,
        "status_reasons": (
            ["generic_lines_detected_but_semantic_assignment_unassessed"]
            if lines else ["insufficient_generic_edge_evidence"]
        ),
        "image_evidence": {
            "roi_xyxy_px": roi,
            "gradient_threshold": round(cutoff, 8),
            "selected_edgel_count": int(np.count_nonzero(mask)),
            "activity_bbox_xyxy_px": activity_box,
            "activity_bbox_semantics": "edge_activity_only_not_verified_silhouette",
            "line_candidates": lines,
            "horizontal_band_proposals": _horizontal_band_proposals(lines, width, height),
        },
        "landmark_assessment": {
            name: {
                "status": "not_assessed",
                "reason": "candidate_edges_are_not_anatomically_identified_in_pr_a",
            }
            for name in ("table", "girdle", "outline", "culet")
        },
        "projection_suitability": {
            "status": "not_assessed",
            "reasons": [
                "table_level_not_yet_verified",
                "pavilion_side_facet_visibility_not_yet_verified",
                "camera_projection_not_calibrated",
            ],
        },
        "semantic_measurements": _empty_slots(),
    }, rgb, energy


def write_diagnostics(image_path, output, expected_sha256=None):
    payload, rgb, energy = analyse_image(image_path, expected_sha256)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "profile-feasibility.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    scale = max(float(np.percentile(energy, 99.0)), 1e-12)
    edge_pixels = np.uint8(np.clip(energy / scale * 255, 0, 255))
    Image.fromarray(edge_pixels, mode="L").save(output / "gradient-evidence.png")
    overlay = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(overlay)
    for line in payload["image_evidence"]["line_candidates"]:
        # Only supported finite spans: global Hough lines exaggerate evidence.
        ends = [tuple(p) for p in line["supported_segment_xy_px"]]
        draw.line(ends, fill=(255, 60, 70), width=2)
    # Box is just edge activity, emphatically not a fitted diamond silhouette.
    bbox = payload["image_evidence"]["activity_bbox_xyxy_px"]
    if bbox:
        draw.rectangle(tuple(bbox), outline=(35, 210, 110), width=1)
    overlay.save(output / "unassigned-line-candidates.png")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-original", action="store_true")
    args = parser.parse_args()
    result = write_diagnostics(
        args.image, args.output,
        ORIGINAL_PROFILE_SHA256 if args.require_original else None,
    )
    print(json.dumps({
        "status": result["status"],
        "archived_original_match": result["source"]["archived_original_match"],
        "candidate_count": len(result["image_evidence"]["line_candidates"]),
        "source_sha256": result["source"]["sha256"],
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
