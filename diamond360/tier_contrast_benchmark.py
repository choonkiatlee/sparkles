"""Measure adjacent-tier tonal separation from retained #26 activation outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as activation
from . import activation_benchmark as ab
from . import asscher_steps as steps
from . import regions as coarse_regions
from . import tier_contrast as tc

SCHEMA = "diamond360-tier-contrast/1"
REGION_TRACE_SCHEMA = "diamond360-region-traces/1"
PAIRS = (("centre", "inner"), ("inner", "middle"))
BOUNDARY_WIDTHS = (.025, .040, .055)
BOUNDARY_GUARD = .010
BOUNDARY_SPECS = {
    "centre__inner": {"semantic": "centre_inner", "coarse_radius": .20},
    "inner__middle": {"semantic": "inner_middle", "coarse_radius": .45},
}


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


def measure_from_activation(
    activation,
    spread_traces=None,
    localized_band_values=None,
    localized_support_pixels=None,
):
    """Consume exact #26 coarse-fixed traces; optional raw-pixel inputs test challengers."""
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
        if localized_band_values and left in localized_band_values and right in localized_band_values:
            localized = tc.sectorized_contrast_trace(
                localized_band_values[left],
                localized_band_values[right],
                indices,
            )
            localized_validity = tc.compose_validity(
                [left_cell["relative_validity"], right_cell["relative_validity"]],
                localized["median_summary"],
            )
            localized_result = {
                **localized,
                "validity": localized_validity,
                "evidence": tc.select_sectorized_evidence(localized["frame_trace"]),
                "support_pixels": {
                    "left": (localized_support_pixels or {}).get(left, {}),
                    "right": (localized_support_pixels or {}).get(right, {}),
                },
            }
        else:
            localized_result = {
                "status": "unavailable",
                "reason": "localized_sector_inputs_unavailable",
            }

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
            "localized": localized_result,
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
            "localized": (
                "within each of the existing eight image-axis sectors, intersect each "
                "coarse radial band with that sector, use fixed common support, compute "
                "abs(log local median_i - log local median_j), and preserve all sector traces"
            ),
            "localized_summary": (
                "per-frame median across eight matched sector separations; q75 is retained "
                "as audit context, not a second production score"
            ),
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
    """Load raw pixels once for standardized and matched-sector challengers."""
    from . import activation as a
    from . import regions as coarse_regions

    processed = Path(processed)
    metadata = json.loads((processed / "sequence.json").read_text())
    selected, _ = ab._select_records(
        metadata,
        list(activation["requested_indices"]),
        bool(activation.get("wrap_explicit")),
    )
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, _, _ = ab._load_frame_arrays(processed, selected)
    radial_masks = a.load_coarse_masks(processed, selected)
    region_paths = [
        processed / record["regions_path"] if record is not None else None
        for record in selected
    ]
    sector_masks = a._stack_masks(region_paths, coarse_regions.SECTORS)

    spreads = {}
    localized = {}
    support_pixels = {}
    for band in ("centre", "inner", "middle"):
        common = a._persistent_support(valid_masks, radial_masks[band], observed)
        spreads[band] = [
            tc.robust_fractional_spread(frame[common])
            if ok and common.any() else None
            for frame, ok in zip(brightness, observed)
        ]
        localized[band] = {}
        support_pixels[band] = {}
        for sector in coarse_regions.SECTORS:
            cell_masks = radial_masks[band] & sector_masks[sector]
            cell_common = a._persistent_support(valid_masks, cell_masks, observed)
            support_pixels[band][sector] = int(cell_common.sum())
            localized[band][sector] = [
                float(np.median(frame[cell_common]))
                if ok and cell_common.any() else None
                for frame, ok in zip(brightness, observed)
            ]
    return {
        "spreads": spreads,
        "localized_band_values": localized,
        "localized_support_pixels": support_pixels,
        "camera_paths": [
            record.get("camera_original_path") if record is not None else None
            for record in selected
        ],
        "region_paths": [
            record.get("regions_path") if record is not None else None
            for record in selected
        ],
        "mask_paths": [
            record.get("registration", {}).get("mask_path")
            if record is not None else None
            for record in selected
        ],
    }


def _fixed_strip_trace(brightness, valid_masks, masks, observed):
    common = activation._persistent_support(valid_masks, masks, observed)
    values = [
        float(np.median(frame[common])) if ok and common.any() else None
        for frame, ok in zip(brightness, observed)
    ]
    union = np.any(masks[observed], axis=0) if observed.any() else np.zeros(masks.shape[1:], bool)
    return values, {
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": (
            float(common.sum() / union.sum()) if union.any() else None
        ),
    }


