"""Small deterministic static index consumed by GitHub Pages (#108)."""
from __future__ import annotations

from .merge import _check_manifest
from .models import INDEX_SCHEMA, CatalogueError
from .serialization import canonical_json


def index_row(manifest: dict) -> dict:
    _check_manifest(manifest)
    listings = sorted(manifest["listings"], key=lambda obs: (obs["observed_at"], obs["url"]))
    latest = listings[-1] if listings else {}
    retrievals = sorted(manifest["retrievals"], key=lambda r: (r["retrieved_at"], r["listing_url"]))
    status = retrievals[-1]["status"] if retrievals else "unknown"
    # Index selects one stable visual locator, never infers a face-up physical angle.
    thumbnail = None
    for kind in ("still", "rotation"):
        for evidence in manifest["evidence"]:
            if evidence["kind"] != kind or evidence["status"] != "success":
                continue
            ref = evidence.get("payload_asset") if kind == "still" else (
                evidence.get("frames") or [{}]
            )[0].get("asset")
            if ref and ref.get("storage"):
                thumbnail = ref["storage"]["url"]
                break
        if thumbnail:
            break
    # Reviewed/approved derivatives are opt-in and never replace original evidence.
    derived = (manifest.get("derived_media") or {}).get("face_up_thumbnail") or {}
    face_up_thumbnail = None
    if (derived.get("review") or {}).get("status") == "verified":
        face_up_thumbnail = (derived.get("asset") or {}).get("storage", {}).get("url")
    metadata = manifest["diamond_metadata"]
    return {
        "id": manifest["id"], "manifest_path": f"data/diamonds/{manifest['id']}.json",
        "lab": manifest["identity"]["lab"],
        "report_number": manifest["identity"]["report_number"],
        "retailer": latest.get("retailer"), "source_url": latest.get("url"),
        "carat": metadata.get("carat"), "colour": metadata.get("colour"),
        "clarity": metadata.get("clarity"), "shape": metadata.get("shape"),
        "dimensions": metadata.get("dimensions"),
        "price": latest.get("price"), "currency": latest.get("currency"),
        "tax_basis": latest.get("tax_basis"),
        "retrieval_status": status,
        "has_motion": any(e["kind"] in {"rotation", "video"} and e["status"] == "success"
                          and (e.get("frames") or e.get("payload_asset")) for e in manifest["evidence"]),
        "thumbnail_url": thumbnail,
        **({"face_up_thumbnail_url": face_up_thumbnail} if face_up_thumbnail else {}),
    }


def build_index(manifests) -> dict:
    rows = [index_row(manifest) for manifest in manifests]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise CatalogueError("Multiple manifests for the same certified diamond")
    result = {"schema": INDEX_SCHEMA, "diamonds": sorted(rows, key=lambda r: r["id"])}
    canonical_json(result)
    return result
