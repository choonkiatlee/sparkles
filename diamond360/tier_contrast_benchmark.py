"""Measure adjacent-tier tonal separation from retained #26 activation outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation_benchmark as ab
from . import tier_contrast as tc

SCHEMA = "diamond360-tier-contrast/1"
REGION_TRACE_SCHEMA = "diamond360-region-traces/1"
PAIRS = (("centre", "inner"), ("inner", "middle"))


def _cell(activation, band):
    return activation["representations"]["coarse"]["regions"][band]["fixed"]


def _pair_id(left, right):
    return f"{left}__{right}"


def _unavailable_standardized(reason):
    return {
        "frame_trace": [],
        "values": [],
        "summary": {
            "finite_frames": 0,
            "q10": None,
            "q50": None,
            "q90": None,
            "status": "unavailable",
            "reasons": [reason],
        },
    }


def measure_from_activation(activation, spread_traces=None):
    """Consume exact #26 coarse-fixed relative traces; do not rederive activation."""
    if activation.get("schema_version") != ab.SCHEMA:
        raise ValueError(f"expected upstream activation schema {ab.SCHEMA}")
    indices = list(activation["requested_indices"])
    pairs = {}
    for left, right in PAIRS:
        left_cell = _cell(activation, left)
        right_cell = _cell(activation, right)
        simple = tc.contrast_trace(
            left_cell["relative_values"],
            right_cell["relative_values"],
            indices,
        )
        simple_validity = tc.compose_validity(
            [left_cell["relative_validity"], right_cell["relative_validity"]],
            simple["summary"],
        )
        if spread_traces and left in spread_traces and right in spread_traces:
            standardized = tc.standardized_trace(
                simple["frame_trace"], spread_traces[left], spread_traces[right]
            )
        else:
            standardized = _unavailable_standardized("standardized_spread_unavailable")
        standardized_validity = tc.compose_validity(
            [left_cell["relative_validity"], right_cell["relative_validity"]],
            standardized["summary"],
        )
        pairs[_pair_id(left, right)] = {
            "left_band": left,
            "right_band": right,
            "primary": True,
            "support_mode": "fixed",
            "representation": "coarse",
            "component_provenance": {
                "left": {
                    "upstream": "#26 coarse-fixed relative activation",
                    "persistent_support_fraction": left_cell.get("persistent_support_fraction"),
                },
                "right": {
                    "upstream": "#26 coarse-fixed relative activation",
                    "persistent_support_fraction": right_cell.get("persistent_support_fraction"),
                },
            },
            "simple": {**simple, "validity": simple_validity},
            "standardized": {**standardized, "validity": standardized_validity},
            "evidence": tc.select_evidence(
                simple["frame_trace"],
                standardized["frame_trace"] if standardized["frame_trace"] else None,
            ),
        }
    return {
        "schema_version": SCHEMA,
        "upstream_activation_schema": activation["schema_version"],
        "requested_indices": indices,
        "accepted_indices": list(activation.get("accepted_indices", [])),
        "excluded": list(activation.get("excluded", [])),
        "wrap_explicit": bool(activation.get("wrap_explicit")),
        "definition": {
            "simple": "abs(r_i,t - r_j,t), where r is #26 coarse-fixed log-relative activation",
            "signed": "r_i,t - r_j,t; preserved for audit/direction only",
            "standardized": "simple separation divided by RMS robust fractional within-band spread",
            "fractional_spread": "1.4826 * MAD(encoded brightness) / median(encoded brightness) on #26 fixed support",
        },
        "candidate_summaries": {
            "q10": "common near-collapse / weak-separation tail",
            "q50": "typical adjacent-tier separation",
            "q90": "strong available separation",
        },
        "pairs": pairs,
        "frame_rgb_paths": list(activation.get("frame_rgb_paths", [])),
    }


def _log_brightness_trace(values):
    result = []
    for value in values:
        if value is None:
            result.append(None)
            continue
        value = float(value)
        result.append(float(np.log(value)) if np.isfinite(value) and value > 0 else None)
    return result