def _boundary_local_inputs(
    processed,
    step_output,
    activation_result,
    widths=BOUNDARY_WIDTHS,
    guard=BOUNDARY_GUARD,
):
    """Measure guarded local strips using fixed #19 and legacy coarse geometry."""
    processed = Path(processed)
    step_output = Path(step_output)
    metadata = json.loads((processed / "sequence.json").read_text())
    indices = list(activation_result["requested_indices"])
    selected, _ = ab._select_records(
        metadata, indices, bool(activation_result.get("wrap_explicit"))
    )
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, _ = ab._load_frame_arrays(processed, selected)
    region_paths = [
        processed / record["regions_path"] if record is not None else None
        for record in selected
    ]
    sector_masks = activation._stack_masks(region_paths, coarse_regions.SECTORS)
    if not sector_masks:
        return {"status": "unavailable", "reason": "sector_masks_unavailable"}

    step_payload = json.loads((step_output / "steps.json").read_text())
    _, step_qc = activation.load_semantic_masks(step_output, selected)
    boundaries = step_payload.get("boundaries") or {}
    shape = brightness.shape[1:]
    zero = np.zeros(shape, bool)

    output = {
        "guard_u": float(guard),
        "widths_u": [float(width) for width in widths],
        "support_mode": "fixed persistent pixel support within each strip/sector",
        "semantic_geometry": "#19 sequence-level eight-sector boundary controls; no per-frame boundary motion",
        "coarse_geometry": "legacy coarse square-radius boundary control",
        "pairs": {},
    }

    for left, right in PAIRS:
        pair_id = _pair_id(left, right)
        spec = BOUNDARY_SPECS[pair_id]
        semantic_control = boundaries.get(spec["semantic"])
        pair_out = {"widths": {}}
        for width in widths:
            width_key = f"{float(width):.3f}"
            by_geometry = {}
            for geometry in ("coarse", "semantic"):
                if geometry == "semantic" and (
                    step_qc.get("template_status") == "unavailable"
                    or semantic_control is None
                ):
                    by_geometry[geometry] = {
                        "status": "unavailable",
                        "reason": step_qc.get("template_reason") or "semantic_boundary_unavailable",
                    }
                    continue

                inside_values = {sector: [] for sector in coarse_regions.SECTORS}
                outside_values = {sector: [] for sector in coarse_regions.SECTORS}
                support = {
                    "inside": {sector: {} for sector in coarse_regions.SECTORS},
                    "outside": {sector: {} for sector in coarse_regions.SECTORS},
                }
                for sector in coarse_regions.SECTORS:
                    inside_masks = []
                    outside_masks = []
                    for position, ok in enumerate(observed):
                        if not ok:
                            inside_masks.append(zero)
                            outside_masks.append(zero)
                            continue
                        sector_mask = sector_masks[sector][position]
                        if geometry == "semantic":
                            strips = steps.boundary_strip_masks(
                                stone_masks[position],
                                semantic_control["sector_u"],
                                width=float(width),
                                guard=float(guard),
                                sector_mask=sector_mask,
                            )
                        else:
                            strips = coarse_regions.boundary_strip_masks(
                                stone_masks[position],
                                spec["coarse_radius"],
                                width=float(width),
                                guard=float(guard),
                                sector_mask=sector_mask,
                            )
                        inside_masks.append(strips["inside"])
                        outside_masks.append(strips["outside"])
                    inside_masks = np.stack(inside_masks)
                    outside_masks = np.stack(outside_masks)
                    inside_values[sector], support["inside"][sector] = _fixed_strip_trace(
                        brightness, valid_masks, inside_masks, observed
                    )
                    outside_values[sector], support["outside"][sector] = _fixed_strip_trace(
                        brightness, valid_masks, outside_masks, observed
                    )

                measured = tc.sectorized_contrast_trace(
                    inside_values, outside_values, indices
                )
                if geometry == "semantic":
                    validity = activation.activation_validity(
                        "semantic",
                        activation_result["upstream_validity"],
                        step_qc,
                        measured["median_summary"]["status"],
                        measured["median_summary"].get("reasons", []),
                    )
                else:
                    validity = activation.activation_validity(
                        "coarse",
                        activation_result["upstream_validity"],
                        None,
                        measured["median_summary"]["status"],
                        measured["median_summary"].get("reasons", []),
                    )
                geometry_meta = (
                    {
                        "type": "semantic",
                        "boundary_name": spec["semantic"],
                        "sector_u": [float(value) for value in semantic_control["sector_u"]],
                    }
                    if geometry == "semantic"
                    else {
                        "type": "coarse",
                        "boundary_name": pair_id,
                        "radius": float(spec["coarse_radius"]),
                    }
                )
                by_geometry[geometry] = {
                    **measured,
                    "validity": validity,
                    "evidence": tc.select_sectorized_evidence(measured["frame_trace"]),
                    "strip_support": support,
                    "geometry": geometry_meta,
                }
            pair_out["widths"][width_key] = by_geometry
        output["pairs"][pair_id] = pair_out
    return output

