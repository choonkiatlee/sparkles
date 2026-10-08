"""Target-blind factor ablation for the #96 LG756520111 frame-16 failure.

This diagnoses, but never changes, the frozen #96 estimator. All counterfactual
fits use its exact edge estimator and octagon consensus: change only which input
frames contribute to (a) outer silhouette vs (b) inner radial evidence.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_outer_octagon as outer_octagon
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-frame-ablation/1"
CERTIFICATE = "IGI-LG756520111"
OMIT_SOURCE_INDEX = 16


def _outer(masks, metadata):
    return outer_octagon.fit_consensus(masks, frame_metadata=metadata)


def _inner(evidence, u, metadata, outer_fit, gauge_id):
    result = wireframe.fit_from_sector_evidence(
        evidence, u, gauge_id=gauge_id,
        frame_metadata=metadata,
        outer_vertices=np.asarray(outer_fit["vertices_topology_order"], float),
        outer_confidence=outer_fit["confidence"],
    )
    result["selected_frames"] = metadata
    result["outer_evidence"] = outer_fit
    return result


def _metric(reference, candidate):
    if reference.get("scaffold") is None or candidate.get("scaffold") is None:
        return {"status": "unavailable", "reasons": ["missing_scaffold"]}
    return validation.compare_scaffolds(
        reference["scaffold"], candidate["scaffold"]
    )


def _boundary_summary(result):
    return {
        name: {
            "global_u": value.get("global_u"),
            "sector_support": value.get("sector_support"),
            "confidence": value.get("confidence"),
            "sector_u_step_order": value.get("sector_u_step_order"),
        }
        for name, value in result.get("boundary_evidence", {}).items()
    }


def _outer_summary(result):
    outer = result.get("outer_evidence") or {}
    return {
        "confidence": outer.get("confidence"),
        "median_vertex_rms": outer.get("median_vertex_rms"),
        "max_vertex_rms": outer.get("max_vertex_rms"),
        "per_frame": outer.get("per_frame"),
    }


def _comparison(reference, result):
    comparison = _metric(reference, result)
    outer_ref = reference.get("outer_evidence")
    outer_new = result.get("outer_evidence")
    outer_rms = None
    outer_max = None
    if outer_ref and outer_new:
        a = np.asarray(outer_ref["vertices_topology_order"], float)
        b = np.asarray(outer_new["vertices_topology_order"], float)
        vertex_distances = np.linalg.norm(a - b, axis=1)
        outer_rms = float(np.sqrt(np.mean(vertex_distances ** 2)))
        outer_max = float(np.max(vertex_distances))
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "selected_source_indices": [
            row.get("source_index") for row in result.get("selected_frames", [])
        ],
        "scaffold_review_reasons": (
            (result.get("scaffold") or {}).get("review_reasons")
        ),
        "boundaries": _boundary_summary(result),
        "outer": _outer_summary(result),
        "outer_vertex_rms_delta_from_full_u": outer_rms,
        "outer_vertex_max_delta_from_full_u": outer_max,
        "validation_status": comparison.get("status"),
        "validation_reasons": comparison.get("reasons"),
        "boundary_displacement": {
            key: {
                "mean_u": row.get("mean_displacement_u"),
                "max_u": row.get("max_displacement_u"),
                "max_local_tier_fraction": row.get(
                    "max_displacement_tier_fraction"
                ),
            }
            for key, row in comparison.get("boundary_displacement", {}).items()
        },
        "semantic_identity_consistency": (
            comparison.get("identity") or {}
        ).get("consistent"),
    }


def analyse_pose(pose_output, omit_source_index=OMIT_SOURCE_INDEX):
    """One 2×2 factor ablation; no frame reselection or parameter tuning."""
    validation.assert_frozen_method(validation.OUTER_METHOD)
    pose_output = Path(pose_output)
    pose = json.loads((pose_output / "asscher-pose.json").read_text())
    full, selected, _, _ = stability._primary_fit(
        pose_output, pose, method=validation.OUTER_METHOD
    )
    full_ids = [item["source_index"] for item in selected]
    if full.get("scaffold") is None:
        raise ValueError("frozen primary geometry is unavailable")
    if full_ids.count(omit_source_index) != 1:
        raise ValueError("omit index is not uniquely in frozen selection")
    subset = [r for r in selected if r["source_index"] != omit_source_index]
    if len(subset) < wireframe.MIN_GEOMETRY_FRAMES:
        raise ValueError("insufficient leave-one-out views")

    evidence_all, u, masks_all, _, meta_all = stability._load_evidence(
        pose_output, selected
    )
    evidence_without, u2, masks_without, _, meta_without = (
        stability._load_evidence(pose_output, subset)
    )
    if not np.array_equal(u, u2):
        raise ValueError("evidence radial grids disagree")
    outer_full = full["outer_evidence"]
    outer_without = _outer(masks_without, meta_without)
    gauge_id = full["semantic_gauge_id"]

    # 2×2 design: outer mask set × inner photometric evidence set.
    # Recomputing the full and leave-out arms is intentionally a reproducibility
    # check against the frozen #115 experiment, not a fitting modification.
    cases = {
        "full_outer_full_inner": full,
        "full_outer_without_inner": _inner(
            evidence_without, u, meta_without, outer_full, gauge_id
        ),
        "without_outer_full_inner": _inner(
            evidence_all, u, meta_all, outer_without, gauge_id
        ),
        "without_outer_without_inner": _inner(
            evidence_without, u, meta_without, outer_without, gauge_id
        ),
    }
    summary = {
        "schema_version": SCHEMA,
        "method": validation.frozen_method_record(validation.OUTER_METHOD),
        "certificate": CERTIFICATE,
        "omitted_source_index": int(omit_source_index),
        "full_selected_source_indices": full_ids,
        "without_selected_source_indices": [
            r["source_index"] for r in subset
        ],
        "factor_design": {
            "rows": "outer octagon fitted from all vs without omitted source",
            "columns": "inner radial evidence from all vs without omitted source",
            "fixed": "all #96 thresholds, topology, #80 sequence gauge, "
                     "primary selected frame list and source pixels",
            "no_reselection": True,
            "interpretation": "diagnostic counterfactual, not independent "
                              "physical geometry truth or an adopted method",
        },
        "cases": {
            key: _comparison(full, result)
            for key, result in cases.items()
        },
    }
    return summary, cases, selected


def _confirm_frozen_reference(summary, reference_dir):
    """Fail closed if the processed source does not reproduce the #115 run."""
    folder = Path(reference_dir) / "per-stone" / CERTIFICATE
    full = json.loads((folder / "primary-wireframe.json").read_text())
    ablated = json.loads(
        (folder / "stability" / "leave-out-0016-wireframe.json").read_text()
    )
    for case_id, expected in [
        ("full_outer_full_inner", full),
        ("without_outer_without_inner", ablated),
    ]:
        case = summary["cases"][case_id]
        expected_indices = [
            r["source_index"] for r in expected["selected_frames"]
        ]
        if case["selected_source_indices"] != expected_indices:
            raise RuntimeError(
                f"{case_id}: frozen #115 selection changed"
            )
        if case["status"] != expected["status"]:
            raise RuntimeError(f"{case_id}: frozen #115 status changed")
        for boundary in ("C1_C2", "C2_C3", "C3_TABLE"):
            actual = case["boundaries"][boundary]["global_u"]
            original = expected["boundary_evidence"][boundary]["global_u"]
            if not np.isclose(actual, original, atol=1e-9, rtol=0):
                raise RuntimeError(
                    f"{case_id}: frozen #115 {boundary} changed"
                )


