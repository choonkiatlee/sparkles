"""Measure adjacent-tier tonal separation from retained #26 activation outputs."""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation as activation
from . import activation_benchmark as ab
from . import asscher_steps as steps
from . import regions as coarse_regions
from . import tier_contrast as tc
from . import pipeline

SCHEMA = "diamond360-tier-contrast/3"
REGION_TRACE_SCHEMA = "diamond360-region-traces/1"
PAIRS = (("centre", "inner"), ("inner", "middle"))
BOUNDARY_FRACTIONS = (.25, .40, .55)
BOUNDARY_GUARD = .010
BOUNDARY_SPECS = {
    "centre__inner": {
        "semantic": "centre_inner",
        "semantic_inner": None,
        "semantic_outer": "inner_middle",
        "coarse_triplet": (0.0, .20, .45),
    },
    "inner__middle": {
        "semantic": "inner_middle",
        "semantic_inner": "centre_inner",
        "semantic_outer": "middle_outer",
        "coarse_triplet": (.20, .45, .70),
    },
}
CORE_INDICES = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE_INDICES = list(range(240,256)) + list(range(0,17))


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


def _strip_trace(brightness, valid_masks, masks, observed):
    """Measure fixed-normalised geometry on each frame's valid strip support.

    Boundary controls stay fixed for the sequence, but the silhouette-normalised
    strip naturally maps to slightly different registered pixels as the outline
    changes. Intersecting those pixels across the whole sequence can erase a
    narrow strip entirely, so support is evaluated per frame and retained as QC.
    """
    values = []
    support_pixels = []
    support_fractions = []
    for frame, valid, mask, ok in zip(
        brightness, valid_masks, masks, observed
    ):
        nominal = int(mask.sum())
        support = valid & mask
        count = int(support.sum()) if ok else 0
        support_pixels.append(count if ok else None)
        support_fractions.append(
            float(count / nominal) if ok and nominal else None
        )
        values.append(
            float(np.median(frame[support]))
            if ok and support.any() else None
        )
    finite_pixels = [
        value for value in support_pixels if value is not None
    ]
    finite_fractions = [
        value for value in support_fractions if value is not None
    ]
    return values, {
        "support_mode": "per_frame_valid_with_fixed_normalised_geometry",
        "per_frame_support_pixels": support_pixels,
        "per_frame_support_fraction": support_fractions,
        "min_support_pixels": min(finite_pixels) if finite_pixels else None,
        "min_support_fraction": (
            min(finite_fractions) if finite_fractions else None
        ),
    }



def _boundary_control(payload, name):
    if name is None:
        return None, "endpoint"
    boundaries = payload.get("boundaries") or {}
    partial = payload.get("partial_boundaries") or {}
    reason = str(payload.get("template_reason") or "")
    if name in boundaries:
        return boundaries[name], "full_template"
    if reason.startswith("no_supported_") and name in partial:
        return partial[name], "partial_boundary"
    return None, "unavailable"


def _semantic_geometry(payload, spec):
    """Resolve one pair's boundary plus adjacent tier references.

    A missing neighbouring boundary may be mirrored from the observed opposite
    span, but only as review. Ambiguous/non-separable templates are never
    rescued.
    """
    template_status = payload.get("template_status", "unavailable")
    template_reason = str(payload.get("template_reason") or "")
    if template_status == "unavailable" and not template_reason.startswith("no_supported_"):
        return {
            "status": "unavailable",
            "reason": template_reason or "semantic_template_unavailable",
        }

    boundary, boundary_source = _boundary_control(payload, spec["semantic"])
    if boundary is None:
        return {
            "status": "unavailable",
            "reason": f"boundary_unavailable:{spec['semantic']}",
        }

    b = np.asarray(boundary["sector_u"], float)
    if spec["semantic_inner"] is None:
        inner = np.zeros(8, float)
        inner_source = "centre_endpoint"
    else:
        inner_control, inner_source = _boundary_control(
            payload, spec["semantic_inner"]
        )
        inner = (
            np.asarray(inner_control["sector_u"], float)
            if inner_control is not None else None
        )

    outer_control, outer_source = _boundary_control(
        payload, spec["semantic_outer"]
    )
    outer = (
        np.asarray(outer_control["sector_u"], float)
        if outer_control is not None else None
    )

    reasons = []
    if inner is None and outer is None:
        return {
            "status": "unavailable",
            "reason": "adjacent_tier_references_unavailable",
        }
    if inner is None:
        inner = np.maximum(.001, b - (outer - b))
        inner_source = "mirrored_outer_span"
        reasons.append(f"mirrored_inner_reference:{spec['semantic_inner']}")
    if outer is None:
        outer = np.minimum(.999, b + (b - inner))
        outer_source = "mirrored_inner_span"
        reasons.append(f"mirrored_outer_reference:{spec['semantic_outer']}")

    if (
        np.any(~np.isfinite(inner))
        or np.any(~np.isfinite(b))
        or np.any(~np.isfinite(outer))
        or np.any(inner >= b)
        or np.any(b >= outer)
    ):
        return {
            "status": "unavailable",
            "reason": "semantic_reference_order_invalid",
        }

    sources = [boundary_source, inner_source, outer_source]
    if template_status == "review":
        reasons.append(payload.get("template_reason") or "semantic_template_review")
    if "partial_boundary" in sources:
        reasons.append(
            "partial_step_boundary:"
            + (template_reason or "full_template_unavailable")
        )
    if any(source in {"partial_boundary", "mirrored_inner_span", "mirrored_outer_span"}
           for source in sources):
        reasons.append("semantic_geometry_partial")
    status = "review" if reasons else "ok"
    return {
        "status": status,
        "reasons": reasons,
        "boundary_name": spec["semantic"],
        "inner_reference_name": spec["semantic_inner"] or "centre_endpoint",
        "outer_reference_name": spec["semantic_outer"],
        "boundary_source": boundary_source,
        "inner_reference_source": inner_source,
        "outer_reference_source": outer_source,
        "inner_sector_u": [float(value) for value in inner],
        "boundary_sector_u": [float(value) for value in b],
        "outer_sector_u": [float(value) for value in outer],
        "template_status": template_status,
        "template_reason": payload.get("template_reason"),
    }


