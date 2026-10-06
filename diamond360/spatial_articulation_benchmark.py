"""Benchmark issue #59 spatial articulation revisions on exact coarse-fixed support."""
from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a
from . import activation_benchmark as ab
from . import articulation_benchmark as arb
from . import benchmark
from . import spatial_articulation as sa

SCHEMA = "diamond360-spatial-articulation/1"
SUMMARY_SCHEMA = "diamond360-spatial-articulation-benchmark/1"

PROFILE_FIELDS = (
    "activity.activation.inner_relative_total_excursion",
    "dark_state.occupancy.inner_mean",
    "activity.mobility.inner_median",
)

TARGET_OBSERVATIONS = (
    "LG756520111-pale-inner-panels",
    "LG756580087-pale-inner-panels",
    "LG836619414-pale-inner-tiers",
    "LG818659722-grouped-dark-stack",
)

SUMMARY_MEASURES = (
    sa.SPATIAL_PRIMARY,
    "contrast_participation",
    "cell_log_spread",
    "adjacent_log_contrast_median",
    sa.COVERAGE_PRIMARY,
    sa.coverage_key("balanced_coverage", 1.10),
    sa.coverage_key("balanced_coverage", 1.20),
    sa.coverage_key("extreme_coverage", 1.15),
    "global_raw_spread",
)


def measure_arrays(
    brightness,
    valid_masks,
    inner_masks,
    stone_masks,
    observed,
    source_indices,
    upstream=None,
):
    """Measure both #59 candidates on the exact #26 coarse-fixed inner support."""
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    inner_masks = np.asarray(inner_masks, bool)
    stone_masks = np.asarray(stone_masks, bool)
    observed = np.asarray(observed, bool)
    source_indices = list(source_indices)

    if (
        brightness.ndim != 3
        or valid_masks.shape != brightness.shape
        or inner_masks.shape != brightness.shape
        or stone_masks.shape != brightness.shape
    ):
        raise ValueError("brightness and mask arrays must share frame-height-width shape")
    if observed.shape != (len(brightness),) or len(source_indices) != len(brightness):
        raise ValueError("observed flags and source indices must match frames")

    valid_masks = valid_masks & np.isfinite(brightness)
    inner_support = a._persistent_support(valid_masks, inner_masks, observed)
    whole_support = a._persistent_support(valid_masks, stone_masks, observed)

    whole_medians = []
    frames = []
    for frame, ok in zip(brightness, observed):
        if not ok:
            whole_medians.append(None)
            frames.append(None)
            continue
        whole_medians.append(
            float(np.median(frame[whole_support])) if whole_support.any() else None
        )
        frames.append(frame)

    trace = sa.articulation_trace(
        frames,
        inner_support,
        source_indices,
        whole_medians=whole_medians,
    )

    nominal_union = (
        np.any(inner_masks[observed], axis=0)
        if observed.any()
        else np.zeros(inner_masks.shape[1:], bool)
    )
    support_fraction = (
        float(inner_support.sum() / nominal_union.sum())
        if nominal_union.any()
        else None
    )

    upstream = upstream or {"status": "ok", "reasons": []}
    for measure, summary in trace["summaries"].items():
        if summary["status"] == "ok":
            reasons = []
        elif not inner_support.any():
            reasons = ["no_inner_support"]
        else:
            reasons = list(summary.get("reasons", [])) or ["insufficient_finite_frames"]
        summary["validity"] = a.activation_validity(
            "coarse",
            upstream,
            None,
            summary["status"],
            reasons,
        )

    return {
        "schema_version": SCHEMA,
        "issue": 59,
        "representation": "coarse",
        "region": "inner",
        "support_mode": "fixed",
        "sector_count": sa.SECTOR_COUNT,
        "coverage_ratios": list(sa.COVERAGE_RATIOS),
        "primary_candidates": {
            "spatial_participation": sa.SPATIAL_PRIMARY,
            "contrast_coverage": sa.COVERAGE_PRIMARY,
        },
        "definition": {
            "cell_log_spread": "Q90(log cell medians) - Q10(log cell medians) across 8 fixed angular sectors",
            "contrast_participation": "(sum |d_i|)^2 / (n * sum d_i^2), d_i = log(cell median_i) - median(log cell medians)",
            "distributed_contrast": "cell_log_spread * contrast_participation",
            "adjacent_log_contrast_median": "median absolute log-luminance difference between adjacent angular-sector medians",
            "contrast_coverage": "within-inner pixels outside median/ratio .. median*ratio, with balanced_coverage=min(p_dark,p_bright)",
            "global_raw_spread": "#51 Q90(Y_inner) - Q10(Y_inner), retained here only as a comparison baseline",
        },
        "requested_indices": source_indices,
        "persistent_support_pixels": int(inner_support.sum()),
        "persistent_support_fraction": support_fraction,
        "whole_persistent_support_pixels": int(whole_support.sum()),
        **trace,
        "evidence": {
            "spatial_participation": sa.select_evidence(
                trace["frame_trace"], sa.SPATIAL_PRIMARY
            ),
            "contrast_coverage": sa.select_evidence(
                trace["frame_trace"], sa.COVERAGE_PRIMARY
            ),
        },
        "within_frame_redundancy": {
            "spatial_vs_global_spread": sa.rank_agreement(
                trace["frame_trace"], sa.SPATIAL_PRIMARY, "global_raw_spread"
            ),
            "coverage_vs_global_spread": sa.rank_agreement(
                trace["frame_trace"], sa.COVERAGE_PRIMARY, "global_raw_spread"
            ),
            "spatial_vs_coverage": sa.rank_agreement(
                trace["frame_trace"], sa.SPATIAL_PRIMARY, sa.COVERAGE_PRIMARY
            ),
        },
    }