def measure_primary_from_region_trace(trace):
    """Reconstruct the simple candidate from committed fixed-support trace artifacts.

    The older benchmark trace stores the exact per-frame coarse fixed-support
    regional medians. The #26 whole-stone normalization cancels in an
    adjacent-band difference, so this is mathematically identical to computing
    the simple candidate from #26 relative traces.
    """
    if trace.get("schema_version") != REGION_TRACE_SCHEMA:
        raise ValueError(f"expected region trace schema {REGION_TRACE_SCHEMA}")
    indices = list(trace.get("requested_indices") or [])
    regions = trace.get("regions") or {}
    pairs = {}
    for left, right in PAIRS:
        try:
            left_values = regions[left]["median_brightness"]
            right_values = regions[right]["median_brightness"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"missing committed regional medians for {left}/{right}") from exc
        simple = tc.contrast_trace(
            _log_brightness_trace(left_values),
            _log_brightness_trace(right_values),
            indices,
        )
        pairs[_pair_id(left, right)] = {
            "left_band": left,
            "right_band": right,
            "simple": simple,
            "evidence": tc.select_evidence(simple["frame_trace"]),
        }
    return {
        "schema_version": SCHEMA,
        "reconstruction_source_schema": REGION_TRACE_SCHEMA,
        "requested_indices": indices,
        "accepted_indices": list(trace.get("accepted_indices", [])),
        "excluded": list(trace.get("excluded", [])),
        "wrap_explicit": bool(trace.get("wrap_explicit")),
        "identity": (
            "abs((log(B_i)-log(B_whole))-(log(B_j)-log(B_whole))) "
            "= abs(log(B_i)-log(B_j))"
        ),
        "pairs": pairs,
    }


def _fixed_spread_inputs(processed, activation):
    """Load processed #26 inputs and calculate robust spread on identical fixed support."""
    from . import activation as a

    processed = Path(processed)
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, _ = ab._select_records(
        metadata,
        list(activation["requested_indices"]),
        bool(activation.get("wrap_explicit")),
    )
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, _, _ = ab._load_frame_arrays(processed, selected)
    masks = a.load_coarse_masks(processed, selected)
    spreads = {}
    for band in ("centre", "inner", "middle"):
        common = a._persistent_support(valid_masks, masks[band], observed)
        values = []
        for frame, ok in zip(brightness, observed):
            values.append(
                tc.robust_fractional_spread(frame[common])
                if ok and common.any() else None
            )
        spreads[band] = values
    return {
        "spreads": spreads,
        "camera_paths": [
            record.get("camera_original_path") if record is not None else None
            for record in selected
        ],
        "region_paths": [
            record.get("regions_path") if record is not None else None
            for record in selected
        ],
    }


def measure_stone(processed, step_output, indices, wrap=False):
    activation = ab.measure_stone(processed, step_output, indices, wrap=wrap)
    spread_inputs = _fixed_spread_inputs(processed, activation)
    result = measure_from_activation(activation, spread_inputs["spreads"])
    result["frame_camera_paths"] = spread_inputs["camera_paths"]
    result["frame_region_paths"] = spread_inputs["region_paths"]
    return result


def _boundary(mask):
    mask = np.asarray(mask, bool)
    if mask.ndim != 2:
        raise ValueError("region mask must be two-dimensional")
    interior = mask.copy()
    interior[1:, :] &= mask[:-1, :]
    interior[:-1, :] &= mask[1:, :]
    interior[:, 1:] &= mask[:, :-1]
    interior[:, :-1] &= mask[:, 1:]
    return mask & ~interior


def _overlay_regions(image, region_path, pair, processed):
    image = image.convert("RGB")
    if region_path is None:
        return image
    with np.load(Path(processed) / region_path) as data:
        left = _boundary(data[pair[0]])
        right = _boundary(data[pair[1]])
    array = np.asarray(image).copy()
    array[left] = (255, 70, 70)
    array[right] = (70, 130, 255)
    return Image.fromarray(array)


