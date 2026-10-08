"""#92 minimal fixed-ruler -> optical image-support smoke test.

Consume the #89 transfer result and the SAME frozen #75/#96 stone-level
scaffold, then sample simple brightness from non-exclusive image-plane
polygons. Never re-estimate, shift, or assign physical ownership to edges.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_topology as topology
from . import asscher_geometry_stability as stability
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-semantic-optical-handoff/1"
POLICY = {
    "geometry": "fixed_primary_scaffold_no_refit",
    "frame_gauge": "existing_80_canonical_gauge",
    "image_support": "overlapping_nonexclusive_semantic_polygons",
    "input_photometry": "canonical_measurement_brightness_not_raw_camera_RGB",
    "raw_mean": "mean_of_input_measurement_brightness_no_extra_transform",
    "normalized_mean": "only_when_supplied_separate_normalized_frame",
    "physical_facet_identity": "not_asserted_from_image_support",
    "c3_table_physical_identity": "review_until_correspondence_validated",
    "fallback": "unavailable_yields_null_not_fabricated_zero",
    "no_estimator_change": True,
    "no_physical_angles_or_quality_score": True,
}


def _mask_polygon(vertices, shape):
    h, w = shape
    image = Image.new("1", (w, h), 0)
    ImageDraw.Draw(image).polygon(
        [(float(x), float(y)) for x,y in vertices], fill=1
    )
    return np.asarray(image, bool)


def sample_fixed_frame(scaffold, frame_transfer, brightness, gauge_mask,
                       valid_mask, *, normalized_brightness=None):
    """Sample already-registered geometry without modifying it in any way."""
    if scaffold.get("schema_version") != topology.SCAFFOLD_SCHEMA:
        raise ValueError("unexpected semantic scaffold schema")
    if frame_transfer.get("schema_version") != stability.TRANSFER_SCHEMA:
        raise ValueError("input must be #89 fixed ruler frame transfer")
    if (frame_transfer.get("refit_performed") is not False
        or frame_transfer.get("semantic_identity_source") != "primary_fixed_scaffold"
        or frame_transfer.get("geometry_mode") != stability.TRANSFER_POLICY):
        raise ValueError("transferred geometry must remain fixed")
    gauge_id=scaffold.get("semantic_gauge",{}).get("gauge_id")
    if not gauge_id or frame_transfer.get("semantic_gauge_id") != gauge_id:
        raise ValueError("semantic gauge disagreement: cannot sample source")
    required=set(scaffold.get("entity_observations",{}))
    entries=frame_transfer.get("entities",{})
    if set(entries) != required:
        raise ValueError("semantic IDs not preserved during ruler transfer")
    raw=np.asarray(brightness,float)
    gauge=np.asarray(gauge_mask,bool)
    valid=np.asarray(valid_mask,bool)
    if raw.ndim != 2 or gauge.shape!=raw.shape or valid.shape!=raw.shape:
        raise ValueError("registered grayscale and masks must share 2D shape")
    norm=None if normalized_brightness is None else np.asarray(normalized_brightness,float)
    if norm is not None and (norm.shape!=raw.shape or not np.isfinite(norm).all()):
        raise ValueError("separately normalized image must be finite and registered")
    if not np.isfinite(raw).all():
        raise ValueError("unscaled brightness must be finite")
    if not gauge.any():
        raise ValueError("gauge mask is empty")
    pixels=valid & gauge
    points=wireframe._scaffold_points_in_gauge(gauge,scaffold)
    support_by_id={s["support_id"]:s for s in scaffold.get("semantic_supports",[])}
    support_masks={}
    rows=[]
    for entity_id in sorted(required):
        entry=entries[entity_id]
        if entry.get("semantic_id") != entity_id:
            raise ValueError("transferred row renamed semantic ID")
        status=entry.get("status")
        if status not in ("ok","review","unavailable"):
            raise ValueError("invalid geometry support status")
        obs=scaffold["entity_observations"][entity_id]
        confidence=entry.get("confidence")
        if confidence is None or not 0<=float(confidence)<=1:
            raise ValueError("missing geometry support confidence")
        region=np.zeros(raw.shape,bool)
        refs=obs.get("support_ids",[])
        if status != "unavailable":
            for support_id in refs:
                support=support_by_id.get(support_id)
                if support is None or entity_id not in support["semantic_ids"]:
                    raise ValueError("semantic support mismatch")
                if support.get("attribution_mode") != "nonexclusive_semantic_support":
                    raise ValueError("exclusive facet pixel assignment forbidden")
                if support_id not in support_masks:
                    support_masks[support_id]=_mask_polygon(
                        [points[v] for v in support["vertex_ids"]],raw.shape)
                region |= support_masks[support_id]
        region &= pixels
        count=int(region.sum())
        row={
            "semantic_id":entity_id,
            "source_index":frame_transfer.get("source_index"),
            "rotation_phase_deg":frame_transfer.get("rotation_phase_deg"),
            "supported_pixel_count":count,
            "raw_mean_brightness":float(raw[region].mean()) if count else None,
            "normalized_mean_brightness":(float(norm[region].mean())
                                          if count and norm is not None else None),
            "geometry_support_status":status,
            "geometry_confidence":float(confidence),
            "image_support_attribution":"nonexclusive_overlapping_not_polished_facet",
            "physical_facet_correspondence":"not_established",
            "geometry_support_kind":entry.get("support_kind"),
            "support_provenance":obs.get("provenance"),
        }
        if entity_id.startswith("C3_") or entity_id=="TABLE":
            row["inner_ring_physical_identity"]="review_not_verified"
        rows.append(row)
    return {
        "schema_version":SCHEMA,
        "policy":POLICY,
        "source_index":frame_transfer.get("source_index"),
        "semantic_gauge_id":gauge_id,
        "scaffold_unchanged":True,
        "refit_performed":False,
        "physical_facet_angle_status":"unavailable",
        "optic_quality_score":None,
        "entities":rows,
    }


def sample_sequence(scaffold, frames):
    """frames = iterable of (transfer, brightness, gauge_mask, valid_mask, normalized_or_None)."""
    results=[]
    for transfer, brightness, gauge_mask, valid_mask, normalized in frames:
        results.append(sample_fixed_frame(
            scaffold,transfer,brightness,gauge_mask,valid_mask,
            normalized_brightness=normalized
        ))
    semantic_ids=[row["semantic_id"] for row in results[0]["entities"]] if results else []
    if any([row["semantic_id"] for row in rec["entities"]] != semantic_ids
           for rec in results):
        raise ValueError("semantic identities changed across observations")
    return {
        "schema_version":SCHEMA,
        "status":"smoke_test_of_fixed_image_support_not_physical_optical_model",
        "frames":results,
        "fixed_semantic_ids":semantic_ids,
        "counts":{"frames":len(results),"entities":len(semantic_ids)},
        "no_physical_angles_or_quality_scores":True,
    }


def save_report(scaffold, frames, path):
    result=sample_sequence(scaffold,frames)
    dst=Path(path)
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return result
