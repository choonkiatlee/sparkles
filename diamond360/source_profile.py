"""Source/acquisition characterisation for ordinary vendor 360 sequences.

Issue #81: keep source facts and diagnostics separate from measurement policy.
The profile describes acquisition evidence; assess_measurement/can_compare decide
what a downstream measurement may claim.

Photometric diagnostics deliberately avoid inferring exposure drift from the
diamond's own brightness changes. Sequence-global stability is estimated only
from background/reference pixels outside the segmented stone when enough
reference support exists.
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import normalized_geometry

SCHEMA = "diamond360-source-profile/1"
STATUS = ("ok", "review", "unavailable")
DEFAULT_MIN_NATIVE_DIAMETER_PX = 96.0
DEFAULT_TARGET_DIAMETER_PX = float(normalized_geometry.DEFAULT_TARGET_DIAMETER)
BACKGROUND_MIN_FRACTION = 0.05
BACKGROUND_LUMINANCE_MAD_REVIEW = 0.02
BACKGROUND_CHANNEL_MAD_REVIEW = 0.03
BACKGROUND_JUMP_REVIEW = 0.05
CLIPPING_REVIEW_FRACTION = 0.02


def specification():
    return {
        "schema_version": SCHEMA,
        "states": list(STATUS),
        "spatial": {
            "minimum_native_effective_diameter_px": DEFAULT_MIN_NATIVE_DIAMETER_PX,
            "common_transfer_target_diameter_px": DEFAULT_TARGET_DIAMETER_PX,
            "interpretation": (
                "Native sampling and declared common-transfer suitability; "
                "not a generic image-quality score."
            ),
        },
        "photometric": {
            "background_min_fraction": BACKGROUND_MIN_FRACTION,
            "background_luminance_mad_review": BACKGROUND_LUMINANCE_MAD_REVIEW,
            "background_channel_mad_review": BACKGROUND_CHANNEL_MAD_REVIEW,
            "background_jump_review": BACKGROUND_JUMP_REVIEW,
            "stone_channel_clipping_review_fraction": CLIPPING_REVIEW_FRACTION,
            "interpretation": (
                "Background/reference stability is source-global evidence. "
                "Whole-stone brightness change is never labelled exposure drift "
                "because it may be the optical signal of interest."
            ),
        },
        "processing": {
            "jpeg_quantization": "Decoded JPEG quantization-table summaries where available.",
            "block_boundary_ratio": (
                "Scene-dependent 8x8 boundary discontinuity proxy; diagnostic only."
            ),
            "acutance_proxy": (
                "Scene-dependent median absolute Laplacian inside the stone; "
                "diagnostic only and not called effective resolution."
            ),
        },
        "comparability": (
            "Measurement-family-specific ok/review/unavailable decisions; "
            "no universal source-quality score."
        ),
    }


def _finite(values):
    return np.asarray(
        [
            float(value)
            for value in values
            if value is not None and np.isfinite(float(value))
        ],
        dtype=float,
    )


def _summary(values):
    data = _finite(values)
    if not len(data):
        return {"count": 0, "min": None, "median": None, "max": None, "mad": None}
    median = float(np.median(data))
    return {
        "count": int(len(data)),
        "min": float(np.min(data)),
        "median": median,
        "max": float(np.max(data)),
        "mad": float(np.median(np.abs(data - median))),
    }


def _status(status, reasons=None, **extra):
    if status not in STATUS:
        raise ValueError(f"unknown status {status}")
    return {"status": status, "reasons": list(reasons or []), **extra}


def _source_dimensions(metadata, manifest):
    dimensions = manifest.get("dimensions")
    if (
        isinstance(dimensions, list)
        and len(dimensions) == 2
        and all(isinstance(v, (int, float)) for v in dimensions)
    ):
        return [int(dimensions[0]), int(dimensions[1])]
    discovered = metadata.get("dimensions") or []
    if len(discovered) == 1 and len(discovered[0]) == 2:
        return [int(discovered[0][0]), int(discovered[0][1])]
    return None


def _stone_diameters(metadata):
    values, widths, heights = [], [], []
    for record in metadata.get("frames", []):
        geometry = record.get("geometry") or {}
        area = geometry.get("area_px")
        if isinstance(area, (int, float)) and float(area) > 0:
            values.append(2.0 * math.sqrt(float(area) / math.pi))
        width = geometry.get("width_px")
        height = geometry.get("height_px")
        if isinstance(width, (int, float)):
            widths.append(float(width))
        if isinstance(height, (int, float)):
            heights.append(float(height))
    return _summary(values), _summary(widths), _summary(heights)


def _sequence_contract(metadata, manifest, pose):
    records = metadata.get("frames") or []
    indices = [
        record.get("source_index")
        for record in records
        if record.get("source_index") is not None
    ]
    duplicate_indices = len(indices) - len(set(indices))
    duplicate_pixels = sum(
        bool(record.get("duplicate_of") or record.get("pixel_duplicate_of"))
        for record in records
    )
    ordering = metadata.get("ordering")
    reasons = []
    if duplicate_indices:
        reasons.append("duplicate_source_indices")
    if duplicate_pixels:
        reasons.append("duplicate_source_frames_detected")
    if ordering != "explicit_manifest":
        reasons.append("ordering_not_explicit_manifest")
    if manifest.get("sequence_complete") is not True:
        reasons.append("complete_cycle_not_proven")

    phase = None
    if isinstance(pose, dict):
        phase = (pose.get("sequence_gauge") or {}).get("phase") or pose.get("phase")
    if not isinstance(phase, dict):
        phase = _status(
            "unavailable",
            ["pose_sequence_phase_not_supplied"],
            physical_camera_angle_calibrated=False,
        )

    return {
        "ordering": _status(
            "review" if reasons else "ok",
            reasons,
            ordering=ordering,
            source_frame_count=manifest.get("source_frame_count"),
            observed_frame_count=len(records),
            sequence_complete=bool(manifest.get("sequence_complete")),
            duplicate_source_index_count=int(duplicate_indices),
            duplicate_pixel_frame_count=int(duplicate_pixels),
        ),
        "sampling": manifest.get("sequence_sampling"),
        "phase": phase,
    }


def _pose_coverage(pose):
    if not isinstance(pose, dict):
        return _status(
            "unavailable",
            ["asscher_pose_output_not_supplied"],
            usable_count=0,
            frame_count=0,
        )
    frames = pose.get("frames") or []
    counts, crown_usable, support = {}, 0, []
    for record in frames:
        assessment = record.get("assessment") or {}
        status = assessment.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        if (
            status in ("ok", "review")
            and record.get("face_role") == "likely_crown_lobe"
        ):
            crown_usable += 1
        canonical = record.get("canonical") or {}
        normalization = canonical.get("normalization") or {}
        value = normalization.get("valid_fraction_of_mask")
        if value is not None:
            support.append(value)

    usable = sum(counts.get(key, 0) for key in ("ok", "review"))
    if usable == 0:
        state, reasons = "unavailable", ["no_geometry_usable_pose_frames"]
    elif crown_usable == 0:
        state, reasons = "review", ["crown_view_interval_not_resolved"]
    else:
        state, reasons = "ok", []
    return _status(
        state,
        reasons,
        usable_count=int(usable),
        frame_count=int(len(frames)),
        crown_usable_count=int(crown_usable),
        status_counts=counts,
        canonical_valid_support_fraction=_summary(support),
        face_selection=pose.get("face_selection"),
    )


def _pose_extents(pose):
    """Prefer source-camera extents from #73 crown or top-ranked usable views."""
    if not isinstance(pose, dict):
        return None
    usable = [
        record
        for record in pose.get("frames") or []
        if (record.get("assessment") or {}).get("status") in ("ok", "review")
        and (record.get("assessment") or {}).get("outline")
    ]
    crown = [
        record
        for record in usable
        if record.get("face_role") == "likely_crown_lobe"
    ]
    if crown:
        selected = crown
        provenance = "asscher_pose_likely_crown_lobe"
    elif usable:
        selected = sorted(
            usable,
            key=lambda record: int(record.get("rank", 10**9)),
        )[: min(16, len(usable))]
        provenance = "asscher_pose_top_ranked_usable_views"
    else:
        return None

    outlines = [record["assessment"]["outline"] for record in selected]
    return {
        "provenance": provenance,
        "diameter": _summary(
            outline.get("effective_diameter_px") for outline in outlines
        ),
        "widths": _summary(outline.get("width_px") for outline in outlines),
        "heights": _summary(outline.get("height_px") for outline in outlines),
    }


