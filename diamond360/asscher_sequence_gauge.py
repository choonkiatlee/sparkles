"""Stable sequence phase and semantic orientation gauge for Asscher rotations.

This module consumes the image-plane pose evidence produced by #73.  It does
not estimate a physical camera angle.  A phase is emitted only when the source
manifest explicitly declares a uniformly sampled cyclic viewer sequence.
"""
from __future__ import annotations

import math

import numpy as np

SCHEMA = "diamond360-asscher-sequence-gauge/1"
UNIFORM_CYCLIC_KIND = "uniform_cyclic_viewer_phase"


def _wrap_0_period(value, period):
    return float(float(value) % float(period))


def _wrap_signed(value, period):
    period = float(period)
    wrapped = (float(value) + period / 2.0) % period - period / 2.0
    # Keep the half-period endpoint deterministic.
    if math.isclose(wrapped, -period / 2.0, abs_tol=1e-12):
        return float(-period / 2.0)
    return float(wrapped)


def _circular_difference_deg(a, b):
    return abs(_wrap_signed(float(b) - float(a), 360.0))


def _phase_reference(face_selection):
    if face_selection.get("status") == "resolved":
        position = face_selection.get("likely_crown_peak_position")
        if position is not None:
            return {
                "position": int(position),
                "source_index": face_selection.get(
                    "likely_crown_peak_source_index"
                ),
                "role": "likely_crown_lobe",
                "provenance": (
                    "asscher_pose_sequence.face_selection."
                    "likely_crown_peak_position"
                ),
                "status": "available",
            }

    lobes = face_selection.get("lobes") or []
    if lobes and lobes[0].get("peak_position") is not None:
        return {
            "position": int(lobes[0]["peak_position"]),
            "source_index": lobes[0].get("peak_source_index"),
            "role": "best_face_on_geometry_lobe",
            "provenance": (
                "asscher_pose_sequence.face_selection.lobes[0].peak_position"
            ),
            "status": "review",
        }
    return None


def _unavailable_phase(reason):
    return {
        "status": "unavailable",
        "reason": reason,
        "coordinate": "observed_sequence_phase",
        "physical_camera_angle_calibrated": False,
        "interpretation": (
            "No angular coordinate is invented when cyclic sampling/order is "
            "not explicitly supported by source provenance."
        ),
    }


