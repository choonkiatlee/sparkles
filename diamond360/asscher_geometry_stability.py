"""Issue #89: multi-view stability and fixed-ruler transfer validation.

The estimator-stability arm deliberately re-runs the frozen #75 fitter on
controlled subsets of the same accepted geometry-support frames. The transfer
arm never calls the fitter: it evaluates new frame evidence against the one
primary stone-level scaffold and its frozen semantic targets.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_validation as validation
from . import asscher_outer_octagon as outer_octagon
from . import asscher_topology as topology
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-geometry-stability/1"
TRANSFER_SCHEMA = "diamond360-asscher-fixed-ruler-transfer/1"
STABILITY_POLICY = "leave_one_out_primary_geometry_views"
TRANSFER_POLICY = "fixed_primary_scaffold_no_refit"


def _metadata(record):
    coordinate = record.get("sequence_coordinate") or {}
    return {
        "source_index": record.get("source_index"),
        "position": record.get("position"),
        "rank": record.get("rank"),
        "face_role": record.get("face_role"),
        "pose_status": record.get("assessment", {}).get("status"),
        "pose_score": record.get("assessment", {}).get("score"),
        "rotation_phase_deg": coordinate.get("rotation_phase_deg"),
        "rotation_phase_0_360_deg": coordinate.get(
            "rotation_phase_0_360_deg"
        ),
        "gauge_quarter_turn": coordinate.get("gauge_quarter_turn"),
        "gauge_status": coordinate.get("gauge_status"),
    }


def _load_gauged_arrays(pose_output, record):
    canonical = record.get("canonical") or {}
    path = canonical.get("path")
    if not path:
        raise ValueError("record has no persisted canonical arrays")
    with np.load(Path(pose_output) / path) as data:
        brightness = wireframe._rotate_to_gauge(
            np.asarray(data["brightness"], float), record
        )
        mask = wireframe._rotate_to_gauge(
            np.asarray(data["mask"], bool), record
        )
        valid = wireframe._rotate_to_gauge(
            np.asarray(data["valid_mask"], bool), record
        )
    return brightness, mask, valid


def _load_evidence(pose_output, records):
    evidence, masks, brightness_frames, metadata = [], [], [], []
    u_reference = None
    for record in records:
        brightness, mask, valid = _load_gauged_arrays(pose_output, record)
        u, sectors = wireframe.extract_sector_evidence(
            brightness, mask, valid
        )
        if u_reference is None:
            u_reference = u
        elif not np.allclose(u_reference, u):
            raise ValueError("canonical frames use incompatible radial grids")
        evidence.append(sectors)
        masks.append(mask)
        brightness_frames.append(brightness)
        metadata.append(_metadata(record))
    if u_reference is None:
        raise ValueError("no frame evidence supplied")
    return (
        np.asarray(evidence, float),
        np.asarray(u_reference, float),
        masks,
        brightness_frames,
        metadata,
    )


def _fit_records(pose_output, records, gauge_id, *, method=validation.OUTER_METHOD):
    evidence, u, masks, brightness, metadata = _load_evidence(
        pose_output, records
    )
    if method in (validation.OUTER_METHOD, validation.WINDOW_METHOD):
        outer_fit = outer_octagon.fit_consensus(
            masks, frame_metadata=metadata
        )
        outer_vertices = np.asarray(
            outer_fit["vertices_topology_order"], float
        )
        outer_confidence = outer_fit["confidence"]
    elif method == validation.LEGACY_METHOD:
        outer_fit = None
        outer_vertices = wireframe._median_outer_vertices(masks)
        outer_confidence = None
    else:
        raise ValueError(f"unknown validation method {method}")
    result = wireframe.fit_from_sector_evidence(
        evidence,
        u,
        gauge_id=gauge_id,
        frame_metadata=metadata,
        outer_vertices=outer_vertices,
        outer_confidence=outer_confidence,
        step_peak_policy=(
            wireframe.steps.WINDOW_PEAK_POLICY
            if method == validation.WINDOW_METHOD
            else wireframe.steps.GLOBAL_PEAK_POLICY
        ),
    )
    result["selected_frames"] = metadata
    if outer_fit is not None:
        result["outer_evidence"] = outer_fit
    return result, brightness, masks


def _primary_fit(pose_output, pose_payload, *, method=validation.OUTER_METHOD):
    gauge_id = wireframe._gauge_id(pose_payload)
    if gauge_id is None:
        return {
            "schema_version": wireframe.SCHEMA,
            "status": "unavailable",
            "reason": "stable_sequence_gauge_unavailable",
            "scaffold": None,
        }, [], [], []
    if method in (validation.OUTER_METHOD, validation.WINDOW_METHOD):
        coarse = wireframe._select_geometry_records(
            pose_payload, max_frames=None
        )
        selected, outer_selection = outer_octagon.select_records(
            coarse,
            max_frames=wireframe.MAX_GEOMETRY_FRAMES,
            min_frames=wireframe.MIN_GEOMETRY_FRAMES,
        )
    elif method == validation.LEGACY_METHOD:
        selected = wireframe._select_geometry_records(pose_payload)
        outer_selection = None
    else:
        raise ValueError(f"unknown validation method {method}")
    if len(selected) < wireframe.MIN_GEOMETRY_FRAMES:
        result = {
            "schema_version": wireframe.SCHEMA,
            "status": "unavailable",
            "reason": (
                "fewer_than_three_outer_octagon_views"
                if outer_selection is not None
                else "fewer_than_three_compatible_geometry_views"
            ),
            "semantic_gauge_id": gauge_id,
            "scaffold": None,
        }
        if outer_selection is not None:
            result["outer_selection"] = outer_selection
        return result, selected, [], []
    result, brightness, masks = _fit_records(
        pose_output, selected, gauge_id, method=method
    )
    if outer_selection is not None:
        result["outer_selection"] = outer_selection
    result["sequence_gauge"] = pose_payload.get("sequence_gauge")
    return result, selected, brightness, masks

def _max_numeric(rows, field):
    values = [
        row.get(field)
        for row in rows.values()
        if row.get("comparable") and row.get(field) is not None
    ]
    return None if not values else float(max(values))


def summarize_validation_record(record):
    measurements = record.get("measurements", {})
    boundaries = measurements.get("boundary_displacement", {})
    entities = measurements.get("entity_displacement", {})
    changes = measurements.get("observation_changes", {})
    return {
        "status": record.get("status"),
        "reasons": list(record.get("reasons", [])),
        "max_boundary_displacement_u": _max_numeric(
            boundaries, "max_displacement_u"
        ),
        "max_boundary_displacement_tier_fraction": _max_numeric(
            boundaries, "max_displacement_tier_fraction"
        ),
        "max_entity_displacement_u": _max_numeric(
            entities, "displacement_u"
        ),
        "max_entity_displacement_tier_fraction": _max_numeric(
            entities, "displacement_tier_fraction"
        ),
        "semantic_identity_consistent": (
            None
            if measurements.get("semantic_identity") is None
            else measurements["semantic_identity"].get("consistent")
        ),
        "provenance_regression_count": sum(
            bool(row.get("provenance_regressed"))
            for row in changes.values()
        ),
        "observation_state_regression_count": sum(
            bool(row.get("observation_state_regressed"))
            for row in changes.values()
        ),
        "validity_regression_count": sum(
            bool(row.get("validity_regressed"))
            for row in changes.values()
        ),
    }


def _leave_one_out(
    pose_output,
    selected,
    primary_result,
    gauge_id,
    benchmark_manifest,
    certificate,
    output,
    *,
    method=validation.OUTER_METHOD,
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    if len(selected) <= wireframe.MIN_GEOMETRY_FRAMES:
        return {
            "policy": STABILITY_POLICY,
            "status": "unavailable",
            "reason": "primary_fit_has_no_removable_geometry_view",
            "runs": [],
        }

    for omitted_index, omitted in enumerate(selected):
        subset = [
            record
            for index, record in enumerate(selected)
            if index != omitted_index
        ]
        candidate, _, _ = _fit_records(
            pose_output, subset, gauge_id, method=method
        )
        case_id = (
            f"{certificate}:leave-out-source-"
            f"{omitted.get('source_index')}"
        )
        record = validation.build_validation_record(
            primary_result,
            candidate,
            benchmark_manifest,
            case_id=case_id,
            comparison_kind="estimator_stability_leave_one_out",
            method=method,
            run_metadata={
                "policy": STABILITY_POLICY,
                "omitted_source_index": omitted.get("source_index"),
                "omitted_position": omitted.get("position"),
                "reference_source_indices": [
                    row.get("source_index") for row in selected
                ],
                "candidate_source_indices": [
                    row.get("source_index") for row in subset
                ],
            },
        )
        stem = f"leave-out-{int(omitted.get('position', omitted_index)):04d}"
        filename = stem + ".json"
        candidate_filename = stem + "-wireframe.json"
        (output / filename).write_text(
            json.dumps(record, indent=2, allow_nan=False) + "\n"
        )
        (output / candidate_filename).write_text(
            json.dumps(candidate, indent=2, allow_nan=False) + "\n"
        )
        runs.append({
            "omitted_source_index": omitted.get("source_index"),
            "omitted_position": omitted.get("position"),
            "validation_path": filename,
            "candidate_wireframe_path": candidate_filename,
            **summarize_validation_record(record),
        })

    statuses = [row["status"] for row in runs]
    summary_status = (
        "unavailable"
        if "unavailable" in statuses
        else "review" if "review" in statuses else "ok"
    )
    return {
        "policy": STABILITY_POLICY,
        "status": summary_status,
        "reference_source_indices": [
            row.get("source_index") for row in selected
        ],
        "run_count": len(runs),
        "runs": runs,
        "max_boundary_displacement_u": max(
            (
                row["max_boundary_displacement_u"]
                for row in runs
                if row["max_boundary_displacement_u"] is not None
            ),
            default=None,
        ),
        "max_boundary_displacement_tier_fraction": max(
            (
                row["max_boundary_displacement_tier_fraction"]
                for row in runs
                if row["max_boundary_displacement_tier_fraction"] is not None
            ),
            default=None,
        ),
        "max_entity_displacement_u": max(
            (
                row["max_entity_displacement_u"]
                for row in runs
                if row["max_entity_displacement_u"] is not None
            ),
            default=None,
        ),
        "max_entity_displacement_tier_fraction": max(
            (
                row["max_entity_displacement_tier_fraction"]
                for row in runs
                if row["max_entity_displacement_tier_fraction"] is not None
            ),
            default=None,
        ),
        "semantic_identity_swap_count": sum(
            row["semantic_identity_consistent"] is False for row in runs
        ),
        "interpretation": (
            "Dispersion is descriptive only. #88 defines no post-hoc numeric "
            "pass/fail threshold."
        ),
    }


def _target_maps(primary_result):
    if primary_result.get("scaffold") is None:
        raise ValueError("primary result has no fixed scaffold")
    crown = {
        boundary_id: np.asarray(
            row["sector_u_step_order"], dtype=float
        )
        for boundary_id, row in primary_result.get(
            "boundary_evidence", {}
        ).items()
    }
    pavilion = {
        family: np.asarray(
            row["sector_u_step_order"], dtype=float
        )
        for family, row in primary_result.get(
            "pavilion_evidence", {}
        ).items()
    }
    required_crown = {"C1_C2", "C2_C3", "C3_TABLE"}
    required_pavilion = {"P1", "P2", "P3"}
    if set(crown) != required_crown:
        raise ValueError("primary result lacks frozen crown targets")
    if set(pavilion) != required_pavilion:
        raise ValueError("primary result lacks frozen pavilion targets")
    return crown, pavilion


def _diagnose_targets(frame_evidence, u, target_map):
    rows = {}
    for semantic_key, targets in target_map.items():
        diagnostics = [
            wireframe._frame_target_diagnostic(
                frame_evidence[sector], u, targets[sector]
            )
            for sector in range(8)
        ]
        rows[semantic_key] = {
            "target_sector_u_step_order": [
                float(value) for value in targets
            ],
            "sectors_step_order": diagnostics,
            "support_fraction": float(np.mean([
                row["supported"] for row in diagnostics
            ])),
            "supported_sector_count": int(sum(
                row["supported"] for row in diagnostics
            )),
        }
    return rows


def _diagnostic_confidence(row):
    z = row.get("z")
    if z is None or not np.isfinite(z):
        return 0.0
    return float(np.clip(0.45 + 0.18 * float(z), 0.0, 1.0))


def _combine_diagnostics(rows):
    if not rows:
        return {
            "status": "unavailable",
            "visibility": "unavailable",
            "confidence": 0.0,
            "supported_count": 0,
            "required_count": 0,
            "median_residual_u": None,
            "minimum_z": None,
        }
    available = [row for row in rows if row.get("z") is not None]
    supported = [row for row in rows if row.get("supported")]
    residuals = [
        row.get("residual_u")
        for row in supported
        if row.get("residual_u") is not None
    ]
    if len(supported) == len(rows):
        status = "ok"
        visibility = "supported"
    elif available:
        status = "review"
        visibility = "partial_or_weak"
    else:
        status = "unavailable"
        visibility = "unavailable"
    return {
        "status": status,
        "visibility": visibility,
        "confidence": (
            0.0
            if not available
            else float(min(_diagnostic_confidence(row) for row in available))
        ),
        "supported_count": len(supported),
        "required_count": len(rows),
        "median_residual_u": (
            None if not residuals else float(np.median(residuals))
        ),
        "minimum_z": (
            None
            if not available
            else float(min(float(row["z"]) for row in available))
        ),
    }


def transfer_entities(boundary_diagnostics, pavilion_diagnostics):
    """Map frozen per-sector evidence to fixed #74 semantic IDs.

    No identity is inferred here: semantic IDs come from the primary scaffold
    and only support/visibility is allowed to change.
    """
    rows = {}
    for topology_sector, orientation in enumerate(topology.ORIENTATIONS):
        raw_sector = wireframe.TOPOLOGY_TO_STEP[topology_sector]
        crown_requirements = {
            "C1": ["C1_C2"],
            "C2": ["C1_C2", "C2_C3"],
            "C3": ["C2_C3", "C3_TABLE"],
        }
        for family, boundary_ids in crown_requirements.items():
            diagnostics = [
                boundary_diagnostics[boundary_id][
                    "sectors_step_order"
                ][raw_sector]
                for boundary_id in boundary_ids
            ]
            rows[f"{family}_{orientation}"] = {
                "semantic_id": f"{family}_{orientation}",
                "support_kind": "fixed_crown_boundary_support",
                **_combine_diagnostics(diagnostics),
            }

        for family in ("P1", "P2", "P3"):
            diagnostic = pavilion_diagnostics[family][
                "sectors_step_order"
            ][raw_sector]
            rows[f"{family}_{orientation}"] = {
                "semantic_id": f"{family}_{orientation}",
                "support_kind": "fixed_nonexclusive_pavilion_locus",
                **_combine_diagnostics([diagnostic]),
            }

    table_diags = boundary_diagnostics["C3_TABLE"]["sectors_step_order"]
    rows["TABLE"] = {
        "semantic_id": "TABLE",
        "support_kind": "fixed_table_boundary_support",
        **_combine_diagnostics(table_diags),
    }
    p3_diags = pavilion_diagnostics["P3"]["sectors_step_order"]
    rows["CULET_REGION"] = {
        "semantic_id": "CULET_REGION",
        "support_kind": "fixed_nonexclusive_p3_inner_support",
        **_combine_diagnostics(p3_diags),
    }
    rows["GIRDLE"] = {
        "semantic_id": "GIRDLE",
        "support_kind": "canonical_silhouette",
        "status": "ok",
        "visibility": "supported",
        "confidence": 0.95,
        "supported_count": 1,
        "required_count": 1,
        "median_residual_u": None,
        "minimum_z": None,
    }
    for orientation in ("NE", "SE", "SW", "NW"):
        rows[f"WINDMILL_{orientation}"] = {
            "semantic_id": f"WINDMILL_{orientation}",
            "support_kind": "not_directly_observed_in_wireframe_v1",
            "status": "unavailable",
            "visibility": "unavailable",
            "confidence": 0.0,
            "supported_count": 0,
            "required_count": 0,
            "median_residual_u": None,
            "minimum_z": None,
        }
    return rows


def _circular_distance(position, centre, size):
    delta = abs(int(position) - int(centre)) % int(size)
    return int(min(delta, int(size) - delta))


def _frame_transfer_status(boundary_diagnostics):
    diagnostics = [
        row
        for boundary in ("C1_C2", "C2_C3", "C3_TABLE")
        for row in boundary_diagnostics[boundary]["sectors_step_order"]
    ]
    supported = sum(row.get("supported", False) for row in diagnostics)
    available = sum(row.get("z") is not None for row in diagnostics)
    if supported == len(diagnostics):
        return "ok", "all_frozen_crown_targets_supported"
    if available:
        return "review", "partial_or_weak_frozen_crown_support"
    return "unavailable", "frozen_crown_support_unavailable"


def transfer_fixed_ruler_frame(
    frame_evidence,
    u,
    primary_result,
    *,
    frame_metadata,
    crown_peak_position,
    sequence_size,
    in_primary_fit=False,
):
    """Evaluate one frame against frozen #75 targets; never fit new geometry."""
    crown_targets, pavilion_targets = _target_maps(primary_result)
    boundary = _diagnose_targets(frame_evidence, u, crown_targets)
    pavilion = _diagnose_targets(frame_evidence, u, pavilion_targets)
    entities = transfer_entities(boundary, pavilion)
    status, reason = _frame_transfer_status(boundary)
    position = frame_metadata.get("position")
    return {
        "schema_version": TRANSFER_SCHEMA,
        "source_index": frame_metadata.get("source_index"),
        "position": position,
        "rotation_phase_deg": frame_metadata.get("rotation_phase_deg"),
        "rotation_phase_0_360_deg": frame_metadata.get(
            "rotation_phase_0_360_deg"
        ),
        "gauge_quarter_turn": frame_metadata.get("gauge_quarter_turn"),
        "gauge_status": frame_metadata.get("gauge_status"),
        "face_role": frame_metadata.get("face_role"),
        "pose_status": frame_metadata.get("pose_status"),
        "pose_score": frame_metadata.get("pose_score"),
        "distance_from_crown_peak_frames": (
            None
            if position is None or crown_peak_position is None
            else _circular_distance(
                position, crown_peak_position, sequence_size
            )
        ),
        "in_primary_geometry_fit": bool(in_primary_fit),
        "geometry_mode": TRANSFER_POLICY,
        "refit_performed": False,
        "semantic_identity_source": "primary_fixed_scaffold",
        "semantic_gauge_id": primary_result.get("semantic_gauge_id"),
        "status": status,
        "reason": reason,
        "boundary_support": boundary,
        "pavilion_support": pavilion,
        "entities": entities,
    }