def measure_stone(processed, step_output, indices, wrap=False):
    activation_result = ab.measure_stone(processed, step_output, indices, wrap=wrap)
    spread_inputs = _fixed_spread_inputs(processed, activation_result)
    result = measure_from_activation(
        activation_result,
        spread_inputs["spreads"],
        spread_inputs["localized_band_values"],
        spread_inputs["localized_support_pixels"],
    )
    boundary_local = _boundary_local_inputs(
        processed,
        step_output,
        activation_result,
    )
    for pair_id, pair in result["pairs"].items():
        pair["boundary_local"] = (
            boundary_local.get("pairs", {}).get(
                pair_id,
                {"status": "unavailable", "reason": boundary_local.get("reason")},
            )
        )
    result["boundary_local_definition"] = {
        key: value for key, value in boundary_local.items() if key != "pairs"
    }
    result["frame_camera_paths"] = spread_inputs["camera_paths"]
    result["frame_region_paths"] = spread_inputs["region_paths"]
    result["frame_mask_paths"] = spread_inputs["mask_paths"]
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


def _overlay_regions(image, region_path, pair, processed, sector=None):
    image = image.convert("RGB")
    if region_path is None:
        return image
    with np.load(Path(processed) / region_path) as data:
        left_mask = np.asarray(data[pair[0]], bool)
        right_mask = np.asarray(data[pair[1]], bool)
        if sector is not None:
            sector_mask = np.asarray(data[sector], bool)
            left_mask &= sector_mask
            right_mask &= sector_mask
        left = _boundary(left_mask)
        right = _boundary(right_mask)
    array = np.asarray(image).copy()
    array[left] = (255, 70, 70)
    array[right] = (70, 130, 255)
    return Image.fromarray(array)


def _render_event_row(
    canvas, draw, y, label, event, result, processed, pair, localized=False
):
    position = event["position"]
    source_index = event["source_index"]
    standardized = event.get("standardized_separation")
    value = event.get("median_separation", event.get("separation"))
    detail = f"{label}: source {source_index}; D={value:.5f}"
    if localized and event.get("strongest_sector"):
        detail += (
            f"; strongest={event['strongest_sector']}"
            f" {event['strongest_sector_separation']:.5f}"
        )
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
        registered = _overlay_regions(
            registered,
            region_path,
            pair,
            processed,
            event.get("strongest_sector") if localized else None,
        )
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



def _draw_localized_panel(destination, pair_id, pair_result, result, processed):
    localized = pair_result.get("localized") or {}
    evidence = localized.get("evidence") or {}
    ordered = [
        ("weakest localized separation", evidence.get("weakest")),
        ("median localized separation", evidence.get("median")),
        ("strongest localized separation", evidence.get("strongest")),
    ]
    rows = [(label, event) for label, event in ordered if event is not None]
    canvas = Image.new("RGB", (1020, 65 + 235 * max(1, len(rows))), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        f"{pair_id}: matched-sector local contrast; camera (left), strongest-sector overlay (right)",
        fill="black",
    )
    draw.text((10, 30), "red = left local cell; blue = right local cell; image-axis sectors only", fill="black")
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
            localized=True,
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
        "localized_status",
        "localized_q10",
        "localized_q50",
        "localized_q90",
        "localized_q75_q50",
    ]
    rows = []
    for pair_id, pair in result["pairs"].items():
        simple = pair["simple"]
        standardized = pair["standardized"]
        localized = pair.get("localized") or {}
        localized_summary = localized.get("median_summary") or {}
        localized_q75 = localized.get("q75_summary") or {}
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
                "localized_status": (localized.get("validity") or {}).get(
                    "status", localized.get("status", "unavailable")
                ),
                "localized_q10": localized_summary.get("q10"),
                "localized_q50": localized_summary.get("q50"),
                "localized_q90": localized_summary.get("q90"),
                "localized_q75_q50": localized_q75.get("q50"),
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
            if (pair.get("localized") or {}).get("frame_trace"):
                _draw_localized_panel(
                    evidence_dir / f"{pair_id}-localized.png",
                    pair_id,
                    pair,
                    result,
                    processed,
                )
    with (output / "tier-contrast.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
