"""Run auditable bright/dark persistence measurements on Asscher 360 intervals."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a
from . import activation_benchmark as ab
from . import occupancy as o
from . import persistence as p

SCHEMA = "diamond360-bright-dark-persistence/1"
THRESHOLDS = (0.60, 0.65, 0.70)
BASELINE_THRESHOLD = 0.65


def _threshold_key(value):
    return f"{float(value):.2f}"


def _check_thresholds(thresholds):
    values = tuple(float(value) for value in thresholds)
    if values != THRESHOLDS:
        raise ValueError(f"persistence benchmark thresholds are fixed at {THRESHOLDS}")
    return values


def _cell_reasons(cell):
    if cell.get("status") == "ok":
        return []
    if cell.get("valid_reference_frames", 0) == 0:
        return ["no_observed_valid_reference_frames"]
    return ["no_run_support"]


def _enrich_event(event, source_indices, shape):
    if event is None:
        return None
    result = dict(event)
    for key in ("start", "middle", "end"):
        pos = event[f"{key}_position"]
        result[f"{key}_source_index"] = source_indices[pos]
    flat = result.pop("representative_flat_pixel", None)
    if flat is not None:
        row, col = divmod(int(flat), int(shape[1]))
        result["representative_pixel"] = {"row": row, "col": col}
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
        for mode in ("fixed", "dynamic"):
            threshold_results = {}
            for threshold in thresholds:
                cell = p.persistence_trace(
                    brightness,
                    valid_masks,
                    region_masks,
                    whole_values,
                    observed,
                    mode,
                    threshold,
                )
                cell["validity"] = a.activation_validity(
                    representation,
                    upstream,
                    step_qc,
                    cell["status"],
                    _cell_reasons(cell),
                )
                cell["evidence"] = {
                    state: _enrich_event(event, source_indices, brightness.shape[1:])
                    for state, event in cell["evidence"].items()
                }
                threshold_results[_threshold_key(threshold)] = cell
            threshold_results[_threshold_key(BASELINE_THRESHOLD)]["evidence_panel"] = (
                f"evidence/{representation}-{region}-{mode}.png"
            )
            regions[region][mode] = {"thresholds": threshold_results}
    return regions


def measure_stone(processed, step_output, indices, wrap=False, thresholds=THRESHOLDS):
    """Measure coarse/semantic x fixed/dynamic persistence on identical frames."""
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
                "coarse",
                coarse_masks,
                brightness,
                valid_masks,
                whole["values"],
                observed,
                upstream,
                None,
                list(indices),
                thresholds,
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
            "semantic",
            semantic_masks,
            brightness,
            valid_masks,
            whole["values"],
            observed,
            upstream,
            step_qc,
            list(indices),
            thresholds,
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
            "definition": "dark iff Y_t(p) < k * G_t; non_dark is the complement",
            "threshold_boundary": "strict_less_than",
            "whole_stone_reference": "same fixed-support G_t used by #27/#28",
            "bright_label_warning": "non_dark is not an independently calibrated bright state",
        },
        "run_definition": (
            "maximal consecutive observed source-step states; gaps, invalid references and support loss "
            "break and censor runs; interval endpoints censor; no end-to-start loop closure"
        ),
        "normalization": "p90 longest observed run frames / requested source steps",
        "units": "observed source steps, not seconds or calibrated degrees",
        "whole_stone_reference": {
            "definition": "median encoded brightness on fixed common registered stone support",
            "source": "diamond360.activation.whole_stone_trace",
            **whole,
        },
        "upstream_validity": upstream,
        "representations": representations,
        "frame_rgb_paths": rgb_paths,
    }


def _support_stack(region_masks, valid_masks, observed, mode):
    supported = valid_masks & region_masks
    if mode == "fixed":
        common = (
            np.all(supported[observed], axis=0)
            if observed.any()
            else np.zeros(region_masks.shape[1:], bool)
        )
        return np.broadcast_to(common, supported.shape).copy()
    return supported


def _state_stack(brightness, whole_values, observed):
    states = np.zeros(brightness.shape, bool)
    reference_valid = np.zeros(len(brightness), bool)
    for i, (frame, whole, ok) in enumerate(zip(brightness, whole_values, observed)):
        if not ok:
            continue
        state = o.relative_dark_state(frame, whole, BASELINE_THRESHOLD)
        if state is not None:
            states[i] = state
            reference_valid[i] = True
    return states, reference_valid


def _overlay(rgb, support, persistent, target_state):
    array = np.asarray(rgb.convert("RGB"), dtype=np.float32).copy()
    if array.shape[:2] != support.shape:
        raise ValueError("evidence RGB and support mask shapes must match")
    array[support] = 0.80 * array[support] + 0.20 * np.array([40.0, 150.0, 255.0])
    tint = (
        np.array([255.0, 45.0, 45.0])
        if target_state == "dark"
        else np.array([255.0, 210.0, 30.0])
    )
    array[persistent] = 0.25 * array[persistent] + 0.75 * tint
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def _write_cell_panel(
    destination,
    title,
    cell,
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
    support = _support_stack(region_masks, valid_masks, observed, mode)
    states, reference_valid = _state_stack(brightness, whole_values, observed)
    canvas = Image.new("RGB", (690, 620), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")
    row_y = 35

    for state_name in ("dark", "non_dark"):
        event = cell["evidence"].get(state_name)
        if event is None:
            draw.text((10, row_y), f"{state_name}: no observed run", fill="black")
            row_y += 285
            continue
        start, middle, end = (
            event[f"{key}_position"] for key in ("start", "middle", "end")
        )
        target = states == (state_name == "dark")
        availability = support & (observed & reference_valid)[:, None, None]
        persistent = np.all((target & availability)[start:end + 1], axis=0)
        draw.text(
            (10, row_y),
            f"{state_name}: {event['observed_run_length_frames']} steps; "
            f"{event['left_boundary']} -> {event['right_boundary']}; "
            f"pixels={int(persistent.sum())}",
            fill="black",
        )
        for j, position in enumerate((start, middle, end)):
            x = 5 + j * 225
            path = rgb_paths[position]
            if path:
                frame = _overlay(
                    Image.open(processed / path),
                    support[position],
                    persistent,
                    state_name,
                )
                frame.thumbnail((215, 220))
                canvas.paste(frame, (x, row_y + 40))
            draw.text((x, row_y + 22), f"src {source_indices[position]}", fill="black")
        row_y += 285

    draw.text(
        (10, 600),
        "blue=support; red=persistent dark; yellow=persistent non-dark",
        fill="black",
    )
    canvas.save(destination)


def _write_baseline_evidence(result, output, processed, step_output):
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
                cell = rep["regions"][region][mode]["thresholds"][
                    _threshold_key(BASELINE_THRESHOLD)
                ]
                _write_cell_panel(
                    output / cell["evidence_panel"],
                    f"{representation} / {region} / {mode} / persistence",
                    cell,
                    result["requested_indices"],
                    rgb_paths,
                    processed,
                    brightness,
                    valid_masks,
                    region_masks,
                    whole_values,
                    observed,
                    mode,
                )


def write_stone_outputs(result, output, processed, step_output):
    """Write machine-readable outputs plus baseline start/middle/end evidence panels."""
    output = Path(output)
    processed = Path(processed)
    step_output = Path(step_output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "persistence.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    fields = [
        "threshold",
        "representation",
        "region",
        "support_mode",
        "status",
        "reasons",
        "requested_source_steps",
        "valid_reference_frames",
        "eligible_pixel_observations",
        "persistent_support_fraction",
        "state",
        "finite_pixels",
        "q50_frames",
        "q90_frames",
        "q90_window_fraction",
        "max_frames",
        "fraction_nonzero",
        "longest_any_censored_fraction",
        "longest_all_censored_fraction",
        "total_runs",
        "completed_runs",
        "censored_runs",
    ]
    rows = []
    for representation, rep in result["representations"].items():
        for region, modes in rep.get("regions", {}).items():
            for mode, wrapper in modes.items():
                for threshold_key, cell in wrapper["thresholds"].items():
                    validity = cell["validity"]
                    for state_name in ("dark", "non_dark"):
                        state = cell[state_name]
                        rows.append({
                            "threshold": float(threshold_key),
                            "representation": representation,
                            "region": region,
                            "support_mode": mode,
                            "status": validity["status"],
                            "reasons": ";".join(validity["reasons"]),
                            "requested_source_steps": cell["requested_source_steps"],
                            "valid_reference_frames": cell["valid_reference_frames"],
                            "eligible_pixel_observations": cell["eligible_pixel_observations"],
                            "persistent_support_fraction": cell["persistent_support_fraction"],
                            "state": state_name,
                            **{
                                key: state.get(key)
                                for key in (
                                    "finite_pixels",
                                    "q50_frames",
                                    "q90_frames",
                                    "q90_window_fraction",
                                    "max_frames",
                                    "fraction_nonzero",
                                    "longest_any_censored_fraction",
                                    "longest_all_censored_fraction",
                                    "total_runs",
                                    "completed_runs",
                                    "censored_runs",
                                )
                            },
                        })

    with (output / "persistence.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    _write_baseline_evidence(result, output, processed, step_output)