def build_phase(
    records,
    source_manifest,
    face_selection,
    *,
    direction_sign=1,
):
    """Return a declared viewer-phase model and per-record phase coordinates."""
    if direction_sign not in (-1, 1):
        raise ValueError("direction_sign must be +1 or -1")

    sampling = source_manifest.get("sequence_sampling")
    if not isinstance(sampling, dict):
        model = _unavailable_phase("sequence_sampling_contract_missing")
        return model, [{} for _ in records]
    if sampling.get("kind") != UNIFORM_CYCLIC_KIND:
        model = _unavailable_phase("sequence_sampling_not_uniform_cyclic")
        return model, [{} for _ in records]
    if source_manifest.get("sequence_complete") is not True:
        model = _unavailable_phase("complete_cycle_not_proven")
        return model, [{} for _ in records]

    period_frames = sampling.get("period_frames")
    if type(period_frames) is not int or period_frames <= 1:
        model = _unavailable_phase("invalid_sampling_period_frames")
        return model, [{} for _ in records]

    positions = [record.get("position") for record in records]
    if (
        len(records) != period_frames
        or positions != list(range(period_frames))
    ):
        model = _unavailable_phase(
            "records_do_not_cover_declared_uniform_cycle"
        )
        return model, [{} for _ in records]

    cycle_deg = sampling.get("nominal_cycle_deg")
    if (
        not isinstance(cycle_deg, (int, float))
        or not np.isfinite(cycle_deg)
        or float(cycle_deg) <= 0
    ):
        model = _unavailable_phase("invalid_nominal_cycle_degrees")
        return model, [{} for _ in records]
    cycle_deg = float(cycle_deg)

    reference = _phase_reference(face_selection)
    if reference is None:
        model = _unavailable_phase("crown_view_reference_unavailable")
        return model, [{} for _ in records]

    reference_position = int(reference["position"])
    if not 0 <= reference_position < period_frames:
        model = _unavailable_phase("phase_reference_outside_cycle")
        return model, [{} for _ in records]

    step_deg = cycle_deg / period_frames
    per_frame = []
    for record in records:
        position = int(record["position"])
        forward_frames = (position - reference_position) % period_frames
        unwrapped = direction_sign * forward_frames * step_deg
        phase_0_cycle = _wrap_0_period(unwrapped, cycle_deg)
        signed = _wrap_signed(phase_0_cycle, cycle_deg)
        per_frame.append(
            {
                "phase_status": reference["status"],
                "rotation_phase_deg": signed,
                "rotation_phase_0_360_deg": phase_0_cycle,
                "rotation_phase_unwrapped_from_reference_deg": float(
                    unwrapped
                ),
                "phase_source": "declared_uniform_cyclic_viewer_sequence",
                "phase_validity": (
                    "approximate_observed_sequence_phase_not_physical_angle"
                ),
                "phase_reference_offset_frames": int(forward_frames),
            }
        )

    model = {
        "status": reference["status"],
        "coordinate": "observed_sequence_phase",
        "period_deg": cycle_deg,
        "nominal_step_deg": float(step_deg),
        "reference_position": reference_position,
        "reference_source_index": reference.get("source_index"),
        "reference_role": reference["role"],
        "reference_provenance": reference["provenance"],
        "direction_sign": int(direction_sign),
        "direction_convention": (
            "increasing source position"
            if direction_sign == 1
            else "decreasing source position"
        ),
        "physical_rotation_direction_known": False,
        "sampling": sampling,
        "physical_camera_angle_calibrated": bool(
            sampling.get("physical_angle_calibrated", False)
        ),
        "wrap": "[0, period) plus signed [-period/2, period/2)",
        "interpretation": (
            "Approximate observed viewer-sequence phase from a declared "
            "uniform cyclic sampling contract; not a calibrated physical "
            "camera or stone rotation angle."
        ),
    }
    return model, per_frame


def _orientation_observation(record):
    canonical = record.get("canonical")
    if not isinstance(canonical, dict):
        return None
    outline = canonical.get("registered_outline") or {}
    value = outline.get("orientation_deg_mod_90")
    if not isinstance(value, (int, float)) or not np.isfinite(value):
        return None
    return float(value) % 90.0


def _quarter_turn_matrix(degrees, canvas_size):
    centre = (float(canvas_size) - 1.0) / 2.0
    angle = math.radians(float(degrees))
    cosine, sine = math.cos(angle), math.sin(angle)
    linear = np.array(
        [[cosine, -sine], [sine, cosine]],
        dtype=float,
    )
    centre_xy = np.array([centre, centre], dtype=float)
    translation = centre_xy - linear @ centre_xy
    matrix = np.eye(3, dtype=float)
    matrix[:2, :2] = linear
    matrix[:2, 2] = translation
    return matrix


def _gauge_reference_index(records, preferred_position, observations):
    by_position = {
        int(records[index]["position"]): index
        for index in observations
        if records[index].get("position") is not None
    }
    if preferred_position in by_position:
        return by_position[preferred_position], "phase_reference"

    usable = [
        index
        for index in observations
        if records[index].get("assessment", {}).get("status")
        in ("ok", "review")
    ]
    if usable:
        index = min(
            usable,
            key=lambda item: (
                int(records[item].get("rank", 10**9)),
                int(records[item].get("position", item)),
            ),
        )
        return index, "best_ranked_usable_pose"
    index = min(
        observations,
        key=lambda item: int(records[item].get("position", item)),
    )
    return index, "first_available_pose"


