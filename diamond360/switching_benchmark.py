"""Run auditable bright/dark switching measurements on Asscher 360 intervals."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a
from . import activation_benchmark as ab
from . import occupancy as o
from . import switching as s

SCHEMA = "diamond360-bright-dark-switching/1"
THRESHOLDS = (0.60, 0.65, 0.70)
BASELINE_THRESHOLD = 0.65


def _threshold_key(value):
    return f"{float(value):.2f}"


def _check_thresholds(thresholds):
    values = tuple(float(value) for value in thresholds)
    if values != THRESHOLDS:
        raise ValueError(f"switching benchmark thresholds are fixed at {THRESHOLDS}")
    return values


def _cell_reasons(cell):
    if cell.get("status") == "ok":
        return []
    if cell.get("valid_reference_pairs", 0) == 0:
        return ["no_observed_valid_reference_pairs"]
    return ["no_pair_support"]


def _enrich_pair_trace(cell, source_indices):
    for item in cell["pair_trace"]:
        item["left_source_index"] = source_indices[item["left_position"]]
        item["right_source_index"] = source_indices[item["right_position"]]


def _enrich_evidence(evidence, source_indices):
    result = {}
    for label, item in evidence.items():
        if item is None:
            result[label] = None
            continue
        enriched = dict(item)
        enriched["left_source_index"] = source_indices[item["left_position"]]
        enriched["right_source_index"] = source_indices[item["right_position"]]
        result[label] = enriched
    return result


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
        for mode in ("fixed", "pair_local"):
            threshold_results = {}
            for threshold in thresholds:
                cell = s.switching_trace(
                    brightness,
                    valid_masks,
                    region_masks,
                    whole_values,
                    observed,
                    mode,
                    threshold,
                )
                _enrich_pair_trace(cell, source_indices)
                cell["validity"] = a.activation_validity(
                    representation,
                    upstream,
                    step_qc,
                    cell["status"],
                    _cell_reasons(cell),
                )
                cell["evidence"] = _enrich_evidence(
                    s.select_pair_evidence(cell["pair_trace"]), source_indices
                )
                threshold_results[_threshold_key(threshold)] = cell
            threshold_results[_threshold_key(BASELINE_THRESHOLD)]["evidence_panel"] = (
                f"evidence/{representation}-{region}-{mode}.png"
            )
            regions[region][mode] = {"thresholds": threshold_results}
    return regions


def measure_stone(processed, step_output, indices, wrap=False, thresholds=THRESHOLDS):
    """Measure coarse/semantic x fixed/pair-local switching on identical frames."""
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
        "state_definition": {
            "source": "diamond360-relative-dark-occupancy/1",
            "definition": "Y_t(p) < k * G_t",
            "threshold_boundary": "strict_less_than",
            "whole_stone_reference": "same fixed-support G_t used by #27",
        },
        "switch_definition": (
            "state differs across an observed adjacent requested source-step pair; "
            "pixels must be supported on both sides of the pair"
        ),
        "regional_summary": "sum switched pixel-pairs / sum eligible pixel-pairs",
        "units": "per observed source-step pair; not seconds or calibrated degrees",
        "whole_stone_reference": {
            "definition": "median encoded brightness on fixed common registered stone support",
            "source": "diamond360.activation.whole_stone_trace",
            **whole,
        },
        "upstream_validity": upstream,
        "representations": representations,
        "frame_rgb_paths": rgb_paths,
    }


def _support_for_pair(region_masks, valid_masks, observed, mode, left, right):
    if mode == "fixed":
        if not observed.any():
            return np.zeros(region_masks.shape[1:], bool)
        return np.all((valid_masks & region_masks)[observed], axis=0)
    return (valid_masks[left] & region_masks[left]) & (valid_masks[right] & region_masks[right])


def _overlay_frame(rgb, support, dark, switched):
    array = np.asarray(rgb.convert("RGB"), dtype=np.float32).copy()
    if array.shape[:2] != support.shape:
        raise ValueError("evidence RGB and support mask shapes must match")
    array[support] = 0.78 * array[support] + 0.22 * np.array([40.0, 150.0, 255.0])
    array[dark] = 0.35 * array[dark] + 0.65 * np.array([255.0, 45.0, 45.0])
    array[switched] = 0.20 * array[switched] + 0.80 * np.array([255.0, 210.0, 30.0])
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
    events = [(label, evidence.get(label)) for label in ("highest", "lowest_nonzero")]
    events = [(label, item) for label, item in events if item is not None]
    width = max(1, len(events)) * 450
    canvas = Image.new("RGB", (width, 315), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")

    for event_slot, (label, item) in enumerate(events):
        left = item["left_position"]
        right = item["right_position"]
        support = _support_for_pair(region_masks, valid_masks, observed, mode, left, right)
        left_state = o.relative_dark_state(brightness[left], whole_values[left], BASELINE_THRESHOLD)
        right_state = o.relative_dark_state(brightness[right], whole_values[right], BASELINE_THRESHOLD)
        switched = np.zeros_like(support)
        if left_state is not None and right_state is not None:
            switched = support & (left_state != right_state)
        x0 = event_slot * 450
        for side, position in enumerate((left, right)):
            dark = np.zeros_like(support)
            state = left_state if side == 0 else right_state
            if state is not None:
                dark = support & state
            path = rgb_paths[position]
            if path:
                frame = _overlay_frame(Image.open(processed / path), support, dark, switched)
                frame.thumbnail((210, 225))
                canvas.paste(frame, (x0 + 5 + side * 220, 55))
            draw.text(
                (x0 + 5 + side * 220, 34),
                f"src {source_indices[position]}",
                fill="black",
            )
        draw.text(
            (x0 + 5, 282),
            f"{label}: switch={item['switch_fraction']:.3f} "
            f"({item['switched_pixels']}/{item['eligible_pixels']})",
            fill="black",
        )
    draw.text((10, 300), "blue=support; red=dark state; yellow=switch across pair", fill="black")
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
            for mode in ("fixed", "pair_local"):
                cell = rep["regions"][region][mode]["thresholds"][_threshold_key(BASELINE_THRESHOLD)]
                _write_cell_panel(
                    output / cell["evidence_panel"],
                    f"{representation} / {region} / {mode} / switching",
                    cell["evidence"], result["requested_indices"], rgb_paths, processed,
                    brightness, valid_masks, region_masks, whole_values, observed, mode,
                )


def write_stone_outputs(result, output, processed, step_output):
    """Write machine-readable outputs and baseline adjacent-pair evidence panels."""
    output = Path(output)
    processed = Path(processed)
    step_output = Path(step_output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "switching.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")

    fields = [
        "threshold", "representation", "region", "support_mode", "status", "reasons",
        "requested_adjacent_pairs", "observed_adjacent_pairs", "eligible_pixel_pairs",
        "switched_pixel_pairs", "regional_switch_rate", "pixel_finite_pixels",
        "pixel_rate_q10", "pixel_rate_q50", "pixel_rate_q90", "pixel_fraction_nonzero",
        "persistent_support_fraction",
    ]
    rows = []
    for representation, rep in result["representations"].items():
        for region, modes in rep.get("regions", {}).items():
            for mode, wrapper in modes.items():
                for threshold_key, cell in wrapper["thresholds"].items():
                    validity = cell["validity"]
                    pixel = cell["per_pixel_rate"]
                    rows.append({
                        "threshold": float(threshold_key),
                        "representation": representation,
                        "region": region,
                        "support_mode": mode,
                        "status": validity["status"],
                        "reasons": ";".join(validity["reasons"]),
                        "requested_adjacent_pairs": cell["requested_adjacent_pairs"],
                        "observed_adjacent_pairs": cell["observed_adjacent_pairs"],
                        "eligible_pixel_pairs": cell["eligible_pixel_pairs"],
                        "switched_pixel_pairs": cell["switched_pixel_pairs"],
                        "regional_switch_rate": cell["regional_switch_rate"],
                        "pixel_finite_pixels": pixel["finite_pixels"],
                        "pixel_rate_q10": pixel["q10"],
                        "pixel_rate_q50": pixel["q50"],
                        "pixel_rate_q90": pixel["q90"],
                        "pixel_fraction_nonzero": pixel["fraction_nonzero"],
                        "persistent_support_fraction": cell["persistent_support_fraction"],
                    })
    with (output / "switching.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    _write_baseline_evidence(result, output, processed, step_output)
