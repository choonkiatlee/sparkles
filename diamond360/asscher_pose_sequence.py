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

        result = {
            "source_index": record.get("source_index"),
            "position": record.get("position"),
            "name": record.get("name"),
            "source_camera_path": record.get("camera_original_path"),
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

    ranked = asscher_pose.rank_assessments(
        [record["assessment"] for record in records]
    )
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
        "ranking": [
            {
                "rank": rank,
                "source_index": records[index]["source_index"],
                "status": records[index]["assessment"]["status"],
                "score": records[index]["assessment"]["score"],
            }
            for rank, index in enumerate(ranked, start=1)
        ],
        "frames": records,
        "qc_path": qc_path,
        "canonical_arrays_persisted": bool(persist_canonical),
        "interpretation": (
            "Ranks image-plane geometry suitability for semantic wireframe fitting; "
            "does not estimate physical facet angles or physical facet lengths."
        ),
    }
    (output / "asscher-pose.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload
