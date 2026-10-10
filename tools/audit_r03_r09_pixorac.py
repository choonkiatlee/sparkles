"""Read-only cache validation for R03/R09 Pixorac frames seen in exact browsers.

Requires the sanitized preceding browser audit. Numeric Loupe viewer keys are
NOT certificates. The source must have been observed at that exact viewer;
the cached frame order is proxy-index order, not verified supplier original.
No original bytes, personal media, identity, manifests or Releases are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.reference_media import _safe_source_url
from diamond_retrieval.resolvers import Loupe360CertificateResolver
from tools.audit_r03_r09_loupe import CASES, validate_route

PIXORAC_HOST = "assets-images.pixorac.com"
# Observed in exact R03/R09 browser request traces in successful Actions #38077318919.
# Source-specific pins; never accept arbitrary unrelated media/cache URLs.
ENCODED_ROOTS = {
    "R03": "aHR0cHM6Ly9sYWJncm93bnMzLnMzLmFwLXNvdXRoZWFzdC0xLmFtYXpvbmF3cy5jb20vc3RvbmVpbWFnZXMzNjAuaHRtbD9kPTExNDY1NTVfQjJD",
    "R09": "aHR0cHM6Ly92aWV3LmdlbTM2MC5pbi9nZW0zNjAuaHRtbD9kPTI1MDcyNDExMzYtVTYwLTMxMUE=",
}
FRAME_COUNT = 256
MAX_FRAME_BYTES = 1_500_000


def observed_source(name: str, audit: dict) -> str:
    """Prove exact browser loaded the vetted proxy, without guessing endpoints."""
    reference_id = CASES[name][0]
    matches = [c for c in audit.get("cases", []) if c.get("reference") == reference_id]
    if len(matches) != 1:
        raise ValueError("Exact reference browser evidence unavailable")
    case = matches[0]
    target_prefix = "/" + ENCODED_ROOTS[name] + "/"
    for step in case.get("browser", []):
        if step.get("input_route") != "landing":
            continue
        if (step.get("page") or {}).get("path") != urlsplit(validate_route(name, "")).path:
            continue
        for request in step.get("relevant_requests", []):
            info = request.get("resource") or {}
            path = info.get("path", "")
            if (
                info.get("host") == PIXORAC_HOST and
                path.startswith(target_prefix) and
                re.fullmatch(r"(?:0|1)[.]webp", path[len(target_prefix):]) and
                request.get("status") == 200 and
                request.get("mime_type") == "image/webp"
            ):
                return "https://" + PIXORAC_HOST + target_prefix[:-1]
    raise ValueError("No matching indexed WebP loaded by pinned exact browser")


def query_metadata(client, name: str, root: str) -> dict:
    """Metadata is source corroboration, NOT third-party certificate proof."""
    token = urlsplit(validate_route(name, "")).path.rsplit("/", 1)[-1]
    body = json.dumps({
        "query": Loupe360CertificateResolver._query,
        "variables": {"cert": token},
    }, separators=(",", ":")).encode()
    try:
        response = client.post(
            Loupe360CertificateResolver.endpoint, timeout=15, content=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if response.status_code != 200:
            return {"status": "metadata_http_unavailable", "http": response.status_code}
        data = json.loads(response.content)
        record = (data.get("data") or {}).get("certificate_by_cert_number")
        if data.get("errors") or not isinstance(record, dict):
            return {"status": "metadata_missing_or_invalid"}
        v360 = record.get("v360") or {}
        upstream = v360.get("url")
        if not isinstance(upstream, str):
            return {"status": "source_not_returned"}
        parts = urlsplit(upstream)
        # Exact cache-root match only, never assume the numeric viewer token
        # proves the returned cert belongs to the PriceScope stone.
        match = parts.scheme == "https" and parts.hostname == PIXORAC_HOST and upstream.rstrip("/") == root
        top = v360.get("top_index")
        count = v360.get("frame_count")
        result = {
            "status": "proxy_match" if match else "proxy_mismatch",
            "frame_count": count,
            "top_index": top if isinstance(top, int) and not isinstance(top, bool) and 0 <= top < FRAME_COUNT else None,
            "provider_report_present": bool(record.get("certNumber")),
            "provider_lab_present": bool(record.get("lab")),
            "identity_independently_verified": False,
        }
        if not match or count not in (255, 256) or isinstance(count, bool):
            result["status"] = "not_confirmed_indexed_proxy"
        return result
    except Exception as exc:
        return {"status": "metadata_transport_error", "error_type": type(exc).__name__}


def request_one(client, root: str, index: int, fmt: str) -> dict:
    if fmt not in {"jpg", "webp"} or not 0 <= index < FRAME_COUNT:
        raise ValueError("Invalid indexed-cache request")
    url = _safe_source_url(root + "/" + str(index) + "." + fmt)
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != PIXORAC_HOST or parts.query or parts.fragment:
        raise ValueError("Only pinned public Pixorac cache is permitted")
    try:
        response = client.get(url, timeout=15)
        data = response.content
        if response.status_code != 200:
            return {"http": response.status_code, "valid": False}
        if not 0 < len(data) <= MAX_FRAME_BYTES:
            return {"http": response.status_code, "valid": False, "reason": "frame_size"}
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            size = list(image.size)
            actual = image.format
        valid = actual == ("JPEG" if fmt == "jpg" else "WEBP")
        return {"http": 200, "valid": valid, "bytes": len(data), "dimensions": size,
                "sha256": hashlib.sha256(data).hexdigest(), "format": actual}
    except Exception as exc:
        return {"valid": False, "status": "unavailable", "error_type": type(exc).__name__}


def validate_full(client, root: str, fmt: str, first_samples: dict[int, dict], count: int = FRAME_COUNT) -> dict:
    if count not in (255, 256):
        raise ValueError("Only observed 255/256 indexed protocols are auditable")
    hashes = {}
    shapes = set()
    for idx in range(count):
        item = first_samples[idx] if idx in first_samples else request_one(client, root, idx, fmt)
        if not item.get("valid") or not item.get("sha256"):
            return {"status": "incomplete", "first_missing_index": idx}
        hashes[idx] = item["sha256"]
        shapes.add(tuple(item["dimensions"]))
    unique = len(set(hashes.values()))
    return {
        "status": (f"complete_{count}_proxy_frames" if unique >= 240 and len(shapes) == 1
                   else "inconsistent_or_effectively_static"),
        "frame_count": len(hashes), "distinct_hashes": unique,
        "dimensions": [list(s) for s in sorted(shapes)],
        "first_sha256": hashes[0], "last_sha256": hashes[count - 1],
        "ordered_hash_digest": hashlib.sha256(
            "".join(hashes[i] for i in range(count)).encode()
        ).hexdigest(),
        "supplier_original_bytes_verified": False,
    }


def audit_one(name: str, browser: dict) -> dict:
    record = {"reference": CASES[name][0], "identity": "unverified",
              "supplier_original_bytes_verified": False}
    try:
        root = observed_source(name, browser)
    except Exception as exc:
        return {**record, "status": "browser_source_unverified",
                "error_type": type(exc).__name__}
    client = UrllibHttpClient(max_bytes=MAX_FRAME_BYTES)
    meta = query_metadata(client, name, root)
    record["metadata"] = meta
    # Only exact matching metadata may establish a fully-indexed rotation.
    count = meta.get("frame_count")
    if meta.get("status") != "proxy_match" or count not in (255, 256) or (count == 255 and name != "R09"):
        return {**record, "status": "proxy_metadata_not_confirmed"}

    top = meta.get("top_index")
    samples_idx = sorted({0, 1, 128, count - 1} | ({top} if top is not None and top < count else set()))
    for fmt in ("jpg", "webp"):
        samples = {idx: request_one(client, root, idx, fmt) for idx in samples_idx}
        record[fmt + "_samples"] = {str(k): v for k, v in samples.items()}
        if all(s.get("valid") and s.get("sha256") for s in samples.values()):
            record["format"] = fmt.upper()
            record["validation"] = validate_full(client, root, fmt, samples, count=count)
            if count == 255:
                extra = request_one(client, root, 255, fmt)
                record["index_255_beyond_declared_count"] = {
                    "valid": extra.get("valid", False), "http": extra.get("http"),
                }
            record["status"] = record["validation"]["status"]
            return record
    record["status"] = "no_consistently_decodable_indexed_cache"
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    source = json.loads(args.browser_audit.read_text("utf-8"))
    if source.get("schema") != "sparkles-opaque-loupe-viewer-audit/1":
        raise SystemExit("Unreviewed browser audit format")
    output = {"schema": "sparkles-opaque-loupe-indexed-cache/1",
              "note": "Read-only exact-viewer proxy bytes, not certified identity or supplier originals",
              "cases": [audit_one(name, source) for name in CASES]}
    value = json.dumps(output, sort_keys=True, indent=2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(value + "\n", encoding="utf-8")
    print("OPAQUE_LOUPE_CACHE " + value, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