def _transfer_window(pose_payload, selected):
    """Use #73's crown lobe when resolved; otherwise derive a broad fixed window.

    The unresolved fallback is based only on the primary geometry-view cluster,
    not on transfer-frame optical evidence. Its base radius reuses #73's
    sequence-size / 8 lobe policy and expands only enough to contain every
    primary fitting view.
    """
    frames = pose_payload.get("frames", [])
    size = len(frames)
    if size < 1:
        raise ValueError("pose sequence has no frames")
    face = pose_payload.get("face_selection") or {}
    crown_peak = face.get("likely_crown_peak_position")
    if face.get("status") == "resolved" and crown_peak is not None:
        radius = int(face.get("lobe_radius_frames") or round(size / 8.0))
        return {
            "centre_position": int(crown_peak),
            "radius_frames": int(radius),
            "provenance": "resolved_73_crown_lobe",
        }

    selected_positions = [
        int(row["position"])
        for row in selected
        if row.get("position") is not None
    ]
    if not selected_positions:
        raise ValueError("cannot derive transfer window without primary positions")
    centre = min(
        selected_positions,
        key=lambda candidate: (
            sum(
                _circular_distance(position, candidate, size)
                for position in selected_positions
            ),
            candidate,
        ),
    )
    selected_radius = max(
        _circular_distance(position, centre, size)
        for position in selected_positions
    )
    return {
        "centre_position": int(centre),
        "radius_frames": int(max(round(size / 8.0), selected_radius)),
        "provenance": (
            "primary_geometry_view_circular_medoid_plus_73_lobe_radius"
        ),
    }


