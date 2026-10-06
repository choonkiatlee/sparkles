"""Run auditable opposing-region coordination measurements on Asscher 360 intervals."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a
from . import activation_benchmark as ab
from . import opposing_symmetry as osym
from .regions import SECTORS

SCHEMA = "diamond360-opposing-region-symmetry/1"
COARSE_RADIAL_BANDS = ("inner", "middle")
SEMANTIC_RADIAL_BANDS = ("inner_step", "middle_step")


def _load_preprocessed_masks(processed, selected, names):
    processed = Path(processed)
    paths = [
        processed / record["regions_path"] if record is not None else None
        for record in selected
    ]
    return a._stack_masks(paths, tuple(names))


def _component_reasons(cell):
    if cell["relative_summary"].get("status") == "ok":
        return []
    if not cell.get("persistent_support_pixels"):
        return ["no_support"]
    return ["insufficient_finite_frames"]


def _component_trace(
    representation,
    region_name,
    region_masks,
    brightness,
    valid_masks,
    whole_values,
    observed,
    support_mode,
    upstream,
    step_qc,
):
    cell = a.regional_trace(
        brightness,
        valid_masks,
        region_masks,
        whole_values,
        observed,
        support_mode,
    )
    validity = a.activation_validity(
        representation,
        upstream,
        step_qc,
        cell["relative_summary"]["status"],
        _component_reasons(cell),
    )
    return {
        "region": region_name,
        "support_mode": support_mode,
        "relative_values": cell["relative_values"],
        "raw_values": cell["raw_values"],
        "relative_summary": cell["relative_summary"],
        "persistent_support_pixels": cell["persistent_support_pixels"],
        "persistent_support_fraction": cell["persistent_support_fraction"],
        "per_frame_support_fraction": cell["per_frame_support_fraction"],
        "validity": validity,
    }


def _surface(
    surface_id,
    representation,
    radial_band,
    sector_masks,
    radial_masks,
    brightness,
    valid_masks,
    whole_values,
    observed,
    upstream,
    step_qc,
    source_indices,
    wrap,
):
    if radial_band is None:
        component_masks = sector_masks
    else:
        band = radial_masks[radial_band]
        component_masks = {
            name: mask & band for name, mask in sector_masks.items()
        }

    modes = {}
    for support_mode in ("fixed", "dynamic"):
        components = {
            name: _component_trace(
                representation,
                name,
                masks,
                brightness,
                valid_masks,
                whole_values,
                observed,
                support_mode,
                upstream,
                step_qc,
            )
            for name, masks in component_masks.items()
        }
        pairs = {}
        for pair_id, (left_name, right_name) in osym.PAIR_DEFINITIONS.items():
            left = components[left_name]
            right = components[right_name]
            pair = osym.pair_trace(
                left["relative_values"],
                right["relative_values"],
                source_indices,
                wrap=wrap,
            )
            local = {
                "status": pair["status"],
                "reasons": pair["reasons"],
            }
            validity = a.compose_validity(
                [left["validity"], right["validity"], local]
            )
            support_values = [
                left["persistent_support_fraction"],
                right["persistent_support_fraction"],
            ]
            finite_support = [
                value for value in support_values if value is not None
            ]
            pair.update(
                pair_id=pair_id,
                left_region=left_name,
                right_region=right_name,
                surface_id=surface_id,
                representation=representation,
                radial_band=radial_band,
                support_mode=support_mode,
                validity=validity,
                component_support={
                    "left": {
                        "persistent_support_pixels":
                            left["persistent_support_pixels"],
                        "persistent_support_fraction":
                            left["persistent_support_fraction"],
                    },
                    "right": {
                        "persistent_support_pixels":
                            right["persistent_support_pixels"],
                        "persistent_support_fraction":
                            right["persistent_support_fraction"],
                    },
                    "worse_persistent_support_fraction":
                        min(finite_support) if finite_support else None,
                },
                trace_provenance={
                    "source": "diamond360.activation.regional_trace",
                    "schema": "diamond360-activation/1",
                    "trace_type": "relative_values",
                    "definition":
                        "log(regional median encoded brightness) - "
                        "log(fixed-support whole-stone median)",
                },
                evidence=osym.select_evidence(pair),
                evidence_panel=(
                    f"evidence/{surface_id}-{support_mode}-{pair_id}.png"
                ),
            )
            pairs[pair_id] = pair
        modes[support_mode] = {
            "components": components,
            "pairs": pairs,
        }
    return {
        "surface_id": surface_id,
        "representation": representation,
        "radial_band": radial_band,
        "support_modes": modes,
    }


def _metric_value(pair, metric):
    item = pair.get("metrics", {}).get(metric, {})
    value = item.get("value")
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _best_representation_disagreement(comparisons, surfaces, metric):
    candidates = []
    for left_surface, right_surface, support_mode, pair_id in comparisons:
        left = (
            surfaces[left_surface]["support_modes"][support_mode]["pairs"][pair_id]
        )
        right = (
            surfaces[right_surface]["support_modes"][support_mode]["pairs"][pair_id]
        )
        left_value = _metric_value(left, metric)
        right_value = _metric_value(right, metric)
        if left_value is None or right_value is None:
            continue
        candidates.append({
            "metric": metric,
            "left_surface": left_surface,
            "right_surface": right_surface,
            "support_mode": support_mode,
            "pair_id": pair_id,
            "left_value": left_value,
            "right_value": right_value,
            "absolute_difference": abs(left_value - right_value),
            "left_evidence_panel": left["evidence_panel"],
            "right_evidence_panel": right["evidence_panel"],
        })
    return (
        max(candidates, key=lambda item: item["absolute_difference"])
        if candidates else None
    )


def _disagreements(surfaces):
    metrics = (
        "correlation",
        "median_absolute_difference",
        "sign_agreement",
    )
    support = {}
    for metric in metrics:
        candidates = []
        for surface_id, surface in surfaces.items():
            for pair_id in osym.PAIR_DEFINITIONS:
                fixed = (
                    surface["support_modes"]["fixed"]["pairs"][pair_id]
                )
                dynamic = (
                    surface["support_modes"]["dynamic"]["pairs"][pair_id]
                )
                left_value = _metric_value(fixed, metric)
                right_value = _metric_value(dynamic, metric)
                if left_value is None or right_value is None:
                    continue
                candidates.append({
                    "metric": metric,
                    "surface_id": surface_id,
                    "pair_id": pair_id,
                    "left_support_mode": "fixed",
                    "right_support_mode": "dynamic",
                    "left_value": left_value,
                    "right_value": right_value,
                    "absolute_difference": abs(left_value - right_value),
                    "left_evidence_panel": fixed["evidence_panel"],
                    "right_evidence_panel": dynamic["evidence_panel"],
                })
        support[metric] = (
            max(candidates, key=lambda item: item["absolute_difference"])
            if candidates else None
        )

    comparisons = []
    for coarse, semantic in (
        ("coarse_inner", "semantic_inner_step"),
        ("coarse_middle", "semantic_middle_step"),
    ):
        if coarse not in surfaces or semantic not in surfaces:
            continue
        for pair_id in osym.PAIR_DEFINITIONS:
            comparisons.append(
                (coarse, semantic, "fixed", pair_id)
            )
    representation = {
        metric: _best_representation_disagreement(
            comparisons, surfaces, metric
        )
        for metric in metrics
    }
    return {
        "support": support,
        "representation": representation,
    }


def measure_stone(processed, step_output, indices, wrap=False):
    """Measure opposing sectors plus inner/middle localisation sensitivities."""
    processed = Path(processed).resolve()
    step_output = Path(step_output).resolve()
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, excluded = ab._select_records(
        metadata, list(indices), wrap
    )
    observed = np.asarray(
        [record is not None for record in selected], bool
    )
    (
        brightness,
        valid_masks,
        stone_masks,
        rgb_paths,
    ) = ab._load_frame_arrays(processed, selected)
    upstream = ab._upstream_validity(selected, excluded)

    whole = a.whole_stone_trace(
        brightness,
        valid_masks,
        stone_masks,
        observed,
    )
    whole_reasons = ab._summary_reason(
        whole["summary"],
        whole["persistent_support_pixels"],
    )
    whole["validity"] = a.activation_validity(
        "whole_stone",
        upstream,
        None,
        whole["summary"]["status"],
        whole_reasons,
    )

    sector_masks = _load_preprocessed_masks(
        processed, selected, SECTORS
    )
    coarse_radial = _load_preprocessed_masks(
        processed, selected, COARSE_RADIAL_BANDS
    )
    semantic_radial, step_qc = a.load_semantic_masks(
        step_output, selected
    )

    surfaces = {
        "coarse_whole": _surface(
            "coarse_whole",
            "coarse",
            None,
            sector_masks,
            {},
            brightness,
            valid_masks,
            whole["values"],
            observed,
            upstream,
            None,
            list(indices),
            wrap,
        )
    }
    for band in COARSE_RADIAL_BANDS:
        surfaces[f"coarse_{band}"] = _surface(
            f"coarse_{band}",
            "coarse",
            band,
            sector_masks,
            coarse_radial,
            brightness,
            valid_masks,
            whole["values"],
            observed,
            upstream,
            None,
            list(indices),
            wrap,
        )
    if semantic_radial:
        for band in SEMANTIC_RADIAL_BANDS:
            surfaces[f"semantic_{band}"] = _surface(
                f"semantic_{band}",
                "semantic",
                band,
                sector_masks,
                semantic_radial,
                brightness,
                valid_masks,
                whole["values"],
                observed,
                upstream,
                step_qc,
                list(indices),
                wrap,
            )

    return {
        "schema_version": SCHEMA,
        "requested_indices": list(indices),
        "accepted_indices": [
            record["source_index"]
            for record in selected
            if record is not None
        ],
        "excluded": excluded,
        "wrap_explicit": bool(wrap),
        "brightness_definition": metadata.get("brightness_definition"),
        "pair_definitions": {
            key: list(value)
            for key, value in osym.PAIR_DEFINITIONS.items()
        },
        "measurement_definition": {
            "component_trace":
                "#26 log-relative regional activation using the same "
                "fixed-support whole-stone G_t",
            "correlation":
                "Pearson correlation across paired finite component "
                "trace observations",
            "median_absolute_difference":
                "median(abs(C_left - C_right)); equals median absolute "
                "log brightness-ratio imbalance",
            "sign_agreement":
                "fraction of non-flat observed adjacent pairs where "
                "component trace deltas have the same sign",
            "flat_rule":
                "adjacent pairs where either component delta is exactly "
                "zero are retained as flat and excluded from the "
                "sign-agreement denominator",
        },
        "surface_policy": {
            "baseline": "coarse whole image-space sectors",
            "radial_sensitivity": [
                "coarse inner",
                "coarse middle",
                "semantic inner_step",
                "semantic middle_step",
            ],
            "omitted": {
                "centre":
                    "sector-restricted centre is too small/ambiguous "
                    "for the baseline pair question",
                "outer":
                    "#26 found outer activation support/pose-sensitive; "
                    "keep it out of the primary localisation experiment",
            },
        },
        "whole_stone_reference": {
            "definition":
                "median encoded brightness on fixed common registered "
                "stone support",
            "source": "diamond360.activation.whole_stone_trace",
            **whole,
        },
        "upstream_validity": upstream,
        "semantic_qc": step_qc,
        "surfaces": surfaces,
        "disagreements": _disagreements(surfaces),
        "frame_rgb_paths": rgb_paths,
    }


def _support_for_frame(
    region_masks,
    valid_masks,
    observed,
    mode,
    position,
):
    supported = valid_masks & region_masks
    if mode == "fixed":
        return (
            np.all(supported[observed], axis=0)
            if observed.any()
            else np.zeros(region_masks.shape[1:], bool)
        )
    return supported[position]


def _overlay_pair(rgb, left, right):
    array = np.asarray(rgb.convert("RGB"), dtype=np.float32).copy()
    if array.shape[:2] != left.shape or left.shape != right.shape:
        raise ValueError("evidence RGB and pair masks must match")
    array[left] = (
        0.55 * array[left]
        + 0.45 * np.array([230.0, 85.0, 70.0])
    )
    array[right] = (
        0.55 * array[right]
        + 0.45 * np.array([65.0, 120.0, 235.0])
    )
    overlap = left & right
    array[overlap] = (
        0.45 * array[overlap]
        + 0.55 * np.array([180.0, 75.0, 200.0])
    )
    return Image.fromarray(
        np.clip(array, 0, 255).astype(np.uint8)
    )


def _draw_trace(draw, box, frames, evidence):
    left, top, right, bottom = box
    draw.line((left, bottom, right, bottom), fill="grey")
    draw.line((left, top, left, bottom), fill="grey")
    finite = [
        value
        for frame in frames
        for value in (frame["left"], frame["right"])
        if value is not None
    ]
    if not finite:
        return
    lo, hi = min(finite), max(finite)
    span = hi - lo or 1.0
    for key, color in (
        ("left", "#c5483b"),
        ("right", "#315fc4"),
    ):
        previous = None
        for i, frame in enumerate(frames):
            value = frame[key]
            if value is None:
                previous = None
                continue
            point = (
                left
                + i * (right - left) / max(1, len(frames) - 1),
                bottom
                - (float(value) - lo)
                / span
                * (bottom - top),
            )
            if previous is not None:
                draw.line((previous, point), fill=color, width=2)
            draw.ellipse(
                (
                    point[0] - 2,
                    point[1] - 2,
                    point[0] + 2,
                    point[1] + 2,
                ),
                fill=color,
            )
            previous = point
    for event in evidence.values():
        if event is None:
            continue
        x = (
            left
            + event["right_position"]
            * (right - left)
            / max(1, len(frames) - 1)
        )
        draw.line(
            (x, top, x, bottom),
            fill="#777777",
            width=1,
        )


def _draw_pair_panel(
    destination,
    title,
    pair,
    left_masks,
    right_masks,
    valid_masks,
    observed,
    rgb_paths,
    processed,
):
    canvas = Image.new("RGB", (1200, 700), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((15, 10), title, fill="black")
    _draw_trace(
        draw,
        (60, 55, 1140, 260),
        pair["frame_trace"],
        pair["evidence"],
    )
    draw.text(
        (60, 270),
        "red=left activation; blue=right activation; "
        "vertical lines=evidence events",
        fill="black",
    )

    events = [
        (name, item)
        for name, item in pair["evidence"].items()
        if item is not None
    ]
    for slot, (label, item) in enumerate(events[:3]):
        x0 = 10 + slot * 395
        for side, position_key in enumerate(
            ("left_position", "right_position")
        ):
            position = item[position_key]
            path = rgb_paths[position]
            if not path:
                continue
            left_support = _support_for_frame(
                left_masks,
                valid_masks,
                observed,
                pair["support_mode"],
                position,
            )
            right_support = _support_for_frame(
                right_masks,
                valid_masks,
                observed,
                pair["support_mode"],
                position,
            )
            frame = _overlay_pair(
                Image.open(processed / path),
                left_support,
                right_support,
            )
            frame.thumbnail((185, 300))
            canvas.paste(
                frame,
                (x0 + side * 195, 335),
            )
            draw.text(
                (x0 + side * 195, 315),
                f"src {pair['frame_trace'][position]['source_index']}",
                fill="black",
            )
        draw.text(
            (x0, 650),
            f"{label}: dL={item['left_delta']:+.4f}, "
            f"dR={item['right_delta']:+.4f}",
            fill="black",
        )
    draw.text(
        (15, 680),
        "region overlays: red=left pair member, "
        "blue=right pair member",
        fill="black",
    )
    canvas.save(destination)


def _surface_masks(
    surface,
    sector_masks,
    coarse_radial,
    semantic_radial,
):
    band = surface["radial_band"]
    if band is None:
        return sector_masks
    radial = (
        semantic_radial
        if surface["representation"] == "semantic"
        else coarse_radial
    )
    return {
        name: mask & radial[band]
        for name, mask in sector_masks.items()
    }


def write_stone_outputs(
    result,
    output,
    processed,
    step_output,
):
    """Write full machine-readable stone output and pair evidence panels."""
    output = Path(output)
    processed = Path(processed)
    step_output = Path(step_output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "opposing-symmetry.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    metadata = json.loads(
        (processed / "sequence.json").read_text()
    )
    selected, _ = ab._select_records(
        metadata,
        result["requested_indices"],
        result["wrap_explicit"],
    )
    observed = np.asarray(
        [record is not None for record in selected],
        bool,
    )
    _, valid_masks, _, rgb_paths = ab._load_frame_arrays(
        processed,
        selected,
    )
    sector_masks = _load_preprocessed_masks(
        processed, selected, SECTORS
    )
    coarse_radial = _load_preprocessed_masks(
        processed, selected, COARSE_RADIAL_BANDS
    )
    semantic_radial, _ = a.load_semantic_masks(
        step_output, selected
    )

    fields = [
        "surface_id",
        "representation",
        "radial_band",
        "support_mode",
        "pair_id",
        "left_region",
        "right_region",
        "status",
        "reasons",
        "paired_frames",
        "correlation",
        "median_absolute_difference",
        "median_signed_difference",
        "sign_agreement",
        "directional_pairs",
        "flat_pairs",
        "worse_persistent_support_fraction",
    ]
    rows = []
    for surface_id, surface in result["surfaces"].items():
        masks = _surface_masks(
            surface,
            sector_masks,
            coarse_radial,
            semantic_radial,
        )
        for mode, payload in surface["support_modes"].items():
            for pair_id, pair in payload["pairs"].items():
                sign = pair["metrics"]["sign_agreement"]
                rows.append({
                    "surface_id": surface_id,
                    "representation": pair["representation"],
                    "radial_band": pair["radial_band"],
                    "support_mode": mode,
                    "pair_id": pair_id,
                    "left_region": pair["left_region"],
                    "right_region": pair["right_region"],
                    "status": pair["validity"]["status"],
                    "reasons":
                        ";".join(pair["validity"]["reasons"]),
                    "paired_frames": pair["paired_frames"],
                    "correlation":
                        pair["metrics"]["correlation"]["value"],
                    "median_absolute_difference":
                        pair["metrics"][
                            "median_absolute_difference"
                        ]["value"],
                    "median_signed_difference":
                        pair["median_signed_difference"],
                    "sign_agreement": sign["value"],
                    "directional_pairs":
                        sign.get("directional_pairs"),
                    "flat_pairs": sign.get("flat_pairs"),
                    "worse_persistent_support_fraction":
                        pair["component_support"][
                            "worse_persistent_support_fraction"
                        ],
                })
                _draw_pair_panel(
                    output / pair["evidence_panel"],
                    f"{surface_id} / {mode} / {pair_id}",
                    pair,
                    masks[pair["left_region"]],
                    masks[pair["right_region"]],
                    valid_masks,
                    observed,
                    rgb_paths,
                    processed,
                )
    with (output / "opposing-symmetry.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("processed", type=Path)
    parser.add_argument("step_output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--wrap", action="store_true")
    args = parser.parse_args()
    indices = [int(value) for value in args.indices.split(",") if value.strip()]
    result = measure_stone(
        args.processed,
        args.step_output,
        indices,
        wrap=args.wrap,
    )
    write_stone_outputs(
        result,
        args.output,
        args.processed,
        args.step_output,
    )
    print(f"{len(result['surfaces'])} surfaces -> {args.output}")


if __name__ == "__main__":
    main()
