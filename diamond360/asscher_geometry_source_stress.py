"""Issue #90: controlled source-pipeline and poor-view geometry stress tests.

The source arm derives hash-valid perturbed source manifests, then runs the
ordinary ingestion -> segmentation -> registration -> pose -> frozen #75 path.
The poor-view arm holds one baseline ruler fixed and evaluates evidence as
viewer phase moves progressively farther from the geometry-support views.

No fitter parameters or validation thresholds are changed here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-geometry-source-stress/1"
PERTURBED_SOURCE_SCHEMA = "diamond360-controlled-source-perturbation/1"
POOR_VIEW_SCHEMA = "diamond360-asscher-poor-view-stress/1"

# Frozen before this issue's source-perturbation outcomes are inspected.
REPRESENTATIVE_CERTIFICATES = (
    "IGI-LG756520111",  # #89: comparatively stable primary estimator
    "IGI-LG836619414",  # #89: deliberately fragile/sensitive comparator
)

PERTURBATIONS = (
    {
        "id": "downsample-75pct-lanczos",
        "kind": "downsample_resample",
        "scale": 0.75,
        "resampler": "LANCZOS",
    },
    {
        "id": "gaussian-blur-0p7px",
        "kind": "gaussian_blur",
        "radius_px": 0.7,
    },
    {
        "id": "exposure-minus-5pct",
        "kind": "brightness",
        "factor": 0.95,
    },
    {
        "id": "exposure-plus-5pct",
        "kind": "brightness",
        "factor": 1.05,
    },
    {
        "id": "contrast-minus-10pct",
        "kind": "contrast",
        "factor": 0.90,
    },
    {
        "id": "contrast-plus-10pct",
        "kind": "contrast",
        "factor": 1.10,
    },
    {
        "id": "jpeg-quality-85-444",
        "kind": "jpeg_recompress",
        "quality": 85,
        "subsampling": 0,
    },
)

# Distance in viewer-frame steps to nearest primary geometry-support view.
# These are sequence-phase distances, not calibrated physical camera angles.
POOR_VIEW_DISTANCE_BINS = (
    (0, 4),
    (5, 8),
    (9, 16),
    (17, 32),
    (33, 64),
    (65, 96),
    (97, 128),
)


def perturbation_matrix():
    return deepcopy(list(PERTURBATIONS))


def stress_policy():
    return {
        "schema_version": SCHEMA,
        "representative_certificates": list(REPRESENTATIVE_CERTIFICATES),
        "perturbations": perturbation_matrix(),
        "source_policy": (
            "each condition is applied uniformly to every source frame in a "
            "representative sequence; non-JPEG conditions are serialized as "
            "lossless PNG so the named pixel transform is not confounded by "
            "an additional lossy re-encode"
        ),
        "estimator_policy": (
            "ordinary pipeline and frozen #75 estimator; no per-source or "
            "per-condition parameter changes"
        ),
        "comparison_policy": validation.metric_policy(),
        "poor_view_distance_bins_frames": [
            [int(lo), int(hi)] for lo, hi in POOR_VIEW_DISTANCE_BINS
        ],
        "physical_angle_claim": False,
        "quality_score": None,
    }


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    return _sha256_bytes(Path(path).read_bytes())


def _image_array(image):
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def apply_perturbation(image, spec):
    """Apply one deterministic, explicitly named source-pixel perturbation."""
    image = image.convert("RGB")
    kind = spec["kind"]
    if kind == "downsample_resample":
        scale = float(spec["scale"])
        if not 0.0 < scale < 1.0:
            raise ValueError("downsample scale must lie in (0, 1)")
        width, height = image.size
        small = image.resize(
            (
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
            ),
            Image.Resampling.LANCZOS,
        )
        return small.resize((width, height), Image.Resampling.LANCZOS)
    if kind == "gaussian_blur":
        radius = float(spec["radius_px"])
        if radius <= 0:
            raise ValueError("blur radius must be positive")
        return image.filter(ImageFilter.GaussianBlur(radius=radius))
    if kind == "brightness":
        factor = float(spec["factor"])
        if factor <= 0:
            raise ValueError("brightness factor must be positive")
        return ImageEnhance.Brightness(image).enhance(factor)
    if kind == "contrast":
        factor = float(spec["factor"])
        if factor <= 0:
            raise ValueError("contrast factor must be positive")
        return ImageEnhance.Contrast(image).enhance(factor)
    if kind == "jpeg_recompress":
        buffer = BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=int(spec["quality"]),
            subsampling=int(spec["subsampling"]),
            optimize=False,
            progressive=False,
        )
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            return decoded.convert("RGB").copy()
    raise ValueError(f"unsupported perturbation kind: {kind}")


def _write_perturbed_image(source_path, destination, spec):
    with Image.open(source_path) as image:
        transformed = apply_perturbation(image, spec)
        destination.parent.mkdir(parents=True, exist_ok=True)
        transformed.save(destination, format="PNG", compress_level=6)


def derive_perturbed_source(
    source_root,
    source_manifest,
    destination,
    spec,
):
    """Create a hash-valid derived sequence without mutating archived sources."""
    source_root = Path(source_root).resolve()
    destination = Path(destination).resolve()
    original = json.loads(Path(source_manifest).read_text())
    if original.get("schema_version") != "diamond360-source/1":
        raise ValueError("stress test requires diamond360-source/1 manifest")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("perturbed source destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)

    result = deepcopy(original)
    result["source_pipeline"] = (
        f"controlled-stress:{spec['id']} over {original.get('source_pipeline')}"
    )
    result["controlled_perturbation"] = {
        "schema_version": PERTURBED_SOURCE_SCHEMA,
        "specification": deepcopy(spec),
        "parent_manifest_canonical_sha256": validation.canonical_sha256(
            original
        ),
        "parent_certificate": original.get("certificate"),
        "ordering_and_source_indices_preserved": True,
    }

    derived_frames = []
    for frame in original.get("frames", []):
        relative = Path(frame["path"])
        source_path = source_root / relative
        derived_relative = relative.with_suffix(".png")
        destination_path = destination / derived_relative
        _write_perturbed_image(source_path, destination_path, spec)

        row = deepcopy(frame)
        row["path"] = derived_relative.as_posix()
        row["sha256"] = _sha256_file(destination_path)
        row["bytes"] = destination_path.stat().st_size
        row["stress_parent_path"] = frame["path"]
        row["stress_parent_sha256"] = frame["sha256"]
        derived_frames.append(row)

    result["frames"] = derived_frames
    manifest_path = destination / "source-manifest.json"
    manifest_path.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return manifest_path, result


def _process_sequence(source, source_manifest, processed, pose_output):
    pipeline.run(
        source,
        processed,
        source_manifest,
        gain=1.0,
        accept_review=True,
    )
    return analyse_processed_sequence(
        processed,
        pose_output,
        persist_canonical=True,
    )


def _primary_from_pose(pose_output, pose_payload):
    return stability._primary_fit(pose_output, pose_payload)


def _pose_lookup(payload):
    return {
        row.get("source_index"): row
        for row in payload.get("frames", [])
    }


def _mean_or_none(values):
    values = [float(value) for value in values if value is not None]
    return None if not values else float(np.mean(values))


def _median_or_none(values):
    values = [float(value) for value in values if value is not None]
    return None if not values else float(np.median(values))


def _support_summary(rows):
    """Aggregate fixed-ruler diagnostics across the same physical source views."""
    if not rows:
        return {
            "status": "unavailable",
            "frame_count": 0,
            "status_counts": {},
            "boundary_support_fraction": {},
            "boundary_median_residual_u": {},
            "entity_ok_fraction": {},
            "entity_mean_confidence": {},
        }

    boundary_ids = ("C1_C2", "C2_C3", "C3_TABLE")
    entity_ids = sorted(rows[0]["entities"])
    return {
        "status": "available",
        "frame_count": len(rows),
        "status_counts": dict(sorted(Counter(
            row["status"] for row in rows
        ).items())),
        "boundary_support_fraction": {
            boundary_id: _mean_or_none([
                row["boundary_support"][boundary_id]["support_fraction"]
                for row in rows
            ])
            for boundary_id in boundary_ids
        },
        "boundary_median_residual_u": {
            boundary_id: _median_or_none([
                diagnostic.get("residual_u")
                for row in rows
                for diagnostic in row["boundary_support"][boundary_id][
                    "sectors_step_order"
                ]
                if diagnostic.get("supported")
            ])
            for boundary_id in boundary_ids
        },
        "entity_ok_fraction": {
            semantic_id: float(np.mean([
                row["entities"][semantic_id]["status"] == "ok"
                for row in rows
            ]))
            for semantic_id in entity_ids
        },
        "entity_mean_confidence": {
            semantic_id: _mean_or_none([
                row["entities"][semantic_id]["confidence"]
                for row in rows
            ])
            for semantic_id in entity_ids
        },
    }


def _support_delta(reference, candidate):
    if (
        reference.get("status") != "available"
        or candidate.get("status") != "available"
    ):
        return {"status": "unavailable"}

    def deltas(field):
        keys = sorted(set(reference[field]) | set(candidate[field]))
        return {
            key: (
                None
                if reference[field].get(key) is None
                or candidate[field].get(key) is None
                else float(
                    candidate[field][key] - reference[field][key]
                )
            )
            for key in keys
        }

    return {
        "status": "available",
        "boundary_support_fraction_delta": deltas(
            "boundary_support_fraction"
        ),
        "boundary_median_residual_u_delta": deltas(
            "boundary_median_residual_u"
        ),
        "entity_ok_fraction_delta": deltas("entity_ok_fraction"),
        "entity_mean_confidence_delta": deltas(
            "entity_mean_confidence"
        ),
    }


def fixed_ruler_support_on_source_indices(
    pose_output,
    pose_payload,
    reference_primary,
    source_indices,
):
    """Evaluate reference ruler on specified source views in another pipeline run."""
    candidate_gauge = wireframe._gauge_id(pose_payload)
    reference_gauge = reference_primary.get("semantic_gauge_id")
    if candidate_gauge != reference_gauge:
        return {
            "status": "unavailable",
            "reason": "semantic_gauge_changed_under_source_perturbation",
            "reference_semantic_gauge_id": reference_gauge,
            "candidate_semantic_gauge_id": candidate_gauge,
            "frames": [],
            "summary": _support_summary([]),
        }

    lookup = _pose_lookup(pose_payload)
    rows = []
    sequence_size = len(pose_payload.get("frames", []))
    selected = set(source_indices)
    for source_index in source_indices:
        record = lookup.get(source_index)
        if record is None:
            continue
        canonical = record.get("canonical") or {}
        coordinate = record.get("sequence_coordinate") or {}
        if (
            not canonical.get("path")
            or coordinate.get("gauge_status") not in ("available", "review")
        ):
            continue
        brightness, mask, valid = stability._load_gauged_arrays(
            pose_output, record
        )
        u, evidence = wireframe.extract_sector_evidence(
            brightness, mask, valid
        )
        row = stability.transfer_fixed_ruler_frame(
            evidence,
            u,
            reference_primary,
            frame_metadata=stability._metadata(record),
            crown_peak_position=None,
            sequence_size=sequence_size,
            in_primary_fit=source_index in selected,
        )
        rows.append(row)

    return {
        "status": "available" if rows else "unavailable",
        "reason": None if rows else "reference_views_unavailable",
        "reference_semantic_gauge_id": reference_gauge,
        "candidate_semantic_gauge_id": candidate_gauge,
        "frames": rows,
        "summary": _support_summary(rows),
    }


def _primary_summary(result):
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "semantic_gauge_id": result.get("semantic_gauge_id"),
        "selected_source_indices": [
            row.get("source_index")
            for row in result.get("selected_frames", [])
        ],
        "selected_positions": [
            row.get("position")
            for row in result.get("selected_frames", [])
        ],
        "scaffold_validity": (
            None
            if result.get("scaffold") is None
            else result["scaffold"].get("validity")
        ),
    }


def _run_source_condition(
    *,
    certificate,
    spec,
    source,
    source_manifest,
    work,
    output,
    benchmark_manifest,
    reference_primary,
    reference_support,
):
    condition_id = spec["id"]
    condition_work = Path(work) / condition_id
    perturbed_source = condition_work / "source"
    perturbed_manifest_path, perturbed_manifest = derive_perturbed_source(
        source, source_manifest, perturbed_source, spec
    )
    processed = condition_work / "processed"
    pose_output = condition_work / "pose"
    pose_payload = _process_sequence(
        perturbed_source,
        perturbed_manifest_path,
        processed,
        pose_output,
    )
    candidate, selected, _, _ = _primary_from_pose(
        pose_output, pose_payload
    )

    validation_record = validation.build_validation_record(
        reference_primary,
        candidate,
        benchmark_manifest,
        case_id=f"{certificate}:{condition_id}",
        comparison_kind="source_pipeline_stress",
        run_metadata={
            "perturbation": deepcopy(spec),
            "derived_source_manifest_sha256": validation.canonical_sha256(
                perturbed_manifest
            ),
            "derived_from_certificate": certificate,
            "candidate_selected_source_indices": [
                row.get("source_index") for row in selected
            ],
        },
    )
    fixed_support = fixed_ruler_support_on_source_indices(
        pose_output,
        pose_payload,
        reference_primary,
        [
            row.get("source_index")
            for row in reference_primary.get("selected_frames", [])
        ],
    )
    validation_summary = stability.summarize_validation_record(
        validation_record
    )
    summary = {
        "condition_id": condition_id,
        "perturbation": deepcopy(spec),
        "derived_source_manifest_sha256": validation.canonical_sha256(
            perturbed_manifest
        ),
        "candidate_primary": _primary_summary(candidate),
        "geometry_comparison": validation_summary,
        "fixed_ruler_support": fixed_support["summary"],
        "fixed_ruler_support_delta_from_baseline": _support_delta(
            reference_support, fixed_support["summary"]
        ),
        "fixed_ruler_status": fixed_support["status"],
        "fixed_ruler_reason": fixed_support["reason"],
    }

    condition_output = Path(output) / "conditions" / condition_id
    condition_output.mkdir(parents=True, exist_ok=True)
    (condition_output / "validation.json").write_text(
        json.dumps(validation_record, indent=2, allow_nan=False) + "\n"
    )
    (condition_output / "wireframe.json").write_text(
        json.dumps(candidate, indent=2, allow_nan=False) + "\n"
    )
    (condition_output / "fixed-ruler-support.json").write_text(
        json.dumps(fixed_support, indent=2, allow_nan=False) + "\n"
    )
    (condition_output / "derived-source-provenance.json").write_text(
        json.dumps({
            "schema_version": PERTURBED_SOURCE_SCHEMA,
            "certificate": certificate,
            "condition": deepcopy(spec),
            "derived_source_manifest_sha256": validation.canonical_sha256(
                perturbed_manifest
            ),
            "frame_count": len(perturbed_manifest.get("frames", [])),
            "source_pixels_committed": False,
        }, indent=2, allow_nan=False) + "\n"
    )
    return summary, candidate, selected


def _distance_to_nearest_primary(position, primary_positions, size):
    return min(
        stability._circular_distance(position, value, size)
        for value in primary_positions
    )


def _bin_for_distance(distance):
    for lo, hi in POOR_VIEW_DISTANCE_BINS:
        if lo <= distance <= hi:
            return f"{lo:03d}-{hi:03d}"
    return None


def poor_view_stress(pose_output, pose_payload, primary_result):
    """Transfer one fixed ruler across the full sequence and bin by phase distance."""
    if primary_result.get("scaffold") is None:
        return {
            "schema_version": POOR_VIEW_SCHEMA,
            "status": "unavailable",
            "reason": "primary_scaffold_unavailable",
        }
    primary_positions = [
        row.get("position")
        for row in primary_result.get("selected_frames", [])
        if row.get("position") is not None
    ]
    if not primary_positions:
        return {
            "schema_version": POOR_VIEW_SCHEMA,
            "status": "unavailable",
            "reason": "primary_geometry_positions_unavailable",
        }

    sequence_size = len(pose_payload.get("frames", []))
    rows = []
    for record in pose_payload.get("frames", []):
        canonical = record.get("canonical") or {}
        coordinate = record.get("sequence_coordinate") or {}
        position = record.get("position")
        if (
            position is None
            or not canonical.get("path")
            or coordinate.get("gauge_status") not in ("available", "review")
        ):
            continue
        brightness, mask, valid = stability._load_gauged_arrays(
            pose_output, record
        )
        u, evidence = wireframe.extract_sector_evidence(
            brightness, mask, valid
        )
        transfer = stability.transfer_fixed_ruler_frame(
            evidence,
            u,
            primary_result,
            frame_metadata=stability._metadata(record),
            crown_peak_position=None,
            sequence_size=sequence_size,
            in_primary_fit=position in set(primary_positions),
        )
        distance = _distance_to_nearest_primary(
            position, primary_positions, sequence_size
        )
        transfer["distance_to_nearest_primary_frame"] = distance
        transfer["distance_bin"] = _bin_for_distance(distance)
        transfer["mean_crown_boundary_support_fraction"] = float(
            np.mean([
                transfer["boundary_support"][boundary_id][
                    "support_fraction"
                ]
                for boundary_id in ("C1_C2", "C2_C3", "C3_TABLE")
            ])
        )
        rows.append(transfer)

    bins = []
    for lo, hi in POOR_VIEW_DISTANCE_BINS:
        label = f"{lo:03d}-{hi:03d}"
        members = [
            row for row in rows if row.get("distance_bin") == label
        ]
        if not members:
            continue
        pose_scores = [
            row.get("pose_score") for row in members
            if row.get("pose_score") is not None
        ]
        bins.append({
            "distance_bin_frames": [int(lo), int(hi)],
            "frame_count": len(members),
            "mean_distance_frames": float(np.mean([
                row["distance_to_nearest_primary_frame"]
                for row in members
            ])),
            "mean_pose_score": _mean_or_none(pose_scores),
            "pose_status_counts": dict(sorted(Counter(
                row.get("pose_status") for row in members
            ).items())),
            "transfer_status_counts": dict(sorted(Counter(
                row["status"] for row in members
            ).items())),
            "mean_crown_boundary_support_fraction": float(np.mean([
                row["mean_crown_boundary_support_fraction"]
                for row in members
            ])),
            "median_crown_boundary_support_fraction": float(np.median([
                row["mean_crown_boundary_support_fraction"]
                for row in members
            ])),
            "mean_crown_entity_confidence": _mean_or_none([
                entity["confidence"]
                for row in members
                for semantic_id, entity in row["entities"].items()
                if semantic_id.startswith(("C1_", "C2_", "C3_"))
            ]),
        })

    return {
        "schema_version": POOR_VIEW_SCHEMA,
        "status": "available",
        "distance_definition": (
            "minimum circular viewer-frame distance to any primary #75 "
            "geometry-support position; not a calibrated camera angle"
        ),
        "primary_positions": primary_positions,
        "semantic_gauge_id": primary_result.get("semantic_gauge_id"),
        "frame_count": len(rows),
        "refit_count": sum(
            bool(row.get("refit_performed")) for row in rows
        ),
        "semantic_identity_swap_count": 0,
        "bins": bins,
        "frames": rows,
        "interpretation": (
            "This is a projection/evidence stress curve. The ruler and semantic "
            "IDs are fixed; only support, residual, visibility and confidence "
            "are allowed to change with viewer-phase distance."
        ),
    }


def _representative_qc_image(source_image, specs, destination):
    items = []
    with Image.open(source_image) as image:
        base = image.convert("RGB")
        items.append(("baseline", base.copy()))
        for spec in specs:
            transformed = apply_perturbation(base, spec)
            items.append((spec["id"], transformed.copy()))

    width = max(image.width for _, image in items)
    label_height = 26
    cell_height = max(image.height for _, image in items) + label_height
    columns = 4
    rows = int(np.ceil(len(items) / columns))
    sheet = Image.new(
        "RGB", (columns * width, rows * cell_height), "white"
    )
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(items):
        x = (index % columns) * width
        y = (index // columns) * cell_height
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 4, y + 5), label, fill=(0, 0, 0))
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=92)


def _pick_qc_source(source, source_manifest):
    manifest = json.loads(Path(source_manifest).read_text())
    frames = manifest.get("frames", [])
    if not frames:
        return None
    by_index = {row.get("source_index"): row for row in frames}
    core = 0 if 0 in by_index else frames[0].get("source_index")
    row = by_index.get(core, frames[0])
    return Path(source) / row["path"]


def run_stone(
    source,
    source_manifest,
    output,
    work,
    benchmark_manifest,
    *,
    certificate,
):
    output = Path(output)
    work = Path(work)
    output.mkdir(parents=True, exist_ok=True)

    baseline_processed = work / "baseline" / "processed"
    baseline_pose_output = work / "baseline" / "pose"
    baseline_pose = _process_sequence(
        source,
        source_manifest,
        baseline_processed,
        baseline_pose_output,
    )
    reference_primary, reference_selected, _, _ = _primary_from_pose(
        baseline_pose_output, baseline_pose
    )
    (output / "baseline-wireframe.json").write_text(
        json.dumps(reference_primary, indent=2, allow_nan=False) + "\n"
    )

    if reference_primary.get("scaffold") is None:
        summary = {
            "schema_version": SCHEMA,
            "certificate": certificate,
            "status": "unavailable",
            "reason": "baseline_primary_scaffold_unavailable",
            "baseline_primary": _primary_summary(reference_primary),
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
        return summary

    reference_source_indices = [
        row.get("source_index") for row in reference_selected
    ]
    baseline_fixed = fixed_ruler_support_on_source_indices(
        baseline_pose_output,
        baseline_pose,
        reference_primary,
        reference_source_indices,
    )
    poor_view = poor_view_stress(
        baseline_pose_output, baseline_pose, reference_primary
    )
    (output / "poor-view-stress.json").write_text(
        json.dumps(poor_view, indent=2, allow_nan=False) + "\n"
    )

    condition_summaries = []
    for spec in PERTURBATIONS:
        summary, _, _ = _run_source_condition(
            certificate=certificate,
            spec=spec,
            source=source,
            source_manifest=source_manifest,
            work=work,
            output=output,
            benchmark_manifest=benchmark_manifest,
            reference_primary=reference_primary,
            reference_support=baseline_fixed["summary"],
        )
        condition_summaries.append(summary)

    qc_source = _pick_qc_source(source, source_manifest)
    if qc_source is not None:
        _representative_qc_image(
            qc_source,
            PERTURBATIONS,
            output / "source-perturbation-qc.jpg",
        )

    geometry_unavailable = sum(
        row["geometry_comparison"]["status"] == "unavailable"
        for row in condition_summaries
    )
    gauge_failures = sum(
        row["fixed_ruler_reason"]
        == "semantic_gauge_changed_under_source_perturbation"
        for row in condition_summaries
    )
    semantic_swaps = sum(
        row["geometry_comparison"].get(
            "semantic_identity_consistent"
        ) is False
        for row in condition_summaries
    )
    summary = {
        "schema_version": SCHEMA,
        "certificate": certificate,
        "status": (
            "review"
            if geometry_unavailable or gauge_failures
            else "ok"
        ),
        "frozen_policy": stress_policy(),
        "baseline_primary": _primary_summary(reference_primary),
        "baseline_fixed_ruler_support": baseline_fixed["summary"],
        "poor_view_stress": {
            key: value
            for key, value in poor_view.items()
            if key != "frames"
        },
        "condition_count": len(condition_summaries),
        "geometry_unavailable_condition_count": geometry_unavailable,
        "gauge_failure_condition_count": gauge_failures,
        "semantic_identity_swap_count": semantic_swaps,
        "conditions": condition_summaries,
        "qc_path": "source-perturbation-qc.jpg",
        "interpretation": (
            "Sensitivity table only. No source-quality score and no per-source "
            "or per-condition threshold tuning."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    return summary


def run_source_benchmark(source_root, output, bundle_manifest):
    validation.assert_frozen_method()
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    bundle_by_certificate = {
        row["certificate"]: row for row in manifest["bundles"]
    }
    missing = set(REPRESENTATIVE_CERTIFICATES) - set(
        bundle_by_certificate
    )
    if missing:
        raise ValueError(
            f"representative benchmark certificates missing: {sorted(missing)}"
        )
    output.mkdir(parents=True, exist_ok=True)

    stones = []
    with tempfile.TemporaryDirectory(
        prefix="sparkles-asscher-source-stress-"
    ) as temporary:
        work_root = Path(temporary)
        for certificate in REPRESENTATIVE_CERTIFICATES:
            item = bundle_by_certificate[certificate]
            source = source_root / certificate
            source_manifest = Path(item["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest = Path.cwd() / source_manifest
            stones.append(run_stone(
                source,
                source_manifest,
                output / "per-stone" / certificate,
                work_root / certificate,
                manifest,
                certificate=certificate,
            ))

    payload = {
        "schema_version": SCHEMA,
        "frozen_policy": stress_policy(),
        "benchmark_inputs": validation.assert_frozen_benchmark_manifest(
            manifest
        ),
        "stone_count": len(stones),
        "stones": stones,
        "interpretation": (
            "Controlled robustness/falsification experiment only. Results are "
            "reported per perturbation and poor-view distance bin; no universal "
            "robustness or source-quality score is computed."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run issue #90 controlled source and poor-view stress tests"
        )
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=Path("docs/360/benchmark/source-bundles.json"),
    )
    args = parser.parse_args()
    result = run_source_benchmark(
        args.source_root, args.output, args.bundle_manifest
    )
    for stone in result["stones"]:
        print(stone["certificate"], stone["status"])
        for condition in stone.get("conditions", []):
            geometry = condition["geometry_comparison"]
            print(
                " ",
                condition["condition_id"],
                geometry["status"],
                "max-tier=",
                geometry.get(
                    "max_boundary_displacement_tier_fraction"
                ),
                "fixed=",
                condition.get("fixed_ruler_status"),
            )


if __name__ == "__main__":
    main()
