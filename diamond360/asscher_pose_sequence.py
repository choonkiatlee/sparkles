"""Run Asscher pose selection on an existing processed diamond360 sequence."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import asscher_pose, normalized_geometry, qc
from .geometry import fit_asscher_outline

SEQUENCE_SCHEMA = "diamond360-asscher-pose-sequence/1"


def _load_mask(path):
    return np.asarray(Image.open(path).convert("L")) > 0


def _load_registered_arrays(processed, record):
    with np.load(processed / record["photometry_path"]) as data:
        brightness = np.asarray(data["encoded_brightness"], float).copy()
        valid = np.asarray(data["valid_mask"], bool).copy()
    mask = _load_mask(processed / record["registration"]["mask_path"])
    return brightness, mask, valid


def _failed_record(record, reason):
    return {
        "source_index": record.get("source_index"),
        "position": record.get("position"),
        "name": record.get("name"),
        "assessment": {
            "schema_version": asscher_pose.SCHEMA,
            "status": "failed",
            "score": 0.0,
            "reasons": [reason],
            "components": {},
            "outline": None,
        },
        "canonical": None,
    }


def _canonical_record(processed, output, record, assessment, persist=True):
    brightness, registered_mask, valid = _load_registered_arrays(
        processed, record
    )
    registered_outline = fit_asscher_outline(registered_mask)
    normalized = normalized_geometry.normalize_frame(
        brightness,
        registered_mask,
        valid,
        centre_xy=registered_outline["centre_xy"],
        rotation_deg=registered_outline["orientation_deg_mod_90"],
    )

    registered_to_canonical = np.asarray(
        normalized["transform"]["source_to_canonical_xy"],
        float,
    )
    camera_to_registered = np.asarray(
        record["registration"]["camera_to_diamond"],
        float,
    )
    if camera_to_registered.shape != (3, 3):
        raise ValueError("registration camera_to_diamond must be 3x3")
    camera_to_canonical = registered_to_canonical @ camera_to_registered
    canonical_to_camera = np.linalg.inv(camera_to_canonical)

    stem = f'{int(record["position"]):04d}'
    canonical_path = Path("canonical") / f"{stem}.npz"
    if persist:
        np.savez_compressed(
            output / canonical_path,
            brightness=normalized["brightness"],
            mask=normalized["mask"],
            valid_mask=normalized["valid_mask"],
        )

    return {
        "path": canonical_path.as_posix() if persist else None,
        "registered_outline": registered_outline,
        "registered_to_canonical_xy": registered_to_canonical.tolist(),
        "camera_to_canonical_xy": camera_to_canonical.tolist(),
        "canonical_to_camera_xy": canonical_to_camera.tolist(),
        "normalization": {
            **normalized["transform"],
            "pose_schema_version": asscher_pose.SCHEMA,
            "orientation_period_deg": 90,
            "quarter_turn_ambiguous": bool(
                registered_outline["quarter_turn_ambiguous"]
            ),
            "rectification": "none",
        },
        "support_provenance": {
            "source_segmentation_mask": record["segmentation"]["mask_path"],
            "registered_mask": record["registration"]["mask_path"],
            "registered_valid_mask": record["registration"]["valid_mask_path"],
            "photometry": record["photometry_path"],
        },
    }



def _circular_distance(a, b, size):
    delta = abs(int(a) - int(b)) % int(size)
    return min(delta, int(size) - delta)


def _circular_window(values, centre, radius):
    size = len(values)
    return [
        values[(int(centre) + offset) % size]
        for offset in range(-int(radius), int(radius) + 1)
    ]


def _face_metric(assessment):
    cues = assessment.get("face_orientation_cues") or {}
    value = cues.get("table_boundary_continuity_score")
    if value is None:
        value = cues.get("central_ring_edge_score")
    return None if value is None else float(value)


def resolve_face_lobes(records, *, sequence_complete):
    """Resolve competing face-on lobes without using source-index labels.

    Geometry finds broad face-on candidates first.  Only when two broad
    geometric peaks are genuinely competitive does the optical table-boundary
    diagnostic choose which lobe is *likely* crown-facing.  The opposite lobe
    is never reclassified as a geometry failure.
    """
    size = len(records)
    unavailable = {
        "status": "unavailable",
        "reason": "requires_complete_ordered_sequence",
    }
    if not sequence_complete or size < 16:
        return unavailable

    positions = [record.get("position") for record in records]
    if positions != list(range(size)):
        return {
            "status": "unavailable",
            "reason": "requires_contiguous_sequence_positions",
        }

    geometry_scores = np.array(
        [
            float(record["assessment"].get("score", 0.0))
            if record["assessment"].get("status") != "failed"
            else 0.0
            for record in records
        ],
        dtype=float,
    )
    smooth_radius = max(2, int(round(size / 32.0)))
    smoothed = np.array(
        [
            np.mean(_circular_window(geometry_scores, index, smooth_radius))
            for index in range(size)
        ],
        dtype=float,
    )

    primary = int(np.argmax(smoothed))
    minimum_separation = max(2, int(round(size / 4.0)))
    candidate_indices = [
        index
        for index in range(size)
        if _circular_distance(index, primary, size) >= minimum_separation
    ]
    if not candidate_indices:
        return {
            "status": "unavailable",
            "reason": "no_separated_competing_lobe",
        }
    secondary = max(candidate_indices, key=lambda index: smoothed[index])
    primary_score = float(smoothed[primary])
    secondary_score = float(smoothed[secondary])
    gap = float(primary_score - secondary_score)

    lobe_radius = max(smooth_radius, int(round(size / 8.0)))

    def lobe_summary(position):
        members = [
            index
            for index in range(size)
            if _circular_distance(index, position, size) <= smooth_radius
        ]
        face_values = [
            _face_metric(records[index]["assessment"])
            for index in members
        ]
        face_values = np.asarray(
            [value for value in face_values if value is not None],
            dtype=float,
        )
        if not len(face_values):
            median = mad = None
        else:
            median = float(np.median(face_values))
            mad = float(np.median(np.abs(face_values - median)))
        return {
            "peak_position": int(position),
            "peak_source_index": records[position].get("source_index"),
            "smoothed_geometry_score": float(smoothed[position]),
            "table_boundary_median": median,
            "table_boundary_mad": mad,
            "window_radius_frames": int(smooth_radius),
        }

    first = lobe_summary(primary)
    second = lobe_summary(secondary)
    result = {
        "status": "not_needed",
        "reason": "one_geometric_lobe_clearly_better",
        "geometry_peak_gap": gap,
        "competitive_gap_threshold": 0.10,
        "lobe_radius_frames": int(lobe_radius),
        "lobes": [first, second],
        "likely_crown_peak_position": None,
        "likely_opposite_peak_position": None,
        "confidence_mad_units": None,
    }
    if gap > 0.10:
        return result

    if (
        first["table_boundary_median"] is None
        or second["table_boundary_median"] is None
    ):
        result.update(
            status="ambiguous",
            reason="table_boundary_metric_unavailable",
        )
        return result

    difference = float(
        first["table_boundary_median"]
        - second["table_boundary_median"]
    )
    noise = max(
        float(first["table_boundary_mad"] or 0.0),
        float(second["table_boundary_mad"] or 0.0),
        0.005,
    )
    confidence = float(abs(difference) / noise)
    result["table_boundary_difference"] = difference
    result["confidence_mad_units"] = confidence
    result["minimum_confidence_mad_units"] = 1.5
    if confidence < 1.5:
        result.update(
            status="ambiguous",
            reason="competing_face_lobes_not_optically_separated",
        )
        return result

    if difference > 0:
        crown, opposite = primary, secondary
    else:
        crown, opposite = secondary, primary
    result.update(
        status="resolved",
        reason="closed_table_boundary_prefers_one_competing_face_on_lobe",
        likely_crown_peak_position=int(crown),
        likely_crown_peak_source_index=records[crown].get("source_index"),
        likely_opposite_peak_position=int(opposite),
        likely_opposite_peak_source_index=records[opposite].get("source_index"),
    )
    return result


def _annotate_face_roles(records, face_selection):
    for record in records:
        record["face_role"] = "unresolved"
    if face_selection.get("status") != "resolved":
        return
    size = len(records)
    radius = int(face_selection["lobe_radius_frames"])
    crown = int(face_selection["likely_crown_peak_position"])
    opposite = int(face_selection["likely_opposite_peak_position"])
    for record in records:
        position = int(record["position"])
        crown_distance = _circular_distance(position, crown, size)
        opposite_distance = _circular_distance(position, opposite, size)
        if crown_distance <= radius and crown_distance <= opposite_distance:
            record["face_role"] = "likely_crown_lobe"
        elif opposite_distance <= radius:
            record["face_role"] = "likely_opposite_lobe"
        else:
            record["face_role"] = "outside_face_on_lobes"


def rank_sequence_records(records, face_selection):
    """Rank geometry-usable crown-lobe frames ahead of competing faces."""
    geometry_order = asscher_pose.rank_assessments(
        [record["assessment"] for record in records]
    )
    geometry_rank = {
        index: rank
        for rank, index in enumerate(geometry_order, start=1)
    }
    for index, rank in geometry_rank.items():
        records[index]["geometry_rank"] = rank

    if face_selection.get("status") != "resolved":
        return geometry_order

    role_order = {
        "likely_crown_lobe": 0,
        "outside_face_on_lobes": 1,
        "unresolved": 1,
        "likely_opposite_lobe": 2,
    }
    status_order = {
        "ok": 0,
        "review": 1,
        "rejected": 2,
        "failed": 3,
    }

    def key(index):
        assessment = records[index]["assessment"]
        status = assessment.get("status", "failed")
        hard_failure = 1 if status in ("rejected", "failed") else 0
        return (
            hard_failure,
            role_order.get(records[index].get("face_role"), 1),
            status_order.get(status, 4),
            -float(assessment.get("score", 0.0)),
            int(records[index].get("position", index)),
        )

    return sorted(range(len(records)), key=key)


def _qc_indices(records, ranked, limit=6):
    usable = [
        index
        for index in ranked
        if records[index]["assessment"]["status"] in ("ok", "review")
    ][:4]
    rejected = [
        index
        for index in ranked
        if records[index]["assessment"]["status"] in ("rejected", "failed")
    ][:2]
    chosen = usable + rejected
    return chosen[:limit]


def _write_qc(processed, output, records, ranked):
    items = []
    for index in _qc_indices(records, ranked):
        result = records[index]
        source_index = result["source_index"]
        status = result["assessment"]["status"]
        score = result["assessment"]["score"]
        source_path = result.get("source_camera_path")
        if source_path:
            rgb = np.asarray(Image.open(processed / source_path).convert("RGB"))
            items.append(
                (
                    f"{source_index} {status} {score:.2f} source",
                    qc.asscher_pose_overlay(rgb, result["assessment"]),
                )
            )
        canonical = result.get("canonical")
        if canonical is not None and canonical.get("path"):
            with np.load(output / canonical["path"]) as data:
                brightness = np.asarray(data["brightness"], float)
            grey = np.rint(np.clip(brightness, 0.0, 1.0) * 255).astype(np.uint8)
            rgb = np.repeat(grey[:, :, None], 3, axis=2)
            items.append(
                (
                    f"{source_index} canonical",
                    Image.fromarray(rgb),
                )
            )
    if items:
        qc.contact_sheet(
            items,
            output / "asscher-pose-qc.jpg",
            columns=4,
        )
        return "asscher-pose-qc.jpg"
    return None


def analyse_processed_sequence(processed, output, *, persist_canonical=True):
    """Persist ranked pose records and optional canonical support for one processed run."""
    processed = Path(processed).resolve()
    output = Path(output).resolve()
    if processed == output or processed in output.parents or output in processed.parents:
        raise ValueError("processed input and pose output must be disjoint")
    if not (processed / "sequence.json").is_file():
        raise ValueError("processed input must contain sequence.json")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("pose output must be a new or empty directory")

    metadata = json.loads((processed / "sequence.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    if persist_canonical:
        (output / "canonical").mkdir(exist_ok=True)

    records = []
    for record in metadata.get("frames", []):
        if (
            record.get("status") != "valid"
            or "segmentation" not in record
            or "registration" not in record
            or "photometry_path" not in record
        ):
            records.append(_failed_record(record, "upstream_geometry_unavailable"))
            continue

        source_mask_path = record["segmentation"].get("mask_path")
        if not source_mask_path:
            records.append(_failed_record(record, "source_mask_unavailable"))
            continue

        source_mask = _load_mask(processed / source_mask_path)
        _, registered_mask, valid = _load_registered_arrays(processed, record)
        valid_fraction = float(
            (registered_mask & valid).sum() / max(1, registered_mask.sum())
        )
        assessment = asscher_pose.assess_frame(
            source_mask,
            valid_fraction=valid_fraction,
        )
        source_camera_path = record.get("camera_original_path")
        if assessment["status"] != "failed" and source_camera_path:
            source_rgb = np.asarray(
                Image.open(processed / source_camera_path).convert("RGB"),
                dtype=float,
            ) / 255.0
            source_brightness = (
                source_rgb
                @ np.array([0.2126, 0.7152, 0.0722], dtype=float)
            )
            assessment["face_orientation_cues"] = (
                asscher_pose.face_orientation_cues(
                    source_brightness,
                    source_mask,
                    assessment["outline"],
                )
            )

        result = {
            "source_index": record.get("source_index"),
            "position": record.get("position"),
            "name": record.get("name"),
            "source_camera_path": source_camera_path,
            "assessment": assessment,
            "canonical": None,
        }
        if assessment["status"] != "failed":
            result["canonical"] = _canonical_record(
                processed,
                output,
                record,
                assessment,
                persist=persist_canonical,
            )
        records.append(result)

    source_manifest = metadata.get("source_manifest") or {}
    sequence_complete = bool(source_manifest.get("sequence_complete"))
    face_selection = resolve_face_lobes(
        records,
        sequence_complete=sequence_complete,
    )
    _annotate_face_roles(records, face_selection)
    ranked = rank_sequence_records(records, face_selection)
    for rank, index in enumerate(ranked, start=1):
        records[index]["rank"] = rank

    qc_path = _write_qc(processed, output, records, ranked)
    payload = {
        "schema_version": SEQUENCE_SCHEMA,
        "pose_specification": asscher_pose.specification(),
        "source_sequence_schema": metadata.get("schema_version"),
        "frame_count": len(records),
        "usable_count": sum(
            record["assessment"]["status"] in ("ok", "review")
            for record in records
        ),
        "face_selection": face_selection,
        "ranking": [
            {
                "rank": rank,
                "geometry_rank": records[index].get("geometry_rank"),
                "source_index": records[index]["source_index"],
                "status": records[index]["assessment"]["status"],
                "score": records[index]["assessment"]["score"],
                "face_role": records[index].get("face_role"),
            }
            for rank, index in enumerate(ranked, start=1)
        ],
        "frames": records,
        "qc_path": qc_path,
        "canonical_arrays_persisted": bool(persist_canonical),
        "interpretation": (
            "Ranks image-plane geometry suitability for semantic wireframe fitting. "
            "On complete ordered rotations with two competitive face-on lobes, "
            "closed-table evidence may mark one lobe as likely crown-facing and "
            "demote the likely opposite face without calling it a geometry failure. "
            "Does not estimate physical facet angles or physical facet lengths."
        ),
    }
    (output / "asscher-pose.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload
