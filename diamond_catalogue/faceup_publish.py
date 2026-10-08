"""Automated storage-neutral catalogue overview thumbnail generation.

No human approval: source SHA verification, outer-silhouette checks and a
deterministic original-colour crop. An uncertain crown pose is labeled as
such and remains useful only as a generic table thumbnail.
"""
from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlsplit

from .faceup_thumbnail import SCHEMA, generate_candidate
from .models import CatalogueError, PlannedAsset


def plan_generated_thumbnail(manifest: dict, record: dict, payload: bytes):
    if record.get("schema") != SCHEMA or record.get("diamond_id") != manifest.get("id"):
        raise CatalogueError("Generated thumbnail identity does not match manifest")
    if record.get("status") not in {
        "likely_crown_candidate", "unverified_pose_candidate", "unverified_still_crop"
    }:
        raise CatalogueError("No suitable geometry thumbnail to publish")
    source = record.get("source") or {}
    derivative = record.get("derivative") or {}
    digest = sha256(payload).hexdigest()
    if (not payload or digest != derivative.get("sha256")
            or len(payload) != derivative.get("byte_count")
            or derivative.get("media_type") != "image/webp"
            or not source.get("sha256")
            or not derivative.get("crop_source_bbox_xyxy")):
        raise CatalogueError("Generated thumbnail payload does not match its derivation")
    if source.get("evidence_kind") == "rotation":
        pos=source.get("frame_position")
        matches=any(
            e.get("kind") == "rotation" and e.get("status") == "success"
            and isinstance(pos,int) and 0 <= pos < len(e.get("frames",[]))
            and e["frames"][pos]["asset"]["sha256"] == source["sha256"]
            and e["frames"][pos]["source_index"] == source.get("source_index")
            for e in manifest.get("evidence",[])
        )
    elif source.get("evidence_kind") == "still":
        matches=any(
            e.get("kind") == "still" and e.get("status") == "success"
            and (e.get("payload_asset") or {}).get("sha256") == source["sha256"]
            for e in manifest.get("evidence",[])
        )
    else:
        matches=False
    if not matches:
        raise CatalogueError("Generated thumbnail source hash has no saved provenance")
    asset=PlannedAsset(
        asset_id=digest,diamond_id=manifest["id"],
        desired_name="asset-"+digest+".webp",
        sha256=digest,byte_count=len(payload),media_type="image/webp",payload=payload,
    )
    metadata={
        "source":dict(source),
        "crop_source_bbox_xyxy":list(derivative["crop_source_bbox_xyxy"]),
        "derivation":{
            "schema":record["schema"],
            "algorithm":record.get("algorithm"),
            "selection":record.get("selection"),
            "candidate_status":record["status"],
            "physical_angle_calibrated":False,
        },
        "generation":{
            "status":"automatic",
            "pose_status":"likely_crown" if record["status"] == "likely_crown_candidate"
                          else "unverified",
            "human_verified":False,
        },
    }
    return asset,metadata


def publish_generated_thumbnail(manifest: dict, *, fetch_bytes, storage, catalogue):
    """Generate, content-hash, upload, and atomically add only an overview icon."""
    if (manifest.get("derived_media") or {}).get("overview_thumbnail"):
        return None
    record,payload,_=generate_candidate(manifest,fetch_bytes=fetch_bytes)
    if not payload:
        return None
    asset,metadata=plan_generated_thumbnail(manifest,record,payload)
    published=storage.publish((asset,))[asset.asset_id]
    url=urlsplit(published.url)
    if (published.sha256 != asset.sha256 or published.byte_count != asset.byte_count
            or not published.locator or not published.backend
            or url.scheme != "https" or not url.hostname or url.username or url.password):
        raise CatalogueError("Storage did not confirm immutable generated thumbnail")
    metadata["asset"]={
        "sha256":asset.sha256,"byte_count":asset.byte_count,
        "media_type":"image/webp",
        "storage":{"backend":published.backend,"locator":published.locator,
                   "url":published.url},
    }
    return catalogue.attach_generated_thumbnail(manifest["id"],metadata)
