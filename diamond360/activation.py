"""Descriptive activation traces for registered Asscher 360 sequences."""
from __future__ import annotations

import math

import numpy as np

_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}
_SUMMARY_KEYS = (
    "q10", "q50", "q90", "bright_excursion", "dark_excursion",
    "total_excursion", "mad_scale",
)


def _finite_values(values):
    out = []
    for value in values:
        if value is None:
            continue
        value = float(value)
        if math.isfinite(value):
            out.append(value)
    return out


def summarise_activation(values):
    finite = _finite_values(values)
    result = {"status": "ok" if len(finite) >= 3 else "unavailable", "finite_frames": len(finite)}
    if len(finite) < 3:
        result.update({key: None for key in _SUMMARY_KEYS})
        return result
    data = np.asarray(finite, float)
    q10, q50, q90 = (float(np.quantile(data, q)) for q in (.1, .5, .9))
    bright = q90 - q50
    dark = q50 - q10
    result.update(
        q10=q10,
        q50=q50,
        q90=q90,
        bright_excursion=bright,
        dark_excursion=dark,
        total_excursion=bright + dark,
        mad_scale=float(1.4826 * np.median(np.abs(data - q50))),
    )
    return result


def _validate_arrays(brightness, valid_masks, masks, observed):
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    masks = np.asarray(masks, bool)
    observed = np.asarray(observed, bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape or masks.shape != brightness.shape:
        raise ValueError("brightness, valid masks and masks must be matching frame-height-width arrays")
    if observed.shape != (len(brightness),):
        raise ValueError("observed flags must match frames")
    valid_masks = valid_masks & np.isfinite(brightness)
    return brightness, valid_masks, masks, observed


def _persistent_support(valid_masks, masks, observed):
    if not observed.any():
        return np.zeros(valid_masks.shape[1:], bool)
    return np.all((valid_masks & masks)[observed], axis=0)


def whole_stone_trace(brightness, valid_masks, stone_masks, observed):
    brightness, valid_masks, stone_masks, observed = _validate_arrays(
        brightness, valid_masks, stone_masks, observed
    )
    common = _persistent_support(valid_masks, stone_masks, observed)
    values = []
    dynamic_support = []
    for frame, valid, stone, ok in zip(brightness, valid_masks, stone_masks, observed):
        nominal = int(stone.sum())
        supported = valid & stone
        dynamic_support.append(float(supported.sum() / nominal) if ok and nominal else None)
        values.append(float(np.median(frame[common])) if ok and common.any() else None)
    return {
        "values": values,
        "persistent_support_pixels": int(common.sum()),
        "per_frame_support_fraction": dynamic_support,
        "summary": summarise_activation(values),
    }


def regional_trace(brightness, valid_masks, region_masks, whole_stone_values, observed, support_mode):
    brightness, valid_masks, region_masks, observed = _validate_arrays(
        brightness, valid_masks, region_masks, observed
    )
    if support_mode not in {"fixed", "dynamic"}:
        raise ValueError('support_mode must be "fixed" or "dynamic"')
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")

    common = _persistent_support(valid_masks, region_masks, observed)
    raw = []
    relative = []
    support_fractions = []
    for frame, valid, region, whole, ok in zip(
        brightness, valid_masks, region_masks, whole_stone_values, observed
    ):
        nominal = int(region.sum())
        dynamic = valid & region
        support_fractions.append(float(dynamic.sum() / nominal) if ok and nominal else None)
        support = common if support_mode == "fixed" else dynamic
        if not ok or not support.any():
            raw.append(None)
            relative.append(None)
            continue
        regional = float(np.median(frame[support]))
        raw.append(regional)
        if whole is None or regional <= 0 or not math.isfinite(regional):
            relative.append(None)
            continue
        whole = float(whole)
        relative.append(float(math.log(regional) - math.log(whole)) if whole > 0 and math.isfinite(whole) else None)

    nominal_union = np.any(region_masks[observed], axis=0) if observed.any() else np.zeros(region_masks.shape[1:], bool)
    return {
        "support_mode": support_mode,
        "raw_values": raw,
        "relative_values": relative,
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / nominal_union.sum()) if nominal_union.any() else None,
        "per_frame_support_fraction": support_fractions,
        "raw_summary": summarise_activation(raw),
        "relative_summary": summarise_activation(relative),
    }


def compose_validity(sources):
    worst = "ok"
    reasons = []
    for source in sources:
        status = source.get("status", "ok")
        if status not in _STATUS_RANK:
            raise ValueError(f"unknown validity status: {status}")
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
        reason = source.get("reason")
        if reason and reason not in reasons:
            reasons.append(reason)
        for item in source.get("reasons", []):
            if item and item not in reasons:
                reasons.append(item)
    return {"status": worst, "reasons": reasons}


COARSE_BANDS = ("centre", "inner", "middle", "outer")
SEMANTIC_BANDS = ("centre", "inner_step", "middle_step", "outer_step")


def _stack_masks(paths, names):
    loaded = []
    shape = None
    for path in paths:
        if path is None:
            loaded.append(None)
            continue
        with np.load(path) as data:
            masks = {name: np.asarray(data[name], bool).copy() for name in names}
        current_shape = next(iter(masks.values())).shape
        if any(mask.shape != current_shape for mask in masks.values()):
            raise ValueError("region masks in one frame must share a shape")
        if shape is None:
            shape = current_shape
        elif shape != current_shape:
            raise ValueError("region masks must share one registered canvas shape")
        loaded.append(masks)
    if shape is None:
        return {}
    return {
        name: np.stack([
            item[name] if item is not None else np.zeros(shape, bool)
            for item in loaded
        ])
        for name in names
    }


