"""Target-blind, method-to-method reports for the frozen #89/#90 experiments.

Only consumes archived JSON summaries. This intentionally cannot retune or run
the estimator, cannot interpret geometry displacement as goodness, and preserves
unavailable results rather than treating missing measurements as zero movement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "diamond360-asscher-method-comparison/1"
OLD_REVISION = "8bbbbf64754f2bcbb48ab435b731bdf95f7722bc"
NEW_REVISION = "6334cc9d0c7e2c9a26854bfaeec7a8ebbb6fc668"


def _by(items, field):
    mapping = {row[field]: row for row in items}
    if len(mapping) != len(items):
        raise ValueError(f"duplicate {field}")
    return mapping


def _delta(before, after):
    return (
        None if before is None or after is None
        else float(after) - float(before)
    )


def _manifest(report):
    return report.get("benchmark_inputs", {}).get("manifest_canonical_sha256")


def compare_stability(before, after):
    base = _by(before["stones"], "certificate")
    new = _by(after["stones"], "certificate")
    if set(base) != set(new):
        raise ValueError("different stability stone sets")
    rows = []
    for name in sorted(base):
        old, current = base[name], new[name]
        a = old.get("estimator_stability", {})
        b = current.get("estimator_stability", {})
        ta = old.get("fixed_ruler_transfer", {})
        tb = current.get("fixed_ruler_transfer", {})
        rows.append({
            "certificate": name,
            "primary_status_before": old.get("primary", {}).get(
                "status", old.get("primary_result_status")
            ),
            "primary_status_after": current.get("primary", {}).get(
                "status", current.get("primary_result_status")
            ),
            "selected_source_indices_before": old.get("primary", {}).get(
                "selected_source_indices", old.get("selected_source_indices")
            ),
            "selected_source_indices_after": current.get("primary", {}).get(
                "selected_source_indices", current.get("selected_source_indices")
            ),
            "leave_one_out_count_before": a.get("run_count"),
            "leave_one_out_count_after": b.get("run_count"),
            "leave_one_out_status_before": a.get("status"),
            "leave_one_out_status_after": b.get("status"),
            "max_boundary_displacement_tier_before": a.get(
                "max_boundary_displacement_tier_fraction"
            ),
            "max_boundary_displacement_tier_after": b.get(
                "max_boundary_displacement_tier_fraction"
            ),
            "max_boundary_displacement_tier_delta": _delta(
                a.get("max_boundary_displacement_tier_fraction"),
                b.get("max_boundary_displacement_tier_fraction")
            ),
            "identity_swaps_before": a.get("semantic_identity_swap_count"),
            "identity_swaps_after": b.get("semantic_identity_swap_count"),
            "transfer_status_counts_before": ta.get("status_counts"),
            "transfer_status_counts_after": tb.get("status_counts"),
            "transfer_outside_fit_before": ta.get("outside_primary_fit_count"),
            "transfer_outside_fit_after": tb.get("outside_primary_fit_count"),
        })
    return rows


def compare_stress(before, after):
    base = _by(before["stones"], "certificate")
    new = _by(after["stones"], "certificate")
    if set(base) != set(new):
        raise ValueError("different stress stone sets")
    rows = []
    for name in sorted(base):
        old, current = base[name], new[name]
        aa = _by(old.get("conditions", []), "condition_id")
        bb = _by(current.get("conditions", []), "condition_id")
        if set(aa) != set(bb):
            raise ValueError(f"changed stress condition set for {name}")
        conditions = []
        for key in sorted(aa):
            x, y = aa[key], bb[key]
            ox = x["geometry_comparison"]
            oy = y["geometry_comparison"]
            conditions.append({
                "condition_id": key,
                "status_before": ox["status"],
                "status_after": oy["status"],
                "max_boundary_tier_before": ox.get(
                    "max_boundary_displacement_tier_fraction"
                ),
                "max_boundary_tier_after": oy.get(
                    "max_boundary_displacement_tier_fraction"
                ),
                "max_boundary_tier_delta": _delta(
                    ox.get("max_boundary_displacement_tier_fraction"),
                    oy.get("max_boundary_displacement_tier_fraction")
                ),
                "gauge_consistent_before": x.get(
                    "identity_detail", {}
                ).get("gauge_consistent"),
                "gauge_consistent_after": y.get(
                    "identity_detail", {}
                ).get("gauge_consistent"),
                "fixed_ruler_status_before": x.get("fixed_ruler_status"),
                "fixed_ruler_status_after": y.get("fixed_ruler_status"),
            })
        rows.append({
            "certificate": name,
            "baseline_primary_status_before": old.get(
                "baseline_primary", {}
            ).get("status"),
            "baseline_primary_status_after": current.get(
                "baseline_primary", {}
            ).get("status"),
            "geometry_unavailable_count_before": old.get(
                "geometry_unavailable_condition_count"
            ),
            "geometry_unavailable_count_after": current.get(
                "geometry_unavailable_condition_count"
            ),
            "gauge_changes_before": old.get("gauge_change_condition_count"),
            "gauge_changes_after": current.get("gauge_change_condition_count"),
            "conditions": conditions,
        })
    return rows


def compare(kind, before, after):
    if kind not in ("stability", "stress"):
        raise ValueError("unknown comparison kind")
    manifest = _manifest(before)
    if not manifest or manifest != _manifest(after):
        raise ValueError("source benchmark manifest changed")
    if after.get("frozen_method", {}).get("wireframe_revision") != NEW_REVISION:
        raise ValueError("new estimator is not the pinned #96 revision")
    old_record = before.get("frozen_method")
    if old_record and old_record.get("wireframe_revision") != OLD_REVISION:
        raise ValueError("baseline is not frozen #75")
    return {
        "schema_version": SCHEMA,
        "experiment": kind,
        "baseline_wireframe_revision": OLD_REVISION,
        "candidate_wireframe_revision": NEW_REVISION,
        "benchmark_manifest_canonical_sha256": manifest,
        "comparison_policy": (
            "descriptive paired metrics only; no post-hoc cutoff, no missing-as-zero; "
            "different selected frames / unavailable fits remain explicit; "
            "no external geometry targets or automatic KEEP decision"
        ),
        "stones": (
            compare_stability(before, after) if kind == "stability"
            else compare_stress(before, after)
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("stability", "stress"), required=True)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.kind, json.loads(args.before.read_text()),
                     json.loads(args.after.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    for row in result["stones"]:
        if args.kind == "stability":
            print(row["certificate"], "primary",
                  row["primary_status_before"], "→", row["primary_status_after"],
                  "max-tier",
                  row["max_boundary_displacement_tier_before"], "→",
                  row["max_boundary_displacement_tier_after"])
        else:
            print(row["certificate"], "unavailable conditions",
                  row["geometry_unavailable_count_before"], "→",
                  row["geometry_unavailable_count_after"],
                  "gauge changes", row["gauge_changes_before"], "→",
                  row["gauge_changes_after"])


if __name__ == "__main__":
    main()