def _eligible_transfer_records(pose_payload, selected):
    frames = pose_payload.get("frames", [])
    size = len(frames)
    window = _transfer_window(pose_payload, selected)
    centre = window["centre_position"]
    radius = window["radius_frames"]
    wrap_positions = {0, max(0, size - 1)}
    records = []
    for record in frames:
        canonical = record.get("canonical") or {}
        coordinate = record.get("sequence_coordinate") or {}
        position = record.get("position")
        if not canonical.get("path") or position is None:
            continue
        if coordinate.get("gauge_status") not in ("available", "review"):
            continue
        in_window = _circular_distance(position, centre, size) <= radius
        if not in_window and int(position) not in wrap_positions:
            continue
        records.append(record)
    records.sort(key=lambda row: int(row.get("position", 10**9)))
    return records, window


def _wrap_summary(rows, sequence_size):
    positions = {
        int(row["position"])
        for row in rows
        if row.get("position") is not None
    }
    last = int(sequence_size) - 1
    gauge_turns = sorted({
        int(row["gauge_quarter_turn"])
        for row in rows
        if row.get("gauge_quarter_turn") in (0, 1, 2, 3)
    })
    gauge_ids = {
        row.get("semantic_gauge_id")
        for row in rows
        if row.get("semantic_gauge_id") is not None
    }
    return {
        "sequence_size": int(sequence_size),
        "contains_position_0": 0 in positions,
        "contains_last_position": last in positions,
        "cyclic_255_to_0_wrap_exercised": (
            int(sequence_size) == 256 and 255 in positions and 0 in positions
        ),
        "last_to_zero_wrap_exercised": last in positions and 0 in positions,
        "missing_gauge_count": sum(
            row.get("gauge_status") not in ("available", "review")
            for row in rows
        ),
        "gauge_quarter_turns_present": gauge_turns,
        "semantic_gauge_ids": sorted(gauge_ids),
        "one_semantic_gauge_for_all_frames": len(gauge_ids) <= 1,
        "refit_count": sum(bool(row.get("refit_performed")) for row in rows),
        "semantic_identity_policy": "fixed_primary_scaffold_ids_no_reassignment",
    }


