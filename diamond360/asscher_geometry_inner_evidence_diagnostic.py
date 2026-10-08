"""Frozen inner-step evidence / silhouette-normalisation audit for #124.

Diagnostic-only: never changes the #96 estimator, its segmentation, or the
meaning of an image contrast line. Both hypothesis peaks and silhouette
differences are observational evidence, not polished facet labels.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.signal import find_peaks

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_steps as steps
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-inner-evidence-diagnostic/1"
FOCUS = "IGI-LG756520111"
OMIT_SOURCE = 16
# Predeclared physical/optical separation: inner-edge locations are hypotheses.
C3_WINDOW = (0.42, 0.60)
PEAK_COUNT = 3


def _finite_float(value):
    return float(value) if np.isfinite(value) else None


def _nullable(values):
    """JSON-safe NaN masking without silently inventing zero edge evidence."""
    x = np.asarray(values, float)
    if x.ndim == 1:
        return [float(v) if np.isfinite(v) else None for v in x]
    if x.ndim == 2:
        return [_nullable(row) for row in x]
    raise ValueError("expected one or two-dimensional evidence")


def candidate_rows(template):
    """Replay discover_template's *unchanged* C3 candidate score."""
    values = [r["prominence"] for r in template.get("candidates", [])]
    positive = [float(v) for v in values if v > 0]
    scale = max(float(np.median(positive)) if positive else 0.0, 1e-6)
    result = []
    for row in template.get("candidates", []):
        u = float(row["u"])
        if not C3_WINDOW[0] <= u <= C3_WINDOW[1]:
            continue
        support = float(row["sector_support"])
        prominence = float(row["prominence"])
        result.append({
            "u": u,
            "index": int(row["index"]),
            "prominence": prominence,
            "sector_support": support,
            "selection_score": float(np.log1p(prominence / scale) + 1.25 * support),
            "eligible": support >= .25,
            "sector_peak_u": [
                None if p is None else p.get("u")
                for p in row["sector_peaks"]
            ],
        })
    return sorted(result, key=lambda r: -r["selection_score"])