def _render_event_row(canvas, draw, y, label, event, result, processed, pair):
    position = event["position"]
    source_index = event["source_index"]
    standardized = event.get("standardized_separation")
    detail = f"{label}: source {source_index}; D={event['separation']:.5f}"
    if standardized is not None:
        detail += f"; S={standardized:.3f}"
    if event.get("rank_disagreement") is not None:
        detail += f"; rank disagreement={event['rank_disagreement']:.2f}"
    draw.text((10, y), detail, fill="black")

    camera_path = result.get("frame_camera_paths", [])[position]
    registered_path = result.get("frame_rgb_paths", [])[position]
    region_path = result.get("frame_region_paths", [])[position]

    if camera_path:
        with Image.open(Path(processed) / camera_path) as image:
            camera = image.convert("RGB")
        camera.thumbnail((480, 190))
        canvas.paste(camera, (10, y + 25))
    if registered_path:
        with Image.open(Path(processed) / registered_path) as image:
            registered = image.convert("RGB")
        registered = _overlay_regions(registered, region_path, pair, processed)
        registered.thumbnail((480, 190))
        canvas.paste(registered, (520, y + 25))


def _draw_pair_panel(destination, pair_id, pair_result, result, processed):
    ordered = [
        ("weakest separation", pair_result["evidence"].get("weakest")),
        ("median separation", pair_result["evidence"].get("median")),
        ("strongest separation", pair_result["evidence"].get("strongest")),
        (
            "simple vs standardized disagreement",
            pair_result["evidence"].get("strongest_formulation_disagreement"),
        ),
    ]
    rows = []
    seen = set()
    for label, event in ordered:
        if event is None:
            continue
        key = event["position"]
        if key in seen:
            continue
        seen.add(key)
        rows.append((label, event))
    canvas = Image.new("RGB", (1020, 65 + 235 * max(1, len(rows))), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        f"{pair_id}: original camera frame (left), registered band overlay (right)",
        fill="black",
    )
    draw.text((10, 30), "red = left band; blue = right band", fill="black")
    left, right = pair_id.split("__", 1)
    for index, (label, event) in enumerate(rows):
        _render_event_row(
            canvas,
            draw,
            60 + index * 235,
            label,
            event,
            result,
            Path(processed),
            (left, right),
        )
    canvas.save(destination)


def write_stone_outputs(result, output, processed=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "tier-contrast.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    fields = [
        "pair",
        "simple_status",
        "simple_q10",
        "simple_q50",
        "simple_q90",
        "standardized_status",
        "standardized_q10",
        "standardized_q50",
        "standardized_q90",
        "left_support_fraction",
        "right_support_fraction",
    ]
    rows = []
    for pair_id, pair in result["pairs"].items():
        simple = pair["simple"]
        standardized = pair["standardized"]
        rows.append(
            {
                "pair": pair_id,
                "simple_status": simple["validity"]["status"],
                "simple_q10": simple["summary"]["q10"],
                "simple_q50": simple["summary"]["q50"],
                "simple_q90": simple["summary"]["q90"],
                "standardized_status": standardized["validity"]["status"],
                "standardized_q10": standardized["summary"]["q10"],
                "standardized_q50": standardized["summary"]["q50"],
                "standardized_q90": standardized["summary"]["q90"],
                "left_support_fraction": pair["component_provenance"]["left"].get(
                    "persistent_support_fraction"
                ),
                "right_support_fraction": pair["component_provenance"]["right"].get(
                    "persistent_support_fraction"
                ),
            }
        )
        if processed is not None:
            evidence_dir = output / "evidence"
            evidence_dir.mkdir(exist_ok=True)
            _draw_pair_panel(
                evidence_dir / f"{pair_id}.png",
                pair_id,
                pair,
                result,
                processed,
            )
    with (output / "tier-contrast.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
