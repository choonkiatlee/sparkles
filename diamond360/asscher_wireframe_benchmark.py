"""Four-stone frozen-parameter benchmark for issue #75."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence
from .asscher_wireframe import fit_pose_sequence, specification

SCHEMA = "diamond360-asscher-wireframe-benchmark/1"


def _stone_summary(certificate, result):
    scaffold = result.get("scaffold")
    observations = {} if scaffold is None else scaffold["entity_observations"]
    return {
        "certificate": certificate,
        "status": result["status"],
        "reason": result.get("reason"),
        "selected_source_indices": [
            row.get("source_index")
            for row in result.get("selected_frames", [])
        ],
        "selected_positions": [
            row.get("position")
            for row in result.get("selected_frames", [])
        ],
        "semantic_gauge_id": result.get("semantic_gauge_id"),
        "outer_selection": result.get("outer_selection"),
        "outer_evidence": result.get("outer_evidence"),
        "scaffold_validity": (
            None if scaffold is None else scaffold.get("validity")
        ),
        "review_reasons": (
            [] if scaffold is None else scaffold.get("review_reasons", [])
        ),
        "boundary_evidence": result.get("boundary_evidence", {}),
        "pavilion_evidence": result.get("pavilion_evidence", {}),
        "representative_entity_confidence": {
            semantic_id: observations.get(semantic_id, {}).get("confidence")
            for semantic_id in (
                "C1_N", "C2_N", "C3_N", "P1_N", "P2_N", "P3_N",
                "TABLE", "CULET_REGION",
            )
        },
        "qc_path": result.get("qc_path"),
    }


def run_source_benchmark(source_root, output, bundle_manifest):
    """Run the same frozen fitter over the retained four-stone source set."""
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    output.mkdir(parents=True, exist_ok=True)
    stones = []

    with tempfile.TemporaryDirectory(
        prefix="sparkles-asscher-wireframe-"
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = item["certificate"]
            source = source_root / certificate
            processed = work / certificate / "processed"
            pose_output = work / certificate / "pose"
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
            analyse_processed_sequence(
                processed,
                pose_output,
                persist_canonical=True,
            )
            result = fit_pose_sequence(
                pose_output,
                output / "per-stone" / certificate,
                processed=processed,
            )
            stones.append(_stone_summary(certificate, result))

    payload = {
        "schema_version": SCHEMA,
        "source_bundle_schema": manifest.get("schema_version"),
        "fit_specification": specification(),
        "parameter_policy": (
            "one frozen issue-75 parameter set for every stone; no per-stone "
            "thresholds, manual vertices, or DiaGem/Sergey target values"
        ),
        "stone_count": len(stones),
        "stones": stones,
    }
    (output / "summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Run the frozen issue-75 wireframe fitter on four retained rotations"
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
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
        print(
            stone["certificate"],
            stone["status"],
            stone["selected_source_indices"],
            stone["review_reasons"],
        )


if __name__ == "__main__":
    main()