def measure_stone(processed, indices, wrap=False):
    processed = Path(processed).resolve()
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, excluded = ab._select_records(metadata, list(indices), wrap)
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = ab._load_frame_arrays(
        processed, selected
    )
    masks = a.load_coarse_masks(processed, selected)
    upstream = ab._upstream_validity(selected, excluded)

    result = measure_arrays(
        brightness,
        valid_masks,
        masks["inner"],
        stone_masks,
        observed,
        list(indices),
        upstream=upstream,
    )
    result.update(
        accepted_indices=[
            record["source_index"] for record in selected if record is not None
        ],
        excluded=excluded,
        wrap_explicit=bool(wrap),
        brightness_definition=metadata.get("brightness_definition"),
        upstream_validity=upstream,
        frame_rgb_paths=rgb_paths,
        frame_camera_paths=[
            record.get("camera_original_path") if record is not None else None
            for record in selected
        ],
        frame_region_paths=[
            record.get("regions_path") if record is not None else None
            for record in selected
        ],
    )
    return result


def _overlay_partition(image, region_path, processed, event):
    image = arb._overlay_inner(image, region_path, processed)
    if not region_path:
        return image
    with np.load(Path(processed) / region_path) as data:
        mask = np.asarray(data["inner"], bool)
    yy, xx = np.nonzero(mask)
    if not len(xx):
        return image

    partition = event.get("partition", {})
    cx = partition.get("centre_x")
    cy = partition.get("centre_y")
    if cx is None or cy is None:
        cx = float(np.mean(xx))
        cy = float(np.mean(yy))
    radius = float(np.max(np.hypot(xx - cx, yy - cy)))
    draw = ImageDraw.Draw(image)
    for index in range(sa.SECTOR_COUNT):
        angle = 2.0 * math.pi * (index + 0.5) / sa.SECTOR_COUNT
        x = cx + radius * math.cos(angle)
        y = cy - radius * math.sin(angle)
        draw.line((cx, cy, x, y), fill=(255, 220, 70), width=1)
    return image


def _evidence_rows(result, family):
    evidence = result["evidence"][family]
    ordered = [
        ("lowest", evidence.get("lowest")),
        ("median", evidence.get("median")),
        ("highest", evidence.get("highest")),
    ]
    pair = evidence.get("matched_brightness_pair")
    if pair:
        ordered.extend(
            [("brightness match A", pair.get("first")), ("brightness match B", pair.get("second"))]
        )
    rows = []
    seen = set()
    for label, event in ordered:
        if not event:
            continue
        position = event["position"]
        if position in seen:
            continue
        seen.add(position)
        rows.append((label, event))
    return rows


