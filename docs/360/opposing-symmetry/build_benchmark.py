"""Reproduce issue #31 across the canonical four-stone benchmark."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from diamond360 import asscher_steps
from diamond360 import benchmark as base_benchmark
from diamond360 import opposing_symmetry_benchmark as ob

CORE = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE = list(range(240, 256)) + list(range(0, 17))
FIELDS = [
    "certificate", "window", "surface_id", "representation", "radial_band",
    "support_mode", "pair_id", "status", "reasons", "paired_frames",
    "correlation", "median_absolute_difference", "median_signed_difference",
    "sign_agreement", "directional_pairs", "flat_pairs",
    "worse_persistent_support_fraction",
]


def _rows(certificate, window, result):
    rows = []
    for surface_id, surface in result["surfaces"].items():
        for mode, payload in surface["support_modes"].items():
            for pair_id, pair in payload["pairs"].items():
                sign = pair["metrics"]["sign_agreement"]
                rows.append({
                    "certificate": certificate,
                    "window": window,
                    "surface_id": surface_id,
                    "representation": pair["representation"],
                    "radial_band": pair["radial_band"],
                    "support_mode": mode,
                    "pair_id": pair_id,
                    "status": pair["validity"]["status"],
                    "reasons": ";".join(pair["validity"]["reasons"]),
                    "paired_frames": pair["paired_frames"],
                    "correlation": pair["metrics"]["correlation"]["value"],
                    "median_absolute_difference": pair["metrics"]["median_absolute_difference"]["value"],
                    "median_signed_difference": pair["median_signed_difference"],
                    "sign_agreement": sign["value"],
                    "directional_pairs": sign.get("directional_pairs"),
                    "flat_pairs": sign.get("flat_pairs"),
                    "worse_persistent_support_fraction": pair["component_support"]["worse_persistent_support_fraction"],
                })
    return rows


def _candidate(result, surface, mode, pair_id, certificate, window, label):
    pair = result["surfaces"][surface]["support_modes"][mode]["pairs"][pair_id]
    return {
        "label": label,
        "certificate": certificate,
        "window": window,
        "surface_id": surface,
        "support_mode": mode,
        "pair_id": pair_id,
        "panel": pair["evidence_panel"],
        "correlation": pair["metrics"]["correlation"]["value"],
        "median_absolute_difference": pair["metrics"]["median_absolute_difference"]["value"],
        "sign_agreement": pair["metrics"]["sign_agreement"]["value"],
        "worse_persistent_support_fraction": pair["component_support"]["worse_persistent_support_fraction"],
    }


def _select_evidence(results):
    core = []
    for certificate, windows in results.items():
        for window, result in windows.items():
            if window != "core":
                continue
            for pair_id in result["pair_definitions"]:
                core.append(_candidate(
                    result, "coarse_whole", "fixed", pair_id,
                    certificate, window, "baseline",
                ))

    selections = []
    correlated = [x for x in core if x["correlation"] is not None]
    if correlated:
        selections.append({
            **max(correlated, key=lambda x: x["correlation"]),
            "label": "highest_core_correlation",
        })
        selections.append({
            **min(correlated, key=lambda x: x["correlation"]),
            "label": "lowest_core_correlation",
        })
    imbalance = [
        x for x in core
        if x["median_absolute_difference"] is not None
    ]
    if imbalance:
        selections.append({
            **max(
                imbalance,
                key=lambda x: x["median_absolute_difference"],
            ),
            "label": "largest_core_pair_imbalance",
        })

    for family, metric in (
        ("support", "correlation"),
        ("representation", "correlation"),
    ):
        candidates = []
        for certificate, windows in results.items():
            for window, result in windows.items():
                item = result["disagreements"][family].get(metric)
                if item is not None:
                    candidates.append((
                        float(item["absolute_difference"]),
                        certificate,
                        window,
                        item,
                    ))
        if not candidates:
            continue
        _, certificate, window, item = max(
            candidates, key=lambda x: x[0]
        )
        result = results[certificate][window]
        if family == "support":
            surface = item["surface_id"]
            pair_id = item["pair_id"]
            for mode in ("fixed", "dynamic"):
                selections.append(_candidate(
                    result,
                    surface,
                    mode,
                    pair_id,
                    certificate,
                    window,
                    f"strongest_support_disagreement_{mode}",
                ))
        else:
            pair_id = item["pair_id"]
            mode = item["support_mode"]
            for side in ("left", "right"):
                surface = item[f"{side}_surface"]
                selections.append(_candidate(
                    result,
                    surface,
                    mode,
                    pair_id,
                    certificate,
                    window,
                    f"strongest_representation_disagreement_{side}",
                ))

    unique = []
    seen = set()
    for item in selections:
        key = (
            item["certificate"],
            item["window"],
            item["panel"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:7]


def run(source_root, work_root, output):
    source_root = Path(source_root).resolve()
    work_root = Path(work_root).resolve()
    output = Path(output).resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)

    base = work_root / "base"
    base_benchmark.run(
        Path("docs/360/benchmark/benchmark.json"),
        base,
        source_root=source_root,
    )

    source_index = json.loads(
        Path("docs/360/benchmark/source-bundles.json").read_text()
    )
    certificates = [
        item["certificate"]
        for item in source_index["bundles"]
    ]
    results = {}
    rows = []
    disagreements = []
    run_status = []
    run_outputs = {}
    for certificate in certificates:
        processed = (
            base / "per-stone" / certificate / "processed"
        )
        results[certificate] = {}
        run_outputs[certificate] = {}
        for window, indices in (
            ("core", CORE),
            ("wide", WIDE),
        ):
            steps = (
                work_root
                / "steps"
                / certificate
                / window
            )
            asscher_steps.run(
                processed,
                steps,
                indices,
                wrap=True,
            )
            stone_out = (
                work_root
                / "opposing"
                / certificate
                / window
            )
            result = ob.measure_stone(
                processed,
                steps,
                indices,
                wrap=True,
            )
            ob.write_stone_outputs(
                result,
                stone_out,
                processed,
                steps,
            )
            results[certificate][window] = result
            run_outputs[certificate][window] = stone_out
            rows.extend(
                _rows(certificate, window, result)
            )
            disagreements.append({
                "certificate": certificate,
                "window": window,
                **result["disagreements"],
            })
            semantic_qc = result.get("semantic_qc") or {}
            semantic_statuses = semantic_qc.get(
                "selected_frame_statuses", []
            )
            run_status.append({
                "certificate": certificate,
                "window": window,
                "accepted_frames": len(result["accepted_indices"]),
                "excluded_frames": len(result["excluded"]),
                "semantic_qc": {
                    "template_status":
                        semantic_qc.get("template_status"),
                    "template_reason":
                        semantic_qc.get("template_reason"),
                    "selected_frame_status_counts": {
                        status: semantic_statuses.count(status)
                        for status in (
                            "ok", "review", "unavailable"
                        )
                    },
                },
                "surface_ids": sorted(result["surfaces"]),
            })

    evidence = _select_evidence(results)
    evidence_dir = output / "per-stone"
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    for item in evidence:
        source = (
            run_outputs[item["certificate"]][item["window"]]
            / item["panel"]
        )
        destination = (
            evidence_dir
            / item["certificate"]
            / item["window"]
            / "evidence"
            / Path(item["panel"]).name
        )
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copyfile(source, destination)
        item["committed_path"] = str(
            destination.relative_to(output)
        )

    summary = {
        "schema_version":
            "diamond360-opposing-region-symmetry-benchmark/1",
        "core_indices": CORE,
        "wide_indices": WIDE,
        "stones": certificates,
        "rows": rows,
        "run_status": run_status,
        "disagreements": disagreements,
        "representative_evidence": evidence,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False)
        + "\n"
    )
    with (output / "summary.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FIELDS
        )
        writer.writeheader()
        writer.writerows([
            {key: row.get(key) for key in FIELDS}
            for row in rows
        ])
    (output / "evidence.json").write_text(
        json.dumps(evidence, indent=2, allow_nan=False)
        + "\n"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()
    summary = run(
        args.source_root,
        args.work_root,
        args.output,
    )
    print(
        f"{len(summary['rows'])} benchmark rows "
        f"-> {args.output}"
    )


if __name__ == "__main__":
    main()
