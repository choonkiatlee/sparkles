"""Conservative, deterministic manifest upsert without losing older evidence."""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation

from .identity import diamond_id
from .models import CatalogueError, SCHEMA
from .serialization import canonical_json

_CERT_FIELDS = ("shape", "origin", "carat", "colour", "clarity", "dimensions", "reported_proportions")


def _equivalent(left, right) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left == right
    if isinstance(left, (int, float, str)) and isinstance(right, (int, float, str)):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return str(left).strip().upper() == str(right).strip().upper()
    return left == right


def _unique_sorted(items: list[dict], key):
    seen = {}
    for value in items:
        identity = key(value)
        if identity in seen and canonical_json(seen[identity]) != canonical_json(value):
            # Same observation at same timestamp with different content is not an idempotent update.
            raise CatalogueError("Conflicting catalogue entries share a logical key")
        seen[identity] = value
    return [seen[k] for k in sorted(seen)]


def _check_manifest(manifest: dict) -> None:
    if manifest.get("schema") != SCHEMA:
        raise CatalogueError("Unsupported diamond catalogue schema")
    identity = manifest.get("identity") or {}
    if diamond_id(identity.get("lab"), identity.get("report_number")) != manifest.get("id"):
        raise CatalogueError("Diamond manifest identity/ID mismatch")
    for evidence in manifest.get("evidence", []):
        references = ([evidence.get("payload_asset")] if evidence.get("payload_asset") else [])
        references += [frame["asset"] for frame in evidence.get("frames", [])]
        for ref in references:
            if not (ref.get("storage") or {}).get("url"):
                raise CatalogueError("Unpublished evidence asset in catalogue manifest")
    thumbnail = (manifest.get("derived_media") or {}).get("overview_thumbnail")
    if thumbnail is not None:
        asset = thumbnail.get("asset") or {}
        source = thumbnail.get("source") or {}
        if (not (asset.get("storage") or {}).get("url")
                or not source.get("sha256")
                or not asset.get("sha256")
                or not thumbnail.get("crop_source_bbox_xyxy")):
            raise CatalogueError("Unpublished or untraceable overview thumbnail")
    canonical_json(manifest)


def merge_manifest(existing: dict | None, incoming: dict) -> dict:
    """Upsert certified identity, append observations, retain older valid evidence."""
    _check_manifest(incoming)
    if existing is None:
        merged = copy.deepcopy(incoming)
    else:
        _check_manifest(existing)
        if existing["id"] != incoming["id"] or existing["identity"] != incoming["identity"]:
            raise CatalogueError("Refusing to merge different certified diamonds")
        merged = copy.deepcopy(existing)
        old_meta, new_meta = merged["diamond_metadata"], incoming["diamond_metadata"]
        for field in _CERT_FIELDS:
            older, newer = old_meta.get(field), new_meta.get(field)
            if older is not None and newer is not None and not _equivalent(older, newer):
                raise CatalogueError(f"Conflicting certified metadata: {field}")
            if older is None and newer is not None:
                old_meta[field] = newer
        old_meta.setdefault("attribution", {}).update({
            k: v for k, v in new_meta.get("attribution", {}).items()
            if k not in old_meta.get("attribution", {})
        })
        for field in ("listings", "retrievals", "evidence"):
            merged[field].extend(copy.deepcopy(incoming[field]))

    merged["listings"] = _unique_sorted(
        merged["listings"], lambda x: (x["observed_at"], x["url"], x.get("retailer_sku") or "")
    )
    merged["retrievals"] = _unique_sorted(
        merged["retrievals"], lambda x: (x["retrieved_at"], x["listing_url"])
    )
    merged["evidence"] = _unique_sorted(merged["evidence"], lambda x: x["record_key"])
    _check_manifest(merged)
    return merged