def _boundary_local_inputs(
    processed,
    step_output,
    activation_result,
    fractions=BOUNDARY_FRACTIONS,
    guard=BOUNDARY_GUARD,
):
    """Measure guarded tier-relative strips with one fixed sequence geometry."""
    processed = Path(processed)
    step_output = Path(step_output)
    metadata = json.loads((processed / "sequence.json").read_text())
    indices = list(activation_result["requested_indices"])
    selected, _ = ab._select_records(
        metadata, indices, bool(activation_result.get("wrap_explicit"))
    )
    observed = np.asarray([record is not None for record in selected], bool)
    brightness, valid_masks, stone_masks, _ = ab._load_frame_arrays(
        processed, selected
    )
    region_paths = [
        processed / record["regions_path"] if record is not None else None
        for record in selected
    ]
    sector_masks = activation._stack_masks(region_paths, coarse_regions.SECTORS)
    if not sector_masks:
        return {"status": "unavailable", "reason": "sector_masks_unavailable"}

    step_payload = json.loads((step_output / "steps.json").read_text())
    shape = brightness.shape[1:]
    zero = np.zeros(shape, bool)
    output = {
        "guard_u": float(guard),
        "scale_fractions": [float(value) for value in fractions],
        "support_mode": (
            "one fixed sequence-level boundary geometry; per-frame valid strip support"
        ),
        "semantic_geometry": (
            "#19 canonical eight-sector boundary controls with adjacent-tier-relative "
            "strip widths; no per-frame boundary motion"
        ),
        "coarse_geometry": (
            "legacy coarse square-radius boundaries with adjacent-ring-relative widths"
        ),
        "pairs": {},
    }

    for left, right in PAIRS:
        pair_id = _pair_id(left, right)
        spec = BOUNDARY_SPECS[pair_id]
        semantic_geometry = _semantic_geometry(step_payload, spec)
        pair_out = {
            "scales": {},
            "semantic_geometry_status": semantic_geometry.get("status"),
            "semantic_geometry_reason": semantic_geometry.get("reason"),
        }
        scale_results = {"coarse": {}, "semantic": {}}

        for fraction in fractions:
            scale_key = f"{float(fraction):.3f}"
            by_geometry = {}
            for geometry in ("coarse", "semantic"):
                if geometry == "semantic" and semantic_geometry.get("status") == "unavailable":
                    by_geometry[geometry] = {
                        "status": "unavailable",
                        "reason": semantic_geometry.get("reason"),
                    }
                    continue

                inside_values = {
                    sector: [] for sector in coarse_regions.SECTORS
                }
                outside_values = {
                    sector: [] for sector in coarse_regions.SECTORS
                }
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
                            strips = steps.relative_boundary_strip_masks(
                                stone_masks[position],
                                semantic_geometry["inner_sector_u"],
                                semantic_geometry["boundary_sector_u"],
                                semantic_geometry["outer_sector_u"],
                                fraction=float(fraction),
                                guard=float(guard),
                                sector_mask=sector_mask,
                            )
                        else:
                            inner_radius, boundary_radius, outer_radius = (
                                spec["coarse_triplet"]
                            )
                            strips = coarse_regions.relative_boundary_strip_masks(
                                stone_masks[position],
                                inner_radius,
                                boundary_radius,
                                outer_radius,
                                fraction=float(fraction),
                                guard=float(guard),
                                sector_mask=sector_mask,
                            )
                        inside_masks.append(strips["inside"])
                        outside_masks.append(strips["outside"])
                    inside_masks = np.stack(inside_masks)
                    outside_masks = np.stack(outside_masks)
                    inside_values[sector], support["inside"][sector] = _strip_trace(
                        brightness, valid_masks, inside_masks, observed
                    )
                    outside_values[sector], support["outside"][sector] = _strip_trace(
                        brightness, valid_masks, outside_masks, observed
                    )

                measured = tc.sectorized_contrast_trace(
                    inside_values, outside_values, indices
                )
                if geometry == "semantic":
                    geometry_validity = {
                        "status": semantic_geometry["status"],
                        "reasons": list(semantic_geometry.get("reasons") or []),
                    }
                    validity = tc.compose_validity(
                        [
                            activation_result["upstream_validity"],
                            geometry_validity,
                        ],
                        measured["median_summary"],
                    )
                    geometry_meta = {
                        "type": "semantic_relative",
                        **semantic_geometry,
                    }
                else:
                    validity = tc.compose_validity(
                        [activation_result["upstream_validity"]],
                        measured["median_summary"],
                    )
                    geometry_meta = {
                        "type": "coarse_relative",
                        "boundary_name": pair_id,
                        "inner_radius": float(spec["coarse_triplet"][0]),
                        "boundary_radius": float(spec["coarse_triplet"][1]),
                        "outer_radius": float(spec["coarse_triplet"][2]),
                    }

                candidate = {
                    **measured,
                    "validity": validity,
                    "evidence": tc.select_sectorized_evidence(
                        measured["frame_trace"]
                    ),
                    "strip_support": support,
                    "geometry": geometry_meta,
                    "scale_fraction": float(fraction),
                }
                by_geometry[geometry] = candidate
                scale_results[geometry][scale_key] = candidate
            pair_out["scales"][scale_key] = by_geometry

        pair_out["multi_scale"] = {}
        for geometry in ("coarse", "semantic"):
            available = {
                key: value
                for key, value in scale_results[geometry].items()
                if value.get("frame_trace")
            }
            if not available:
                pair_out["multi_scale"][geometry] = {
                    "status": "unavailable",
                    "reason": "no_available_scales",
                }
                continue
            consensus = tc.multiscale_sector_consensus(available)
            validity = tc.compose_validity(
                [value["validity"] for value in available.values()],
                consensus["median_summary"],
            )
            pair_out["multi_scale"][geometry] = {
                **consensus,
                "validity": validity,
                "evidence": tc.select_sectorized_evidence(
                    consensus["frame_trace"]
                ),
                "geometry": next(iter(available.values()))["geometry"],
            }
        output["pairs"][pair_id] = pair_out
    return output


