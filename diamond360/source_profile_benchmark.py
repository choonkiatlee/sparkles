"""Heterogeneous source/acquisition benchmark for issue #81."""
from __future__ import annotations

import argparse
import json
import tempfile
from itertools import combinations
from pathlib import Path

from . import pipeline, source_profile
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-source-profile-benchmark/1"


def _discover_sources(source_root, bundle_manifest):
    source_root = Path(source_root).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    sources = []
    seen = set()
    for item in manifest.get("bundles", []):
        name = item["certificate"]
        source = source_root / name
        source_manifest = Path(item["source_manifest"])
        if not source_manifest.is_absolute():
            source_manifest = Path.cwd() / source_manifest
        sources.append((name, source, source_manifest))
        seen.add(name)

    for candidate in sorted(source_root.iterdir()):
        if (
            candidate.is_dir()
            and candidate.name not in seen
            and (candidate / "source-manifest.json").is_file()
        ):
            sources.append(
                (
                    candidate.name,
                    candidate,
                    candidate / "source-manifest.json",
                )
            )
    return manifest, sources


def _profile_summary(name, profile):
    measurements = {
        family: source_profile.assess_measurement(profile, family)
        for family in source_profile.MEASUREMENT_FAMILIES
    }
    return {
        "source_id": name,
        "source_pipeline": profile["source"].get("source_pipeline"),
        "source_dimensions_px": profile["source"].get("dimensions_px"),
        "sequence_ordering": profile["sequence"]["ordering"],
        "phase": profile["sequence"]["phase"],
        "spatial_sampling": profile["spatial_sampling"],
        "compression_processing": profile["compression_processing"],
        "photometric": profile["photometric"],
        "pose_coverage": profile["pose_coverage"],
        "physical_scale": profile["physical_scale"],
        "measurements": measurements,
    }


def run_source_benchmark(
    source_root,
    output,
    bundle_manifest="docs/360/benchmark/source-bundles.json",
    *,
    maximum_diagnostic_frames=64,
):
    """Run frozen source profiling over retained and optional extra sources."""
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    bundle, sources = _discover_sources(source_root, bundle_manifest)
    if not sources:
        raise ValueError("no benchmark source directories found")
    output.mkdir(parents=True, exist_ok=True)
    profiles = {}
    summaries = []

    with tempfile.TemporaryDirectory(prefix="sparkles-source-profile-") as tmp:
        work = Path(tmp)
        for name, source, manifest_path in sources:
            if not source.is_dir():
                raise ValueError(f"missing benchmark source directory: {source}")
            processed = work / name / "processed"
            pose_output = work / name / "pose"
            pipeline.run(
                source,
                processed,
                manifest_path,
                gain=1.0,
                accept_review=True,
            )
            pose = analyse_processed_sequence(
                processed,
                pose_output,
                persist_canonical=False,
            )
            profile = source_profile.build_from_processed(
                processed,
                pose=pose,
                maximum_diagnostic_frames=maximum_diagnostic_frames,
            )
            profiles[name] = profile
            summaries.append(_profile_summary(name, profile))
            destination = output / "per-source" / name
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "source-profile.json").write_text(
                json.dumps(profile, indent=2, allow_nan=False) + "\n"
            )

    pairwise = []
    for left_name, right_name in combinations(sorted(profiles), 2):
        pairwise.append(
            {
                "left": left_name,
                "right": right_name,
                "measurements": {
                    family: source_profile.can_compare(
                        profiles[left_name],
                        profiles[right_name],
                        family,
                    )
                    for family in source_profile.MEASUREMENT_FAMILIES
                },
            }
        )

    result = {
        "schema_version": SCHEMA,
        "source_bundle_schema": bundle.get("schema_version"),
        "source_profile_schema": source_profile.SCHEMA,
        "maximum_diagnostic_frames": maximum_diagnostic_frames,
        "sources": summaries,
        "pairwise": pairwise,
        "interpretation": (
            "Benchmark of source/acquisition support and measurement-specific "
            "comparability. No field or status is a diamond-quality score."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run heterogeneous source-profile benchmark"
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--bundle-manifest",
        default=Path("docs/360/benchmark/source-bundles.json"),
        type=Path,
    )
    parser.add_argument("--maximum-diagnostic-frames", type=int, default=64)
    args = parser.parse_args()
    result = run_source_benchmark(
        args.source_root,
        args.output,
        args.bundle_manifest,
        maximum_diagnostic_frames=args.maximum_diagnostic_frames,
    )
    for item in result["sources"]:
        print(
            item["source_id"],
            item["source_pipeline"],
            {
                family: state["status"]
                for family, state in item["measurements"].items()
            },
        )


if __name__ == "__main__":
    main()
