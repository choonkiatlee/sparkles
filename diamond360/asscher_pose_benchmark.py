"""Four-stone real-sequence benchmark for Asscher frame suitability."""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from . import pipeline, qc
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-pose-benchmark/1"


def _frame_summary(record):
    assessment = record["assessment"]
    components = assessment.get("components", {})
    face = assessment.get("face_orientation_cues", {})
    return {
        "source_index": record.get("source_index"),
        "rank": record.get("rank"),
        "status": assessment["status"],
        "score": assessment["score"],
        "reasons": assessment.get("reasons", []),
        "projection_consistency": components.get(
            "projection_consistency", {}
        ).get("score"),
        "opposite_parallelism_deg": components.get(
            "opposite_parallelism", {}
        ).get("value"),
        "outline_fit_residual": components.get(
            "outline_fit", {}
        ).get("value"),
        "squareness_error": components.get(
            "squareness", {}
        ).get("value"),
        "corner_imbalance": components.get(
            "corner_balance", {}
        ).get("value"),
        "central_radial_spoke_score": face.get(
            "central_radial_spoke_score"
        ),
        "central_ring_edge_score": face.get(
            "central_ring_edge_score"
        ),
        "table_boundary_angular_entropy": face.get(
            "table_boundary_angular_entropy"
        ),
        "table_boundary_continuity_score": face.get(
            "table_boundary_continuity_score"
        ),
        "centre_gradient_ratio": face.get(
            "centre_gradient_ratio"
        ),
        "central_diagonal_spoke_energy_ratio": face.get(
            "central_diagonal_spoke_energy_ratio"
        ),
        "central_diagonal_to_cardinal_energy_ratio": face.get(
            "central_diagonal_to_cardinal_energy_ratio"
        ),
    }


def _render_reference_faces(processed, pose_output, payload, source_indices=(0, 128)):
    """Render independent benchmark anchors for crown/opposite-face review."""
    items = []
    lookup = {
        record.get("source_index"): record
        for record in payload["frames"]
    }
    for source_index in source_indices:
        record = lookup.get(source_index)
        if record is None or not record.get("source_camera_path"):
            continue
        rgb = np.asarray(
            Image.open(
                Path(processed) / record["source_camera_path"]
            ).convert("RGB")
        )
        assessment = record["assessment"]
        items.append(
            (
                (
                    f"{source_index} rank {record.get('rank')} "
                    f"{assessment['status']} {assessment['score']:.2f}"
                ),
                qc.asscher_pose_overlay(rgb, assessment),
            )
        )
    if not items:
        return None
    destination = Path(pose_output) / "reference-faces.jpg"
    qc.contact_sheet(items, destination, columns=2)
    return destination.name


def _reference_face_metrics(payload, source_indices=(0, 128)):
    lookup = {
        record.get("source_index"): record
        for record in payload["frames"]
    }
    return {
        str(source_index): (
            None
            if source_index not in lookup
            else _frame_summary(lookup[source_index])
        )
        for source_index in source_indices
    }



def _sequence_coordinate_summary(payload):
    gauge = payload.get("sequence_gauge") or {}
    phase = gauge.get("phase") or {}
    orientation = gauge.get("orientation_gauge") or {}
    frames = payload.get("frames", [])

    phases = [
        record.get("sequence_coordinate", {}).get(
            "rotation_phase_0_360_deg"
        )
        for record in frames
    ]
    available_phases = [
        float(value) for value in phases if value is not None
    ]
    period = float(phase.get("period_deg") or 360.0)
    nominal_step = phase.get("nominal_step_deg")
    phase_step_errors = []
    if (
        nominal_step is not None
        and len(available_phases) == len(frames)
        and len(frames) > 1
    ):
        expected = (
            float(nominal_step)
            * int(phase.get("direction_sign", 1))
        ) % period
        for first, second in zip(
            available_phases,
            available_phases[1:] + available_phases[:1],
        ):
            observed = (second - first) % period
            phase_step_errors.append(abs(observed - expected))

    gauge_frames = [
        record.get("sequence_coordinate", {})
        for record in frames
        if record.get("canonical") is not None
    ]
    transform_available = sum(
        row.get("camera_to_sequence_gauge_xy") is not None
        for row in gauge_frames
    )
    quarter_turns = [
        row.get("gauge_quarter_turn")
        for row in gauge_frames
        if row.get("gauge_quarter_turn") is not None
    ]
    return {
        "phase_status": phase.get("status"),
        "phase_reference_position": phase.get("reference_position"),
        "nominal_step_deg": nominal_step,
        "phase_frame_count": len(available_phases),
        "maximum_phase_step_error_deg": (
            None if not phase_step_errors else max(phase_step_errors)
        ),
        "orientation_gauge_status": orientation.get("status"),
        "orientation_reference_position": orientation.get(
            "reference_position"
        ),
        "orientation_physically_unique": orientation.get(
            "physically_unique"
        ),
        "equivalent_global_quarter_turns": orientation.get(
            "equivalent_global_quarter_turns"
        ),
        "orientation_observation_count": orientation.get(
            "observation_count"
        ),
        "maximum_neighbor_branch_jump_deg": orientation.get(
            "maximum_neighbor_branch_jump_deg"
        ),
        "closure_jump_deg": orientation.get("closure_jump_deg"),
        "gauge_transform_count": transform_available,
        "canonical_frame_count": len(gauge_frames),
        "selected_quarter_turns": sorted(set(quarter_turns)),
    }


