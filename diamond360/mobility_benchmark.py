"""Derive contrast mobility directly from issue #26 activation outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import activation_benchmark as ab
from . import mobility as m

SCHEMA = "diamond360-contrast-mobility/1"

# #26 retained fixed whole-stone raw plus coarse-fixed local relative activation.
# Outer and semantic fixed traces remain explicit inherited-REVISE sensitivity/QC.
PRIMARY = (
    ("whole_stone", "whole_stone", "fixed", "raw"),
    ("coarse", "centre", "fixed", "relative"),
    ("coarse", "inner", "fixed", "relative"),
    ("coarse", "middle", "fixed", "relative"),
)


def _trace_id(representation, region, support_mode, trace_type):
    return f"{representation}/{region}/{support_mode}/{trace_type}"


def _upstream_role(representation, region, support_mode, trace_type):
    key = (representation, region, support_mode, trace_type)
    if key == ("whole_stone", "whole_stone", "fixed", "raw"):
        return "KEEP", "primary broad activation primitive"
    if (
        representation == "coarse"
        and support_mode == "fixed"
        and region in {"centre", "inner", "middle"}
    ):
        if trace_type == "relative":
            return "KEEP", "primary local activation descriptor"
        return "KEEP", "audit activation primitive"
    if support_mode == "fixed" and (representation == "semantic" or region == "outer"):
        return "REVISE", "upstream sensitivity/QC candidate"
    return "REJECT", "not selected for contrast-mobility derivation"


def _iter_activation_traces(activation):
    whole = activation["whole_stone"]
    yield {
        "representation": "whole_stone",
        "region": "whole_stone",
        "support_mode": "fixed",
        "trace_type": "raw",
        "values": whole["values"],
        "summary": whole["summary"],
        "validity": whole["validity"],
        "support": {
            "persistent_support_pixels": whole.get("persistent_support_pixels"),
            "per_frame_support_fraction": whole.get("per_frame_support_fraction"),
        },
    }
    for representation, rep in activation.get("representations", {}).items():
        for region, modes in rep.get("regions", {}).items():
            cell = modes.get("fixed")
            if not cell:
                continue
            for trace_type in ("raw", "relative"):
                values_key = f"{trace_type}_values"
                summary_key = f"{trace_type}_summary"
                validity_key = f"{trace_type}_validity"
                if values_key not in cell:
                    continue
                disposition, role = _upstream_role(
                    representation, region, "fixed", trace_type
                )
                if disposition == "REJECT":
                    continue
                yield {
                    "representation": representation,
                    "region": region,
                    "support_mode": "fixed",
                    "trace_type": trace_type,
                    "values": cell[values_key],
                    "summary": cell[summary_key],
                    "validity": cell[validity_key],
                    "support": {
                        "persistent_support_pixels": cell.get("persistent_support_pixels"),
                        "persistent_support_fraction": cell.get("persistent_support_fraction"),
                        "per_frame_support_fraction": cell.get("per_frame_support_fraction"),
                    },
                    "upstream_disposition": disposition,
                    "upstream_role": role,
                }


def measure_from_activation(activation):
    """Consume an exact #26 result; never rederive brightness, masks or support."""
    if activation.get("schema_version") != ab.SCHEMA:
        raise ValueError(f"expected upstream activation schema {ab.SCHEMA}")
    indices = list(activation["requested_indices"])
    wrap = bool(activation.get("wrap_explicit"))
    traces = {}
    for source in _iter_activation_traces(activation):
        representation = source["representation"]
        region = source["region"]
        support_mode = source["support_mode"]
        trace_type = source["trace_type"]
        disposition, role = _upstream_role(
            representation, region, support_mode, trace_type
        )
        measured = m.mobility_trace(source["values"], indices, wrap=wrap)
        trace_id = _trace_id(representation, region, support_mode, trace_type)
        traces[trace_id] = {
            "representation": representation,
            "region": region,
            "support_mode": support_mode,
            "trace_type": trace_type,
            "primary": (representation, region, support_mode, trace_type) in PRIMARY,
            "upstream_activation": {
                "schema_version": activation["schema_version"],
                "disposition": source.get("upstream_disposition", disposition),
                "role": source.get("upstream_role", role),
                "summary": source["summary"],
                "support": source["support"],
            },
            **measured,
        }
        traces[trace_id]["validity"] = m.mobility_validity(
            source["validity"], measured["summary"]
        )
        traces[trace_id]["evidence"] = m.select_pair_evidence(
            measured["pair_trace"]
        )
        traces[trace_id]["evidence_panel"] = (
            f"evidence/{trace_id.replace('/', '-')}.png"
        )

    return {
        "schema_version": SCHEMA,
        "upstream_activation_schema": activation["schema_version"],
        "requested_indices": indices,
        "accepted_indices": list(activation.get("accepted_indices", [])),
        "excluded": list(activation.get("excluded", [])),
        "wrap_explicit": wrap,
        "definition": "m_t = abs(a_t - a_(t-1)) for observed adjacent source steps",
        "units": (
            "activation-trace units per observed source step; "
            "not seconds or calibrated degrees"
        ),
        "summary_candidates": {
            "median": "primary robust typical adjacent-step absolute change",
            "q90": (
                "experimental upper-tail summary; retain only if median hides "
                "sparse visible events"
            ),
        },
        "traces": traces,
        "frame_rgb_paths": list(activation.get("frame_rgb_paths", [])),
    }