def _run_transfer(
    pose_output,
    pose_payload,
    primary_result,
    selected,
    output,
):
    output = Path(output)
    records, window = _eligible_transfer_records(
        pose_payload, selected
    )
    selected_positions = {
        row.get("position") for row in selected
    }
    crown_peak = pose_payload.get("face_selection", {}).get(
        "likely_crown_peak_position"
    )
    sequence_size = len(pose_payload.get("frames", []))
    transfer_centre = window["centre_position"]
    transfer_radius = window["radius_frames"]
    rows = []
    render_items = []

    for record in records:
        brightness, mask, valid = _load_gauged_arrays(
            pose_output, record
        )
        u, evidence = wireframe.extract_sector_evidence(
            brightness, mask, valid
        )
        meta = _metadata(record)
        transfer = transfer_fixed_ruler_frame(
            evidence,
            u,
            primary_result,
            frame_metadata=meta,
            crown_peak_position=(
                crown_peak if crown_peak is not None else transfer_centre
            ),
            sequence_size=sequence_size,
            in_primary_fit=record.get("position") in selected_positions,
        )
        in_window = (
            _circular_distance(
                record.get("position"), transfer_centre, sequence_size
            )
            <= transfer_radius
        )
        transfer["transfer_scope"] = (
            "crown_view_window"
            if in_window
            else "cyclic_wrap_control"
        )
        rows.append(transfer)
        render_items.append((transfer, brightness, mask))

    wrap = _wrap_summary(rows, sequence_size)
    semantic_ids = sorted(
        primary_result["scaffold"]["entity_observations"]
    )
    entity_status_counts = {
        semantic_id: {
            status: sum(
                frame["entities"][semantic_id]["status"] == status
                for frame in rows
            )
            for status in ("ok", "review", "unavailable")
        }
        for semantic_id in semantic_ids
    }
    crown_rows = [
        row for row in rows
        if row["transfer_scope"] == "crown_view_window"
    ]
    payload = {
        "schema_version": TRANSFER_SCHEMA,
        "policy": TRANSFER_POLICY,
        "primary_semantic_gauge_id": primary_result.get(
            "semantic_gauge_id"
        ),
        "primary_source_indices": [
            row.get("source_index") for row in selected
        ],
        "primary_positions": [
            row.get("position") for row in selected
        ],
        "crown_peak_position": crown_peak,
        "transfer_window": window,
        "frame_count": len(rows),
        "crown_view_frame_count": len(crown_rows),
        "cyclic_wrap_control_count": sum(
            row["transfer_scope"] == "cyclic_wrap_control"
            for row in rows
        ),
        "outside_primary_fit_count": sum(
            not row["in_primary_geometry_fit"] for row in rows
        ),
        "status_counts": {
            status: sum(row["status"] == status for row in rows)
            for status in ("ok", "review", "unavailable")
        },
        "crown_view_status_counts": {
            status: sum(row["status"] == status for row in crown_rows)
            for status in ("ok", "review", "unavailable")
        },
        "entity_status_counts": entity_status_counts,
        "semantic_identity_swap_count": 0,
        "wrap_check": wrap,
        "frames": rows,
        "interpretation": (
            "Every frame is evaluated against the same primary semantic "
            "scaffold/targets. Support, residual, visibility and confidence may "
            "change; semantic geometry and IDs do not."
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "transfer.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload, render_items


def _write_primary_failure_qc(
    selected, brightness_frames, masks, output
):
    images = []
    for record, brightness, mask in zip(
        selected, brightness_frames, masks
    ):
        grey = np.rint(
            np.clip(brightness, 0.0, 1.0) * 255
        ).astype(np.uint8)
        rgb = np.repeat(grey[:, :, None], 3, axis=2)
        rgb[~np.asarray(mask, bool)] = 0
        image = Image.fromarray(rgb)
        images.append(_annotate(
            image,
            (
                f"src{record.get('source_index')} "
                f"p{record.get('position')} "
                f"{record.get('assessment', {}).get('status')}"
            ),
        ))
    if not images:
        return None
    path = Path(output) / "primary-failure-qc.jpg"
    wireframe._contact_sheet(images, path, columns=4)
    return path.name


def _annotate(image, text):
    image = image.copy()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 22), fill=(0, 0, 0))
    draw.text((4, 5), text, fill=(255, 255, 255))
    return image