def _validate_sequence_coordinate_contract(payload):
    summary = _sequence_coordinate_summary(payload)
    if summary["phase_status"] not in ("available", "review"):
        raise ValueError(
            "benchmark sequence must expose declared viewer phase"
        )
    if summary["phase_frame_count"] != len(payload.get("frames", [])):
        raise ValueError("benchmark phase must cover every source frame")
    if (
        summary["maximum_phase_step_error_deg"] is None
        or summary["maximum_phase_step_error_deg"] > 1e-9
    ):
        raise ValueError("benchmark phase is not cyclically uniform")
    if summary["orientation_gauge_status"] != "available":
        raise ValueError("benchmark semantic orientation gauge unavailable")
    if summary["orientation_physically_unique"] is not False:
        raise ValueError("benchmark gauge must preserve 90-degree ambiguity")
    if summary["equivalent_global_quarter_turns"] != [0, 1, 2, 3]:
        raise ValueError("benchmark quarter-turn equivalence not explicit")
    if (
        summary["gauge_transform_count"]
        != summary["canonical_frame_count"]
    ):
        raise ValueError(
            "every canonical benchmark frame must map into sequence gauge"
        )
    return summary

def _summarise_stone(certificate, payload):
    frames = payload["frames"]
    counts = Counter(
        record["assessment"]["status"]
        for record in frames
    )
    usable = [
        record
        for record in frames
        if record["assessment"]["status"] in ("ok", "review")
    ]
    rejected = [
        record
        for record in frames
        if record["assessment"]["status"] == "rejected"
    ]
    ordered = sorted(frames, key=lambda record: record.get("rank", 10**9))
    usable_scores = np.array(
        [record["assessment"]["score"] for record in usable],
        dtype=float,
    )
    sequence_coordinate = _validate_sequence_coordinate_contract(payload)
    return {
        "certificate": certificate,
        "frame_count": len(frames),
        "sequence_coordinate": sequence_coordinate,
        "status_counts": dict(sorted(counts.items())),
        "face_selection": payload.get("face_selection"),
        "usable_score_quantiles": (
            None
            if not len(usable_scores)
            else {
                "q10": float(np.quantile(usable_scores, 0.10)),
                "median": float(np.median(usable_scores)),
                "q90": float(np.quantile(usable_scores, 0.90)),
            }
        ),
        "top_candidates": [
            _frame_summary(record)
            for record in ordered
            if record["assessment"]["status"] in ("ok", "review")
        ][:12],
        "borderline_usable": (
            None
            if not usable
            else _frame_summary(
                min(
                    usable,
                    key=lambda record: record["assessment"]["score"],
                )
            )
        ),
        "first_rejected": (
            None
            if not rejected
            else _frame_summary(
                max(
                    rejected,
                    key=lambda record: record["assessment"]["score"],
                )
            )
        ),
        "qc_path": payload.get("qc_path"),
        "reference_faces_path": payload.get("reference_faces_path"),
        "reference_face_metrics": _reference_face_metrics(payload),
    }


def run_source_benchmark(source_root, output, bundle_manifest):
    """Preprocess four retained rotations and apply the frozen v1 pose policy."""
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    output.mkdir(parents=True, exist_ok=True)
    stones = []

    with tempfile.TemporaryDirectory(
        prefix="sparkles-asscher-pose-"
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = item["certificate"]
            source = source_root / certificate
            processed = work / certificate / "processed"
            source_manifest = Path(item["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest = Path.cwd() / source_manifest
            pipeline.run(
                source,
                processed,
                source_manifest,
                gain=1.0,
                accept_review=True,
            )
            pose_output = output / "per-stone" / certificate
            payload = analyse_processed_sequence(
                processed,
                pose_output,
                persist_canonical=False,
            )
            payload["reference_faces_path"] = _render_reference_faces(
                processed,
                pose_output,
                payload,
            )
            stones.append(_summarise_stone(certificate, payload))

    result = {
        "schema_version": SCHEMA,
        "source_bundle_schema": manifest.get("schema_version"),
        "policy": (
            "frozen diamond360-asscher-pose/1; no tuning to DiaGem/Sergey "
            "facet-angle values"
        ),
        "stones": stones,
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run Asscher pose suitability on retained benchmark rotations"
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=Path("docs/360/benchmark/source-bundles.json"),
    )
    args = parser.parse_args()
    result = run_source_benchmark(
        args.source_root,
        args.output,
        args.bundle_manifest,
    )
    for stone in result["stones"]:
        top = stone["top_candidates"][:5]
        print(
            stone["certificate"],
            stone["status_counts"],
            "top=",
            [
                (row["source_index"], round(row["score"], 3))
                for row in top
            ],
        )


if __name__ == "__main__":
    main()
