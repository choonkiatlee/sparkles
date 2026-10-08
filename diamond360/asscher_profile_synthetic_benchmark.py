"""Frozen, source-independent synthetic pavilion silhouette generalization matrix.

The named HOLDOUT cases and seeds are predetermined; changing the estimator
to improve a single case must not silently rewrite the reference distribution.
Every failure is reported, not discarded. No DiaGem fixture or expert angles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import asscher_profile_projected_fit as fit
from .asscher_profile_synthetic import Scene, Side, sample_scene, render_scene

SCHEMA = "sparkles-pavilion-synthetic-benchmark/1"
POLICY = {
    "holdout_case_ids": [
        "h01_single_clean", "h02_two_clean", "h03_three_clean",
        "h04_asymmetric_2_3", "h05_blur", "h06_noisy",
        "h07_occluded_right", "h08_sheared_projection",
        "h09_shadow_most_of_right", "h10_random_dropout",
        "h11_sparse_both", "h12_weak_changepoint",
    ],
    "matching_tolerance_image_px": 8.0,
    "failure_cases_must_be_reported": True,
    "heldout_is_not_fitting_input": True,
    "physical_angle_targets": "not_applicable",
}


def holdout_cases() -> list[tuple[str, Scene]]:
    """Hardcoded independent cases; never read a real diamond profile."""
    return [
        ("h01_single_clean", Scene(Side((),(0.91,)),Side((),(1.01,)),seed=151)),
        ("h02_two_clean", Scene(
            Side((0.42,),(1.60,0.51)),Side((0.56,),(1.49,0.49)),seed=152)),
        ("h03_three_clean", Scene(
            Side((0.25,0.66),(1.73,0.55,1.43)),
            Side((0.28,0.68),(1.64,0.59,1.50)),seed=153)),
        ("h04_asymmetric_2_3", Scene(
            Side((0.39,),(1.65,0.54)),
            Side((0.24,0.64),(1.54,0.50,1.47)),seed=154)),
        ("h05_blur", Scene(
            Side((0.29,0.63),(1.60,0.61,1.41)),
            Side((0.43,),(1.58,0.53)),
            blur_std_rows=2.4,noise_std_px=1.0,seed=155)),
        ("h06_noisy", Scene(
            Side((0.42,),(1.5,0.6)),Side((0.40,),(1.4,0.56)),
            noise_std_px=2.25,outlier_probability=0.05,seed=156)),
        ("h07_occluded_right", Scene(
            Side((0.31,0.69),(1.67,0.53,1.42)),
            Side((0.35,0.71),(1.57,0.57,1.36)),seed=157,
            right_occlusion=(0.39,0.61),inner_distractors=True)),
        ("h08_sheared_projection", Scene(
            Side((0.40,),(1.72,0.56)),
            Side((0.37,0.72),(1.44,0.49,1.37)),seed=158,
            shear_dx_per_dy=0.14,inner_distractors=True)),
        ("h09_shadow_most_of_right", Scene(
            Side((0.40,),(1.6,0.5)),
            Side((0.37,0.68),(1.64,0.52,1.39)),seed=159,
            right_shadow_from_fraction=0.40)),
        ("h10_random_dropout", Scene(
            Side((0.30,0.72),(1.70,0.61,1.51)),
            Side((0.43,),(1.43,0.57)),seed=160,
            dropout=0.50,inner_distractors=True)),
        ("h11_sparse_both", Scene(
            Side((0.42,),(1.54,0.58)),
            Side((0.44,),(1.63,0.56)),seed=161,dropout=0.80)),
        ("h12_weak_changepoint", Scene(
            Side((0.48,),(0.89,0.99)),
            Side((0.52,),(0.84,0.96)),seed=162,noise_std_px=1.45)),
    ]


def _evaluate_side(true_breaks: list, estimate: dict) -> dict:
    guesses = estimate.get("candidate_break_y_px", [])
    free = set(range(len(guesses)))
    matched = []
    tol = POLICY["matching_tolerance_image_px"]
    # Independent optimal-per-truth nearest unmatched match, diagnostic only.
    for y in true_breaks:
        eligible = [(abs(y - guesses[j]), j) for j in free
                    if abs(y - guesses[j]) <= tol]
        if eligible:
            distance, index = min(eligible)
            free.remove(index)
            matched.append(round(float(distance), 4))
    return {
        "true_break_y_px": true_breaks,
        "predicted_break_y_px": guesses,
        "fit_status": estimate["status"],
        "true_break_count": len(true_breaks),
        "predicted_break_count": len(guesses),
        "matched_break_count_at_8px": len(matched),
        "false_positive_breaks": len(free),
        "missed_true_breaks": len(true_breaks)-len(matched),
        "matched_absolute_errors_px": matched,
        "generating_segment_count_recovered": (
            estimate.get("segment_count") == len(true_breaks)+1
        ),
        "observed_count": estimate.get("observed_point_count", 0),
    }


def run_benchmark(output: Path) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    all_cases = []
    montage_cases = []
    for index, (name, scene) in enumerate(holdout_cases()):
        generated = sample_scene(scene)
        # Crucial leak barrier: only the observation object enters fitting.
        inferred = fit.fit_observations(generated["observations"])
        sides = {}
        for side in ("left", "right"):
            sides[side] = _evaluate_side(
                generated["truth"][side+"_break_y_px"], inferred["sides"][side]
            )
        all_cases.append({
            "id": name, "seed": scene.seed,
            "truth_scope": "2d_synthetic_only",
            "sides": sides,
            "estimator_policy": fit.POLICY,
            "physical_facet_angles": None,
        })
        if index in (0, 2, 6, 8):
            montage_cases.append((name, render_scene(scene, inferred)))
    all_sides = [side for case in all_cases for side in case["sides"].values()]
    positives = sum(s["true_break_count"] for s in all_sides)
    guessed = sum(s["predicted_break_count"] for s in all_sides)
    matched = sum(s["matched_break_count_at_8px"] for s in all_sides)
    matched_errors = [v for s in all_sides for v in s["matched_absolute_errors_px"]]
    accuracy = sum(s["generating_segment_count_recovered"] for s in all_sides)
    report = {
        "schema_version": SCHEMA,
        "policy": POLICY,
        "policy_sha256": hashlib.sha256(
            json.dumps(POLICY,sort_keys=True,separators=(",",":")).encode()
        ).hexdigest(),
        "estimator_policy_sha256": hashlib.sha256(
            json.dumps(fit.POLICY,sort_keys=True,separators=(",",":")).encode()
        ).hexdigest(),
        "source_kind": "no_real_diamond_data_ever_loaded",
        "data_partition": "fixed_predeclared_synthetic_holdout",
        "summary": {
            "cases": len(all_cases), "left_right_side_evaluations": len(all_sides),
            "true_breaks": positives, "proposed_breaks": guessed,
            "matched_breaks_8px": matched,
            "break_recall": round(matched/positives,4) if positives else None,
            "break_precision": round(matched/guessed,4) if guessed else None,
            "segment_count_accuracy": round(accuracy/len(all_sides),4),
            "mean_matched_abs_break_error_px": (
                round(sum(matched_errors)/len(matched_errors),4)
                if matched_errors else None
            ),
            "unavailable_side_count": sum(s["fit_status"]=="unavailable" for s in all_sides),
            "ambiguous_side_count": sum(s["fit_status"]=="ambiguous" for s in all_sides),
        },
        "cases": all_cases,
        "external_DiaGem_and_Sergey_used_for_tuning": False,
        "physical_pavilion_angles_claimed": False,
        "limitations": [
            "2D silhouette, not 3D Asscher facet planes or perspective calibration",
            "image-plane breakpoints are not polished P1/P2/P3 facet junctions",
            "thematic synthetic cases cannot establish real-world accuracy",
            "unavailable cases count as missed true breaks, never silently excluded",
        ],
    }
    (output/"synthetic-holdout-report.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    panel_w, panel_h=410,300
    montage=Image.new("RGB",(2*panel_w,2*panel_h),(250,250,252))
    draw=ImageDraw.Draw(montage)
    for i,(name,img) in enumerate(montage_cases):
        x=(i%2)*panel_w;y=(i//2)*panel_h
        montage.paste(img,(x,y+24))
        draw.text((x+12,y+6),name,fill=(28,39,52))
    montage.save(output/"synthetic-pavilion-montage.png")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    doc=run_benchmark(args.output)
    print(json.dumps(doc["summary"],sort_keys=True))
    print("Failure cases (not hidden):")
    for case in doc["cases"]:
        if any(
            side["missed_true_breaks"] or side["false_positive_breaks"]
            for side in case["sides"].values()
        ):
            print(case["id"],json.dumps({
                k:{"miss":v["missed_true_breaks"],"extra":v["false_positive_breaks"],
                   "status":v["fit_status"]}
                for k,v in case["sides"].items()
            },sort_keys=True))


if __name__=="__main__":
    main()
