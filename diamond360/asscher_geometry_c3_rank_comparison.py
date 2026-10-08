"""Frozen #96 / #131 / frame-consistent C3 experiments on identical #89 stones."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_geometry_method_comparison as comparison
from . import asscher_geometry_validation as validation

SCHEMA = "diamond360-asscher-c3-frame-rank-comparison/1"


def compare(control, window, frame):
    method_cases=(
        ("control",control,validation.OUTER_METHOD),
        ("window",window,validation.WINDOW_METHOD),
        ("frame",frame,validation.FRAME_RANK_METHOD),
    )
    for name, report, method in method_cases:
        if report.get("frozen_method",{}).get("method_revision") != method:
            raise ValueError(f"{name}: method revision is not {method}")
        if report.get("benchmark_inputs",{}).get(
            "manifest_canonical_sha256"
        ) != validation.BENCHMARK_MANIFEST_CANONICAL_SHA256:
            raise ValueError(f"{name}: wrong frozen four-stone manifest")
        certificates=[row["certificate"] for row in report.get("stones",[])]
        if len(certificates)!=4 or len(set(certificates))!=4:
            raise ValueError(f"{name}: incomplete four-stone benchmark")
    identities=[{row["certificate"] for row in report["stones"]}
                for _,report,_ in method_cases]
    if identities[0]!=identities[1] or identities[0]!=identities[2]:
        raise ValueError("matched certificate set differs across policies")
    rows=[]
    by_stone=[
        {r["certificate"]:r for r in report["stones"]}
        for _,report,_ in method_cases
    ]
    first, second = comparison.compare_stability(control,window),comparison.compare_stability(window,frame)
    old_to_window={r["certificate"]:r for r in first}
    window_to_new={r["certificate"]:r for r in second}
    for cert in sorted(identities[0]):
        b,w,f=(source[cert] for source in by_stone)
        summary = {
            "certificate":cert,
            "control_status":b.get("status"),
            "window_status":w.get("status"),
            "candidate_status":f.get("status"),
            "control_selected_indices":b.get("selected_source_indices"),
            "window_selected_indices":w.get("selected_source_indices"),
            "candidate_selected_indices":f.get("selected_source_indices"),
            "control_max_tier_displacement":(b.get("estimator_stability") or {}).get("max_boundary_displacement_tier_fraction"),
            "window_max_tier_displacement":(w.get("estimator_stability") or {}).get("max_boundary_displacement_tier_fraction"),
            "candidate_max_tier_displacement":(f.get("estimator_stability") or {}).get("max_boundary_displacement_tier_fraction"),
            "control_stability":b.get("estimator_stability"),
            "window_stability":w.get("estimator_stability"),
            "candidate_stability":f.get("estimator_stability"),
            "control_to_window_metric_comparison":old_to_window[cert],
            "window_to_frame_metric_comparison":window_to_new[cert],
        }
        rows.append(summary)
    return {
        "schema_version":SCHEMA,
        "frozen_manifest":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "methods":[method for _,_,method in method_cases],
        "interpretation":(
            "Predeclared experimental image-space C3 ranking; no facet "
            "identity ground truth or grading claim. Numeric #88 differences "
            "are descriptive, not pass/fail thresholds."
        ),
        "source_stress":"deferred_manual_only",
        "stones":rows,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--control",type=Path,required=True)
    parser.add_argument("--window",type=Path,required=True)
    parser.add_argument("--candidate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    r=compare(
        json.loads(a.control.read_text()),
        json.loads(a.window.read_text()),
        json.loads(a.candidate.read_text()),
    )
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    for row in r["stones"]:
        print(row["certificate"],"statuses",
              row["control_status"],row["window_status"],row["candidate_status"],
              "tier-fractions",
              row["control_max_tier_displacement"],
              row["window_max_tier_displacement"],
              row["candidate_max_tier_displacement"])


if __name__=="__main__":
    main()
