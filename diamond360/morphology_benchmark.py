"""Run auditable broad-vs-fragmented bright-flash morphology measurements."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from . import activation as a
from . import activation_benchmark as ab
from . import morphology as m

SCHEMA = "diamond360-flash-morphology/1"
THRESHOLDS = (0.90, 1.00, 1.10)
BASELINE_THRESHOLD = 1.00
CONNECTIVITY = 8


def _threshold_key(value):
    return f"{float(value):.2f}"


def _check_thresholds(thresholds):
    values = tuple(float(value) for value in thresholds)
    if values != THRESHOLDS:
        raise ValueError(f"morphology benchmark thresholds are fixed at {THRESHOLDS}")
    return values


def _summary_reasons(cell):
    summary = cell["summary"]
    if summary.get("status") == "ok":
        return []
    if cell.get("persistent_support_pixels", 0) == 0:
        return ["no_support"]
    return ["no_active_frames_or_reference_scale"]


def _enrich_source_indices(cell, source_indices):
    for frame in cell["frames"]:
        position = frame["position"]
        frame["source_index"] = source_indices[position]


def measure_stone(
    processed,
    indices,
    wrap=False,
    thresholds=THRESHOLDS,
    connectivity=CONNECTIVITY,
):
    """Measure whole-stone bright-flash morphology on identical fixed/dynamic support."""
    thresholds = _check_thresholds(thresholds)
    if connectivity != CONNECTIVITY:
        raise ValueError(f"morphology benchmark connectivity is fixed at {CONNECTIVITY}")
    processed = Path(processed).resolve()
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, excluded = ab._select_records(metadata, list(indices), wrap)
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = ab._load_frame_arrays(processed, selected)
    upstream = ab._upstream_validity(selected, excluded)

    whole = a.whole_stone_trace(brightness, valid_masks, stone_masks, observed)
    whole_reasons = ab._summary_reason(whole["summary"], whole["persistent_support_pixels"])
    whole["validity"] = a.activation_validity(
        "whole_stone", upstream, None, whole["summary"]["status"], whole_reasons
    )

    supports = {}
    for support_mode in ("fixed", "dynamic"):
        sweep = m.threshold_sweep(
            brightness,
            valid_masks,
            stone_masks,
            whole["values"],
            observed,
            support_mode,
            thresholds=thresholds,
            connectivity=connectivity,
        )
        for cell in sweep.values():
            _enrich_source_indices(cell, list(indices))
            reasons = _summary_reasons(cell)
            cell["validity"] = a.activation_validity(
                "whole_stone",
                upstream,
                None,
                cell["summary"]["status"],
                reasons,
            )
        baseline = sweep[_threshold_key(BASELINE_THRESHOLD)]
        supports[support_mode] = {
            "thresholds": sweep,
            "baseline_evidence": m.select_frame_evidence(
                baseline["frames"], list(indices)
            ),
            "threshold_sensitivity": m.select_threshold_sensitivity(
                sweep, list(indices), baseline=_threshold_key(BASELINE_THRESHOLD)
            ),
        }

    baseline_key = _threshold_key(BASELINE_THRESHOLD)
    support_disagreement = m.select_support_disagreement(
        supports["fixed"]["thresholds"][baseline_key]["frames"],
        supports["dynamic"]["thresholds"][baseline_key]["frames"],
        list(indices),
    )

    return {
        "schema_version": SCHEMA,
        "requested_indices": list(indices),
        "accepted_indices": [
            record["source_index"] for record in selected if record is not None
        ],
        "excluded": excluded,
        "wrap_explicit": bool(wrap),
        "brightness_definition": metadata.get("brightness_definition"),
        "active_field_definition": (
            "Y_t(p) > G_t + k*S_t on declared whole-stone support; "
            "G_t is #26 median encoded brightness and S_t is 1.4826*MAD about G_t, "
            "both measured on fixed common registered stone support"
        ),
        "contrast_scale_definition": "S_t = 1.4826 * median(|Y_t(p)-G_t|) on fixed common support",
        "threshold_boundary": "strict_greater_than",
        "thresholds": list(thresholds),
        "baseline_threshold": BASELINE_THRESHOLD,
        "connectivity": connectivity,
        "representation_policy": {
            "production_geometry": "whole registered stone",
            "support_axis": ["fixed", "dynamic"],
            "radial_partition_axis": "omitted",
            "reason": (
                "coarse/semantic radial boundaries would split otherwise connected "
                "whole-stone flashes and therefore manufacture the morphology being measured"
            ),
        },
        "candidate_measurements": {
            "largest_component_fraction": (
                "largest active 8-connected component pixels / all active pixels"
            ),
            "effective_component_count": (
                "inverse Simpson concentration of connected-component area shares; "
                "1 for one component and N for N equal components"
            ),
            "component_count": "raw audit field only, not a retained scalar by default",
        },
        "whole_stone_reference": {
            "definition": (
                "median encoded brightness on fixed common registered stone support"
            ),
            "source": "diamond360.activation.whole_stone_trace",
            **whole,
        },
        "upstream_validity": upstream,
        "supports": supports,
        "support_disagreement": support_disagreement,
        "frame_rgb_paths": rgb_paths,
    }


def _support_for_frame(valid_masks, stone_masks, observed, support_mode, position):
    if support_mode == "fixed":
        if not observed.any():
            return np.zeros(stone_masks.shape[1:], bool)
        return np.all((valid_masks & stone_masks)[observed], axis=0)
    return valid_masks[position] & stone_masks[position]


def _overlay(rgb, support, active):
    array = np.asarray(rgb.convert("RGB"), dtype=np.float32).copy()
    if array.shape[:2] != support.shape:
        raise ValueError("evidence RGB and support mask shapes must match")
    structure = np.ones((3, 3), bool)
    labels, count = ndimage.label(active & support, structure=structure)
    largest = np.zeros_like(support)
    if count:
        sizes = np.bincount(labels.ravel())[1:]
        label = int(np.argmax(sizes)) + 1
        largest = labels == label
    array[support] = 0.88 * array[support] + 0.12 * np.array([40.0, 140.0, 255.0])
    array[active & support] = (
        0.50 * array[active & support] + 0.50 * np.array([255.0, 175.0, 30.0])
    )
    array[largest] = 0.25 * array[largest] + 0.75 * np.array([255.0, 35.0, 35.0])
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def _render_tile(
    processed,
    rgb_paths,
    brightness,
    valid_masks,
    stone_masks,
    whole_values,
    observed,
    position,
    support_mode,
    threshold,
):
    path = rgb_paths[position]
    if not path:
        return None
    support = _support_for_frame(
        valid_masks, stone_masks, observed, support_mode, position
    )
    common = (
        np.all((valid_masks & stone_masks)[observed], axis=0)
        if observed.any() else np.zeros(stone_masks.shape[1:], bool)
    )
    scale = m.robust_bright_scale(brightness[position], common, whole_values[position])
    state = m.relative_bright_state(
        brightness[position], whole_values[position], scale, threshold
    )
    active = np.zeros_like(support) if state is None else state & support
    with Image.open(processed / path) as source:
        tile = _overlay(source, support, active)
    tile.thumbnail((220, 220))
    return tile


def _diagnostic_slots(result):
    fixed = result["supports"]["fixed"]["baseline_evidence"]
    slots = []
    for label in ("broadest", "most_fragmented"):
        item = fixed.get(label)
        if item is not None:
            slots.append((label, item["position"], "fixed"))
    matched = fixed.get("matched_active_area_pair")
    if matched:
        slots.append(("matched A", matched["left"]["position"], "fixed"))
        slots.append(("matched B", matched["right"]["position"], "fixed"))
    threshold = result["supports"]["fixed"].get("threshold_sensitivity")
    if threshold:
        slots.append(("threshold-sensitive", threshold["position"], "fixed"))
    disagreement = result.get("support_disagreement", {}).get("strongest")
    if disagreement:
        slots.append(("support fixed", disagreement["position"], "fixed"))
        slots.append(("support dynamic", disagreement["position"], "dynamic"))
    control = result.get("support_disagreement", {}).get("control")
    if control and all(
        not (position == control["position"] and mode == "fixed")
        for _, position, mode in slots
    ):
        slots.append(("low-disagreement", control["position"], "fixed"))
    return slots


def write_stone_outputs(result, output, processed):
    """Write compact JSON/CSV plus one morphology diagnostic panel."""
    output = Path(output)
    processed = Path(processed).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "morphology.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    fields = [
        "support_mode",
        "threshold",
        "status",
        "reasons",
        "observed_frames",
        "active_frames",
        "active_frame_fraction",
        "median_active_fraction",
        "median_largest_component_fraction",
        "q10_largest_component_fraction",
        "q90_largest_component_fraction",
        "median_effective_component_count",
        "q90_effective_component_count",
        "median_boundary_active_fraction",
        "median_reference_scale",
        "persistent_support_fraction",
    ]
    rows = []
    for support_mode, wrapper in result["supports"].items():
        for threshold_key, cell in wrapper["thresholds"].items():
            summary = cell["summary"]
            validity = cell["validity"]
            rows.append({
                "support_mode": support_mode,
                "threshold": float(threshold_key),
                "status": validity["status"],
                "reasons": ";".join(validity["reasons"]),
                **{key: summary.get(key) for key in fields if key in summary},
                "persistent_support_fraction": cell.get("persistent_support_fraction"),
            })
    with (output / "morphology.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in fields} for row in rows])

    metadata = json.loads((processed / "sequence.json").read_text())
    selected, _ = ab._select_records(
        metadata, result["requested_indices"], result["wrap_explicit"]
    )
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = ab._load_frame_arrays(
        processed, selected
    )
    whole_values = a.whole_stone_trace(
        brightness, valid_masks, stone_masks, observed
    )["values"]

    slots = _diagnostic_slots(result)
    columns = 4
    tile_w, tile_h = 240, 270
    rows_n = max(1, (len(slots) + columns - 1) // columns)
    canvas = Image.new("RGB", (columns * tile_w, rows_n * tile_h + 45), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        "blue=support; orange=bright active field; red=largest connected component",
        fill="black",
    )
    for slot, (label, position, support_mode) in enumerate(slots):
        x = (slot % columns) * tile_w
        y = 45 + (slot // columns) * tile_h
        tile = _render_tile(
            processed,
            rgb_paths,
            brightness,
            valid_masks,
            stone_masks,
            whole_values,
            observed,
            position,
            support_mode,
            BASELINE_THRESHOLD,
        )
        if tile is not None:
            canvas.paste(tile, (x + 8, y + 28))
        draw.text(
            (x + 8, y + 6),
            f"{label}: src {result['requested_indices'][position]} ({support_mode})",
            fill="black",
        )
    canvas.save(output / "evidence" / "diagnostic.png")


def main():
    parser = argparse.ArgumentParser(
        description="Measure broad-vs-fragmented bright-flash morphology"
    )
    parser.add_argument("processed", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--wrap", action="store_true")
    args = parser.parse_args()
    indices = [int(value) for value in args.indices.split(",")]
    result = measure_stone(args.processed, indices, wrap=args.wrap)
    write_stone_outputs(result, args.output, args.processed)
    print(args.output / "morphology.json")


if __name__ == "__main__":
    main()