def _physical_scale(widths, heights, certificate_dimensions_mm, pose_coverage):
    if certificate_dimensions_mm is None:
        return _status(
            "unavailable",
            ["certificate_face_up_dimensions_not_supplied"],
            physical_width_mm=None,
            physical_length_mm=None,
        )
    if (
        not isinstance(certificate_dimensions_mm, (list, tuple))
        or len(certificate_dimensions_mm) != 2
        or not all(
            isinstance(value, (int, float))
            and np.isfinite(value)
            and float(value) > 0
            for value in certificate_dimensions_mm
        )
    ):
        raise ValueError("certificate_dimensions_mm must be [width_mm, length_mm]")
    width_mm, length_mm = map(float, certificate_dimensions_mm)
    width_px, height_px = widths.get("median"), heights.get("median")
    if width_px is None or height_px is None:
        return _status(
            "unavailable",
            ["source_stone_extent_unavailable"],
            physical_width_mm=width_mm,
            physical_length_mm=length_mm,
        )
    state = "ok" if pose_coverage["status"] == "ok" else "review"
    reasons = [] if state == "ok" else ["pose_support_requires_review"]
    return _status(
        state,
        reasons,
        physical_width_mm=width_mm,
        physical_length_mm=length_mm,
        approximate_pixels_per_mm_xy=[
            float(width_px / width_mm),
            float(height_px / length_mm),
        ],
        interpretation=(
            "Approximate face-up image scale only; no depth or 3-D facet geometry "
            "is inferred."
        ),
    )


