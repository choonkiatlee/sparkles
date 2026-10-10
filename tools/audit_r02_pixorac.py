"""Read-only exact-report Pixorac recovery audit for learning reference R02.

No arbitrary source URLs, supplier-ID guessing, GitHub publication, or changes
to reference manifests. The Pixorac root must come from a matching Loupe360
IGI report response. The decoded supplier viewer is constrained to R02's
previously observed mediassests Vision360 source (an optional supplied d key
is allowed, but never invented).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.resolvers import Loupe360CertificateResolver

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "ps285166-r02"
REPORT = "LG634479985"
LAB = "IGI"
SUPPLIER_HOST = "mediassests.s3.amazonaws.com"
PROXY_HOST = "assets-images.pixorac.com"
FRAME_COUNT = 256
MAX_FRAME_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
_TOKEN = re.compile(r"/[A-Za-z0-9_-]{20,1024}={0,2}\Z")
_D = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,90}\Z")


def trust_anchor() -> None:
    """Refuse execution if the curated reference has changed unexpectedly."""
    path = ROOT / "data" / "references" / (REFERENCE + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("id") != REFERENCE or record.get("identity") != {
        "lab": LAB, "report_number": REPORT, "status": "reported",
    }:
        raise ValueError("R02 trusted reported identity changed")
    if not any(item.get("kind") == "still" and item.get("status") == "success"
               for item in record.get("evidence", [])):
        raise ValueError("R02 published still is absent")
    if any(item.get("kind") in ("rotation", "video") and item.get("status") == "success"
           for item in record.get("evidence", [])):
        raise ValueError("R02 already has published motion; audit is stale")


def report_matches(record: object, requested: str = REPORT) -> bool:
    return (
        isinstance(record, dict)
        and record.get("certNumber") == requested
        and record.get("lab") == LAB
    )


def proxy_source(v360: object) -> tuple[str, int, str]:
    """Validate the EXACT encoded Pixorac root and decoded known R02 viewer."""
    if not isinstance(v360, dict):
        raise ValueError("missing_v360_record")
    url = v360.get("url")
    if not isinstance(url, str) or len(url) > 1600:
        raise ValueError("missing_or_long_v360_url")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != PROXY_HOST or
            parts.query or parts.fragment or not _TOKEN.fullmatch(parts.path)):
        raise ValueError("no_valid_exact_pixorac_wrapper")
    decoded = Loupe360CertificateResolver._unwrap_v360(url)
    supplier = urlsplit(decoded)
    if (supplier.scheme != "https" or supplier.netloc != SUPPLIER_HOST
            or supplier.path.lower() != "/v360/vision360.html"
            or supplier.fragment or supplier.username or supplier.password):
        raise ValueError("pixorac_does_not_wrap_known_r02_supplier")
    query = parse_qs(supplier.query, keep_blank_values=True)
    if query and (set(query) != {"d"} or len(query["d"]) != 1
                  or not _D.fullmatch(query["d"][0])):
        raise ValueError("unexpected_supplier_query")
    count, top = v360.get("frame_count"), v360.get("top_index")
    if type(count) is not int or count != FRAME_COUNT:
        raise ValueError("no_valid_256_frame_count")
    if type(top) is not int or not 0 <= top < FRAME_COUNT:
        raise ValueError("no_valid_top_index")
    return url, top, "supplied_d_key" if query else "generic_no_d_key"


def query_record(client: UrllibHttpClient, requested: str) -> dict | None:
    payload = json.dumps({
        "query": Loupe360CertificateResolver._query,
        "variables": {"cert": requested},
    }).encode("utf-8")
    response = client.post(
        Loupe360CertificateResolver.endpoint, timeout=20, content=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError("lookup_http_" + str(response.status_code))
    decoded = json.loads(response.content)
    if not isinstance(decoded, dict) or decoded.get("errors"):
        raise ValueError("lookup_invalid_or_graphql_error")
    data = decoded.get("data")
    record = data.get("certificate_by_cert_number") if isinstance(data, dict) else None
    return record if isinstance(record, dict) else None


def read_frame(client: UrllibHttpClient, root: str, index: int, extension: str) -> dict:
    url = root + f"/{index}.{extension}"
    result = client.get(url, timeout=15)
    if result.status_code != 200 or result.url != url:
        raise ValueError("missing_or_redirected_proxy_frame")
    data = result.content
    if not data or len(data) > MAX_FRAME_BYTES:
        raise ValueError("oversized_or_empty_proxy_frame")
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        fmt, size = img.format, img.size
    if fmt != ("JPEG" if extension == "jpg" else "WEBP"):
        raise ValueError("unexpected_proxy_image_format")
    return {
        "bytes": len(data), "dimensions": size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def verify_frames(client: UrllibHttpClient, root: str, top: int) -> dict:
    """Bounded full verification; no source bytes escape this function."""
    for extension in ("jpg", "webp"):
        frames: dict[int, dict] = {}
        try:
            for index in sorted({0, 1, top, 255}):
                frames[index] = read_frame(client, root, index, extension)
        except Exception:
            continue
        try:
            for index in range(FRAME_COUNT):
                if index not in frames:
                    frames[index] = read_frame(client, root, index, extension)
                if sum(frame["bytes"] for frame in frames.values()) > MAX_TOTAL_BYTES:
                    raise ValueError("source_total_exceeds_limit")
        except Exception as exc:
            return {"outcome": "incomplete_indexed_frames", "format": extension,
                    "reason_class": type(exc).__name__}
        sizes = {tuple(value["dimensions"]) for value in frames.values()}
        hashes = [frames[index]["sha256"] for index in range(FRAME_COUNT)]
        valid = len(sizes) == 1 and len(set(hashes)) >= 240
        return {
            "outcome": "complete_indexed_proxy_frames" if valid else "inconsistent_frames",
            "format": extension, "frames": len(frames),
            "dimensions": list(next(iter(sizes))) if len(sizes) == 1 else None,
            "distinct_hashes": len(set(hashes)),
            "first_sha256": hashes[0], "top_sha256": hashes[top],
            "last_sha256": hashes[-1],
            "ordered_hash_digest": hashlib.sha256("".join(hashes).encode()).hexdigest(),
            "original_supplier_bytes_verified": False,
            "identity_independently_verified": False,
        }
    return {"outcome": "no_valid_indexed_jpeg_or_webp_samples"}


def audit(client: UrllibHttpClient) -> dict:
    trust_anchor()
    result = {"reference": REFERENCE, "reported_lab": LAB, "reported_report": REPORT,
              "mode": "read_only", "publication": False}
    # The numeric lookup is diagnostic only: NEVER use it to authorize frame reads.
    try:
        numeric = query_record(client, REPORT.removeprefix("LG"))
        result["numeric_variant"] = (
            "exact_numeric_igi" if report_matches(numeric, REPORT.removeprefix("LG"))
            else "absent_or_mismatch"
        )
    except Exception as exc:
        result["numeric_variant"] = "unavailable_" + type(exc).__name__
    try:
        record = query_record(client, REPORT)
    except Exception as exc:
        result["outcome"] = "prefixed_lookup_unavailable"
        result["reason_class"] = type(exc).__name__
        return result
    if not report_matches(record):
        result["outcome"] = "exact_igi_report_not_confirmed_by_provider"
        return result
    result["exact_report_match"] = True
    result["still_present"] = isinstance(record.get("image"), str) and bool(record["image"])
    result["direct_video_present"] = isinstance(record.get("video"), str) and bool(record["video"])
    v360 = record.get("v360")
    result["v360_present"] = isinstance(v360, dict) and bool(v360.get("url"))
    try:
        root, top, source_kind = proxy_source(v360)
    except (ValueError, TypeError) as exc:
        result["outcome"] = "no_eligible_exact_pixorac_cache"
        result["reason"] = str(exc)
        return result
    result["supplier_viewer_kind"] = source_kind
    result["declared_frame_count"] = FRAME_COUNT
    result["top_index"] = top
    result["proxy_root_sha256"] = hashlib.sha256(root.encode()).hexdigest()
    try:
        result["probe"] = verify_frames(client, root, top)
        result["outcome"] = result["probe"]["outcome"]
    except Exception as exc:
        result["outcome"] = "bounded_proxy_transport_failure"
        result["reason_class"] = type(exc).__name__
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    outcome = audit(UrllibHttpClient(max_bytes=MAX_FRAME_BYTES))
    output = json.dumps(outcome, sort_keys=True, indent=2)
    print(output, flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
