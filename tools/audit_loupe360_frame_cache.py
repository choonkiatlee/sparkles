#!/usr/bin/env python3
"""Bounded, exact-cert read-only Loupe360 image-frame availability audit (#221).

The returned Nivoda V360Info URL is an exact reported media location, not
an inferred supplier ID. Query only its documented index suffixes.
Never publish proxy/derivative bytes as original supplier JPEGs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from audit_loupe360_browser_references import EXACT, PUBLIC_ENDPOINT


def metadata_for(report):
    query = """query($cert:String!){
      certificate_by_cert_number(cert_number:$cert){
        certNumber lab v360 {url frame_count top_index id}
      }
    }"""
    payload = json.dumps({"query": query, "variables": {"cert": report}}).encode()
    request = urllib.request.Request(
        PUBLIC_ENDPOINT, payload, method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "Sparkles-reference-frame-audit/1"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("Exact-report metadata request failed")
        body = json.load(io.BytesIO(response.read(256 * 1024)))
    if body.get("errors"):
        raise ValueError("Exact-report metadata query rejected")
    record = (body.get("data") or {}).get("certificate_by_cert_number")
    if not isinstance(record, dict) or record.get("certNumber") != report or record.get("lab") != "IGI":
        raise ValueError("Certificate or lab identity mismatch")
    v360 = record.get("v360")
    if not isinstance(v360, dict):
        raise ValueError("No V360 metadata")
    root = v360.get("url")
    parts = urlsplit(root or "")
    if (parts.scheme != "https" or parts.netloc != "assets-images.pixorac.com"
        or parts.query or parts.fragment or
        not re.fullmatch(r"/[A-Za-z0-9_\-=]+", parts.path)):
        raise ValueError("Untrusted V360 image proxy URL")
    count = v360.get("frame_count")
    if count != 256:
        raise ValueError("Expected exact 256-frame source")
    top = int(v360.get("top_index"))
    if not 0 <= top < 256:
        raise ValueError("Top-frame index is out of range")
    return root.rstrip("/"), top


def request_frame(url):
    request = urllib.request.Request(
        url, headers={"Accept": "image/jpeg,image/webp",
                      "User-Agent": "Sparkles-reference-frame-audit/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            data = response.read(5 * 1024 * 1024 + 1)
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    except urllib.error.HTTPError as error:
        return {"status": error.code}
    except Exception as error:
        return {"status": "transport_error", "error_type": type(error).__name__}
    result = {"status": status, "mime": mime, "byte_count": len(data)}
    if status != 200 or len(data) > 5 * 1024 * 1024:
        return result
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            if decoded.format not in {"JPEG", "WEBP"}:
                raise ValueError("Unexpected decoded format")
            result.update({"format": decoded.format,
                           "dimensions": list(decoded.size),
                           "sha256": hashlib.sha256(data).hexdigest()})
    except Exception as error:
        result["decode_error_type"] = type(error).__name__
    return result


def audit(report):
    root, top = metadata_for(report)
    output = {"report": report, "source_host": "assets-images.pixorac.com",
              "top_index": top, "frame_count_declared": 256, "format_samples": {}}
    # Vendor documentation describes indexed JPEGs, while the live viewer
    # requests indexed WebP. Test original-candidate JPEG first.
    indices = sorted({0, 1, top, 255})
    for suffix in ("jpg", "webp"):
        output["format_samples"][suffix] = {}
        for index in indices:
            output["format_samples"][suffix][index] = request_frame(root + f"/{index}.{suffix}")
            time.sleep(0.08)

    jpg = output["format_samples"]["jpg"]
    webp = output["format_samples"]["webp"]
    def all_valid(items, fmt):
        return all(
            x.get("status") == 200 and x.get("format") == fmt
            and x.get("sha256") and x.get("dimensions")
            for x in items.values()
        )
    preferred = ("jpg" if all_valid(jpg, "JPEG")
                 else "webp" if all_valid(webp, "WEBP") else None)
    output["preferred_indexed_variant"] = preferred
    if preferred is None:
        output["result"] = "no_complete_frame_format_established"
        return output

    known = dict(output["format_samples"][preferred])
    for index in range(256):
        if index not in known:
            known[index] = request_frame(root + f"/{index}.{preferred}")
            time.sleep(0.05)
        if not (known[index].get("status") == 200 and known[index].get("sha256")
                and known[index].get("format") == ("JPEG" if preferred == "jpg" else "WEBP")):
            output["result"] = "incomplete_indexed_frames"
            output["first_missing_index"] = index
            return output
    sizes = {tuple(known[index]["dimensions"]) for index in range(256)}
    unique_sha = len({known[index]["sha256"] for index in range(256)})
    output.update({
        "format": "JPEG" if preferred == "jpg" else "WEBP",
        "dimensions_unique": [list(x) for x in sorted(sizes)],
        "unique_frame_hashes": unique_sha,
        "first_frame_sha256": known[0]["sha256"],
        "top_frame_sha256": known[top]["sha256"],
        "last_frame_sha256": known[255]["sha256"],
        "ordered_sha256_digest": hashlib.sha256(
            "".join(known[i]["sha256"] for i in range(256)).encode()
        ).hexdigest(),
        "result": ("full_256_proxy_frames_validated"
                   if len(sizes) == 1 and unique_sha > 1 else
                   "frames_exist_but_inconsistent"),
        "original_supplier_bytes_verified": False,
    })
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for ref, report in EXACT.items():
        try:
            results.append({"reference": ref, **audit(report)})
        except Exception as error:
            results.append({"reference": ref, "report": report,
                            "result": "diagnostic_error",
                            "error_type": type(error).__name__})
    output = {
        "schema": "sparkles-loupe360-proxy-frame-audit/1",
        "note": "Proof of proxy frame availability, not supplier-original byte provenance",
        "cases": results,
    }
    text = json.dumps(output, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
