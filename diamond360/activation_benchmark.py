"""Run auditable activation measurements on registered Asscher 360 intervals."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as a

SCHEMA = "diamond360-activation/1"


def _validate_interval(indices, source_frame_count=None, wrap=False):
    if len(indices) < 2 or len(indices) != len(set(indices)) or any(type(i) is not int or i < 0 for i in indices):
        raise ValueError("Select at least two unique nonnegative source indices")
    if wrap and (type(source_frame_count) is not int or source_frame_count <= 0):
        raise ValueError("Wrap requires a known source frame count")
    if source_frame_count is not None and any(i >= source_frame_count for i in indices):
        raise ValueError("Source index exceeds source frame count")
    for left, right in zip(indices, indices[1:]):
        if right != left + 1 and not (wrap and left == source_frame_count - 1 and right == 0):
            raise ValueError("Activation traces require consecutive source indices")


def _select_records(metadata, indices, wrap):
    _validate_interval(indices, metadata.get("source_frame_count"), wrap)
    lookup = {}
    for record in metadata.get("frames", []):
        lookup.setdefault(record.get("source_index"), []).append(record)
    selected = []
    excluded = []
    seen = set()
    for source_index in indices:
        records = lookup.get(source_index, [])
        if len(records) > 1:
            raise ValueError(f"Ambiguous source index {source_index}")
        record = records[0] if records else None
        digest = record.get("pixel_sha256", record.get("sha256")) if record else None
        reason = (
            "missing_frame" if record is None else
            "unaccepted_outline" if "registration" not in record else
            "duplicate_frame" if digest in seen else
            None
        )
        if reason:
            selected.append(None)
            excluded.append({"source_index": source_index, "reason": reason})
        else:
            seen.add(digest)
            selected.append(record)
    if not any(record is not None for record in selected):
        raise ValueError("No accepted frames in activation interval")
    return selected, excluded


def _upstream_validity(selected, excluded):
    sources = []
    for record in selected:
        if record is None:
            continue
        segmentation = record.get("segmentation", {})
        status = segmentation.get("status", "ok")
        reasons = list(segmentation.get("reasons") or [])
        if status == "review" and not reasons:
            reasons = ["segmentation_review"]
        elif status in {"failed", "unavailable"}:
            status = "unavailable"
            if not reasons:
                reasons = ["segmentation_unavailable"]
        sources.append({"status": status, "reasons": reasons})
    if excluded:
        sources.append({"status": "review", "reason": "requested_frames_excluded"})
    return a.compose_validity(sources or [{"status": "unavailable", "reason": "no_accepted_frames"}])


def _load_frame_arrays(processed, selected):
    shape = None
    brightness = []
    valid_masks = []
    stone_masks = []
    rgb_paths = []
    for record in selected:
        if record is None:
            brightness.append(None)
            valid_masks.append(None)
            stone_masks.append(None)
            rgb_paths.append(None)
            continue
        with np.load(processed / record["photometry_path"]) as data:
            frame = np.asarray(data["encoded_brightness"], float).copy()
            valid = np.asarray(data["valid_mask"], bool).copy()
        mask = np.asarray(Image.open(processed / record["registration"]["mask_path"]).convert("L")) > 0
        if frame.shape != valid.shape or frame.shape != mask.shape:
            raise ValueError("Photometry and registered mask shapes must match")
        if shape is None:
            shape = frame.shape
        elif shape != frame.shape:
            raise ValueError("Registered activation frames must share one canvas shape")
        brightness.append(frame)
        valid_masks.append(valid)
        stone_masks.append(mask)
        rgb_paths.append(record["registration"].get("rgb_path"))
    if shape is None:
        raise ValueError("No readable activation frames")
    zero = np.zeros(shape, float)
    false = np.zeros(shape, bool)
    return (
        np.stack([x if x is not None else zero for x in brightness]),
        np.stack([x if x is not None else false for x in valid_masks]),
        np.stack([x if x is not None else false for x in stone_masks]),
        rgb_paths,
    )


def _summary_reason(summary, support_pixels):
    if summary.get("status") == "ok":
        return []
    if not support_pixels:
        return ["no_support"]
    return ["insufficient_finite_frames"]


def _region_cells(representation, masks, brightness, valid_masks, whole_values, observed, upstream, step_qc, source_indices):
    regions = {}
    for region, region_masks in masks.items():
        regions[region] = {}
        for mode in ("fixed", "dynamic"):
            cell = a.regional_trace(brightness, valid_masks, region_masks, whole_values, observed, mode)
            raw_support = cell["persistent_support_pixels"] if mode == "fixed" else max((x or 0) for x in cell["per_frame_support_fraction"])
            raw_reasons = _summary_reason(cell["raw_summary"], raw_support)
            relative_reasons = _summary_reason(cell["relative_summary"], raw_support)
            cell["raw_validity"] = a.activation_validity(
                representation, upstream, step_qc, cell["raw_summary"]["status"], raw_reasons
            )
            cell["relative_validity"] = a.activation_validity(
                representation, upstream, step_qc, cell["relative_summary"]["status"], relative_reasons
            )
            cell["raw_evidence"] = select_evidence_frames(cell["raw_values"], source_indices)
            cell["relative_evidence"] = select_evidence_frames(cell["relative_values"], source_indices)
            regions[region][mode] = cell
    return regions


def measure_stone(processed, step_output, indices, wrap=False):
    processed = Path(processed).resolve()
    step_output = Path(step_output).resolve()
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, excluded = _select_records(metadata, list(indices), wrap)
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, rgb_paths = _load_frame_arrays(processed, selected)
    upstream = _upstream_validity(selected, excluded)

    whole = a.whole_stone_trace(brightness, valid_masks, stone_masks, observed)
    whole_reasons = _summary_reason(whole["summary"], whole["persistent_support_pixels"])
    whole["validity"] = a.activation_validity(
        "whole_stone", upstream, None, whole["summary"]["status"], whole_reasons
    )
    whole["evidence"] = select_evidence_frames(whole["values"], list(indices))

    coarse_masks = a.load_coarse_masks(processed, selected)
    semantic_masks, step_qc = a.load_semantic_masks(step_output, selected)
    representations = {
        "coarse": {
            "source_indices": list(indices),
            "regions": _region_cells(
                "coarse", coarse_masks, brightness, valid_masks, whole["values"], observed,
                upstream, None, list(indices)
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
            upstream, step_qc, list(indices)
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
        "trace_definition": {
            "whole_stone": "median encoded brightness on fixed common registered stone support",
            "regional_raw": "median encoded brightness in declared region/support mode",
            "regional_relative": "log(regional median) - log(fixed-support whole-stone median)",
            "excursions": "Q90-Q50 bright, Q50-Q10 dark, sum = Q90-Q10 total",
            "mad_scale": "1.4826 * median absolute deviation about Q50",
        },
        "upstream_validity": upstream,
        "whole_stone": whole,
        "representations": representations,
        "frame_rgb_paths": rgb_paths,
    }


def _is_adjacent(left, right):
    return right == left + 1 or (right == 0 and left > 0)


def select_evidence_frames(trace, source_indices):
    if len(trace) != len(source_indices):
        raise ValueError("trace and source indices must have equal length")
    finite = [(i, float(value)) for i, value in enumerate(trace)
              if value is not None and math.isfinite(float(value))]
    if not finite:
        return {key: None for key in ("q10", "q50", "q90", "largest_positive_move", "largest_negative_move")}

    values = np.asarray([value for _, value in finite], float)
    result = {}
    for label, q in (("q10", .1), ("q50", .5), ("q90", .9)):
        target = float(np.quantile(values, q))
        position, value = min(finite, key=lambda item: (abs(item[1] - target), item[0]))
        result[label] = {"position": position, "source_index": source_indices[position], "value": value}

    positive = []
    negative = []
    for position in range(1, len(trace)):
        previous, current = trace[position - 1], trace[position]
        if previous is None or current is None or not _is_adjacent(source_indices[position - 1], source_indices[position]):
            continue
        previous, current = float(previous), float(current)
        if not math.isfinite(previous) or not math.isfinite(current):
            continue
        delta = current - previous
        item = {"position": position, "source_index": source_indices[position], "value": current, "delta": delta}
        if delta > 0:
            positive.append(item)
        elif delta < 0:
            negative.append(item)
    result["largest_positive_move"] = max(positive, key=lambda item: (item["delta"], -item["position"])) if positive else None
    result["largest_negative_move"] = min(negative, key=lambda item: (item["delta"], item["position"])) if negative else None
    return result


def _draw_evidence(trace, indices, evidence, rgb_paths, processed, destination, title):
    width, height = 1000, 620
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((15, 12), title, fill="black")
    finite = [float(v) for v in trace if v is not None and math.isfinite(float(v))]
    left, top, right, bottom = 60, 55, 960, 250
    draw.line((left, bottom, right, bottom), fill="grey")
    draw.line((left, top, left, bottom), fill="grey")
    if finite:
        lo, hi = min(finite), max(finite)
        span = hi - lo or 1.0
        previous = None
        for i, value in enumerate(trace):
            if value is None or not math.isfinite(float(value)):
                previous = None
                continue
            point = (left + i * (right - left) / max(1, len(trace) - 1), bottom - (float(value) - lo) / span * (bottom - top))
            if previous is not None:
                draw.line((previous, point), fill="black", width=2)
            draw.ellipse((point[0]-2, point[1]-2, point[0]+2, point[1]+2), fill="black")
            previous = point

    items = []
    for label in ("q10", "q50", "q90", "largest_positive_move", "largest_negative_move"):
        item = evidence.get(label)
        if item is not None and all(existing[1]["position"] != item["position"] for existing in items):
            items.append((label, item))
    thumb_w = 180
    for j, (label, item) in enumerate(items[:5]):
        x = 20 + j * 195
        y = 300
        path = rgb_paths[item["position"]]
        if path:
            frame = Image.open(processed / path).convert("RGB")
            frame.thumbnail((thumb_w, 240))
            image.paste(frame, (x + (thumb_w-frame.width)//2, y))
        suffix = f" Δ {item['delta']:+.3g}" if "delta" in item else ""
        draw.text((x, 275), f"{label}: src {item['source_index']}{suffix}", fill="black")
    image.save(destination)


def write_stone_outputs(result, output, processed):
    output = Path(output)
    processed = Path(processed)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence").mkdir(exist_ok=True)
    (output / "activation.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")

    fields = [
        "representation", "region", "support_mode", "trace_type", "status", "reasons",
        "finite_frames", "q10", "q50", "q90", "bright_excursion", "dark_excursion",
        "total_excursion", "mad_scale", "persistent_support_fraction",
    ]
    rows = []
    whole = result["whole_stone"]
    rows.append({
        "representation": "whole_stone", "region": "whole_stone", "support_mode": "fixed", "trace_type": "raw",
        "status": whole["validity"]["status"], "reasons": ";".join(whole["validity"]["reasons"]),
        **{key: whole["summary"].get(key) for key in fields if key in whole["summary"]},
        "persistent_support_fraction": None,
    })
    _draw_evidence(
        whole["values"], result["requested_indices"], whole["evidence"], result["frame_rgb_paths"], processed,
        output / "evidence" / "whole-stone.png", "Whole-stone activation"
    )

    for representation, rep in result["representations"].items():
        for region, modes in rep.get("regions", {}).items():
            for mode, cell in modes.items():
                for trace_type, values, summary, validity, evidence in (
                    ("raw", cell["raw_values"], cell["raw_summary"], cell["raw_validity"], cell["raw_evidence"]),
                    ("relative", cell["relative_values"], cell["relative_summary"], cell["relative_validity"], cell["relative_evidence"]),
                ):
                    row = {
                        "representation": representation, "region": region, "support_mode": mode, "trace_type": trace_type,
                        "status": validity["status"], "reasons": ";".join(validity["reasons"]),
                        "persistent_support_fraction": cell.get("persistent_support_fraction"),
                    }
                    row.update({key: summary.get(key) for key in ("finite_frames", "q10", "q50", "q90", "bright_excursion", "dark_excursion", "total_excursion", "mad_scale")})
                    rows.append(row)
                    slug = f"{representation}-{region}-{mode}-{trace_type}.png"
                    _draw_evidence(values, result["requested_indices"], evidence, result["frame_rgb_paths"], processed,
                                   output / "evidence" / slug, f"{representation} / {region} / {mode} / {trace_type}")
    with (output / "activation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in fields} for row in rows])