def _spatial_sampling(metadata, pose=None):
    pose_extents = _pose_extents(pose)
    if pose_extents is None:
        diameter, widths, heights = _stone_diameters(metadata)
        provenance = "processed_sequence_all_views_fallback"
        fallback_reason = "pose_conditioned_native_sampling_unavailable"
    else:
        diameter = pose_extents["diameter"]
        widths = pose_extents["widths"]
        heights = pose_extents["heights"]
        provenance = pose_extents["provenance"]
        fallback_reason = None

    native = diameter.get("median")
    if native is None:
        state, reasons = "unavailable", ["stone_effective_diameter_unavailable"]
        common = _status(
            "unavailable",
            reasons,
            target_effective_diameter_px=DEFAULT_TARGET_DIAMETER_PX,
        )
    elif native < DEFAULT_MIN_NATIVE_DIAMETER_PX:
        state, reasons = "review", ["native_stone_sampling_below_research_floor"]
        common = _status(
            "review",
            ["common_transfer_requires_large_upsampling"],
            target_effective_diameter_px=DEFAULT_TARGET_DIAMETER_PX,
            median_scale=float(DEFAULT_TARGET_DIAMETER_PX / native),
            requires_upsampling=True,
        )
    else:
        state, reasons = "ok", []
        needs_upsampling = native < DEFAULT_TARGET_DIAMETER_PX
        common = _status(
            "review" if needs_upsampling else "ok",
            ["common_transfer_requires_upsampling"] if needs_upsampling else [],
            target_effective_diameter_px=DEFAULT_TARGET_DIAMETER_PX,
            median_scale=float(DEFAULT_TARGET_DIAMETER_PX / native),
            requires_upsampling=bool(needs_upsampling),
        )
    if fallback_reason and state != "unavailable":
        state = "review"
        reasons = list(reasons) + [fallback_reason]
    return _status(
        state,
        reasons,
        extent_provenance=provenance,
        effective_diameter_px=diameter,
        stone_width_px=widths,
        stone_height_px=heights,
        common_transfer=common,
    )


