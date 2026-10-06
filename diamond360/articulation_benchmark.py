"""Benchmark within-inner-region tonal articulation on exact coarse-fixed support."""
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
from . import articulation as ar
from . import benchmark as benchmark

SCHEMA = "diamond360-inner-articulation/1"
SUMMARY_SCHEMA = "diamond360-inner-articulation-benchmark/1"
PRIMARY_MEASURE = "raw_spread"

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


def _frame_spread(frame, support):
    if not support.any():
        return None
    values = np.asarray(frame, float)[support]
    values = values[np.isfinite(values)]
    if values.size < 3:
        return None
    return float(np.quantile(values, 0.9) - np.quantile(values, 0.1))


def measure_arrays(
    brightness,
    valid_masks,
    inner_masks,
    stone_masks,
    observed,
    source_indices,
    upstream=None,
):
    """Pure measurement kernel over already-registered arrays."""
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
    whole_spreads = []
    region_pixels = []
    for frame, ok in zip(brightness, observed):
        if not ok:
            whole_medians.append(None)
            whole_spreads.append(None)
            region_pixels.append(None)
            continue
        if whole_support.any():
            values = frame[whole_support]
            whole_medians.append(float(np.median(values)))
            whole_spreads.append(_frame_spread(frame, whole_support))
        else:
            whole_medians.append(None)
            whole_spreads.append(None)
        region_pixels.append(frame[inner_support] if inner_support.any() else None)

    trace = ar.articulation_trace(
        region_pixels,
        source_indices,
        whole_medians=whole_medians,
        whole_spreads=whole_spreads,
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
        elif measure == "relative_to_whole_contrast":
            reasons = ["whole_stone_contrast_reference_unavailable"]
        else:
            reasons = ["insufficient_finite_frames"]
        summary["validity"] = a.activation_validity(
            "coarse",
            upstream,
            None,
            summary["status"],
            reasons,
        )

    return {
        "schema_version": SCHEMA,
        "representation": "coarse",
        "region": "inner",
        "support_mode": "fixed",
        "primary_measure": PRIMARY_MEASURE,
        "definition": {
            "raw_spread": "Q90(Y_inner,t) - Q10(Y_inner,t)",
            "relative_to_whole_median": "raw_spread / whole-stone fixed-support median",
            "log_spread": "log(Q90(Y_inner,t)) - log(Q10(Y_inner,t))",
            "relative_to_whole_contrast": "raw_spread / (Q90(Y_whole,t)-Q10(Y_whole,t))",
        },
        "requested_indices": source_indices,
        "persistent_support_pixels": int(inner_support.sum()),
        "persistent_support_fraction": support_fraction,
        "whole_persistent_support_pixels": int(whole_support.sum()),
        **trace,
        "evidence": ar.select_evidence(trace["frame_trace"], PRIMARY_MEASURE),
        "normalization_rank_agreement": ar.rank_agreement(
            trace["frame_trace"], PRIMARY_MEASURE
        ),
    }


def measure_stone(processed, indices, wrap=False):
    """Measure issue #51 on the exact #26 coarse-fixed inner support."""
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


def _boundary(mask):
    mask = np.asarray(mask, bool)
    interior = mask.copy()
    interior[1:, :] &= mask[:-1, :]
    interior[:-1, :] &= mask[1:, :]
    interior[:, 1:] &= mask[:, :-1]
    interior[:, :-1] &= mask[:, 1:]
    return mask & ~interior


def _overlay_inner(image, region_path, processed):
    image = image.convert("RGB")
    if not region_path:
        return image
    with np.load(Path(processed) / region_path) as data:
        boundary = _boundary(data["inner"])
    array = np.asarray(image).copy()
    array[boundary] = (255, 70, 70)
    return Image.fromarray(array)


def _evidence_rows(result):
    evidence = result["evidence"]
    ordered = [
        ("lowest articulation", evidence.get("lowest")),
        ("median articulation", evidence.get("median")),
        ("highest articulation", evidence.get("highest")),
    ]
    pair = evidence.get("matched_brightness_pair")
    if pair:
        ordered.extend(
            [
                ("matched brightness A", pair.get("first")),
                ("matched brightness B", pair.get("second")),
            ]
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


def _draw_evidence(destination, result, processed):
    rows = _evidence_rows(result)
    canvas = Image.new("RGB", (1020, 65 + 235 * max(1, len(rows))), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        "Within-inner articulation: original camera frame (left), registered inner outline (right)",
        fill="black",
    )
    draw.text(
        (10, 30),
        "primary = Q90-Q10 on exact coarse-fixed inner support; red = inner-region boundary",
        fill="black",
    )

    for index, (label, event) in enumerate(rows):
        y = 60 + index * 235
        text = (
            f"{label}: src {event['source_index']}; "
            f"raw={event['raw_spread']:.5f}"
        )
        if event.get("log_spread") is not None:
            text += f"; log={event['log_spread']:.5f}"
        if event.get("whole_median") is not None:
            text += f"; whole={event['whole_median']:.5f}"
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
                registered = _overlay_inner(image, region_path, processed)
            registered.thumbnail((480, 190))
            canvas.paste(registered, (520, y + 25))
    canvas.save(destination)


def write_stone_outputs(result, output, processed=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "articulation.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    frame_fields = [
        "source_index",
        "status",
        "supported_pixels",
        "whole_median",
        "whole_spread",
        "pixel_q10",
        "pixel_q50",
        "pixel_q90",
        *ar.MEASURES,
    ]
    with (output / "articulation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=frame_fields)
        writer.writeheader()
        for row in result["frame_trace"]:
            writer.writerow({key: row.get(key) for key in frame_fields})

    summary_fields = [
        "measure",
        "status",
        "reasons",
        "finite_frames",
        "q10",
        "q50",
        "q90",
    ]
    with (output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        for measure, summary in result["summaries"].items():
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
        _draw_evidence(
            evidence / "inner-articulation.png",
            result,
            Path(processed),
        )


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def _spearman(pairs):
    pairs = [
        (float(left), float(right))
        for left, right in pairs
        if left is not None
        and right is not None
        and math.isfinite(float(left))
        and math.isfinite(float(right))
    ]
    if len(pairs) < 3:
        return None
    left = np.asarray(_average_ranks([value[0] for value in pairs]), float)
    right = np.asarray(_average_ranks([value[1] for value in pairs]), float)
    if np.std(left) == 0 or np.std(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _profile_values(profile, field):
    values = {}
    if not profile:
        return values
    for stone in profile.get("stones", []):
        cell = stone.get("measurements", {}).get(field, {})
        values[stone.get("certificate")] = cell.get("value")
    return values


def _tier_values(tier_contrast, pair_id, statistic):
    values = {}
    if not tier_contrast:
        return values
    for row in tier_contrast.get("rows", []):
        if row.get("window") == "core" and row.get("pair") == pair_id:
            values[row.get("certificate")] = row.get(statistic)
    return values


def build_benchmark_summary(
    results,
    profile=None,
    tier_contrast=None,
    observations=None,
):
    """Aggregate four-stone core/wide runs without fitting thresholds."""
    rows = []
    for certificate, windows in sorted(results.items()):
        for window, result in windows.items():
            for measure, summary in result["summaries"].items():
                rows.append(
                    {
                        "certificate": certificate,
                        "window": window,
                        "measure": measure,
                        "q10": summary["q10"],
                        "q50": summary["q50"],
                        "q90": summary["q90"],
                        "status": summary["validity"]["status"],
                        "persistent_support_fraction": result[
                            "persistent_support_fraction"
                        ],
                    }
                )

    sensitivity = {}
    certificates = sorted(results)
    for measure in ar.MEASURES:
        sensitivity[measure] = {}
        for statistic in ("q10", "q50", "q90"):
            pairs = []
            for certificate in certificates:
                core = (
                    results.get(certificate, {})
                    .get("core", {})
                    .get("summaries", {})
                    .get(measure, {})
                    .get(statistic)
                )
                wide = (
                    results.get(certificate, {})
                    .get("wide", {})
                    .get("summaries", {})
                    .get(measure, {})
                    .get(statistic)
                )
                pairs.append((core, wide))
            sensitivity[measure][statistic] = {
                "core_wide_rank_spearman": _spearman(pairs),
                "paired_stones": sum(
                    left is not None and right is not None for left, right in pairs
                ),
            }

    core_primary = {
        certificate: results[certificate]["core"]["summaries"][PRIMARY_MEASURE]
        for certificate in certificates
        if "core" in results[certificate]
    }
    profile_redundancy = {}
    for field in PROFILE_FIELDS:
        reference = _profile_values(profile, field)
        profile_redundancy[field] = {}
        for statistic in ("q10", "q50", "q90"):
            pairs = [
                (
                    core_primary[certificate].get(statistic),
                    reference.get(certificate),
                )
                for certificate in core_primary
            ]
            profile_redundancy[field][statistic] = {
                "spearman": _spearman(pairs),
                "paired_stones": sum(
                    left is not None and right is not None for left, right in pairs
                ),
            }

    tier_redundancy = {}
    if tier_contrast:
        for pair_id in ("centre__inner", "inner__middle"):
            tier_redundancy[pair_id] = {}
            for statistic in ("q10", "q50", "q90"):
                reference = _tier_values(tier_contrast, pair_id, statistic)
                pairs = [
                    (
                        core_primary[certificate].get(statistic),
                        reference.get(certificate),
                    )
                    for certificate in core_primary
                ]
                tier_redundancy[pair_id][statistic] = {
                    "spearman": _spearman(pairs),
                    "paired_stones": sum(
                        left is not None and right is not None
                        for left, right in pairs
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
        lookup = {
            row["source_index"]: row
            for row in core["frame_trace"]
        }
        observation_rows.append(
            {
                "id": observation_id,
                "certificate": certificate,
                "concept": observation.get("concept"),
                "role": observation.get("role"),
                "summary": observation.get("summary"),
                "source_frames": observation.get("source_frames", []),
                "articulation": [
                    {
                        "source_index": source_index,
                        "raw_spread": lookup.get(source_index, {}).get("raw_spread"),
                        "relative_to_whole_median": lookup.get(
                            source_index, {}
                        ).get("relative_to_whole_median"),
                        "log_spread": lookup.get(source_index, {}).get("log_spread"),
                    }
                    for source_index in observation.get("source_frames", [])
                ],
            }
        )

    return {
        "schema_version": SUMMARY_SCHEMA,
        "descriptor_schema": SCHEMA,
        "issue": 51,
        "primary_measure": PRIMARY_MEASURE,
        "scope": (
            "descriptive within-inner tonal articulation only; no quality direction, "
            "leakage inference, or threshold fitting"
        ),
        "rows": rows,
        "core_wide_sensitivity": sensitivity,
        "redundancy_diagnostics": {
            "note": "Spearman correlations are diagnostic only at n=4.",
            "retained_profile": profile_redundancy,
            "adjacent_tier_contrast": tier_redundancy,
            "adjacent_tier_status": (
                "available" if tier_contrast else "pending_sibling_49"
            ),
        },
        "human_observation_checks": observation_rows,
        "disposition": "PENDING_SOURCE_EVIDENCE_REVIEW",
        "disposition_rule": (
            "KEEP only if low articulation visibly matches pale/flat inner observations, "
            "survives normalization, and adds information beyond retained descriptors "
            "and sibling #49; otherwise REVISE or REJECT."
        ),
    }


def write_benchmark_summary(summary, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    fields = [
        "certificate",
        "window",
        "measure",
        "q10",
        "q50",
        "q90",
        "status",
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


def run_benchmark(
    manifest_path,
    source_root,
    output,
    tier_contrast_summary=None,
):
    """Reprocess the canonical source bundles and run core/wide articulation."""
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
        with tempfile.TemporaryDirectory(prefix=f".articulation-{certificate}-") as td:
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
    observations = _load_optional(
        repo_root / "docs/360/calibration/human-observations.json"
    )
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
        f"{len({row['certificate'] for row in summary['rows']})} stones "
        f"-> {args.output}"
    )


if __name__ == "__main__":
    main()
