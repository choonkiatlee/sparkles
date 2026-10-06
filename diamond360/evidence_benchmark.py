"""Generate compact #21 evidence packets from the four benchmark source bundles."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from . import activation_benchmark as activation
from . import asscher_steps
from . import benchmark
from . import coordination_benchmark as coordination
from . import descriptor_profile as dp
from . import evidence_packet as evidence
from . import mobility_benchmark as mobility
from . import morphology_benchmark as morphology
from . import occupancy_benchmark as occupancy
from . import opposing_symmetry_benchmark as opposing
from . import persistence_benchmark as persistence
from . import pipeline
from . import switching_benchmark as switching


SUMMARY_SCHEMA = "diamond360-evidence-packet-benchmark/1"


def measure_native_results(processed, step_output, indices, wrap=True):
    """Run existing descriptor implementations and retain their native evidence.

    This orchestration does not define or recalculate any descriptor formula:
    every measurement and evidence selector remains owned by #26-#33.
    """
    activation_result = activation.measure_stone(
        processed, step_output, indices, wrap=wrap
    )
    return {
        "activation": activation_result,
        "occupancy": occupancy.measure_stone(
            processed, step_output, indices, wrap=wrap
        ),
        "switching": switching.measure_stone(
            processed, step_output, indices, wrap=wrap
        ),
        "persistence": persistence.measure_stone(
            processed, step_output, indices, wrap=wrap
        ),
        "mobility": mobility.measure_from_activation(activation_result),
        "coordination": coordination.measure_from_activation(activation_result),
        "opposing": opposing.measure_stone(
            processed, step_output, indices, wrap=wrap
        ),
        "morphology": morphology.measure_stone(
            processed, indices, wrap=wrap
        ),
    }


def _load_profile(repository_root, certificate):
    path = (
        Path(repository_root)
        / "docs"
        / "360"
        / "profile"
        / "per-stone"
        / f"{certificate}.json"
    )
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != dp.PROFILE_SCHEMA:
        raise ValueError(
            f"{certificate}: expected profile schema {dp.PROFILE_SCHEMA}"
        )
    return payload


def _manifest_ref(certificate):
    return (
        "docs/360/benchmark/per-stone/"
        f"{certificate}/source-manifest.json"
    )


def _prepare_core_source(source, source_manifest, indices, destination):
    """Copy only the canonical core originals into a temporary sparse source."""
    source = Path(source)
    destination = Path(destination)
    wanted = set(indices)
    selected = [
        frame for frame in source_manifest.get("frames", [])
        if frame.get("source_index") in wanted
    ]
    if {frame.get("source_index") for frame in selected} != wanted:
        raise ValueError("benchmark source is missing canonical core frames")
    destination.mkdir(parents=True, exist_ok=True)
    for frame in selected:
        relative = Path(frame["path"])
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    sparse_manifest = dict(source_manifest)
    sparse_manifest["frames"] = selected
    sparse_manifest["sequence_complete"] = False
    sparse_manifest["selection"] = {
        "window_contract": dp.WINDOW_ID,
        "source_indices": list(indices),
        "reason": "temporary preprocessing subset for evidence packet generation",
    }
    path = destination / "source-manifest.json"
    path.write_text(json.dumps(sparse_manifest, indent=2) + "\n")
    return path


def run(
    repository_root,
    source_root,
    output,
    certificates=None,
    min_items=4,
    max_items=6,
):
    repository_root = Path(repository_root).resolve()
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest_path = (
        repository_root / "docs" / "360" / "benchmark" / "benchmark.json"
    )
    manifest = benchmark.validate_manifest(
        json.loads(manifest_path.read_text())
    )
    requested = set(certificates or [])
    unknown = requested - {
        stone["certificate"] for stone in manifest["stones"]
    }
    if unknown:
        raise ValueError(f"unknown benchmark certificates: {sorted(unknown)}")

    stones = [
        stone
        for stone in manifest["stones"]
        if stone["source_status"] == "complete"
        and (not requested or stone["certificate"] in requested)
    ]
    output.mkdir(parents=True, exist_ok=True)
    summaries = []

    for stone in stones:
        certificate = stone["certificate"]
        source = source_root / certificate
        if not source.is_dir():
            raise ValueError(
                f"{certificate}: expected extracted benchmark source at {source}"
            )
        source_manifest_path = benchmark.source_contract(
            source, stone["source_frame_count"]
        )
        source_manifest = json.loads(source_manifest_path.read_text())
        indices = benchmark.cyclic_window(
            stone["faceup_center"],
            manifest["core_window"],
            stone["source_frame_count"],
        )
        if indices != dp.CORE_INDICES:
            raise ValueError(
                f"{certificate}: benchmark core window differs from #45 {dp.WINDOW_ID}"
            )
        wrap = any(right < left for left, right in zip(indices, indices[1:]))

        with tempfile.TemporaryDirectory(
            prefix=f"sparkles-evidence-{certificate}-"
        ) as temporary:
            work = Path(temporary)
            processed = work / "processed"
            steps = work / "steps"
            core_source = work / "source"
            core_manifest = _prepare_core_source(
                source,
                source_manifest,
                indices,
                core_source,
            )
            pipeline.run(
                core_source,
                processed,
                order_manifest=core_manifest,
                gain=1.0,
                diagnostic_indices=indices,
                accept_review=True,
            )
            asscher_steps.run(
                processed,
                steps,
                indices,
                wrap=wrap,
            )
            results = measure_native_results(
                processed,
                steps,
                indices,
                wrap=wrap,
            )
            profile = _load_profile(repository_root, certificate)
            packet = evidence.build_packet(
                results,
                profile,
                source_manifest,
                source_manifest_ref=_manifest_ref(certificate),
                min_items=min_items,
                max_items=max_items,
            )
            target = output / "per-stone" / certificate
            evidence.write_packet(
                packet,
                target,
                source_root=source,
                verify_hashes=True,
            )

        summaries.append({
            "certificate": certificate,
            "selected_count": packet["selected_count"],
            "covered_families": packet["covered_families"],
            "uncovered_available_families": (
                packet["uncovered_available_families"]
            ),
            "packet": f"per-stone/{certificate}/evidence.json",
            "contact_sheet": (
                f"per-stone/{certificate}/{packet['contact_sheet']}"
            ),
        })

    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "profile_schema": dp.PROFILE_SCHEMA,
        "packet_schema": evidence.PACKET_SCHEMA,
        "window_contract": dp.WINDOW_ID,
        "source_bundles": "docs/360/benchmark/source-bundles.json",
        "stones": summaries,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--certificates",
        help="optional comma-separated subset of benchmark certificates",
    )
    parser.add_argument("--min-items", type=int, default=4)
    parser.add_argument("--max-items", type=int, default=6)
    args = parser.parse_args()
    certificates = (
        [part.strip() for part in args.certificates.split(",") if part.strip()]
        if args.certificates
        else None
    )
    try:
        result = run(
            args.repository_root,
            args.source_root,
            args.output,
            certificates=certificates,
            min_items=args.min_items,
            max_items=args.max_items,
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(
        f"{len(result['stones'])} evidence packets -> "
        f"{Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
