"""Pure DiamondResult -> publication plan, then validated URL finalization."""
from __future__ import annotations

import copy
import hashlib
from urllib.parse import urlsplit
from typing import Mapping

from diamond_retrieval.models import (
    CertificateEvidence, DiamondResult, EvidenceStatus, IdentityOutcome,
    RotationEvidence, StillEvidence, VideoEvidence,
)

from .identity import diamond_id, normalize_identity
from .models import CatalogueError, PlannedAsset, PublicationPlan, PublishedAsset, SCHEMA
from .serialization import canonical_json, json_value, provenance_steps

_MEDIA_EXTENSIONS = {
    "application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
    "image/webp": ".webp", "image/gif": ".gif", "video/mp4": ".mp4",
    "video/webm": ".webm", "application/octet-stream": ".bin",
}


def _media_type(evidence, *, frame: bool = False) -> str:
    if frame:
        return "image/jpeg"  # #97 motion frames are original JPEG source bytes.
    declared = getattr(evidence, "media_type", None) or evidence.metadata.get("media_type")
    if declared:
        return str(declared).split(";", 1)[0].strip().lower()
    kind = str(evidence.kind)
    if kind == "certificate":
        return "application/pdf"
    if kind == "still":
        return "image/jpeg"
    return "application/octet-stream"


def _asset_reference(asset: PlannedAsset) -> dict:
    return {"asset_id": asset.asset_id, "sha256": asset.sha256,
            "byte_count": asset.byte_count, "media_type": asset.media_type,
            "storage": None}


