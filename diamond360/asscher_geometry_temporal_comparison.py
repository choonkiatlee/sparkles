"""Compare the temporal candidate experiment against immutable v2 and v3.

Metric computations are the existing #88 compare_stability implementation;
there is no target-fit reward, judgment threshold, or claim of polished facets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_geometry_method_comparison as comparison
from . import asscher_geometry_validation as validation

SCHEMA = "diamond360-asscher-temporal-candidate-comparison/1"


def compare(control, experiment, *, control_method):
    if control_method not in (validation.OUTER_METHOD, validation.WINDOW_METHOD):
        raise ValueError("control must be frozen v2 or v3")
    for report, name, expected_method in (
        (control, "control", control_method),
        (experiment, "experiment", validation.TEMPORAL_METHOD),
    ):
        reported_method = (report.get("frozen_method") or {}).get("method_revision")
        if reported_method != expected_method:
            raise ValueError(f"{name}: expected method {expected_method}, got {reported_method}")
        actual_sha = (report.get("benchmark_inputs") or {}).get("manifest_canonical_sha256")
        if actual_sha != validation.BENCHMARK_MANIFEST_CANONICAL_SHA256:
            raise ValueError(f"{name}: non-frozen source manifest")
    control_stones = [s.get("certificate") for s in control["stones"]]
    candidate_stones = [s.get("certificate") for s in experiment["stones"]]
    if control_stones != candidate_stones or len(control_stones) != 4:
        raise ValueError("four-stone frozen benchmark coverage differs")
    return {
        "schema_version": SCHEMA,
        "control_method": control_method,
        "experiment_method": validation.TEMPORAL_METHOD,
        "frozen_manifest_sha256": validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "candidate_rank_policy": validation.FROZEN_TEMPORAL_EXPERIMENT_POLICY,
        "interpretation": (
            "Descriptive paired #88 stability/identity/support comparison, "
            "not a grading or true-facet correctness measurement. "
            "Unavailable cases remain unavailable; no numerical pass threshold."
        ),
        "stones": comparison.compare_stability(control, experiment),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--control-method", choices=(validation.OUTER_METHOD, validation.WINDOW_METHOD),
                   required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = compare(json.loads(args.control.read_text()),
                     json.loads(args.experiment.read_text()),
                     control_method=args.control_method)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    for stone in report["stones"]:
        print(stone["certificate"], stone.get("primary_status_before"),
              "->", stone.get("primary_status_after"), "max-tier",
              stone.get("max_boundary_displacement_tier_before"),
              "->", stone.get("max_boundary_displacement_tier_after"))


if __name__ == "__main__":
    main()