def build_profile(
    metadata,
    *,
    pose=None,
    certificate_dimensions_mm=None,
    image_diagnostics=None,
):
    """Build a deterministic profile from existing pipeline and pose outputs."""
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a sequence.json-style mapping")
    manifest = metadata.get("source_manifest") or {}
    pose_coverage = _pose_coverage(pose)
    spatial = _spatial_sampling(metadata, pose)
    image_diagnostics = image_diagnostics or {}

    compression = image_diagnostics.get(
        "compression_processing",
        _status("unavailable", ["image_bytes_not_analysed"]),
    )
    photometric = image_diagnostics.get(
        "photometric",
        _status(
            "unavailable",
            ["image_bytes_not_analysed"],
            whole_stone_exposure_drift="unsupported_inference",
        ),
    )
    source = {
        "manifest_schema_version": manifest.get("schema_version"),
        "source_pipeline": manifest.get("source_pipeline"),
        "certificate": manifest.get("certificate"),
        "item_id": manifest.get("item_id"),
        "viewer": manifest.get("viewer"),
        "retrieved_at": manifest.get("retrieved_at"),
        "metadata_url": manifest.get("metadata_url"),
        "metadata_sha256": manifest.get("metadata_sha256"),
        "dimensions_px": _source_dimensions(metadata, manifest),
        "source_frame_count": manifest.get("source_frame_count"),
        "sequence_complete": bool(manifest.get("sequence_complete")),
        "ordering_provenance": manifest.get("ordering"),
        "ordering_validation": manifest.get("ordering_validation"),
        "extraction_assumptions": {
            key: manifest.get(key)
            for key in (
                "bootstrap_url",
                "bootstrap_sha256",
                "still_url",
                "still_sha256",
            )
            if manifest.get(key) is not None
        },
    }
    return {
        "schema_version": SCHEMA,
        "source": source,
        "sequence": _sequence_contract(metadata, manifest, pose),
        "spatial_sampling": spatial,
        "compression_processing": compression,
        "photometric": photometric,
        "pose_coverage": pose_coverage,
        "physical_scale": _physical_scale(
            spatial["stone_width_px"],
            spatial["stone_height_px"],
            certificate_dimensions_mm,
            pose_coverage,
        ),
        "diagnostic_provenance": {
            "source_sequence_schema": metadata.get("schema_version"),
            "source_manifest_schema": manifest.get("schema_version"),
            "pose_schema": pose.get("schema_version") if pose else None,
            "normalized_geometry_schema": normalized_geometry.SCHEMA,
            "specification": specification(),
        },
        "interpretation": (
            "Source/acquisition evidence only. Fields describe support and "
            "limitations for downstream measurements; they are not proxies "
            "for diamond quality."
        ),
    }


def _jpeg_quantization_summary(image):
    tables = getattr(image, "quantization", None) or {}
    values = [int(value) for table in tables.values() for value in table]
    return None if not values else float(np.median(values))


def _block_boundary_ratio(gray):
    gray = np.asarray(gray, float)
    if min(gray.shape) < 24:
        return None
    vertical = np.abs(np.diff(gray, axis=1))
    horizontal = np.abs(np.diff(gray, axis=0))
    vb = vertical[:, np.arange(vertical.shape[1]) % 8 == 7]
    vn = vertical[:, np.arange(vertical.shape[1]) % 8 != 7]
    hb = horizontal[np.arange(horizontal.shape[0]) % 8 == 7, :]
    hn = horizontal[np.arange(horizontal.shape[0]) % 8 != 7, :]
    boundary = np.concatenate([vb.ravel(), hb.ravel()])
    interior = np.concatenate([vn.ravel(), hn.ravel()])
    return float(np.median(boundary) / max(float(np.median(interior)), 1e-6))


def _acutance_proxy(gray, mask):
    gray, mask = np.asarray(gray, float), np.asarray(mask, bool)
    if gray.shape != mask.shape or int(mask.sum()) < 64:
        return None
    values = np.abs(ndi.laplace(gray, mode="nearest"))[mask]
    return float(np.median(values)) if len(values) else None