def template_summary(data, u):
    template = steps.discover_template(data, u)
    selected = None
    if template.get("controls"):
        selected = float(template["controls"][0]["global_u"])
    else:
        part = template.get("partial_controls") or {}
        if "centre_inner" in part:
            selected = float(part["centre_inner"]["global_u"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sector_medians = np.nanmedian(np.asarray(data, float), axis=0)
        raw = np.nanmedian(sector_medians, axis=0)
    return {
        "status": template["status"],
        "reason": template.get("reason"),
        "c3_selected_global_u": selected,
        "c3_candidates": candidate_rows(template),
        "consensus_profile": _nullable(template["consensus"]),
        "raw_sector_median_profile": _nullable(raw),
        "per_sector_evidence": _nullable(sector_medians),
    }


def _peaks(profile, u):
    """Descriptive per-frame/sector peaks, not semantic facet assignments."""
    values = np.asarray(profile, float)
    allowed = (u >= C3_WINDOW[0]) & (u <= C3_WINDOW[1])
    ids = np.flatnonzero(allowed & np.isfinite(values))
    if len(ids) < 3:
        return []
    v = values[ids]
    found, _ = find_peaks(v, distance=3)
    if not len(found):
        found = np.asarray([int(np.argmax(v))])
    zs = steps._robust_z(values)
    ranked = sorted(found, key=lambda i: -v[i])[:PEAK_COUNT]
    return [{
        "u": float(u[ids[i]]),
        "evidence": float(v[i]),
        "z": _finite_float(zs[ids[i]]),
    } for i in ranked]


def _rms_fraction(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if a.shape != b.shape or np.any(b <= 0):
        return None
    return float(np.sqrt(np.mean(((a - b) / b) ** 2)))


def inspect_evidence(records, pose_output, focus_index=OMIT_SOURCE):
    """Audit selected frames in a single #80 gauge, without re-fitting."""
    if len(records) < 3:
        raise ValueError("at least three frozen selected records needed")
    frames, outlines = [], []
    common_u = None
    for record in records:
        brightness, mask, valid = stability._load_gauged_arrays(pose_output, record)
        u, sector = stability.wireframe.extract_sector_evidence(
            brightness, mask, valid
        )
        if common_u is None:
            common_u = u
        elif not np.allclose(common_u, u):
            raise ValueError("incompatible radial grid")
        angles = np.linspace(0, 2 * np.pi, 96, endpoint=False)
        _, contour, _, _ = steps._ray_geometry(mask, angles)
        outlines.append(contour)
        norm = (record.get("canonical") or {}).get("normalization") or {}
        fit = ((record.get("canonical") or {}).get("registered_outline") or {})
        assess = (record.get("assessment") or {}).get("outline") or {}
        frames.append({
            "source_index": record["source_index"],
            "position": record.get("position"),
            "sequence_gauge_quarter_turn": (
                (record.get("sequence_coordinate") or {}).get("gauge_quarter_turn")
            ),
            "registered_orientation_deg_mod_90": fit.get(
                "orientation_deg_mod_90"
            ),
            "source_centre_xy": norm.get("source_centre_xy"),
            "source_centroid_yx": norm.get("source_centroid_yx"),
            "isotropic_scale": norm.get("isotropic_scale"),
            "normalization_type": norm.get("transform_type"),
            "rectification": norm.get("rectification"),
            "source_outline_aspect_ratio": assess.get("aspect_ratio"),
            "source_outline_residual": assess.get(
                "normalized_q90_boundary_residual"
            ),
            "sector_evidence": sector,
        })
    med = np.median(np.stack(outlines), axis=0)
    for record, contour in zip(frames, outlines):
        record["silhouette_ray_rms_fraction_of_median"] = _rms_fraction(
            contour, med
        )
        record["silhouette_ray_max_abs_fraction_of_median"] = float(
            np.max(np.abs(contour / med - 1.0))
        )
        record["silhouette_ray_radius_px"] = contour.tolist()
    evidence = np.stack([r.pop("sector_evidence") for r in frames])
    full = template_summary(evidence, common_u)
    omitted = next((i for i, row in enumerate(frames)
                    if row["source_index"] == focus_index), None)
    if omitted is not None and len(frames) >= 4:
        without = template_summary(
            np.delete(evidence, omitted, axis=0), common_u
        )
    else:
        without = None
    for row, frame_evidence in zip(frames, evidence):
        row["c3_per_sector_top_peaks"] = [
            _peaks(frame_evidence[sector], common_u)
            for sector in range(8)
        ]
        row["c3_peak_support_at_full_and_omitted_u"] = {}
        targets = {
            "full": full["c3_selected_global_u"],
            "without": None if without is None else without["c3_selected_global_u"],
        }
        for label, target in targets.items():
            if target is None:
                continue
            local = [
                steps._local_peak(frame_evidence[sector], common_u, target, radius=.025)
                for sector in range(8)
            ]
            row["c3_peak_support_at_full_and_omitted_u"][label] = [
                None if p is None else {
                    "u": p["u"], "evidence": p["evidence"], "z": p["z"],
                }
                for p in local
            ]
    return {
        "schema_version": SCHEMA,
        "selected_source_indices": [r["source_index"] for r in frames],
        "with_all": full,
        "without_focus_frame": without,
        "focus_source_index": focus_index,
        "radial_grid_u": common_u.tolist(),
        "silhouette_median_ray_radius_px": med.tolist(),
        "frames": frames,
        "hypothesis": (
            "silhouette-normalized inner edges may vary because canonical "
            "registration is a similarity transform, not projective rectification"
        ),
        "limitations": (
            "A stable silhouette is not proof that a bright/dark interior line "
            "belongs to a polished facet. Apparent radial peak migration may "
            "reflect virtual/reflected facets, projection or true asymmetry."
        ),
    }


def _graph(result, path):
    """Fixed-axis, target-blind overlay of both candidate modes and frame traces."""
    width, height = 1150, 640
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = 75, 60, 1100, 540
    u = np.asarray(result["radial_grid_u"], float)
    all_data = np.asarray(result["with_all"]["consensus_profile"], float)
    without = result["without_focus_frame"]
    wo_data = (None if without is None else
               np.asarray(without["consensus_profile"], float))
    in_window = (u >= .36) & (u <= .66)
    hi = max(
        float(np.nanmax(all_data[in_window])),
        float(np.nanmax(wo_data[in_window])) if wo_data is not None else 0,
        1e-6,
    ) * 1.1
    def xy(xx, yy):
        return (
            int(left + (float(xx) - .36) / .30 * (right - left)),
            int(bottom - min(max(float(yy), 0), hi) / hi * (bottom - top)),
        )
    draw.line((left, bottom, right, bottom), fill="black", width=2)
    draw.line((left, top, left, bottom), fill="black", width=2)
    for values, color in ((all_data, (30, 70, 170)),
                          (wo_data, (190, 75, 35))):
        if values is None:
            continue
        pts = [xy(uu, vv) for uu, vv in zip(u[in_window], values[in_window])]
        draw.line(pts, fill=color, width=3)
    for label, result_case, color in (
        ("full", result["with_all"], (30, 70, 170)),
        ("omit", without, (190, 75, 35)),
    ):
        if result_case is None or result_case["c3_selected_global_u"] is None:
            continue
        target = result_case["c3_selected_global_u"]
        x = xy(target, 0)[0]
        draw.line((x, top, x, bottom), fill=color, width=2)
        draw.text((x + 5, top + (0 if label == "full" else 20)),
                  f"{label} u={target:.3f}", fill=color)
    draw.text((75, 10),
              "Frozen #96 median radial evidence: all 5 (blue) / omit 16 (orange)",
              fill="black")
    draw.text((75, 568),
              "Image-space contrast only. Neither peak is established as a physical facet boundary.",
              fill="black")
    draw.text((75, 594),
              "Canonical normalization is similarity only; no projective square-on rectification.",
              fill="black")
    img.save(path)


def confirm_reference(report, reference_dir):
    """Fail closed if the frozen #115 source/fit baseline cannot be replayed."""
    root = Path(reference_dir) / "per-stone" / FOCUS
    reference = json.loads((root / "primary-wireframe.json").read_text())
    ablated = json.loads(
        (root / "stability" / "leave-out-0016-wireframe.json").read_text()
    )
    if report["selected_source_indices"] != [
        row["source_index"] for row in reference["selected_frames"]
    ]:
        raise RuntimeError("selected source indices differ from frozen #115")
    for label, observed, original in (
        ("all", report["with_all"]["c3_selected_global_u"], reference),
        ("without", (
            report["without_focus_frame"] or {}
        ).get("c3_selected_global_u"), ablated),
    ):
        expected = original["boundary_evidence"]["C3_TABLE"]["global_u"]
        if observed is None or not np.isclose(
            observed, expected, rtol=0, atol=1e-9
        ):
            raise RuntimeError(
                f"{label} C3 boundary does not reproduce frozen #115: "
                f"{observed} vs {expected}"
            )
    return True


def run(source, source_manifest, output, *, reference_dir=None):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sparkles-inner-evidence-") as tmp:
        work = Path(tmp)
        processed, pose_dir = work / "processed", work / "pose"
        pipeline.run(Path(source), processed, Path(source_manifest),
                     gain=1.0, accept_review=True)
        pose = analyse_processed_sequence(
            processed, pose_dir, persist_canonical=True
        )
        primary, selected, _, _ = stability._primary_fit(
            pose_dir, pose, method=validation.OUTER_METHOD
        )
        report = inspect_evidence(selected, pose_dir)
        report["method"] = validation.frozen_method_record(validation.OUTER_METHOD)
        report["primary_status"] = primary.get("status")
        report["primary_reason"] = primary.get("reason")
        report["primary_c3_table_global_u"] = (
            (primary.get("boundary_evidence") or {}).get("C3_TABLE", {}).get("global_u")
        )
        if reference_dir is not None:
            confirm_reference(report, reference_dir)
            report["frozen_115_reproduction_checked"] = True
        else:
            report["frozen_115_reproduction_checked"] = False
        report["frozen_estimator_unchanged"] = True
        _graph(report, output / "c3-evidence-modes.png")
        report["qc_path"] = "c3-evidence-modes.png"
        (output / "diagnostic.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()
    r = run(args.source_root, args.source_manifest, args.output,
            reference_dir=args.reference_dir)
    print("selected", r["selected_source_indices"])
    print("C3 table full", r["with_all"]["c3_selected_global_u"])
    other = r["without_focus_frame"]
    print("C3 table without", other["c3_selected_global_u"] if other else None)
    for f in r["frames"]:
        print("frame", f["source_index"],
              "outline_rms_fraction", f["silhouette_ray_rms_fraction_of_median"],
              "rotation_deg", f["registered_orientation_deg_mod_90"])


if __name__ == "__main__":
    main()
