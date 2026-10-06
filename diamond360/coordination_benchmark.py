"""Derive concentric-band coordination directly from issue #26 activation outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import activation_benchmark as ab
from . import coordination as c

SCHEMA = "diamond360-concentric-coordination/1"
_BANDS = ("centre", "inner", "middle", "outer")
_ADJACENT = (("centre", "inner"), ("inner", "middle"), ("middle", "outer"))


def _source_region(representation, band):
    if representation == "coarse" or band == "centre":
        return band
    return f"{band}_step"


def _component_disposition(representation, band, support_mode):
    if support_mode != "fixed":
        return "REJECT", "upstream dynamic-support activation is QC only"
    if representation == "coarse" and band in {"centre", "inner", "middle"}:
        return "KEEP", "primary #26 local relative activation"
    if representation == "coarse" and band == "outer":
        return "REVISE", "outer activation remains support-sensitive in #26"
    return "REVISE", "semantic activation remains a localisation/QC candidate in #26"


def _worse_disposition(left, right):
    rank = {"KEEP": 0, "REVISE": 1, "REJECT": 2}
    return left if rank[left] >= rank[right] else right


def _cell(activation, representation, band, support_mode):
    region = _source_region(representation, band)
    return activation["representations"][representation]["regions"][region][support_mode]


def _pair_id(left, right):
    return f"{left}__{right}"


def _measure_representation(activation, representation, support_mode="fixed", outer_only=False):
    indices = list(activation["requested_indices"])
    wrap = bool(activation.get("wrap_explicit"))
    pairs = {}
    pair_set = _ADJACENT if outer_only else tuple(
        (left, right)
        for i, left in enumerate(_BANDS)
        for right in _BANDS[i + 1 :]
    )
    for left, right in pair_set:
        if outer_only and "outer" not in {left, right}:
            continue
        left_cell = _cell(activation, representation, left, support_mode)
        right_cell = _cell(activation, representation, right, support_mode)
        left_disp, left_role = _component_disposition(representation, left, support_mode)
        right_disp, right_role = _component_disposition(representation, right, support_mode)
        measured = c.measure_pair(
            left_cell["relative_values"],
            right_cell["relative_values"],
            indices,
            left_cell["relative_validity"],
            right_cell["relative_validity"],
            wrap=wrap,
        )
        pairs[_pair_id(left, right)] = {
            "left_band": left,
            "right_band": right,
            "adjacent": (left, right) in _ADJACENT,
            "primary": (
                representation == "coarse"
                and support_mode == "fixed"
                and (left, right) in {("centre", "inner"), ("inner", "middle")}
            ),
            "support_mode": support_mode,
            "component_provenance": {
                "left": {
                    "region": _source_region(representation, left),
                    "disposition": left_disp,
                    "role": left_role,
                    "support_fraction": left_cell.get("persistent_support_fraction"),
                },
                "right": {
                    "region": _source_region(representation, right),
                    "disposition": right_disp,
                    "role": right_role,
                    "support_fraction": right_cell.get("persistent_support_fraction"),
                },
            },
            "inherited_disposition": _worse_disposition(left_disp, right_disp),
            **measured,
        }

    matrix = {band: {other: None for other in _BANDS} for band in _BANDS}
    for band in _BANDS:
        matrix[band][band] = 1.0
    for pair in pairs.values():
        value = pair["level_correlation"]["pearson_r"]
        matrix[pair["left_band"]][pair["right_band"]] = value
        matrix[pair["right_band"]][pair["left_band"]] = value
    return {"pairs": pairs, "level_correlation_matrix": matrix}


def measure_from_activation(activation):
    """Consume exact #26 activation output; never recompute photometry or masks."""
    if activation.get("schema_version") != ab.SCHEMA:
        raise ValueError(f"expected upstream activation schema {ab.SCHEMA}")
    result = {
        "schema_version": SCHEMA,
        "upstream_activation_schema": activation["schema_version"],
        "requested_indices": list(activation["requested_indices"]),
        "accepted_indices": list(activation.get("accepted_indices", [])),
        "excluded": list(activation.get("excluded", [])),
        "wrap_explicit": bool(activation.get("wrap_explicit")),
        "trace_definition": "#26 fixed-support regional log-relative activation",
        "candidate_summaries": {
            "pearson_r": "aligned level correlation; sign preserves coordinated vs alternating states",
            "same_direction_fraction": "adjacent-change sign agreement excluding exact ties; audit candidate",
        },
        "representations": {},
        "frame_rgb_paths": list(activation.get("frame_rgb_paths", [])),
    }
    for representation in ("coarse", "semantic"):
        regions = activation.get("representations", {}).get(representation, {}).get("regions", {})
        if not regions:
            result["representations"][representation] = {
                "status": "unavailable",
                "reason": "upstream_representation_unavailable",
            }
            continue
        fixed = _measure_representation(activation, representation, "fixed")
        # #26 rejected dynamic support as primary. Keep only middle<->outer as a
        # direct support-motion falsification diagnostic for the weakest band.
        dynamic_outer = _measure_representation(
            activation, representation, "dynamic", outer_only=True
        )
        result["representations"][representation] = {
            "fixed": fixed,
            "outer_support_sensitivity": dynamic_outer,
        }
    return result