def _draw_evidence(destination, result, processed, family):
    rows = _evidence_rows(result, family)
    key = (
        sa.SPATIAL_PRIMARY
        if family == "spatial_participation"
        else sa.COVERAGE_PRIMARY
    )
    canvas = Image.new("RGB", (1020, 65 + 235 * max(1, len(rows))), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        f"Issue #59 {family}: camera frame (left), registered fixed-partition view (right)",
        fill="black",
    )
    draw.text(
        (10, 30),
        f"primary={key}; red=inner boundary; yellow=eight fixed angular sectors",
        fill="black",
    )

    for index, (label, event) in enumerate(rows):
        y = 60 + index * 235
        text = (
            f"{label}: src {event['source_index']}; {key}={event[key]:.5f}; "
            f"global spread={event['global_raw_spread']:.5f}"
        )
        draw.text((10, y), text, fill="black")
        position = event["position"]
        camera_path = result["frame_camera_paths"][position]
        rgb_path = result["frame_rgb_paths"][position]
        region_path = result["frame_region_paths"][position]
        if camera_path:
            with Image.open(Path(processed) / camera_path) as image:
                camera = image.convert("RGB")
            camera.thumbnail((480, 190))
            canvas.paste(camera, (10, y + 25))
        if rgb_path:
            with Image.open(Path(processed) / rgb_path) as image:
                registered = _overlay_partition(
                    image.convert("RGB"), region_path, processed, event
                )
            registered.thumbnail((480, 190))
            canvas.paste(registered, (520, y + 25))
    canvas.save(destination)