def _background_reference(rgb, mask):
    rgb, mask = np.asarray(rgb, float) / 255.0, np.asarray(mask, bool)
    background = ~ndi.binary_dilation(mask, iterations=3)
    fraction = float(np.mean(background))
    if fraction < BACKGROUND_MIN_FRACTION:
        return None
    pixels = rgb[background]
    if len(pixels) < 100:
        return None
    median_rgb = np.median(pixels, axis=0)
    return {
        "background_fraction": fraction,
        "median_rgb": median_rgb.tolist(),
        "median_luminance": float(
            median_rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=float)
        ),
    }


def _stone_clipping(rgb, mask):
    rgb, mask = np.asarray(rgb, np.uint8), np.asarray(mask, bool)
    pixels = rgb[mask]
    if not len(pixels):
        return None
    low, high = np.mean(pixels <= 1, axis=0), np.mean(pixels >= 254, axis=0)
    return {
        "low_fraction_rgb": low.astype(float).tolist(),
        "high_fraction_rgb": high.astype(float).tolist(),
        "max_channel_fraction": float(max(np.max(low), np.max(high))),
    }


def analyse_image_diagnostics(processed, *, maximum_frames=None):
    """Measure source-byte diagnostics from a processed pipeline directory.

    Background/reference pixels are used for sequence-global photometric
    stability. Stone brightness itself is retained only for clipping support
    and is not used to infer exposure drift.
    """
    processed = Path(processed)
    metadata = json.loads((processed / "sequence.json").read_text())
    candidates = [
        record
        for record in metadata.get("frames", [])
        if record.get("status") == "valid"
        and record.get("camera_original_path")
        and (record.get("segmentation") or {}).get("mask_path")
    ]
    if maximum_frames is not None and len(candidates) > maximum_frames:
        chosen = np.linspace(
            0, len(candidates) - 1, int(maximum_frames)
        ).round().astype(int)
        candidates = [candidates[index] for index in sorted(set(chosen))]

    jpeg_quant, bytes_per_pixel, block_ratios, acutance = [], [], [], []
    clipping, background = [], []
    for record in candidates:
        image_path = processed / record["camera_original_path"]
        mask_path = processed / record["segmentation"]["mask_path"]
        with Image.open(image_path) as image:
            image.load()
            quant = _jpeg_quantization_summary(image)
            if quant is not None:
                jpeg_quant.append(quant)
            rgb = np.asarray(image.convert("RGB"))
        mask = np.asarray(Image.open(mask_path).convert("L")) > 0
        height, width = rgb.shape[:2]
        bytes_per_pixel.append(
            float(image_path.stat().st_size / max(1, height * width))
        )
        gray = (
            rgb.astype(float) / 255.0
            @ np.array([0.2126, 0.7152, 0.0722], dtype=float)
        )
        value = _block_boundary_ratio(gray)
        if value is not None:
            block_ratios.append(value)
        value = _acutance_proxy(gray, mask)
        if value is not None:
            acutance.append(value)
        value = _stone_clipping(rgb, mask)
        if value is not None:
            clipping.append(value)
        value = _background_reference(rgb, mask)
        if value is not None:
            background.append(value)

    compression = (
        _status(
            "ok",
            [],
            analysed_frame_count=len(candidates),
            jpeg_quantization_median=_summary(jpeg_quant),
            bytes_per_pixel=_summary(bytes_per_pixel),
            jpeg_block_boundary_ratio_scene_dependent=_summary(block_ratios),
            acutance_proxy_scene_dependent=_summary(acutance),
            resampling_evidence=_status(
                "unavailable", ["no_validated_scene_independent_detector_in_v1"]
            ),
            sharpening_halo_evidence=_status(
                "unavailable", ["no_validated_scene_independent_detector_in_v1"]
            ),
            denoising_evidence=_status(
                "unavailable", ["no_validated_scene_independent_detector_in_v1"]
            ),
        )
        if candidates
        else _status(
            "unavailable",
            ["no_source_camera_frames_with_masks"],
            analysed_frame_count=0,
        )
    )

    clipping_summary = _summary(
        item["max_channel_fraction"] for item in clipping
    )
    if not background:
        reference = _status(
            "unavailable",
            ["insufficient_background_reference_support"],
            analysed_frame_count=0,
        )
    else:
        luminance = np.asarray(
            [item["median_luminance"] for item in background], dtype=float
        )
        channels = np.asarray(
            [item["median_rgb"] for item in background], dtype=float
        )
        luminance_median = float(np.median(luminance))
        luminance_mad = float(np.median(np.abs(luminance - luminance_median)))
        channel_medians = np.median(channels, axis=0)
        channel_mads = np.median(np.abs(channels - channel_medians), axis=0)
        jumps = (
            np.abs(np.diff(luminance))
            if len(luminance) > 1
            else np.asarray([], dtype=float)
        )
        reasons = []
        if luminance_mad > BACKGROUND_LUMINANCE_MAD_REVIEW:
            reasons.append("background_luminance_variation")
        if float(np.max(channel_mads)) > BACKGROUND_CHANNEL_MAD_REVIEW:
            reasons.append("background_channel_variation")
        if len(jumps) and float(np.max(jumps)) > BACKGROUND_JUMP_REVIEW:
            reasons.append("abrupt_background_luminance_change")
        reference = _status(
            "review" if reasons else "ok",
            reasons,
            analysed_frame_count=len(background),
            background_fraction=_summary(
                item["background_fraction"] for item in background
            ),
            median_rgb=channel_medians.astype(float).tolist(),
            channel_mad_rgb=channel_mads.astype(float).tolist(),
            luminance_median=luminance_median,
            luminance_mad=luminance_mad,
            maximum_adjacent_luminance_jump=(
                None if not len(jumps) else float(np.max(jumps))
            ),
            interpretation=(
                "Sequence-global source reference outside the segmented stone; "
                "not derived from diamond brightness."
            ),
        )

    clipping_reasons = []
    if (
        clipping_summary["max"] is not None
        and clipping_summary["max"] > CLIPPING_REVIEW_FRACTION
    ):
        clipping_reasons.append("material_stone_channel_clipping")
    photometric_reasons = list(clipping_reasons)
    if reference["status"] == "unavailable":
        photometric_reasons.append("source_global_reference_unavailable")
    elif reference["status"] == "review":
        photometric_reasons.extend(reference["reasons"])
    photometric = _status(
        "review" if photometric_reasons else "ok",
        sorted(set(photometric_reasons)),
        background_reference=reference,
        stone_channel_clipping_fraction=clipping_summary,
        whole_stone_exposure_drift="unsupported_inference",
        framewise_normalization_applied=False,
        colour_calibrated=False,
        radiometric_calibrated=False,
        interpretation=(
            "Stone brightness dynamics are not treated as exposure drift. "
            "Photometric stability uses only source-global reference evidence "
            "where available."
        ),
    )
    return {
        "compression_processing": compression,
        "photometric": photometric,
    }


