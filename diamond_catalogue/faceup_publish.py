"""Human-reviewed and hash-bound publication of original-colour thumbnails."""
from __future__ import annotations
from hashlib import sha256
from urllib.parse import urlsplit

from .models import PlannedAsset, CatalogueError
from .faceup_thumbnail import SCHEMA, generate_candidate


def plan_reviewed_thumbnail(manifest, record, payload, *, approved_image_sha,
                            approved_source_sha, reviewer):
    """Reject all unapproved/still-only/untraceable thumbnail candidates."""
    if record.get("schema") != SCHEMA or record.get("diamond_id") != manifest.get("id"):
        raise CatalogueError("Thumbnail candidate identity mismatch")
    if (record.get("status") not in {"likely_crown_candidate", "unverified_pose_candidate"}
            or record.get("review_status") != "unverified"):
        raise CatalogueError("No source-frame thumbnail available for manual approval")
    source = record.get("source") or {}
    derivative = record.get("derivative") or {}
    digest = sha256(payload).hexdigest()
    if (digest != approved_image_sha or digest != derivative.get("sha256")
            or source.get("sha256") != approved_source_sha
            or source.get("evidence_kind") != "rotation"
            or not reviewer or len(approved_source_sha) != 64):
        raise CatalogueError("Approved candidate hash/source did not match")
    pos=source.get("frame_position")
    if not any(
        entry.get("kind") == "rotation"
        and isinstance(pos,int) and 0 <= pos < len(entry.get("frames", []))
        and entry["frames"][pos]["asset"]["sha256"] == approved_source_sha
        and entry["frames"][pos]["source_index"] == source["source_index"]
        for entry in manifest.get("evidence", [])
    ):
        raise CatalogueError("Approved image is not tied to published original frame")
    if len(payload) != derivative.get("byte_count") or derivative.get("media_type") != "image/webp":
        raise CatalogueError("Derivative media changed after human review")
    asset=PlannedAsset(
        asset_id=digest, diamond_id=manifest["id"],
        desired_name="asset-"+digest+".webp",
        sha256=digest, byte_count=len(payload), media_type="image/webp",
        payload=payload,
    )
    meta={
        "source":dict(source),
        "crop_source_bbox_xyxy":list(derivative["crop_source_bbox_xyxy"]),
        "derivation":{"schema":record["schema"],"algorithm":record["algorithm"],
                      "selection":record.get("selection"),
                      "candidate_status":record["status"],
                      "physical_angle_calibrated":False},
        "review":{"status":"verified","method":"human_visual","reviewer":str(reviewer),
                  "candidate_sha256":digest,"approved_source_sha256":approved_source_sha},
    }
    return asset,meta


def publish_reviewed_thumbnail(manifest, *, fetch_bytes, storage, catalogue,
                               approved_image_sha, approved_source_sha, reviewer):
    """Regenerate from immutable sources and commit only matching approved bytes."""
    record,payload,_=generate_candidate(manifest,fetch_bytes=fetch_bytes)
    if not payload:
        raise CatalogueError("No thumbnail candidate available for approval")
    asset,metadata=plan_reviewed_thumbnail(
        manifest,record,payload,approved_image_sha=approved_image_sha,
        approved_source_sha=approved_source_sha,reviewer=reviewer,
    )
    resolved=storage.publish((asset,))[asset.asset_id]
    if (resolved.sha256 != asset.sha256 or resolved.byte_count != asset.byte_count
            or not resolved.locator or not resolved.backend
            or urlsplit(resolved.url).scheme != "https"):
        raise CatalogueError("Storage derivative integrity/URL verification failed")
    metadata["asset"]={
        "sha256":asset.sha256,"byte_count":asset.byte_count,"media_type":"image/webp",
        "storage":{"backend":resolved.backend,"locator":resolved.locator,"url":resolved.url},
    }
    return catalogue.attach_verified_thumbnail(manifest["id"],metadata)