def measure_stone(processed, step_output, indices, wrap=False):
    activation = ab.measure_stone(processed, step_output, indices, wrap=wrap)
    return measure_from_activation(activation)


def _draw_pair_panel(destination, title, evidence, rgb_paths, processed):
    labels = ("largest", "median", "lowest_nonzero")
    events = [
        (label, evidence.get(label))
        for label in labels
        if evidence.get(label) is not None
    ]
    width = max(1, len(events)) * 430
    canvas = Image.new("RGB", (width, 315), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")
    for slot, (label, item) in enumerate(events):
        x0 = slot * 430
        for side, position_key in enumerate(("left_position", "right_position")):
            position = item[position_key]
            path = rgb_paths[position] if position < len(rgb_paths) else None
            if path:
                with Image.open(processed / path) as image:
                    frame = image.convert("RGB")
                frame.thumbnail((200, 220))
                canvas.paste(frame, (x0 + 5 + side * 210, 55))
            draw.text(
                (x0 + 5 + side * 210, 35),
                (
                    f"src {item['left_source_index']}"
                    if side == 0
                    else f"src {item['right_source_index']}"
                ),
                fill="black",
            )
        draw.text(
            (x0 + 5, 282),
            (
                f"{label}: |delta|={item['mobility']:.5f}; "
                f"delta={item['signed_delta']:+.5f}"
            ),
            fill="black",
        )
    canvas.save(destination)


def write_stone_outputs(result, output, processed):
    output = Path(output)
    processed = Path(processed)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "mobility.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    fields = [
        "trace_id",
        "representation",
        "region",
        "support_mode",
        "trace_type",
        "primary",
        "upstream_disposition",
        "status",
        "reasons",
        "requested_adjacent_pairs",
        "observed_adjacent_pairs",
        "median",
        "q90",
        "activation_total_excursion",
        "persistent_support_fraction",
    ]
    rows = []
    for trace_id, trace in result["traces"].items():
        upstream = trace["upstream_activation"]
        summary = trace["summary"]
        rows.append(
            {
                "trace_id": trace_id,
                "representation": trace["representation"],
                "region": trace["region"],
                "support_mode": trace["support_mode"],
                "trace_type": trace["trace_type"],
                "primary": trace["primary"],
                "upstream_disposition": upstream["disposition"],
                "status": trace["validity"]["status"],
                "reasons": ";".join(trace["validity"]["reasons"]),
                "requested_adjacent_pairs": summary["requested_adjacent_pairs"],
                "observed_adjacent_pairs": summary["observed_adjacent_pairs"],
                "median": summary["median"],
                "q90": summary["q90"],
                "activation_total_excursion": upstream["summary"].get(
                    "total_excursion"
                ),
                "persistent_support_fraction": upstream["support"].get(
                    "persistent_support_fraction"
                ),
            }
        )
        _draw_pair_panel(
            output / trace["evidence_panel"],
            trace_id,
            trace["evidence"],
            result["frame_rgb_paths"],
            processed,
        )
    with (output / "mobility.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