def _write_transfer_qc(render_items, scaffold, output, limit=12):
    if not render_items:
        return None
    ranked = sorted(
        render_items,
        key=lambda item: (
            item[0].get("distance_from_crown_peak_frames")
            if item[0].get("distance_from_crown_peak_frames") is not None
            else 10**9,
            int(item[0].get("position", 10**9)),
        ),
    )
    chosen = []
    if len(ranked) <= limit:
        chosen = ranked
    else:
        indexes = np.linspace(0, len(ranked) - 1, limit, dtype=int)
        chosen = [ranked[int(index)] for index in indexes]

    # Always make the cyclic boundary auditable when those frames are present.
    by_position = {
        item[0].get("position"): item for item in render_items
    }
    for position in (255, 0):
        if position in by_position and by_position[position] not in chosen:
            chosen.append(by_position[position])
    chosen = chosen[: limit + 2]

    images = []
    for row, brightness, mask in chosen:
        overlay = wireframe._draw_scaffold_on_frame(
            brightness, mask, scaffold
        )
        label = (
            f"p{row.get('position')} src{row.get('source_index')} "
            f"d{row.get('distance_from_crown_peak_frames')} "
            f"{row.get('status')}"
        )
        images.append(_annotate(overlay, label))
    path = Path(output) / "transfer-qc.jpg"
    wireframe._contact_sheet(images, path, columns=4)
    return path.name