def load_coarse_masks(processed, selected_records):
    from pathlib import Path
    processed = Path(processed)
    paths = [processed / record["regions_path"] if record is not None else None for record in selected_records]
    return _stack_masks(paths, COARSE_BANDS)


def load_semantic_masks(step_output, selected_records):
    import json
    from pathlib import Path

    step_output = Path(step_output)
    payload = json.loads((step_output / "steps.json").read_text())
    template_status = payload.get("template_status", "unavailable")
    qc = {
        "template_status": template_status,
        "template_reason": payload.get("template_reason"),
        "selected_frame_statuses": [],
    }
    if template_status == "unavailable":
        return {}, qc

    lookup = {frame.get("source_index"): frame for frame in payload.get("frames", [])}
    paths = []
    statuses = []
    for record in selected_records:
        if record is None:
            paths.append(None)
            continue
        frame = lookup.get(record.get("source_index"))
        if frame is None or not frame.get("region_path"):
            paths.append(None)
            statuses.append("unavailable")
            continue
        paths.append(step_output / frame["region_path"])
        statuses.append(frame.get("status", "unavailable"))
    qc["selected_frame_statuses"] = statuses
    return _stack_masks(paths, SEMANTIC_BANDS), qc


def activation_validity(representation, upstream, step_qc, local_status, local_reasons):
    if representation not in {"whole_stone", "coarse", "semantic"}:
        raise ValueError("representation must be whole_stone, coarse or semantic")
    sources = [upstream, {"status": local_status, "reasons": list(local_reasons)}]
    if representation == "semantic":
        if step_qc is None:
            sources.append({"status": "unavailable", "reason": "semantic_qc_missing"})
        else:
            sources.append({
                "status": step_qc.get("template_status", "unavailable"),
                "reason": step_qc.get("template_reason"),
            })
            statuses = step_qc.get("selected_frame_statuses", [])
            if "unavailable" in statuses:
                sources.append({"status": "unavailable", "reason": "semantic_frame_unavailable"})
            elif "review" in statuses:
                sources.append({"status": "review", "reason": "semantic_frame_review"})
    return compose_validity(sources)


COARSE_BANDS = ("centre", "inner", "middle", "outer")
SEMANTIC_BANDS = ("centre", "inner_step", "middle_step", "outer_step")


def _first_mask_shape(root, records, bands):
    for record in records:
        if record is None:
            continue
        path = record.get("regions_path")
        if not path:
            continue
        with np.load(root / path) as data:
            return data[bands[0]].shape
    return None


def load_coarse_masks(processed, selected_records):
    from pathlib import Path
    processed = Path(processed)
    shape = _first_mask_shape(processed, selected_records, COARSE_BANDS)
    if shape is None:
        raise ValueError("No accepted coarse region masks in selected records")
    out = {name: [] for name in COARSE_BANDS}
    for record in selected_records:
        if record is None:
            for name in COARSE_BANDS:
                out[name].append(np.zeros(shape, bool))
            continue
        path = record.get("regions_path")
        if not path:
            raise ValueError("Selected coarse record is missing regions_path")
        with np.load(processed / path) as data:
            for name in COARSE_BANDS:
                out[name].append(np.asarray(data[name], bool).copy())
    return {name: np.stack(frames) for name, frames in out.items()}


def load_semantic_masks(step_output, selected_records):
    import json
    from pathlib import Path
    step_output = Path(step_output)
    metadata = json.loads((step_output / "steps.json").read_text())
    qc = {
        "template_status": metadata.get("template_status", "unavailable"),
        "template_reason": metadata.get("template_reason"),
        "selected_frame_statuses": [],
    }
    if qc["template_status"] == "unavailable":
        return {}, qc

    lookup = {frame.get("source_index"): frame for frame in metadata.get("frames", [])}
    available = [lookup.get(record.get("source_index")) for record in selected_records if record is not None]
    available = [frame for frame in available if frame and frame.get("region_path")]
    if not available:
        raise ValueError("No semantic region masks match selected records")
    with np.load(step_output / available[0]["region_path"]) as data:
        shape = data[SEMANTIC_BANDS[0]].shape

    out = {name: [] for name in SEMANTIC_BANDS}
    for record in selected_records:
        if record is None:
            qc["selected_frame_statuses"].append("unavailable")
            for name in SEMANTIC_BANDS:
                out[name].append(np.zeros(shape, bool))
            continue
        frame = lookup.get(record.get("source_index"))
        if not frame or not frame.get("region_path"):
            qc["selected_frame_statuses"].append("unavailable")
            for name in SEMANTIC_BANDS:
                out[name].append(np.zeros(shape, bool))
            continue
        qc["selected_frame_statuses"].append(frame.get("status", "unavailable"))
        with np.load(step_output / frame["region_path"]) as data:
            for name in SEMANTIC_BANDS:
                out[name].append(np.asarray(data[name], bool).copy())
    return {name: np.stack(frames) for name, frames in out.items()}, qc


def activation_validity(representation, upstream, step_qc, local_status, local_reasons):
    if representation not in {"whole_stone", "coarse", "semantic"}:
        raise ValueError("unknown activation representation")
    sources = [upstream, {"status": local_status, "reasons": list(local_reasons)}]
    if representation == "semantic":
        if step_qc is None:
            sources.append({"status": "unavailable", "reason": "semantic_qc_missing"})
        else:
            sources.append({
                "status": step_qc.get("template_status", "unavailable"),
                "reason": step_qc.get("template_reason"),
            })
            statuses = step_qc.get("selected_frame_statuses", [])
            if any(status == "unavailable" for status in statuses):
                sources.append({"status": "unavailable", "reason": "semantic_frame_unavailable"})
            elif any(status == "review" for status in statuses):
                sources.append({"status": "review", "reason": "semantic_frame_review"})
    return compose_validity(sources)