def _branch_assignment(
    records,
    observation_indices,
    anchor_index,
    *,
    cyclic,
    reference_quarter_turn,
):
    """Choose quarter-turn branches by minimum sequence discontinuity."""
    if reference_quarter_turn not in (0, 1, 2, 3):
        raise ValueError("reference_quarter_turn must be 0, 1, 2 or 3")

    ordered = sorted(
        observation_indices,
        key=lambda index: int(records[index]["position"]),
    )
    if cyclic:
        anchor_at = ordered.index(anchor_index)
        ordered = ordered[anchor_at:] + ordered[:anchor_at]
    else:
        # On an incomplete sequence do not invent a wrap edge.
        anchor_index = ordered[0]

    theta = {
        index: _orientation_observation(records[index])
        for index in ordered
    }
    states = range(4)
    infinity = float("inf")
    costs = {
        state: (0.0 if state == reference_quarter_turn else infinity)
        for state in states
    }
    parents = []

    for previous_index, index in zip(ordered[:-1], ordered[1:]):
        next_costs = {}
        next_parents = {}
        for state in states:
            candidate = theta[index] + 90.0 * state
            choices = []
            for previous_state in states:
                previous_candidate = (
                    theta[previous_index] + 90.0 * previous_state
                )
                jump = _circular_difference_deg(
                    previous_candidate,
                    candidate,
                )
                choices.append(
                    (
                        costs[previous_state] + jump * jump,
                        previous_state,
                    )
                )
            best_cost, best_parent = min(choices)
            next_costs[state] = best_cost
            next_parents[state] = best_parent
        costs = next_costs
        parents.append(next_parents)

    if cyclic and len(ordered) > 1:
        anchor_theta = theta[ordered[0]] + 90.0 * reference_quarter_turn
        final_choices = []
        for state in states:
            final_theta = theta[ordered[-1]] + 90.0 * state
            closure = _circular_difference_deg(final_theta, anchor_theta)
            final_choices.append((costs[state] + closure * closure, state))
        objective, final_state = min(final_choices)
    else:
        objective, final_state = min((costs[state], state) for state in states)

    assignments = {ordered[-1]: final_state}
    state = final_state
    for step in range(len(ordered) - 2, -1, -1):
        parent_map = parents[step]
        state = parent_map[state]
        assignments[ordered[step]] = state

    return assignments, float(objective), ordered, anchor_index


def _unavailable_gauge(reason):
    return {
        "status": "unavailable",
        "reason": reason,
        "orientation_period_deg": 90.0,
        "physically_unique": False,
        "equivalent_global_quarter_turns": [0, 1, 2, 3],
    }