def _labelled_panel(image, title, subtitle, width=340):
    image = image.convert("RGB")
    image.thumbnail((width, width), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, width + 54), "white")
    x = (width - image.width) // 2
    y = 54 + (width - image.height) // 2
    canvas.paste(image, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 7), title, fill="black")
    draw.text((8, 28), subtitle, fill="black")
    return canvas


def write_qc(pose_output, processed, selected, cases, output):
    """Native RGB QC: one common source frame, four unchanged fitted rulers."""
    shared = next(
        r for r in selected if r["source_index"] != OMIT_SOURCE_INDEX
    )
    brightness, mask, _ = stability._load_gauged_arrays(pose_output, shared)
    titles = [
        ("full_outer_full_inner", "Full outer + full inner"),
        ("full_outer_without_inner", "Full outer + omit-16 inner"),
        ("without_outer_full_inner", "Omit-16 outer + full inner"),
        ("without_outer_without_inner", "Omit-16 outer + omit-16 inner"),
    ]
    panels = []
    for key, title in titles:
        result = cases[key]
        if result.get("scaffold") is None:
            image = Image.new("RGB", (320, 320), "gray")
        else:
            image = wireframe._draw_scaffold_on_source(
                processed, shared, mask, result["scaffold"]
            )
            if image is None:
                image = wireframe._draw_scaffold_on_frame(
                    brightness, mask, result["scaffold"]
                )
        e = result.get("boundary_evidence", {}).get("C3_TABLE", {})
        subtitle = f"C3_TABLE u={e.get('global_u', 'missing'):.3f}" if e else (
            "C3_TABLE unavailable"
        )
        panels.append(_labelled_panel(image, title, subtitle))
    canvas = Image.new("RGB", (680, 788), "white")
    for i, item in enumerate(panels):
        canvas.paste(item, ((i % 2) * 340, (i // 2) * 394))
    output = Path(output)
    canvas.save(output, quality=93)
    return output.name, shared["source_index"]


def run(source_root, source_manifest, output, *, reference_dir=None):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    source_root, source_manifest = Path(source_root), Path(source_manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sparkles-frame-ablation-") as tmp:
        processed = Path(tmp) / "processed"
        pose_output = Path(tmp) / "pose"
        pipeline.run(
            source_root, processed, source_manifest,
            gain=1.0, accept_review=True,
        )
        analyse_processed_sequence(
            processed, pose_output, persist_canonical=True
        )
        summary, cases, selected = analyse_pose(pose_output)
        if reference_dir is not None:
            _confirm_frozen_reference(summary, reference_dir)
            summary["frozen_115_reproduction_checked"] = True
        else:
            summary["frozen_115_reproduction_checked"] = False
        qc_path, qc_source = write_qc(
            pose_output, processed, selected, cases, output / "factor-qc.jpg"
        )
        summary["qc_path"] = qc_path
        summary["qc_reference_source_index"] = qc_source
        (output / "diagnostic.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()
    report = run(
        args.source_root, args.source_manifest, args.output,
        reference_dir=args.reference_dir,
    )
    for name, row in report["cases"].items():
        d = row.get("boundary_displacement", {}).get("C3_TABLE", {})
        print(name, row["status"],
              "C3_TABLE", row["boundaries"].get("C3_TABLE", {}).get("global_u"),
              "max tier delta", d.get("max_local_tier_fraction"),
              "outer max", row["outer_vertex_max_delta_from_full_u"])


if __name__ == "__main__":
    main()