def plan_publication(result: DiamondResult) -> PublicationPlan:
    """Plan source-preserving publication without side effects or binary JSON."""
    lab, report = normalize_identity(result.metadata.lab, result.metadata.report_number)
    identifier = diamond_id(lab, report)
    if any(c.outcome == IdentityOutcome.CONFLICT for c in result.identity_comparisons):
        raise CatalogueError("Identity comparison conflict: refusing publication")

    assets: dict[str, PlannedAsset] = {}

    def add_asset(payload: bytes, media_type: str) -> dict:
        if not isinstance(payload, bytes) or not payload:
            raise CatalogueError("Empty/non-byte source evidence must not be published")
        digest = hashlib.sha256(payload).hexdigest()
        media_type = media_type.lower()
        if media_type not in _MEDIA_EXTENSIONS:
            # Unknown evidence kinds remain extensible; never guess their extension.
            media_type = "application/octet-stream"
        existing = assets.get(digest)
        if existing and existing.media_type != media_type:
            raise CatalogueError("Same source bytes have conflicting media types")
        if not existing:
            assets[digest] = PlannedAsset(
                asset_id=digest, diamond_id=identifier,
                desired_name=f"asset-{digest}{_MEDIA_EXTENSIONS[media_type]}",
                sha256=digest, byte_count=len(payload), media_type=media_type,
                payload=payload,
            )
        return _asset_reference(assets[digest])

    manifest_evidence = []
    for item in result.evidence:
        item_status = str(item.status.value) if isinstance(item.status, EvidenceStatus) else str(item.status)
        entry = {
            "identifier": item.identifier,
            "kind": str(item.kind),
            "status": item_status,
            "provenance": provenance_steps(item.provenance),
            "metadata": {k: json_value(v) for k, v in item.metadata.items()
                         if k in {"sha256", "media_type", "extraction_status", "extraction_error", "format", "supplier", "frame_count", "dimensions", "sequence_complete", "physical_angle_calibrated", "ordering"}},
            "identity_observations": [
                {"field": obs.field, "value": json_value(obs.value),
                 "provenance": provenance_steps(obs.provenance)}
                for obs in item.identity_observations
            ],
            "payload_asset": None,
        }
        if item.payload and not (isinstance(item, RotationEvidence) and item.frames):
            expected_hash = item.metadata.get("sha256")
            if expected_hash is not None and str(expected_hash).lower() != hashlib.sha256(item.payload).hexdigest():
                raise CatalogueError("Evidence payload SHA-256 mismatch")
            entry["payload_asset"] = add_asset(item.payload, _media_type(item))
        if isinstance(item, CertificateEvidence):
            entry["extracted_fields"] = json_value(item.extracted_fields)
        if isinstance(item, StillEvidence):
            entry["dimensions"] = json_value(item.dimensions)
        if isinstance(item, VideoEvidence):
            entry["media_type"] = _media_type(item)
        if isinstance(item, RotationEvidence):
            entry["face_up_hint"] = json_value(item.face_up_hint)
            frames = []
            for frame in item.frames:
                if hashlib.sha256(frame.payload).hexdigest() != frame.sha256.lower():
                    raise CatalogueError("Rotation frame SHA-256 mismatch")
                if len(frame.dimensions) != 2 or min(frame.dimensions) <= 0 or frame.source_index < 0:
                    raise CatalogueError("Invalid rotation frame dimensions/index")
                frames.append({
                    "source_index": frame.source_index,
                    "stored_position": frame.stored_position,
                    "source_batch": frame.source_batch,
                    "dimensions": list(frame.dimensions),
                    "asset": add_asset(frame.payload, _media_type(item, frame=True)),
                })
            entry["frames"] = frames  # Preserve original order, even with repeated bytes.
        # The record key includes physical evidence identity and source provenance, but not observation time.
        identity_material = {"identifier": entry["identifier"], "kind": entry["kind"],
                             "provenance": entry["provenance"], "payload_asset": entry["payload_asset"],
                             "frames": entry.get("frames", [])}
        entry["record_key"] = hashlib.sha256(canonical_json(identity_material).encode()).hexdigest()
        manifest_evidence.append(entry)

    metadata = result.metadata
    fields = ("origin", "shape", "carat", "colour", "clarity", "dimensions", "reported_proportions")
    diamond_metadata = {field: json_value(getattr(metadata, field)) for field in fields}
    diamond_metadata["attribution"] = {
        k: {"source": v.source, "locator": v.locator}
        for k, v in sorted(metadata.attribution.items()) if k in fields
    }
    observation = {
        "url": result.listing_url,
        "retailer": urlsplit(result.listing_url).hostname,
        "retailer_sku": metadata.retailer_sku,
        "observed_at": json_value(result.retrieved_at),
        "price": json_value(metadata.price),
        "currency": metadata.currency,
        "tax_basis": metadata.tax_basis,
    }
    attempts = [
        {"reference_identifier": a.reference_identifier, "kind": str(a.kind),
         "retrieval_key": a.retrieval_key, "status": a.status.value,
         "message": a.message, "locator": a.locator, "provenance": provenance_steps(a.provenance)}
        for a in result.attempts
    ]
    identity_comparisons = [
        {"field": c.field, "outcome": c.outcome.value,
         "values": json_value(c.values), "provenance": provenance_steps(c.provenance)}
        for c in result.identity_comparisons
    ]
    retrieval = {
        "retrieved_at": json_value(result.retrieved_at), "listing_url": result.listing_url,
        "status": result.status.value, "completion_reasons": list(result.completion_reasons),
        "certificate_link": result.certificate_link,
        "attempts": attempts, "identity_comparisons": identity_comparisons,
        "provenance": provenance_steps(result.provenance),
    }
    manifest = {
        "schema": SCHEMA, "id": identifier,
        "identity": {"lab": lab, "report_number": report},
        "diamond_metadata": diamond_metadata,
        "listings": [observation], "retrievals": [retrieval],
        "evidence": manifest_evidence,
    }
    # Fail now if any arbitrary metadata accidentally attempts to include raw bytes.
    canonical_json(manifest)
    return PublicationPlan(identifier, manifest, tuple(sorted(assets.values(), key=lambda a: a.asset_id)))


def _valid_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def finalize_manifest(plan: PublicationPlan, published: Mapping[str, PublishedAsset]) -> dict:
    """Materialise a publishable manifest only after every planned asset is resolved."""
    if not set(a.asset_id for a in plan.assets).issubset(published):
        raise CatalogueError("Cannot commit manifest: one or more assets were not published")
    verified = {}
    for asset in plan.assets:
        target = published[asset.asset_id]
        if hashlib.sha256(asset.payload).hexdigest() != asset.sha256 or len(asset.payload) != asset.byte_count:
            raise CatalogueError("Source bytes mutated between planning and publication")
        if target.sha256 != asset.sha256 or target.byte_count != asset.byte_count:
            raise CatalogueError("Published asset does not match planned source")
        if not target.backend or not target.locator or not _valid_url(target.url):
            raise CatalogueError("Published asset has no valid public HTTPS locator")
        verified[asset.asset_id] = {"backend": target.backend, "locator": target.locator, "url": target.url}

    manifest = copy.deepcopy(plan.manifest)
    for evidence in manifest["evidence"]:
        refs = ([evidence["payload_asset"]] if evidence["payload_asset"] is not None else [])
        refs += [frame["asset"] for frame in evidence.get("frames", [])]
        for ref in refs:
            ref["storage"] = verified[ref.pop("asset_id")]
    canonical_json(manifest)
    return manifest