def build_from_processed(
    processed,
    *,
    pose=None,
    certificate_dimensions_mm=None,
    maximum_diagnostic_frames=None,
):
    processed = Path(processed)
    metadata = json.loads((processed / "sequence.json").read_text())
    if pose is None:
        pose_payload = None
    elif isinstance(pose, dict):
        pose_payload = pose
    else:
        pose_payload = json.loads(Path(pose).read_text())
    diagnostics = analyse_image_diagnostics(
        processed, maximum_frames=maximum_diagnostic_frames
    )
    return build_profile(
        metadata,
        pose=pose_payload,
        certificate_dimensions_mm=certificate_dimensions_mm,
        image_diagnostics=diagnostics,
    )


def _spatial_measurement(profile):
    spatial = profile["spatial_sampling"]
    common = spatial.get("common_transfer") or {}
    if spatial["status"] == "unavailable":
        return _status("unavailable", spatial["reasons"])
    if spatial["status"] == "review" or common.get("status") == "review":
        return _status(
            "review",
            list(spatial["reasons"]) + list(common.get("reasons") or []),
        )
    return _status("ok", [], normalization=normalized_geometry.SCHEMA)


def assess_measurement(profile, measurement_family):
    """Assess one measurement family against one source profile."""
    if profile.get("schema_version") != SCHEMA:
        raise ValueError("unsupported source profile schema")
    sequence = profile["sequence"]
    pose = profile["pose_coverage"]
    photometric = profile["photometric"]
    physical = profile["physical_scale"]

    if measurement_family == "geometry_topology":
        if pose["status"] == "unavailable":
            return _status("unavailable", pose["reasons"])
        spatial = _spatial_measurement(profile)
        if spatial["status"] == "unavailable":
            return spatial
        reasons = list(pose["reasons"]) + list(spatial["reasons"])
        return _status("review" if reasons else "ok", reasons)

    if measurement_family == "spatial_optical_morphology":
        return _spatial_measurement(profile)

    if measurement_family == "physical_spatial_scale":
        return _status(physical["status"], physical["reasons"])

    if measurement_family == "ordered_dynamics":
        ordering = sequence["ordering"]
        return _status(ordering["status"], ordering["reasons"])

    if measurement_family == "angular_persistence":
        ordering, phase = sequence["ordering"], sequence["phase"]
        if ordering["status"] == "unavailable" or phase.get("status") == "unavailable":
            reasons = list(ordering["reasons"]) + list(phase.get("reasons") or [])
            if phase.get("reason"):
                reasons.append(phase["reason"])
            return _status("unavailable", sorted(set(reasons)))
        reasons = list(ordering["reasons"])
        if phase.get("status") not in ("available", "ok"):
            reasons.append("phase_contract_requires_review")
        if pose["status"] == "unavailable":
            reasons.append("pose_coverage_unavailable")
        return _status(
            "review" if reasons else "ok",
            reasons,
            coordinate="observed_viewer_sequence_phase",
            physical_camera_angle_calibrated=bool(
                phase.get("physical_camera_angle_calibrated", False)
            ),
        )

    if measurement_family == "relative_luminance_dynamics":
        reference = photometric.get("background_reference") or {}
        reasons = list(photometric.get("reasons") or [])
        if reference.get("status") == "unavailable":
            reasons.append("source_global_photometric_stability_unresolved")
        return _status("review" if reasons else "ok", sorted(set(reasons)))

    if measurement_family == "absolute_luminance_amplitude":
        if photometric.get("radiometric_calibrated") is True:
            return _status("ok", [])
        return _status("review", ["source_is_not_radiometrically_calibrated"])

    if measurement_family == "chromatic_activity":
        reasons = list(photometric.get("reasons") or [])
        if photometric.get("colour_calibrated") is not True:
            reasons.append("source_is_not_colour_calibrated")
        clipping = photometric.get("stone_channel_clipping_fraction") or {}
        if (
            clipping.get("max") is not None
            and clipping["max"] > CLIPPING_REVIEW_FRACTION
        ):
            reasons.append("material_stone_channel_clipping")
        return _status("review" if reasons else "ok", sorted(set(reasons)))

    if measurement_family == "tier_edge_crispness":
        result = _spatial_measurement(profile)
        if result["status"] == "ok":
            result["normalization"] = normalized_geometry.SCHEMA
        return result

    raise ValueError(f"unknown measurement family: {measurement_family}")


