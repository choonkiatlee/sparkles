"""Run auditable relative-dark occupancy measurements on Asscher 360 intervals."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a
from . import activation_benchmark as ab
from . import occupancy as o

SCHEMA = "diamond360-relative-dark-occupancy/1"
THRESHOLDS = (0.60, 0.65, 0.70)
BASELINE_THRESHOLD = 0.65

# Public reuse of the deterministic gap-aware selector proven by #26.
select_evidence_frames = ab.select_evidence_frames


def _threshold_key(value):
    return f"{float(value):.2f}"


def _check_thresholds(thresholds):
    values = tuple(float(value) for value in thresholds)
    if values != THRESHOLDS:
        raise ValueError(f"occupancy benchmark thresholds are fixed at {THRESHOLDS}")
    return values


def _summary_reasons(cell):
    if cell["summary"].get("status") == "ok":
        return []
    counts = [value for value in cell.get("supported_pixel_counts", []) if value is not None]
    if not counts or max(counts, default=0) == 0:
        return ["no_support"]
    return ["invalid_whole_stone_reference_or_no_finite_occupancy"]


def _region_cells(
    representation,
    masks,
    brightness,
    valid_masks,
    whole_values,
    observed,
    upstream,
    step_qc,
    source_indices,
    thresholds,
):
    regions = {}
    for region, region_masks in masks.items():
        regions[region] = {}
        for mode in ("fixed", "dynamic"):
            threshold_results = {}
            for threshold in thresholds:
                cell = o.occupancy_trace(
                    brightness,
                    valid_masks,
                    region_masks,
                    whole_values,
                    observed,
                    mode,
                    threshold,
                )
                reasons = _summary_reasons(cell)
                cell["validity"] = a.activation_validity(
                    representation,
                    upstream,
                    step_qc,
                    cell["summary"]["status"],
                    reasons,
                )
                cell["evidence"] = select_evidence_frames(cell["values"], source_indices)
                threshold_results[_threshold_key(threshold)] = cell
            threshold_results[_threshold_key(BASELINE_THRESHOLD)]["evidence_panel"] = (
                f"evidence/{representation}-{region}-{mode}.png"
            )
            regions[region][mode] = {"thresholds": threshold_results}
    return regions


def measure_stone(processed, step_output, indices, wrap=False, thresholds=THRESHOLDS):
    """Measure all coarse/semantic × fixed/dynamic occupancy cells on identical frames."""
    thresholds = _check_thresholds(thresholds)
    processed = Path(processed).resolve()
    step_output = Path(step_output).resolve()
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, excluded = ab._select_records(metadata, list(indices), wrap)
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = ab._load_frame_arrays(processed, selected)
    upstream = ab._upstream_validity(selected, excluded)

    whole = a.whole_stone_trace(brightness, valid_masks, stone_masks, observed)
    whole_reasons = [] if whole["summary"].get("status") == "ok" else [
        "no_support" if not whole["persistent_support_pixels"] else "insufficient_finite_frames"
    ]
    whole["validity"] = a.activation_validity(
        "whole_stone", upstream, None, whole["summary"]["status"], whole_reasons
    )

    coarse_masks = a.load_coarse_masks(processed, selected)
    semantic_masks, step_qc = a.load_semantic_masks(step_output, selected)
    representations = {
        "coarse": {
            "source_indices": list(indices),
            "regions": _region_cells(
                "coarse", coarse_masks, brightness, valid_masks, whole["values"], observed,
                upstream, None, list(indices), thresholds,
            ),
        },
        "semantic": {
            "source_indices": list(indices),
            "qc": step_qc,
            "regions": {},
        },
    }
    if semantic_masks:
        representations["semantic"]["regions"] = _region_cells(
            "semantic", semantic_masks, brightness, valid_masks, whole["values"], observed,
            upstream, step_qc, list(indices), thresholds,
        )
    else:
        representations["semantic"]["validity"] = a.activation_validity(
            "semantic", upstream, step_qc, "unavailable", ["semantic_masks_unavailable"]
        )

    return {
        "schema_version": SCHEMA,
        "requested_indices": list(indices),
        "accepted_indices": [record["source_index"] for record in selected if record is not None],
        "excluded": excluded,
        "wrap_explicit": bool(wrap),
        "brightness_definition": metadata.get("brightness_definition"),
        "thresholds": list(thresholds),
        "baseline_threshold": BASELINE_THRESHOLD,
        "occupancy_definition": "count(Y_t(p) < k * G_t on supported region pixels) / supported pixel count",
        "threshold_boundary": "strict_less_than",
        "whole_stone_reference": {
            "definition": "median encoded brightness on fixed common registered stone support",
            "source": "diamond360.activation.whole_stone_trace",
            **whole,
        },
        "upstream_validity": upstream,
        "representations": representations,
        "frame_rgb_paths": rgb_paths,
    }


def _support_for_frame(region_masks, valid_masks, observed, mode, position):
    if mode == "fixed":
        if not observed.any():
            return np.zeros(region_masks.shape[1:], bool)
        return np.all((valid_masks & region_masks)[observed], axis=0)
    return valid_masks[position] & region_masks[position]


def _overlay_frame(rgb, support, dark):
    array = np.asarray(rgb.convert("RGB"), dtype=np.float32).copy()
    if array.shape[:2] != support.shape:
        raise ValueError("evidence RGB and support mask shapes must match")
    array[support] = 0.75 * array[support] + 0.25 * np.array([40.0, 150.0, 255.0])
    array[dark] = 0.30 * array[dark] + 0.70 * np.array([255.0, 35.0, 35.0])
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def _write_cell_panel(
    destination,
    title,
    evidence,
    source_indices,
    rgb_paths,
    processed,
    brightness,
    valid_masks,
    region_masks,
    whole_values,
    observed,
    mode,
):
    items = []
    for label in ("q10", "q50", "q90", "largest_positive_move", "largest_negative_move"):
        item = evidence.get(label)
        if item is not None and all(existing[1]["position"] != item["position"] for existing in items):
            items.append((label, item))
    width = max(1, len(items)) * 230
    canvas = Image.new("RGB", (width, 300), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")
    for slot, (label, item) in enumerate(items):
        position = item["position"]
        support = _support_for_frame(region_masks, valid_masks, observed, mode, position)
        whole = whole_values[position]
        dark = np.zeros_like(support)
        if whole is not None and math.isfinite(float(whole)) and float(whole) > 0:
            dark = support & (brightness[position] < BASELINE_THRESHOLD * float(whole))
        x = slot * 230
        path = rgb_paths[position]
        if path:
            frame = _overlay_frame(Image.open(processed / path), support, dark)
            frame.thumbnail((215, 225))
            canvas.paste(frame, (x + 7, 55))
        suffix = f" d={item['delta']:+.3f}" if "delta" in item else ""
        draw.text((x + 7, 33), f"{label} src {source_indices[position]}{suffix}", fill="black")
    draw.text((10, 282), "blue=supported region; red=classified relatively dark (k=0.65)", fill="black")
    canvas.save(destination)


def _write_baseline_evidence(result, output, processed, step_output):
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, _ = ab._select_records(metadata, result["requested_indices"], result["wrap_explicit"])
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = ab._load_frame_arrays(processed, selected)
    whole_values = a.whole_stone_trace(brightness, valid_masks, stone_masks, observed)["values"]
    mask_sets = {"coarse": a.load_coarse_masks(processed, selected)}
    semantic, _ = a.load_semantic_masks(step_output, selected)
    if semantic:
        mask_sets["semantic"] = semantic

    for representation, masks in mask_sets.items():
        rep = result["representations"][representation]
        for region, region_masks in masks.items():
            if region not in rep.get("regions", {}):
                continue
            for mode in ("fixed", "dynamic"):
                cell = rep["regions"][region][mode]["thresholds"][_threshold_key(BASELINE_THRESHOLD)]
                _write_cell_panel(
                    output / cell["evidence_panel"],
                    f"{representation} / {region} / {mode} / occupancy",
                    cell["evidence"], result["requested_indices"], rgb_paths, processed,
                    brightness, valid_masks, region_masks, whole_values, observed, mode,
                )


def write_stone_outputs(result, output, processed, step_output):
    """Write machine-readable outputs and baseline dark-pixel evidence panels."""
    output = Path(output)
    processed = Path(processed)
    step_output = Path(step_output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "occupancy.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")

    fields = [
        "threshold", "representation", "region", "support_mode", "status", "reasons",
        "finite_frames", "mean", "median", "q10", "q50", "q90",
        "persistent_support_fraction",
    ]
    rows = []
    for representation, rep in result["representations"].items():
        for region, modes in rep.get("regions", {}).items():
            for mode, wrapper in modes.items():
                for threshold_key, cell in wrapper["thresholds"].items():
                    summary = cell["summary"]
                    validity = cell["validity"]
                    rows.append({
                        "threshold": float(threshold_key),
                        "representation": representation,
                        "region": region,
                        "support_mode": mode,
                        "status": validity["status"],
                        "reasons": ";".join(validity["reasons"]),
                        "finite_frames": summary["finite_frames"],
                        "mean": summary["mean"],
                        "median": summary["median"],
                        "q10": summary["q10"],
                        "q50": summary["q50"],
                        "q90": summary["q90"],
                        "persistent_support_fraction": cell.get("persistent_support_fraction"),
                    })
    with (output / "occupancy.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    _write_baseline_evidence(result, output, processed, step_output)