def measure_stone(processed, step_output, indices, wrap=False):
    activation_result = ab.measure_stone(
        processed, step_output, indices, wrap=wrap
    )
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
                {
                    "status": "unavailable",
                    "reason": boundary_local.get("reason"),
                },
            )
        )
        broad_trace = (pair.get("localized") or {}).get("frame_trace") or []
        for geometries in (
            pair["boundary_local"].get("scales") or {}
        ).values():
            coarse = geometries.get("coarse") or {}
            semantic = geometries.get("semantic") or {}
            for candidate in (coarse, semantic):
                if broad_trace and candidate.get("frame_trace"):
                    candidate["strongest_disagreement_vs_broad"] = (
                        tc.strongest_rank_disagreement(
                            broad_trace,
                            "median_separation",
                            candidate["frame_trace"],
                            "median_separation",
                        )
                    )
            if coarse.get("frame_trace") and semantic.get("frame_trace"):
                semantic["strongest_disagreement_vs_coarse_boundary"] = (
                    tc.strongest_rank_disagreement(
                        coarse["frame_trace"],
                        "median_separation",
                        semantic["frame_trace"],
                        "median_separation",
                    )
                )

        multi = pair["boundary_local"].get("multi_scale") or {}
        coarse_multi = multi.get("coarse") or {}
        semantic_multi = multi.get("semantic") or {}
        for candidate in (coarse_multi, semantic_multi):
            if broad_trace and candidate.get("frame_trace"):
                candidate["strongest_disagreement_vs_broad"] = (
                    tc.strongest_rank_disagreement(
                        broad_trace,
                        "median_separation",
                        candidate["frame_trace"],
                        "median_separation",
                    )
                )
        if (
            coarse_multi.get("frame_trace")
            and semantic_multi.get("frame_trace")
        ):
            semantic_multi["strongest_disagreement_vs_coarse_boundary"] = (
                tc.strongest_rank_disagreement(
                    coarse_multi["frame_trace"],
                    "median_separation",
                    semantic_multi["frame_trace"],
                    "median_separation",
                )
            )

    semantic_pairs = {
        pair_id: (
            ((pair.get("boundary_local") or {}).get("multi_scale") or {})
            .get("semantic", {})
        )
        for pair_id, pair in result["pairs"].items()
    }
    centre_inner = semantic_pairs.get("centre__inner") or {}
    inner_middle = semantic_pairs.get("inner__middle") or {}
    if centre_inner.get("frame_trace") and inner_middle.get("frame_trace"):
        joint = tc.joint_nested_tier_readability(
            centre_inner["frame_trace"],
            inner_middle["frame_trace"],
        )
        joint_validity = tc.compose_validity(
            [
                centre_inner.get("validity") or {"status": "unavailable"},
                inner_middle.get("validity") or {"status": "unavailable"},
            ],
            joint["median_summary"],
        )
        result["tier_readability_profile"] = {
            **joint,
            "validity": joint_validity,
            "research_only": True,
            "definition": (
                "per-sector weakest-link min(boundary-local centre-inner, "
                "boundary-local inner-middle), plus exact signed tonal ordering"
            ),
            "quality_direction": None,
        }
    else:
        result["tier_readability_profile"] = {
            "status": "unavailable",
            "reason": "semantic_multiscale_pair_unavailable",
            "research_only": True,
            "quality_direction": None,
        }

    result["boundary_local_definition"] = {
        key: value
        for key, value in boundary_local.items()
        if key != "pairs"
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

def _overlay_boundary_strips(
    image, mask_path, region_path, geometry, fraction, guard, sector, processed
):
    image = image.convert("RGB")
    if not mask_path or not region_path or not sector:
        return image
    processed = Path(processed)
    mask = np.asarray(Image.open(processed / mask_path).convert("L")) > 0
    with np.load(processed / region_path) as data:
        sector_mask = np.asarray(data[sector], bool)
    if geometry.get("type") == "semantic_relative":
        strips = steps.relative_boundary_strip_masks(
            mask,
            geometry["inner_sector_u"],
            geometry["boundary_sector_u"],
            geometry["outer_sector_u"],
            fraction=float(fraction),
            guard=float(guard),
            sector_mask=sector_mask,
        )
    elif geometry.get("type") == "coarse_relative":
        strips = coarse_regions.relative_boundary_strip_masks(
            mask,
            geometry["inner_radius"],
            geometry["boundary_radius"],
            geometry["outer_radius"],
            fraction=float(fraction),
            guard=float(guard),
            sector_mask=sector_mask,
        )
    else:
        return image
    array = np.asarray(image).copy()
    inside = strips["inside"]
    outside = strips["outside"]
    if inside.any():
        array[inside] = (
            .65 * array[inside] + .35 * np.array([255, 70, 70])
        ).astype(np.uint8)
    if outside.any():
        array[outside] = (
            .65 * array[outside] + .35 * np.array([70, 130, 255])
        ).astype(np.uint8)
    return Image.fromarray(array)


def _draw_boundary_local_panel(
    destination,
    pair_id,
    pair_result,
    result,
    processed,
    geometry_name,
    display_fraction=.40,
):
    boundary = pair_result.get("boundary_local") or {}
    candidate = (boundary.get("multi_scale") or {}).get(geometry_name, {})
    evidence = candidate.get("evidence") or {}
    if not candidate.get("frame_trace") or not evidence:
        return False
    ordered = [
        ("weakest multiscale separation", evidence.get("weakest")),
        ("median multiscale separation", evidence.get("median")),
        ("strongest multiscale separation", evidence.get("strongest")),
    ]
    rows = [(label, event) for label, event in ordered if event is not None]
    if not rows:
        return False
    canvas = Image.new("RGB", (1020, 65 + 235 * len(rows)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 10),
        f"{pair_id}: {geometry_name} tier-relative multiscale contrast",
        fill="black",
    )
    draw.text(
        (10, 30),
        (
            f"consensus across alpha={result.get('boundary_local_definition', {}).get('scale_fractions')}; "
            f"overlay alpha={display_fraction:.2f}; red=inside blue=outside"
        ),
        fill="black",
    )
    geometry = candidate.get("geometry") or {}
    guard = result.get("boundary_local_definition", {}).get(
        "guard_u", BOUNDARY_GUARD
    )
    for index, (label, event) in enumerate(rows):
        position = event["position"]
        source_index = event["source_index"]
        value = event.get("median_separation")
        strongest = event.get("strongest_sector")
        strongest_value = event.get("strongest_sector_separation")
        value_text = f"{value:.5f}" if value is not None else "n/a"
        detail = f"{label}: source {source_index}; median={value_text}"
        if strongest is not None and strongest_value is not None:
            detail += f"; strongest={strongest} {strongest_value:.5f}"
        if event.get("median_scale_spread") is not None:
            detail += f"; scale-spread={event['median_scale_spread']:.5f}"
        y = 60 + index * 235
        draw.text((10, y), detail, fill="black")
        camera_path = result.get("frame_camera_paths", [])[position]
        registered_path = result.get("frame_rgb_paths", [])[position]
        mask_path = result.get("frame_mask_paths", [])[position]
        region_path = result.get("frame_region_paths", [])[position]
        if camera_path:
            with Image.open(Path(processed) / camera_path) as source:
                source = source.convert("RGB")
            source.thumbnail((480, 190))
            canvas.paste(source, (10, y + 25))
        if registered_path:
            with Image.open(Path(processed) / registered_path) as registered:
                registered = registered.convert("RGB")
            registered = _overlay_boundary_strips(
                registered,
                mask_path,
                region_path,
                geometry,
                display_fraction,
                guard,
                strongest,
                processed,
            )
            registered.thumbnail((480, 190))
            canvas.paste(registered, (520, y + 25))
    canvas.save(destination)
    return True


def _draw_same_frame_boundary_comparison(
    destination,
    pair_id,
    pair_result,
    result,
    processed,
    display_fraction=.40,
):
    """Compare broad and revised multiscale formulations on aligned frames."""
    boundary = pair_result.get("boundary_local") or {}
    multi = boundary.get("multi_scale") or {}
    semantic = multi.get("semantic") or {}
    coarse = multi.get("coarse") or {}
    evidence = semantic.get("evidence") or {}
    if not semantic.get("frame_trace") or not coarse.get("frame_trace"):
        return False
    ordered = [
        ("weak", evidence.get("weakest")),
        ("typical", evidence.get("median")),
        ("strong", evidence.get("strongest")),
        (
            "vs broad disagreement",
            semantic.get("strongest_disagreement_vs_broad"),
        ),
    ]
    rows = [(label, event) for label, event in ordered if event is not None]
    if not rows:
        return False

    canvas = Image.new("RGB", (1510, 70 + 250 * len(rows)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 8),
        f"{pair_id}: same-frame revised PR-A comparison",
        fill="black",
    )
    draw.text(
        (10, 28),
        (
            "camera source | coarse tier-relative strips | #19 tier-relative strips; "
            f"values=multiscale consensus, overlays alpha={display_fraction:.2f}"
        ),
        fill="black",
    )
    guard = result.get("boundary_local_definition", {}).get(
        "guard_u", BOUNDARY_GUARD
    )
    simple_trace = (pair_result.get("simple") or {}).get("frame_trace") or []
    broad_trace = (pair_result.get("localized") or {}).get("frame_trace") or []

    def fmt(value):
        return "n/a" if value is None else f"{float(value):.5f}"

    for row_index, (label, event) in enumerate(rows):
        position = event["position"]
        semantic_row = semantic["frame_trace"][position]
        coarse_row = coarse["frame_trace"][position]
        sector = (
            event.get("strongest_sector")
            or semantic_row.get("strongest_sector")
        )
        simple_value = (
            simple_trace[position].get("separation")
            if position < len(simple_trace) else None
        )
        broad_value = (
            broad_trace[position].get("median_separation")
            if position < len(broad_trace) else None
        )
        y = 58 + row_index * 250
        detail = (
            f"{label}: source {event['source_index']} · whole={fmt(simple_value)} · "
            f"broad-sector={fmt(broad_value)} · coarse-multiscale={fmt(coarse_row.get('median_separation'))} · "
            f"semantic-multiscale={fmt(semantic_row.get('median_separation'))} · sector={sector or 'n/a'}"
        )
        if event.get("rank_disagreement") is not None:
            detail += f" · rank-disagreement={event['rank_disagreement']:.2f}"
        draw.text((10, y), detail, fill="black")
        camera_path = result.get("frame_camera_paths", [])[position]
        registered_path = result.get("frame_rgb_paths", [])[position]
        mask_path = result.get("frame_mask_paths", [])[position]
        region_path = result.get("frame_region_paths", [])[position]
        if camera_path:
            with Image.open(Path(processed) / camera_path) as source:
                source = source.convert("RGB")
            source.thumbnail((480, 205))
            canvas.paste(source, (10, y + 25))
        if registered_path:
            with Image.open(Path(processed) / registered_path) as base:
                base = base.convert("RGB")
            coarse_image = _overlay_boundary_strips(
                base,
                mask_path,
                region_path,
                coarse.get("geometry") or {},
                display_fraction,
                guard,
                sector,
                processed,
            )
            semantic_image = _overlay_boundary_strips(
                base,
                mask_path,
                region_path,
                semantic.get("geometry") or {},
                display_fraction,
                guard,
                sector,
                processed,
            )
            coarse_image.thumbnail((480, 205))
            semantic_image.thumbnail((480, 205))
            canvas.paste(coarse_image, (515, y + 25))
            canvas.paste(semantic_image, (1010, y + 25))
    canvas.save(destination)
    return True


def _write_boundary_local_csv(result, output):
    rows = []
    for pair_id, pair in result.get("pairs", {}).items():
        boundary = pair.get("boundary_local") or {}
        for scale_key, geometries in (boundary.get("scales") or {}).items():
            for geometry_name, candidate in geometries.items():
                summary = candidate.get("median_summary") or {}
                q75 = candidate.get("q75_summary") or {}
                support = candidate.get("strip_support") or {}
                pixels = []
                fractions = []
                for side in ("inside", "outside"):
                    for cell in (support.get(side) or {}).values():
                        value = cell.get("min_support_pixels")
                        if value is not None:
                            pixels.append(int(value))
                        value = cell.get("min_support_fraction")
                        if value is not None:
                            fractions.append(float(value))
                rows.append({
                    "pair": pair_id,
                    "scale_fraction": scale_key,
                    "geometry": geometry_name,
                    "status": (candidate.get("validity") or {}).get(
                        "status", candidate.get("status")
                    ),
                    "q10": summary.get("q10"),
                    "q50": summary.get("q50"),
                    "q90": summary.get("q90"),
                    "q75_frame_median": q75.get("q50"),
                    "scale_spread_q50": None,
                    "finite_frames": summary.get("finite_frames"),
                    "min_frame_support_pixels": min(pixels) if pixels else None,
                    "min_frame_support_fraction": (
                        min(fractions) if fractions else None
                    ),
                })
        for geometry_name, candidate in (
            boundary.get("multi_scale") or {}
        ).items():
            summary = candidate.get("median_summary") or {}
            q75 = candidate.get("q75_summary") or {}
            spread = candidate.get("scale_spread_summary") or {}
            rows.append({
                "pair": pair_id,
                "scale_fraction": "consensus",
                "geometry": geometry_name,
                "status": (candidate.get("validity") or {}).get(
                    "status", candidate.get("status")
                ),
                "q10": summary.get("q10"),
                "q50": summary.get("q50"),
                "q90": summary.get("q90"),
                "q75_frame_median": q75.get("q50"),
                "scale_spread_q50": spread.get("q50"),
                "finite_frames": summary.get("finite_frames"),
                "min_frame_support_pixels": None,
                "min_frame_support_fraction": None,
            })
    if not rows:
        return
    fields = list(rows[0])
    with (Path(output) / "boundary-local.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)



def _profile_row(name, candidate):
    rows = candidate.get("frame_trace") or []
    q25_key = (
        "q25_joint_separation"
        if name == "joint_weakest_link" else "q25_separation"
    )
    median_key = (
        "median_joint_separation"
        if name == "joint_weakest_link" else "median_separation"
    )
    coverage_events = [
        row for row in rows
        if row.get(q25_key) is not None and row.get(median_key) is not None
    ]
    strongest_coverage = (
        max(
            coverage_events,
            key=lambda row: (
                float(row[median_key]) - float(row[q25_key]),
                -int(row.get("position", 0)),
            ),
        )
        if coverage_events else None
    )
    result = {
        "profile": name,
        "status": (candidate.get("validity") or {}).get(
            "status", candidate.get("status")
        ),
        "q25_frame_q50": (candidate.get("q25_summary") or {}).get("q50"),
        "median_frame_q50": (candidate.get("median_summary") or {}).get("q50"),
        "q75_frame_q50": (candidate.get("q75_summary") or {}).get("q50"),
        "q90_frame_q50": (candidate.get("q90_summary") or {}).get("q50"),
        "iqr_frame_q50": (candidate.get("iqr_summary") or {}).get("q50"),
        "mad_frame_q50": (candidate.get("mad_summary") or {}).get("q50"),
        "scale_spread_q50": (candidate.get("scale_spread_summary") or {}).get("q50"),
        "max_coverage_gap": (
            float(strongest_coverage[median_key] - strongest_coverage[q25_key])
            if strongest_coverage else None
        ),
        "max_coverage_gap_source_index": (
            strongest_coverage.get("source_index")
            if strongest_coverage else None
        ),
    }
    if name == "joint_weakest_link":
        event = (candidate.get("evidence") or {}).get(
            "strongest_joint_median_penalty"
        )
        result["max_joint_median_penalty"] = (
            event.get("joint_median_penalty") if event else None
        )
        result["max_joint_median_penalty_source_index"] = (
            event.get("source_index") if event else None
        )
    return result


def _write_tier_readability_profile_csv(result, output):
    rows = []
    for pair_id in ("centre__inner", "inner__middle"):
        candidate = (
            (((result.get("pairs") or {}).get(pair_id) or {})
             .get("boundary_local") or {})
            .get("multi_scale", {})
            .get("semantic", {})
        )
        if candidate.get("frame_trace"):
            rows.append(_profile_row(pair_id, candidate))
    joint = result.get("tier_readability_profile") or {}
    if joint.get("frame_trace"):
        row = _profile_row("joint_weakest_link", joint)
        for state, value in (joint.get("ordering_fractions") or {}).items():
            row[f"ordering_{state}_fraction"] = value
        rows.append(row)
    if not rows:
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with (Path(output) / "tier-readability-profile.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
        rows.append({
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
        })
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
            for geometry_name in ("semantic", "coarse"):
                _draw_boundary_local_panel(
                    evidence_dir
                    / f"{pair_id}-boundary-{geometry_name}.png",
                    pair_id,
                    pair,
                    result,
                    processed,
                    geometry_name,
                )
            _draw_same_frame_boundary_comparison(
                evidence_dir / f"{pair_id}-boundary-comparison.png",
                pair_id,
                pair,
                result,
                processed,
            )
    with (output / "tier-contrast.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    _write_boundary_local_csv(result, output)
    _write_tier_readability_profile_csv(result, output)


def _comparison_rows(certificate, pipeline_name, window, result):
    rows = []
    for pair_id, pair in result.get("pairs", {}).items():
        localized = pair.get("localized") or {}
        base = {
            "certificate": certificate,
            "pipeline": pipeline_name,
            "window": window,
            "pair": pair_id,
            "broad_localized_status": (localized.get("validity") or {}).get(
                "status", localized.get("status")
            ),
            "broad_localized_q50": (
                localized.get("median_summary") or {}
            ).get("q50"),
        }
        boundary = pair.get("boundary_local") or {}
        for scale_key, geometries in (
            boundary.get("scales") or {}
        ).items():
            row = dict(base)
            row["scale_fraction"] = scale_key
            row["formulation"] = "single_scale"
            for geometry_name in ("coarse", "semantic"):
                candidate = geometries.get(geometry_name) or {}
                summary = candidate.get("median_summary") or {}
                row[f"{geometry_name}_status"] = (
                    candidate.get("validity") or {}
                ).get("status", candidate.get("status"))
                row[f"{geometry_name}_q10"] = summary.get("q10")
                row[f"{geometry_name}_q50"] = summary.get("q50")
                row[f"{geometry_name}_q90"] = summary.get("q90")
                row[f"{geometry_name}_scale_spread_q50"] = None
            rows.append(row)

        row = dict(base)
        row["scale_fraction"] = "consensus"
        row["formulation"] = "multiscale_consensus"
        for geometry_name in ("coarse", "semantic"):
            candidate = (
                boundary.get("multi_scale") or {}
            ).get(geometry_name, {})
            summary = candidate.get("median_summary") or {}
            spread = candidate.get("scale_spread_summary") or {}
            row[f"{geometry_name}_status"] = (
                candidate.get("validity") or {}
            ).get("status", candidate.get("status"))
            row[f"{geometry_name}_q10"] = summary.get("q10")
            row[f"{geometry_name}_q50"] = summary.get("q50")
            row[f"{geometry_name}_q90"] = summary.get("q90")
            row[f"{geometry_name}_scale_spread_q50"] = spread.get("q50")
        rows.append(row)
    return rows



def _profile_comparison_rows(certificate, pipeline_name, window, result):
    base = {
        "certificate": certificate,
        "pipeline": pipeline_name,
        "window": window,
    }
    rows = []
    for pair_id in ("centre__inner", "inner__middle"):
        candidate = (
            (((result.get("pairs") or {}).get(pair_id) or {})
             .get("boundary_local") or {})
            .get("multi_scale", {})
            .get("semantic", {})
        )
        if candidate.get("frame_trace"):
            rows.append({**base, **_profile_row(pair_id, candidate)})
    joint = result.get("tier_readability_profile") or {}
    if joint.get("frame_trace"):
        row = {**base, **_profile_row("joint_weakest_link", joint)}
        for state, value in (joint.get("ordering_fractions") or {}).items():
            row[f"ordering_{state}_fraction"] = value
        rows.append(row)
    return rows


def _diagnostic_control(payload, name):
    control, source = _boundary_control(payload, name)
    if control is None:
        return None, source
    return np.asarray(control["sector_u"], float), source


def _geometry_diagnostic(canonical_payload, alternative_payload):
    rows = {}
    for name in steps.BOUNDARIES:
        canonical, canonical_source = _diagnostic_control(
            canonical_payload, name
        )
        alternative, alternative_source = _diagnostic_control(
            alternative_payload, name
        )
        if canonical is None or alternative is None:
            rows[name] = {
                "status": "unavailable",
                "canonical_source": canonical_source,
                "alternative_source": alternative_source,
            }
            continue
        delta = alternative - canonical
        rows[name] = {
            "status": "ok",
            "canonical_source": canonical_source,
            "alternative_source": alternative_source,
            "canonical_median_u": float(np.median(canonical)),
            "alternative_median_u": float(np.median(alternative)),
            "median_signed_delta_u": float(np.median(delta)),
            "median_abs_delta_u": float(np.median(np.abs(delta))),
            "max_abs_delta_u": float(np.max(np.abs(delta))),
        }
    return rows


def run_source_benchmark(source_root, output, bundle_manifest):
    """Run revised PR-A comparisons with one canonical wide #19 ruler."""
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    profile_rows = []
    stones = []

    with tempfile.TemporaryDirectory(
        prefix="sparkles-tier-readability-"
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = item["certificate"]
            source = source_root / certificate
            order_manifest = source / "source-manifest.json"
            processed = work / certificate / "processed"
            processed.parent.mkdir(parents=True, exist_ok=True)
            pipeline.run(
                source,
                processed,
                order_manifest,
                gain=1.0,
                diagnostic_indices=CORE_INDICES,
                accept_review=True,
            )
            pipeline_name = (
                "Workshop"
                if certificate == "IGI-LG756520111"
                else "Diajewel"
            )

            canonical_step_output = (
                work / certificate / "steps-canonical-wide"
            )
            steps.run(
                processed,
                canonical_step_output,
                WIDE_INDICES,
                wrap=True,
            )
            canonical_payload = json.loads(
                (canonical_step_output / "steps.json").read_text()
            )

            core_diagnostic_output = (
                work / certificate / "steps-diagnostic-core"
            )
            steps.run(
                processed,
                core_diagnostic_output,
                CORE_INDICES,
                wrap=True,
            )
            core_payload = json.loads(
                (core_diagnostic_output / "steps.json").read_text()
            )

            stone_summary = {
                "certificate": certificate,
                "pipeline": pipeline_name,
                "canonical_geometry": {
                    "window": "wide",
                    "requested_indices": WIDE_INDICES,
                    "template_status": canonical_payload.get(
                        "template_status"
                    ),
                    "template_reason": canonical_payload.get(
                        "template_reason"
                    ),
                },
                "geometry_diagnostics": {
                    "core_only_vs_canonical_wide": _geometry_diagnostic(
                        canonical_payload, core_payload
                    ),
                    "core_only_template_status": core_payload.get(
                        "template_status"
                    ),
                    "core_only_template_reason": core_payload.get(
                        "template_reason"
                    ),
                },
                "windows": {},
            }

            for window, indices in (
                ("core", CORE_INDICES),
                ("wide", WIDE_INDICES),
            ):
                measured = measure_stone(
                    processed,
                    canonical_step_output,
                    indices,
                    wrap=True,
                )
                destination = (
                    output / "per-stone" / certificate / window
                )
                write_stone_outputs(
                    measured, destination, processed=processed
                )
                rows.extend(
                    _comparison_rows(
                        certificate,
                        pipeline_name,
                        window,
                        measured,
                    )
                )
                profile_rows.extend(
                    _profile_comparison_rows(
                        certificate,
                        pipeline_name,
                        window,
                        measured,
                    )
                )
                stone_summary["windows"][window] = {
                    "measurement_geometry": "canonical_wide",
                    "tier_contrast_json": str(
                        destination.relative_to(output)
                        / "tier-contrast.json"
                    ),
                    "boundary_local_csv": str(
                        destination.relative_to(output)
                        / "boundary-local.csv"
                    ),
                    "evidence_dir": str(
                        destination.relative_to(output) / "evidence"
                    ),
                }
            stones.append(stone_summary)

    summary = {
        "schema_version": (
            "diamond360-tier-readability-pr-b-benchmark/1"
        ),
        "descriptor_schema": SCHEMA,
        "core_indices": CORE_INDICES,
        "wide_indices": WIDE_INDICES,
        "canonical_geometry_window": "wide",
        "boundary_scale_fractions": list(BOUNDARY_FRACTIONS),
        "boundary_guard_u": BOUNDARY_GUARD,
        "stones": stones,
        "interpretation": (
            "Research comparison only: PR B derives spatial coverage, "
            "joint weakest-link nested readability and signed instantaneous "
            "tonal ordering from the canonical PR-A multiscale semantic field."
        ),
        "non_goals": [
            "no production-profile field or master tier-readability score",
            "no fitted threshold or assumed quality direction",
            "no replacement for PR-C human frame-level calibration",
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    if rows:
        fields = list(rows[0])
        with (output / "comparison.csv").open(
            "w", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    if profile_rows:
        fields = []
        for row in profile_rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        with (output / "readability-profile.csv").open(
            "w", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(profile_rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=Path("docs/360/benchmark/source-bundles.json"),
    )
    args = parser.parse_args()
    run_source_benchmark(args.source_root, args.output, args.bundle_manifest)
    print(f"wrote tier readability PR-B benchmark -> {args.output}")


if __name__ == "__main__":
    main()