MEASUREMENT_FAMILIES = (
    "geometry_topology",
    "spatial_optical_morphology",
    "physical_spatial_scale",
    "ordered_dynamics",
    "angular_persistence",
    "relative_luminance_dynamics",
    "absolute_luminance_amplitude",
    "chromatic_activity",
    "tier_edge_crispness",
)


def can_compare(left, right, measurement_family):
    """Return pairwise cross-source comparability for one measurement family."""
    left_state = assess_measurement(left, measurement_family)
    right_state = assess_measurement(right, measurement_family)
    reasons = [
        f"left:{reason}" for reason in left_state["reasons"]
    ] + [
        f"right:{reason}" for reason in right_state["reasons"]
    ]
    if "unavailable" in (left_state["status"], right_state["status"]):
        return _status(
            "unavailable",
            sorted(set(reasons)),
            measurement_family=measurement_family,
        )
    state = (
        "review"
        if "review" in (left_state["status"], right_state["status"])
        else "ok"
    )

    if measurement_family == "absolute_luminance_amplitude":
        if not (
            left["photometric"].get("radiometric_calibrated")
            and right["photometric"].get("radiometric_calibrated")
        ):
            state = "review"
            reasons.append("cross_source_radiometric_calibration_missing")

    elif measurement_family == "chromatic_activity":
        if not (
            left["photometric"].get("colour_calibrated")
            and right["photometric"].get("colour_calibrated")
        ):
            state = "review"
            reasons.append("cross_source_colour_calibration_missing")

    elif measurement_family in ("spatial_optical_morphology", "tier_edge_crispness"):
        lt = (
            left["spatial_sampling"]
            .get("common_transfer", {})
            .get("target_effective_diameter_px")
        )
        rt = (
            right["spatial_sampling"]
            .get("common_transfer", {})
            .get("target_effective_diameter_px")
        )
        if lt != rt:
            state = "review"
            reasons.append("common_spatial_transfer_mismatch")

    elif measurement_family == "angular_persistence":
        lp, rp = left["sequence"].get("phase") or {}, right["sequence"].get("phase") or {}
        if lp.get("period_deg") != rp.get("period_deg"):
            state = "review"
            reasons.append("viewer_phase_period_mismatch")
        if not (
            lp.get("physical_camera_angle_calibrated")
            and rp.get("physical_camera_angle_calibrated")
        ):
            reasons.append("viewer_sequence_phase_not_physical_angle")

    elif measurement_family == "relative_luminance_dynamics":
        if (
            left["source"].get("source_pipeline")
            != right["source"].get("source_pipeline")
        ):
            state = "review"
            reasons.append("different_source_pipelines")

    return _status(
        state,
        sorted(set(reasons)),
        measurement_family=measurement_family,
    )