def write_stone_outputs(result, output, processed=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "spatial-articulation.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    frame_fields = [
        "source_index",
        "status",
        "supported_pixels",
        "whole_median",
        "cell_log_spread",
        "contrast_participation",
        "distributed_contrast",
        "adjacent_log_contrast_median",
        "global_raw_spread",
        sa.coverage_key("dark_fraction", 1.15),
        sa.coverage_key("bright_fraction", 1.15),
        sa.coverage_key("extreme_coverage", 1.15),
        sa.COVERAGE_PRIMARY,
        sa.coverage_key("balanced_coverage", 1.10),
        sa.coverage_key("balanced_coverage", 1.20),
    ]
    with (output / "spatial-articulation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=frame_fields)
        writer.writeheader()
        for row in result["frame_trace"]:
            writer.writerow({key: row.get(key) for key in frame_fields})

    summary_fields = [
        "measure", "status", "reasons", "finite_frames", "q10", "q50", "q90"
    ]
    with (output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        for measure in SUMMARY_MEASURES:
            summary = result["summaries"][measure]
            validity = summary["validity"]
            writer.writerow(
                {
                    "measure": measure,
                    "status": validity["status"],
                    "reasons": ";".join(validity["reasons"]),
                    "finite_frames": summary["finite_frames"],
                    "q10": summary["q10"],
                    "q50": summary["q50"],
                    "q90": summary["q90"],
                }
            )

    if processed is not None:
        evidence = output / "evidence"
        evidence.mkdir(exist_ok=True)
        for family in ("spatial_participation", "contrast_coverage"):
            _draw_evidence(
                evidence / f"{family}.png",
                result,
                Path(processed),
                family,
            )


def _core_summary(results, certificate, measure):
    return (
        results.get(certificate, {})
        .get("core", {})
        .get("summaries", {})
        .get(measure, {})
    )


def _measure_redundancy(results, certificates, measure, references):
    output = {}
    for name, reference in references.items():
        output[name] = {}
        for statistic in ("q10", "q50", "q90"):
            pairs = [
                (_core_summary(results, cert, measure).get(statistic), reference.get(cert))
                for cert in certificates
            ]
            output[name][statistic] = {
                "spearman": arb._spearman(pairs),
                "paired_stones": sum(
                    left is not None and right is not None for left, right in pairs
                ),
            }
    return output


def build_benchmark_summary(results, profile=None, tier_contrast=None, observations=None):
    rows = []
    for certificate, windows in sorted(results.items()):
        for window, result in windows.items():
            for measure in SUMMARY_MEASURES:
                summary = result["summaries"][measure]
                rows.append(
                    {
                        "certificate": certificate,
                        "window": window,
                        "measure": measure,
                        "q10": summary["q10"],
                        "q50": summary["q50"],
                        "q90": summary["q90"],
                        "status": summary["validity"]["status"],
                        "persistent_support_fraction": result["persistent_support_fraction"],
                    }
                )

    certificates = sorted(results)
    sensitivity = {}
    for measure in (
        sa.SPATIAL_PRIMARY,
        sa.COVERAGE_PRIMARY,
        sa.coverage_key("balanced_coverage", 1.10),
        sa.coverage_key("balanced_coverage", 1.20),
        "global_raw_spread",
    ):
        sensitivity[measure] = {}
        for statistic in ("q10", "q50", "q90"):
            pairs = [
                (
                    results[cert]["core"]["summaries"][measure].get(statistic),
                    results[cert]["wide"]["summaries"][measure].get(statistic),
                )
                for cert in certificates
            ]
            sensitivity[measure][statistic] = {
                "core_wide_rank_spearman": arb._spearman(pairs),
                "paired_stones": sum(
                    left is not None and right is not None for left, right in pairs
                ),
            }

    references = {
        field: arb._profile_values(profile, field)
        for field in PROFILE_FIELDS
    }
    references["#51_global_raw_spread"] = {
        cert: _core_summary(results, cert, "global_raw_spread").get("q50")
        for cert in certificates
    }
    references["other_candidate"] = {
        cert: _core_summary(results, cert, sa.COVERAGE_PRIMARY).get("q50")
        for cert in certificates
    }

    spatial_redundancy = _measure_redundancy(
        results, certificates, sa.SPATIAL_PRIMARY, references
    )

    coverage_references = {
        field: arb._profile_values(profile, field)
        for field in PROFILE_FIELDS
    }
    coverage_references["#51_global_raw_spread"] = {
        cert: _core_summary(results, cert, "global_raw_spread").get("q50")
        for cert in certificates
    }
    coverage_references["other_candidate"] = {
        cert: _core_summary(results, cert, sa.SPATIAL_PRIMARY).get("q50")
        for cert in certificates
    }
    coverage_redundancy = _measure_redundancy(
        results, certificates, sa.COVERAGE_PRIMARY, coverage_references
    )

    tier_redundancy = {"spatial_participation": {}, "contrast_coverage": {}}
    if tier_contrast:
        for pair_id in ("centre__inner", "inner__middle"):
            reference = arb._tier_values(tier_contrast, pair_id, "q50")
            for family, measure in (
                ("spatial_participation", sa.SPATIAL_PRIMARY),
                ("contrast_coverage", sa.COVERAGE_PRIMARY),
            ):
                pairs = [
                    (_core_summary(results, cert, measure).get("q50"), reference.get(cert))
                    for cert in certificates
                ]
                tier_redundancy[family][pair_id] = {
                    "spearman_q50": arb._spearman(pairs),
                    "paired_stones": sum(
                        left is not None and right is not None for left, right in pairs
                    ),
                }

    observation_rows = []
    wanted = set(TARGET_OBSERVATIONS)
    raw_observations = (
        observations.get("observations", observations)
        if isinstance(observations, dict)
        else observations or []
    )
    for observation in raw_observations:
        observation_id = observation.get("id") or observation.get("observation_id")
        if observation_id not in wanted:
            continue
        certificate = observation.get("certificate")
        core = results.get(certificate, {}).get("core")
        if not core:
            continue
        lookup = {row["source_index"]: row for row in core["frame_trace"]}
        observation_rows.append(
            {
                "id": observation_id,
                "certificate": certificate,
                "concept": observation.get("concept"),
                "role": observation.get("role"),
                "summary": observation.get("summary"),
                "source_frames": observation.get("source_frames", []),
                "measurements": [
                    {
                        "source_index": source_index,
                        sa.SPATIAL_PRIMARY: lookup.get(source_index, {}).get(sa.SPATIAL_PRIMARY),
                        sa.COVERAGE_PRIMARY: lookup.get(source_index, {}).get(sa.COVERAGE_PRIMARY),
                        "global_raw_spread": lookup.get(source_index, {}).get("global_raw_spread"),
                    }
                    for source_index in observation.get("source_frames", [])
                ],
            }
        )

    return {
        "schema_version": SUMMARY_SCHEMA,
        "descriptor_schema": SCHEMA,
        "issue": 59,
        "primary_candidates": {
            "spatial_participation": sa.SPATIAL_PRIMARY,
            "contrast_coverage": sa.COVERAGE_PRIMARY,
        },
        "validation_target": "source-evidence falsifiability plus internal consistency with prior AI evaluation annotations; not human perceptual ground truth",
        "rows": rows,
        "core_wide_sensitivity": sensitivity,
        "redundancy_diagnostics": {
            "note": "Spearman correlations are diagnostic only at n=4.",
            "spatial_participation": spatial_redundancy,
            "contrast_coverage": coverage_redundancy,
            "adjacent_tier_contrast": tier_redundancy,
            "adjacent_tier_status": "available" if tier_contrast else "pending",
        },
        "evaluation_observation_checks": observation_rows,
        "disposition": "PENDING_SOURCE_EVIDENCE_REVIEW",
        "disposition_rule": (
            "KEEP only if a candidate adds stable, visually interpretable spatial information "
            "beyond #51 spread and retained occupancy/activity metrics. AI evaluation annotations "
            "are secondary consistency checks, not human ground truth."
        ),
    }


def write_benchmark_summary(summary, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    fields = [
        "certificate", "window", "measure", "q10", "q50", "q90", "status",
        "persistent_support_fraction",
    ]
    with (output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [{key: row.get(key) for key in fields} for row in summary["rows"]]
        )


def _load_optional(path):
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def run_benchmark(manifest_path, source_root, output, tier_contrast_summary=None):
    from .pipeline import run as preprocess

    manifest_path = Path(manifest_path).resolve()
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = benchmark.validate_manifest(json.loads(manifest_path.read_text()))
    results = {}

    for stone in manifest["stones"]:
        if stone["source_status"] != "complete":
            continue
        certificate = stone["certificate"]
        source = source_root / certificate
        if not source.is_dir():
            raise ValueError(f"{certificate}: expected source directory {source}")
        order_manifest = benchmark.source_contract(
            source, stone["source_frame_count"]
        )
        wide_indices = benchmark.cyclic_window(
            stone["faceup_center"],
            manifest["wide_window"],
            stone["source_frame_count"],
        )
        with tempfile.TemporaryDirectory(prefix=f".spatial-articulation-{certificate}-") as td:
            processed = Path(td) / "processed"
            preprocess(
                source,
                processed,
                order_manifest=order_manifest,
                gain=1.0,
                diagnostic_indices=wide_indices,
                accept_review=True,
            )
            windows = {}
            for window, size in (
                ("core", manifest["core_window"]),
                ("wide", manifest["wide_window"]),
            ):
                indices = benchmark.cyclic_window(
                    stone["faceup_center"],
                    size,
                    stone["source_frame_count"],
                )
                wrap = any(right < left for left, right in zip(indices, indices[1:]))
                result = measure_stone(processed, indices, wrap=wrap)
                write_stone_outputs(
                    result,
                    output / "per-stone" / certificate / window,
                    processed=processed,
                )
                windows[window] = result
            results[certificate] = windows

    repo_root = manifest_path.parents[3]
    profile = _load_optional(repo_root / "docs/360/profile/comparison.json")
    observations = _load_optional(repo_root / "docs/360/calibration/human-observations.json")
    tier_contrast = _load_optional(tier_contrast_summary)
    summary = build_benchmark_summary(
        results,
        profile=profile,
        tier_contrast=tier_contrast,
        observations=observations,
    )
    write_benchmark_summary(summary, output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tier-contrast-summary", type=Path)
    args = parser.parse_args()
    try:
        summary = run_benchmark(
            args.manifest,
            args.source_root,
            args.output,
            tier_contrast_summary=args.tier_contrast_summary,
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(
        f"{len({row['certificate'] for row in summary['rows']})} stones -> {args.output}"
    )


if __name__ == "__main__":
    main()