def build_orientation_gauge(
    records,
    phase_model,
    source_manifest,
    *,
    reference_quarter_turn=0,
):
    """Resolve #73's per-frame mod-90 pose into one stable sequence gauge."""
    observation_indices = [
        index
        for index, record in enumerate(records)
        if _orientation_observation(record) is not None
    ]
    if not observation_indices:
        model = _unavailable_gauge("no_pose_orientation_observations")
        return model, [{} for _ in records]

    preferred_position = phase_model.get("reference_position")
    anchor_index, anchor_source = _gauge_reference_index(
        records,
        preferred_position,
        observation_indices,
    )
    sequence_complete = bool(source_manifest.get("sequence_complete"))
    assignments, objective, ordered, effective_anchor = _branch_assignment(
        records,
        observation_indices,
        anchor_index,
        cyclic=sequence_complete,
        reference_quarter_turn=reference_quarter_turn,
    )
    anchor_record = records[effective_anchor]

    per_frame = [{} for _ in records]
    jumps = []
    previous_angle = None
    for index in ordered:
        record = records[index]
        branch = int(assignments[index])
        observed_mod90 = _orientation_observation(record)
        selected_deg = _wrap_0_period(
            observed_mod90 + 90.0 * branch,
            360.0,
        )
        if previous_angle is not None:
            jumps.append(
                _circular_difference_deg(previous_angle, selected_deg)
            )
        previous_angle = selected_deg

        coordinate = {
            "gauge_status": (
                "available"
                if record.get("assessment", {}).get("status")
                in ("ok", "review")
                else "review"
            ),
            "gauge_quarter_turn": branch,
            "orientation_deg_mod_90": float(observed_mod90),
            "selected_orientation_branch_deg": selected_deg,
            "gauge_rotation_applied_deg": float(-90.0 * branch),
            "gauge_branch_provenance": (
                "sequence_continuity_from_usable_pose"
                if record.get("assessment", {}).get("status")
                in ("ok", "review")
                else "sequence_continuity_from_low_suitability_pose"
            ),
        }

        canonical = record.get("canonical") or {}
        normalization = canonical.get("normalization") or {}
        canvas_size = normalization.get("canvas_size_px")
        camera_to_canonical = canonical.get("camera_to_canonical_xy")
        if (
            type(canvas_size) is int
            and canvas_size > 0
            and camera_to_canonical is not None
        ):
            camera_to_canonical = np.asarray(
                camera_to_canonical,
                dtype=float,
            )
            if camera_to_canonical.shape == (3, 3):
                canonical_to_gauge = _quarter_turn_matrix(
                    -90.0 * branch,
                    canvas_size,
                )
                camera_to_gauge = (
                    canonical_to_gauge @ camera_to_canonical
                )
                coordinate.update(
                    canonical_to_sequence_gauge_xy=(
                        canonical_to_gauge.tolist()
                    ),
                    sequence_gauge_to_canonical_xy=(
                        np.linalg.inv(canonical_to_gauge).tolist()
                    ),
                    camera_to_sequence_gauge_xy=(
                        camera_to_gauge.tolist()
                    ),
                    sequence_gauge_to_camera_xy=(
                        np.linalg.inv(camera_to_gauge).tolist()
                    ),
                )
        per_frame[index] = coordinate

    if sequence_complete and len(ordered) > 1:
        first_angle = per_frame[ordered[0]][
            "selected_orientation_branch_deg"
        ]
        last_angle = per_frame[ordered[-1]][
            "selected_orientation_branch_deg"
        ]
        closure_jump = _circular_difference_deg(last_angle, first_angle)
    else:
        closure_jump = None

    status = (
        "available"
        if len(observation_indices) >= 2 and sequence_complete
        else "review"
    )
    model = {
        "status": status,
        "reference_position": anchor_record.get("position"),
        "reference_source_index": anchor_record.get("source_index"),
        "reference_provenance": anchor_source,
        "selected_reference_quarter_turn": int(reference_quarter_turn),
        "selection": (
            "minimum squared circular orientation discontinuity over "
            "quarter-turn branches"
        ),
        "cyclic_closure_in_objective": bool(sequence_complete),
        "orientation_period_deg": 90.0,
        "physically_unique": False,
        "physical_compass_claim": "none",
        "equivalent_global_quarter_turns": [0, 1, 2, 3],
        "observation_count": len(observation_indices),
        "objective": float(objective),
        "maximum_neighbor_branch_jump_deg": (
            None if not jumps else float(max(jumps))
        ),
        "closure_jump_deg": closure_jump,
        "interpretation": (
            "N/E/S/W is a deterministic sequence gauge. A global 90-degree "
            "rotation is geometrically equivalent unless independent source "
            "evidence establishes an absolute orientation."
        ),
    }
    return model, per_frame


def build_sequence_coordinates(
    records,
    source_manifest,
    face_selection,
    *,
    direction_sign=1,
    reference_quarter_turn=0,
):
    """Build the #80 sequence coordinate contract without mutating #73 data."""
    phase, phase_frames = build_phase(
        records,
        source_manifest,
        face_selection,
        direction_sign=direction_sign,
    )
    gauge, gauge_frames = build_orientation_gauge(
        records,
        phase,
        source_manifest,
        reference_quarter_turn=reference_quarter_turn,
    )

    frames = []
    for index, record in enumerate(records):
        coordinate = {
            "source_index": record.get("source_index"),
            "position": record.get("position"),
            "face_role": record.get("face_role"),
            **phase_frames[index],
            **gauge_frames[index],
        }
        if "phase_status" not in coordinate:
            coordinate.update(
                phase_status="unavailable",
                rotation_phase_deg=None,
                rotation_phase_0_360_deg=None,
                phase_source=None,
                phase_validity=None,
            )
        if "gauge_status" not in coordinate:
            coordinate.update(
                gauge_status="unavailable",
                gauge_quarter_turn=None,
                gauge_rotation_applied_deg=None,
                camera_to_sequence_gauge_xy=None,
            )
        frames.append(coordinate)

    return {
        "schema_version": SCHEMA,
        "phase": phase,
        "orientation_gauge": gauge,
        "frames": frames,
        "interpretation": (
            "Sequence-level coordinate contract for stable semantic identity. "
            "Phase is observed viewer-sequence phase, not a calibrated "
            "physical camera angle; semantic orientation is conventional and "
            "retains explicit 90-degree equivalence."
        ),
    }