def apply_diagnostic_perturbation(rgb, kind):
    """Controlled RGB perturbations for validating source diagnostics."""
    x = np.asarray(rgb, np.uint8)
    if x.ndim != 3 or x.shape[2] != 3:
        raise ValueError("rgb must be uint8-like HxWx3")
    work = x.astype(float) / 255.0

    if kind == "blur":
        out = ndi.gaussian_filter(work, sigma=(0.8, 0.8, 0), mode="nearest")
    elif kind == "downsample":
        small = ndi.zoom(work, (0.5, 0.5, 1), order=1, prefilter=False)
        out = ndi.zoom(
            small,
            (
                work.shape[0] / small.shape[0],
                work.shape[1] / small.shape[1],
                1,
            ),
            order=1,
            prefilter=False,
        )[: work.shape[0], : work.shape[1], :]
    elif kind == "sharpen":
        smooth = ndi.gaussian_filter(work, sigma=(0.8, 0.8, 0), mode="nearest")
        out = np.clip(work + 0.75 * (work - smooth), 0.0, 1.0)
    elif kind == "exposure":
        out = np.clip(work * 1.10, 0.0, 1.0)
    elif kind == "contrast":
        out = np.clip((work - 0.5) * 1.12 + 0.5, 0.0, 1.0)
    elif kind == "white_balance":
        out = np.clip(
            work * np.array([1.05, 1.0, 0.95], dtype=float),
            0.0,
            1.0,
        )
    elif kind == "jpeg":
        buffer = io.BytesIO()
        Image.fromarray(
            np.rint(work * 255.0).astype(np.uint8),
            mode="RGB",
        ).save(buffer, format="JPEG", quality=70, optimize=False)
        buffer.seek(0)
        out = np.asarray(Image.open(buffer).convert("RGB"), float) / 255.0
    else:
        raise ValueError(f"unknown perturbation: {kind}")

    return np.rint(out * 255.0).clip(0, 255).astype(np.uint8)