def measure_stone(processed, step_output, indices, wrap=False):
    activation = ab.measure_stone(processed, step_output, indices, wrap=wrap)
    return measure_from_activation(activation)


def _draw_trace(draw, box, values, label, fill):
    x0, y0, x1, y1 = box
    finite = [float(v) for v in values if v is not None]
    if not finite:
        return
    lo, hi = min(finite), max(finite)
    span = hi - lo or 1.0
    points = []
    for i, value in enumerate(values):
        if value is None:
            points.append(None)
            continue
        x = x0 + (x1 - x0) * i / max(1, len(values) - 1)
        y = y1 - (float(value) - lo) / span * (y1 - y0)
        points.append((x, y))
    previous = None
    for point in points:
        if point is None:
            previous = None
            continue
        if previous is not None:
            draw.line([previous, point], fill=fill, width=2)
        previous = point
    draw.text((x0, y0 - 16), label, fill=fill)


def _draw_pair_panel(destination, title, pair, rgb_paths, processed):
    evidence = pair["evidence"]
    slots = [
        ("coordinated", evidence.get("strongest_coordinated")),
        ("divergent", evidence.get("strongest_divergent")),
        ("typical", evidence.get("typical_directional")),
    ]
    slots = [(label, event) for label, event in slots if event is not None]
    canvas = Image.new("RGB", (900, 360 + 230 * max(1, len(slots))), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 10), title, fill="black")
    _draw_trace(draw, (40, 70, 860, 160), pair["values_a"], pair["left_band"], "blue")
    _draw_trace(draw, (40, 205, 860, 295), pair["values_b"], pair["right_band"], "red")
    for slot, (label, event) in enumerate(slots):
        y = 340 + slot * 230
        draw.text(
            (10, y),
            f"{label}: {event['left_source_index']}->{event['right_source_index']} "
            f"da={event['delta_a']:+.5f} db={event['delta_b']:+.5f}",
            fill="black",
        )
        for side, position_key in enumerate(("left_position", "right_position")):
            position = event[position_key]
            path = rgb_paths[position] if position < len(rgb_paths) else None
            if path:
                with Image.open(processed / path) as image:
                    frame = image.convert("RGB")
                frame.thumbnail((400, 185))
                canvas.paste(frame, (10 + side * 440, y + 28))
    canvas.save(destination)


def write_stone_outputs(result, output, processed=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "coordination.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    fields = [
        "representation", "pair", "primary", "inherited_disposition",
        "level_status", "pearson_r", "aligned_finite_frames",
        "change_status", "same_direction_fraction", "opposite_direction_fraction",
        "directional_pairs", "left_support_fraction", "right_support_fraction",
    ]
    rows = []
    for representation, rep in result.get("representations", {}).items():
        fixed = rep.get("fixed") if isinstance(rep, dict) else None
        if not fixed:
            continue
        for pair_id, pair in fixed["pairs"].items():
            rows.append({
                "representation": representation,
                "pair": pair_id,
                "primary": pair["primary"],
                "inherited_disposition": pair["inherited_disposition"],
                "level_status": pair["level_validity"]["status"],
                "pearson_r": pair["level_correlation"]["pearson_r"],
                "aligned_finite_frames": pair["level_correlation"]["aligned_finite_frames"],
                "change_status": pair["change_validity"]["status"],
                "same_direction_fraction": pair["change_coordination"]["summary"]["same_direction_fraction"],
                "opposite_direction_fraction": pair["change_coordination"]["summary"]["opposite_direction_fraction"],
                "directional_pairs": pair["change_coordination"]["summary"]["directional_pairs"],
                "left_support_fraction": pair["component_provenance"]["left"].get("support_fraction"),
                "right_support_fraction": pair["component_provenance"]["right"].get("support_fraction"),
            })
            if processed is not None and pair["adjacent"]:
                evidence_dir = output / "evidence"
                evidence_dir.mkdir(exist_ok=True)
                _draw_pair_panel(
                    evidence_dir / f"{representation}-{pair_id}.png",
                    f"{representation} fixed relative {pair_id}",
                    pair,
                    result["frame_rgb_paths"],
                    Path(processed),
                )
    with (output / "coordination.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
