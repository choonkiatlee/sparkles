"""Target-blind paired #96 vs window-local experimental #89/#90 reports.

Uses immutable #115 artifacts and unchanged #88 geometry/stress metrics.
Differences in unavailable states and selected views are preserved, not scored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_geometry_method_comparison as previous
from . import asscher_geometry_validation as validation

SCHEMA = "diamond360-asscher-window-peak-comparison/1"


def compare(kind, control, experiment):
    if kind not in ("stability", "stress"):
        raise ValueError("unsupported benchmark")
    expected = validation.BENCHMARK_MANIFEST_CANONICAL_SHA256
    for name, report, method in (
        ("control", control, validation.OUTER_METHOD),
        ("experiment", experiment, validation.WINDOW_METHOD),
    ):
        if report.get("frozen_method", {}).get("method_revision") != method:
            raise ValueError(f"{name}: wrong peak-selection method")
        fingerprint = report.get("benchmark_inputs", {}).get(
            "manifest_canonical_sha256"
        )
        if fingerprint != expected:
            raise ValueError(f"{name}: changed frozen source manifest")
    return {
        "schema_version": SCHEMA,
        "benchmark": kind,
        "control_method": validation.OUTER_METHOD,
        "experimental_method": validation.WINDOW_METHOD,
        "pinned_benchmark_manifest_sha256": expected,
        "peak_selection_policy": validation.FROZEN_WINDOW_EXPERIMENT_POLICY,
        "interpretation": (
            "paired observational comparison, no numeric acceptance "
            "threshold; missing measurements stay null; do not interpret "
            "edge positions as confirmed physical facet boundaries"
        ),
        "stones": (
            previous.compare_stability(control, experiment)
            if kind == "stability"
            else previous.compare_stress(control, experiment)
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=("stability", "stress"))
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = compare(
        args.kind,
        json.loads(args.control.read_text()),
        json.loads(args.experiment.read_text()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    for row in report["stones"]:
        print(row["certificate"], row.get("primary_status_before"),
              "->", row.get("primary_status_after"),
              "max-tier",
              row.get("max_boundary_displacement_tier_before"),
              "->", row.get("max_boundary_displacement_tier_after"),
              "source-unavailable",
              row.get("geometry_unavailable_count_before"),
              "->", row.get("geometry_unavailable_count_after"))


if __name__ == "__main__":
    main()
