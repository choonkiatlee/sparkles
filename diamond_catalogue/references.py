"""Git-native, agent-authored educational reference diamonds (#195).

Reference identity is deliberately weaker than a certified catalogue diamond.
These records carry curated commentary and source hints; future technical media
enrichment may attach the *existing* catalogue evidence shape without rewriting
the curator's statements.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .identity import diamond_id, normalize_identity
from .models import CatalogueError
from .serialization import json_document

SCHEMA = "sparkles-reference/1"
INDEX_SCHEMA = "sparkles-reference-index/1"
ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "data" / "references"
INDEX_PATH = ROOT / "data" / "reference-index.json"
DIAMOND_DIR = ROOT / "data" / "diamonds"
CATALOGUE_INDEX = ROOT / "data" / "catalog.json"

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_TAG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_CARAT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_FIELDS = {
    "schema", "id", "label", "identity", "linked_diamond_id",
    "diamond_metadata", "commentary", "source_links", "media_sources",
    "topics", "evidence", "enrichment_attempts",
}
_METADATA_FIELDS = {
    "shape", "carat", "colour", "clarity", "origin", "dimensions",
    "reported_proportions",
}


def _object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise CatalogueError(f"{name} must be an object")
    return value


def _text(value: object, name: str, *, max_length: int = 8000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise CatalogueError(f"{name} must be nonempty text (max {max_length})")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise CatalogueError(f"{name} has control characters")
    return value


def _url(value: object, name: str) -> str:
    text = _text(value, name, max_length=2048)
    if any(c.isspace() or ord(c) == 127 for c in text):
        raise CatalogueError(f"{name} has unsafe URL characters")
    try:
        parts = urlsplit(text)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise CatalogueError(f"{name} has an invalid URL") from exc
    if (parts.scheme != "https" or not host or parts.username is not None
            or parts.password is not None or port not in (None, 443)
            or not parts.netloc or host == "localhost" or host.endswith((".local", ".internal"))):
        raise CatalogueError(f"{name} requires a public HTTPS URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.startswith("."):
            raise CatalogueError(f"{name} requires a public hostname")
    else:
        # No IP-literal URLs, even if apparently public: avoid future SSRF
        # when an enrichment workflow is introduced.
        raise CatalogueError(f"{name} cannot be an IP address")
    return text


def _links(value: object, field: str, *, required: bool) -> None:
    if not isinstance(value, list) or (required and not value):
        raise CatalogueError(f"{field} must be a {'nonempty ' if required else ''}list")
    seen = set()
    for item in value:
        obj = _object(item, field + " item")
        allowed = {"kind", "url", "note"} if field == "source_links" else {
            "kind", "url", "provider", "status"
        }
        if set(obj) - allowed:
            raise CatalogueError(f"{field} has unknown fields")
        kind = _text(obj.get("kind"), f"{field}.kind", max_length=60)
        url = _url(obj.get("url"), f"{field}.url")
        if (kind, url) in seen:
            raise CatalogueError(f"{field} contains duplicate link")
        seen.add((kind, url))
        if field == "source_links":
            if obj.get("note") is not None:
                _text(obj["note"], f"{field}.note", max_length=500)
        else:
            if kind not in {"viewer", "still", "video"}:
                raise CatalogueError("Unrecognized media source kind")
            _text(obj.get("provider"), "media_sources.provider", max_length=80)
            if obj.get("status") != "linked_unverified":
                raise CatalogueError("Curated media URLs must start as linked_unverified")


def validate_reference(value: dict, *, expected_id: str | None = None,
                       diamond_dir: Path | None = None) -> dict:
    """Validate a reference without promoting a viewer ID to a certificate."""
    ref = _object(value, "reference")
    if set(ref) - _FIELDS:
        raise CatalogueError("Unknown reference fields")
    if ref.get("schema") != SCHEMA:
        raise CatalogueError("Unsupported reference schema")
    identifier = _text(ref.get("id"), "id", max_length=96)
    if not _ID.fullmatch(identifier) or identifier.startswith("ref-"):
        raise CatalogueError("Invalid reference id (do not include basket prefix)")
    if expected_id is not None and identifier != expected_id:
        raise CatalogueError("Reference filename/ID mismatch")
    _text(ref.get("label"), "label", max_length=180)
    _text(ref.get("commentary"), "commentary", max_length=8000)
    identity = _object(ref.get("identity"), "identity")
    if set(identity) != {"status", "lab", "report_number"}:
        raise CatalogueError("identity needs exactly status, lab and report_number")
    status = identity["status"]
    if status not in {"unverified", "reported", "linked"}:
        raise CatalogueError("Unknown reference identity status")
    lab, report = identity["lab"], identity["report_number"]
    if lab is not None:
        _text(lab, "identity.lab", max_length=100)
    if report is not None:
        _text(report, "identity.report_number", max_length=100)
        if lab is None or status == "unverified":
            raise CatalogueError("A reported certificate requires lab and reported/linked status")
        normalize_identity(lab, report)
    elif status != "unverified":
        raise CatalogueError("Reported/linked identity requires a full certificate")
    linked = ref.get("linked_diamond_id")
    if linked is not None:
        if status != "linked" or linked != diamond_id(lab, report):
            raise CatalogueError("Verified catalogue link does not match certified identity")
        path = (diamond_dir or DIAMOND_DIR) / f"{linked}.json"
        try:
            certified = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CatalogueError("Linked certified manifest does not exist or is invalid") from exc
        if (certified.get("id") != linked or
                (certified.get("identity") or {}).get("lab") != normalize_identity(lab, report)[0] or
                (certified.get("identity") or {}).get("report_number") != normalize_identity(lab, report)[1]):
            raise CatalogueError("Linked certified manifest identity mismatch")
    elif status == "linked":
        raise CatalogueError("Linked identity requires an existing certified diamond")
    metadata = _object(ref.get("diamond_metadata"), "diamond_metadata")
    if set(metadata) - _METADATA_FIELDS:
        raise CatalogueError("Unsupported reference metadata field")
    for name in ("shape", "colour", "clarity", "origin"):
        if metadata.get(name) is not None:
            _text(metadata[name], f"diamond_metadata.{name}", max_length=90)
    carat = metadata.get("carat")
    if carat is not None and (
        isinstance(carat, bool) or not isinstance(carat, (str, int, float)) or
        not _CARAT.fullmatch(str(carat)) or float(carat) <= 0
    ):
        raise CatalogueError("Invalid reference carat")
    if "dimensions" in metadata and metadata["dimensions"] is not None:
        dims = metadata["dimensions"]
        if not isinstance(dims, list) or len(dims) < 2 or not all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and 0 < x < 100
            for x in dims
        ):
            raise CatalogueError("Invalid reference dimensions")
    if "reported_proportions" in metadata and metadata["reported_proportions"] is not None:
        _object(metadata["reported_proportions"], "reported_proportions")
    _links(ref.get("source_links"), "source_links", required=True)
    _links(ref.get("media_sources", []), "media_sources", required=False)
    topics = ref.get("topics", [])
    if not isinstance(topics, list) or len(topics) != len(set(map(str, topics))):
        raise CatalogueError("topics must contain unique strings")
    for topic in topics:
        if not isinstance(topic, str) or len(topic) > 70 or not _TAG.fullmatch(topic):
            raise CatalogueError("Invalid topic slug")
    evidence = ref.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(e, dict) for e in evidence):
        raise CatalogueError("evidence must be a list of records")
    for record in evidence:
        if record.get("kind") not in {"certificate", "still", "rotation", "video"} or (
            record.get("status") not in {"success", "extraction_failed"}
        ):
            raise CatalogueError("Invalid published reference evidence kind or status")
        if not isinstance(record.get("record_key"), str) or not re.fullmatch(
            r"[a-f0-9]{64}", record["record_key"]
        ):
            raise CatalogueError("Invalid published evidence record key")
        asset = record.get("payload_asset")
        frames = record.get("frames", [])
        if record["kind"] == "rotation":
            if record["status"] != "success" or not isinstance(frames, list) or len(frames) != 256:
                raise CatalogueError("Reference rotation must have a verified complete 256-frame sequence")
            indices = [frame.get("source_index") for frame in frames if isinstance(frame, dict)]
            if indices != list(range(256)):
                raise CatalogueError("Reference rotation has incomplete or unordered source frames")
            if asset is not None:
                raise CatalogueError("Reference rotations may not pretend a bundle is playable motion")
            for frame in frames:
                _stored_asset(frame.get("asset"))
        elif asset is None:
            raise CatalogueError("Published reference still/video/PDF lacks stored asset")
        else:
            _stored_asset(asset)
    attempts = ref.get("enrichment_attempts", [])
    if not isinstance(attempts, list) or len(attempts) > 3000:
        raise CatalogueError("Invalid reference enrichment attempt list")
    for attempt in attempts:
        obj = _object(attempt, "enrichment attempt")
        if set(obj) != {"reference_identifier", "kind", "status", "locator"}:
            raise CatalogueError("Invalid enrichment attempt fields")
        _text(obj["reference_identifier"], "enrichment.reference_identifier", max_length=180)
        if obj["kind"] not in {"certificate", "still", "rotation", "video"}:
            raise CatalogueError("Invalid enrichment attempt kind")
        if obj["status"] not in {
            "success", "unsupported", "missing", "download_failed",
            "processing_failed", "extraction_failed", "invalid_payload",
            "resolution_failed", "resolution_limit", "resolved", "duplicate",
            "not_requested",
        }:
            raise CatalogueError("Invalid enrichment attempt status")
        if obj["locator"] is not None:
            _text(obj["locator"], "enrichment.locator", max_length=2048)
    return ref


def _stored_asset(value: object) -> None:
    asset = _object(value, "stored asset")
    if (not isinstance(asset.get("sha256"), str) or
            not re.fullmatch(r"[a-f0-9]{64}", asset["sha256"]) or
            not isinstance(asset.get("byte_count"), int) or
            isinstance(asset["byte_count"], bool) or asset["byte_count"] <= 0):
        raise CatalogueError("Invalid published reference source hash/size")
    storage = _object(asset.get("storage"), "published storage")
    _url(storage.get("url"), "published reference asset URL")
    if not storage.get("backend") or not storage.get("locator"):
        raise CatalogueError("Published reference asset needs a storage locator")


def index_row(manifest: dict) -> dict:
    validate_reference(manifest)
    meta = manifest["diamond_metadata"]
    sources = manifest["source_links"]
    evidence = manifest.get("evidence", [])
    has_motion = any(
        e.get("status") == "success" and e.get("kind") in ("rotation", "video") and
        (e.get("frames") or e.get("payload_asset")) for e in evidence
    )
    thumb = None
    for kind in ("still", "rotation"):
        for item in evidence:
            if item.get("status") != "success" or item.get("kind") != kind:
                continue
            asset = item.get("payload_asset") if kind == "still" else (
                (item.get("frames") or [{}])[0].get("asset")
            )
            url = ((asset or {}).get("storage") or {}).get("url")
            if url:
                thumb = _url(url, "published thumbnail")
                break
        if thumb:
            break
    return {
        "id": manifest["id"],
        "selection_id": f"ref-{manifest['id']}",
        "manifest_path": f"data/references/{manifest['id']}.json",
        "label": manifest["label"],
        "lab": manifest["identity"]["lab"],
        "report_number": manifest["identity"]["report_number"],
        "identity_status": manifest["identity"]["status"],
        "linked_diamond_id": manifest.get("linked_diamond_id"),
        "carat": meta.get("carat"),
        "shape": meta.get("shape"),
        "colour": meta.get("colour"),
        "clarity": meta.get("clarity"),
        "source_url": sources[0]["url"],
        "topics": manifest.get("topics", []),
        "commentary_excerpt": manifest["commentary"][:180],
        "has_motion": bool(has_motion),
        "thumbnail_url": thumb,
    }


def build_index(manifests: list[dict], *, certified_ids=()) -> dict:
    rows = [index_row(record) for record in manifests]
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise CatalogueError("Duplicate reference ID")
    basket_ids = [r["selection_id"] for r in rows]
    if len(set(basket_ids)) != len(basket_ids) or set(basket_ids) & set(certified_ids):
        raise CatalogueError("Shared comparison basket ID collision")
    # Two references claiming the same full report require manual reconciliation,
    # never silently merge and lose curated commentary.
    reports = [diamond_id(r["lab"], r["report_number"]) for r in rows
               if r["lab"] and r["report_number"]]
    if len(set(reports)) != len(reports):
        raise CatalogueError("Duplicate reported certificate across references")
    return {"schema": INDEX_SCHEMA, "references": sorted(rows, key=lambda r: r["id"])}


def build_repository_index(*, directory: Path = REFERENCE_DIR,
                           catalogue_index: Path = CATALOGUE_INDEX,
                           diamond_dir: Path = DIAMOND_DIR) -> dict:
    if not directory.is_dir():
        raise CatalogueError("Missing reference directory")
    manifests = []
    for path in sorted(directory.glob("*.json")):
        if not path.is_file() or path.is_symlink():
            raise CatalogueError("Unsafe reference manifest path")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validate_reference(manifest, expected_id=path.stem, diamond_dir=diamond_dir)
        manifests.append(manifest)
    certified_ids = ()
    if catalogue_index.is_file():
        catalogue = json.loads(catalogue_index.read_text(encoding="utf-8"))
        if not isinstance(catalogue, dict) or not isinstance(catalogue.get("diamonds"), list):
            raise CatalogueError("Malformed certified catalogue index")
        certified_ids = (row["id"] for row in catalogue["diamonds"])
    return build_index(manifests, certified_ids=certified_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate the static learning-reference index")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail when index is stale")
    group.add_argument("--write", action="store_true", help="regenerate index")
    args = parser.parse_args()
    try:
        document = json_document(build_repository_index())
        if args.write:
            INDEX_PATH.write_text(document, encoding="utf-8")
            print(f"Wrote {INDEX_PATH.relative_to(ROOT)}")
        elif not INDEX_PATH.is_file() or INDEX_PATH.read_text(encoding="utf-8") != document:
            parser.error("Reference index missing/stale: run python -m diamond_catalogue.references --write")
    except (CatalogueError, ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