def _write_stability_qc(primary_result, stability_output, output):
    images = []
    if primary_result.get("scaffold") is not None:
        images.append(_annotate(
            topology.render_scaffold(primary_result["scaffold"], size=420),
            "primary",
        ))
    for run in stability_output.get("runs", []):
        candidate_path = (
            Path(output) / "stability" / run["candidate_wireframe_path"]
        )
        candidate = json.loads(candidate_path.read_text())
        scaffold = candidate.get("scaffold")
        if scaffold is None:
            image = topology.render_scaffold(
                primary_result["scaffold"], size=420
            )
        else:
            image = topology.render_scaffold(scaffold, size=420)
        fraction = run.get("max_boundary_displacement_tier_fraction")
        label = (
            f"omit {run.get('omitted_source_index')} "
            f"max-tier={fraction:.3f}"
            if fraction is not None
            else f"omit {run.get('omitted_source_index')} unavailable"
        )
        images.append(_annotate(image, label))
    if not images:
        return None
    path = Path(output) / "stability-qc.jpg"
    wireframe._contact_sheet(images, path, columns=4)
    return path.name


def run_stone(
    pose_output,
    output,
    benchmark_manifest,
    *,
    certificate,
    method=validation.OUTER_METHOD,
):
    validation.assert_frozen_method(method)
    validation.assert_frozen_benchmark_manifest(benchmark_manifest)
    pose_output = Path(pose_output)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    pose_payload = json.loads(
        (pose_output / "asscher-pose.json").read_text()
    )

    primary, selected, primary_brightness, primary_masks = _primary_fit(
        pose_output, pose_payload, method=method
    )
    (output / "primary-wireframe.json").write_text(
        json.dumps(primary, indent=2, allow_nan=False) + "\n"
    )
    if primary.get("scaffold") is None:
        failure_qc = _write_primary_failure_qc(
            selected, primary_brightness, primary_masks, output
        )
        summary = {
            "schema_version": SCHEMA,
            "certificate": certificate,
            "frozen_method": validation.frozen_method_record(method),
            "status": "unavailable",
            "reason": primary.get("reason"),
            "primary_result_status": primary.get("status"),
            "semantic_gauge_id": primary.get("semantic_gauge_id"),
            "selected_source_indices": [
                row.get("source_index") for row in selected
            ],
            "selected_positions": [
                row.get("position") for row in selected
            ],
            "partial_step_controls": primary.get(
                "partial_step_controls", {}
            ),
            "primary_failure_qc_path": failure_qc,
            "interpretation": (
                "The frozen #75 primary estimator failed on this retained "
                "stone. #89 preserves the failure and does not tune or invent "
                "a transfer scaffold."
            ),
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
        return summary

    stability = _leave_one_out(
        pose_output,
        selected,
        primary,
        primary.get("semantic_gauge_id"),
        benchmark_manifest,
        certificate,
        output / "stability",
        method=method,
    )
    transfer, render_items = _run_transfer(
        pose_output,
        pose_payload,
        primary,
        selected,
        output,
    )
    transfer_qc = _write_transfer_qc(
        render_items, primary["scaffold"], output
    )
    stability_qc = _write_stability_qc(
        primary, stability, output
    )

    if stability["status"] == "unavailable":
        status = "review"
        reasons = ["estimator_stability_contains_unavailable_subset"]
    elif transfer["wrap_check"]["missing_gauge_count"]:
        status = "review"
        reasons = ["transfer_contains_missing_gauge"]
    elif transfer["semantic_identity_swap_count"]:
        status = "unavailable"
        reasons = ["semantic_identity_swap_detected"]
    else:
        status = "ok" if stability["status"] == "ok" else "review"
        reasons = (
            []
            if status == "ok"
            else ["estimator_stability_requires_review"]
        )

    summary = {
        "schema_version": SCHEMA,
        "certificate": certificate,
        "status": status,
        "reasons": reasons,
        "frozen_method": validation.frozen_method_record(method),
        "primary": {
            "status": primary.get("status"),
            "semantic_gauge_id": primary.get("semantic_gauge_id"),
            "selected_source_indices": [
                row.get("source_index") for row in selected
            ],
            "selected_positions": [
                row.get("position") for row in selected
            ],
        },
        "estimator_stability": {
            key: value
            for key, value in stability.items()
            if key != "runs"
        },
        "fixed_ruler_transfer": {
            key: value
            for key, value in transfer.items()
            if key != "frames"
        },
        "stability_qc_path": stability_qc,
        "transfer_qc_path": transfer_qc,
        "interpretation": (
            "Estimator-stability dispersion and fixed-ruler support are "
            "reported separately. Numeric displacement remains descriptive "
            "under the frozen #88 contract."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    return summary


def run_source_benchmark(
    source_root, output, bundle_manifest, *, method=validation.OUTER_METHOD
):
    validation.assert_frozen_method(method)
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output.mkdir(parents=True, exist_ok=True)
    stones = []

    with tempfile.TemporaryDirectory(
        prefix="sparkles-asscher-stability-"
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = item["certificate"]
            source = source_root / certificate
            processed = work / certificate / "processed"
            pose_output = work / certificate / "pose"
            source_manifest = Path(item["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest = Path.cwd() / source_manifest

            pipeline.run(
                source,
                processed,
                source_manifest,
                gain=1.0,
                accept_review=True,
            )
            analyse_processed_sequence(
                processed,
                pose_output,
                persist_canonical=True,
            )
            stones.append(run_stone(
                pose_output,
                output / "per-stone" / certificate,
                manifest,
                certificate=certificate,
                method=method,
            ))

    payload = {
        "schema_version": SCHEMA,
        "stability_policy": STABILITY_POLICY,
        "transfer_policy": TRANSFER_POLICY,
        "metric_contract": validation.SCHEMA,
        "frozen_method": validation.frozen_method_record(method),
        "benchmark_inputs": validation.assert_frozen_benchmark_manifest(
            manifest
        ),
        "stone_count": len(stones),
        "stones": stones,
        "interpretation": (
            "No per-stone tuning and no numeric displacement acceptance "
            "threshold. Stability and transfer failures are preserved."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen #75 estimator stability and fixed-ruler transfer "
            "validation on the retained Asscher benchmark rotations"
        )
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=Path("docs/360/benchmark/source-bundles.json"),
    )
    parser.add_argument(
        "--method", choices=(validation.LEGACY_METHOD, validation.OUTER_METHOD,
                   validation.WINDOW_METHOD),
        default=validation.OUTER_METHOD,
    )
    args = parser.parse_args()
    result = run_source_benchmark(
        args.source_root,
        args.output,
        args.bundle_manifest,
        method=args.method,
    )
    for stone in result["stones"]:
        stability = stone.get("estimator_stability", {})
        transfer = stone.get("fixed_ruler_transfer", {})
        print(stone["certificate"], stone["status"])
        print(
            "  stability max tier fraction:",
            stability.get("max_boundary_displacement_tier_fraction"),
        )
        print(
            "  transfer:",
            transfer.get("status_counts"),
            "wrap:",
            transfer.get("wrap_check", {}).get(
                "last_to_zero_wrap_exercised"
            ),
        )


if __name__ == "__main__":
    main()
