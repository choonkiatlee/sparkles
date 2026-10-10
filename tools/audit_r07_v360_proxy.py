#!/usr/bin/env python3
"""Bounded read-only test of R07's *exact-report* V360 Diamonds proxy path.

Never touches the restricted v360.diamonds viewer or guesses its frame API.
No media is written, published, stored in artifacts or persisted on disk.
Uses the production certificate-bound resolver/downloader for complete proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.models import ROTATION, EvidenceStatus
from diamond_retrieval.reference_media import retrieve_reference_media
from diamond_retrieval.resolvers import Loupe360CertificateResolver

ROOT = Path(__file__).resolve().parents[1]
REF = "ps285166-r07"
REPORT = "LG625406458"
VIEWER = "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i"
_PROXY = re.compile(r"/[A-Za-z0-9_-]{20,1024}={0,2}\Z")


def verify_manifest():
    record = json.loads((ROOT / "data/references" / (REF + ".json")).read_text())
    if record.get("id") != REF or record.get("identity") != {
        "lab": "IGI", "report_number": REPORT, "status": "reported"
    }:
        raise ValueError("R07 curated report identity changed")
    if record.get("media_sources") != [{
        "kind": "viewer", "provider": "v360.diamonds",
        "status": "linked_unverified", "url": VIEWER
    }]:
        raise ValueError("R07 buyer-supplied source changed")
    if not any(e.get("status") == "success" and e.get("kind") == "still"
               for e in record.get("evidence", [])):
        raise ValueError("R07 stored still missing")
    return record


def probe(client):
    output = {"reference": REF, "report": REPORT,
              "schema": "sparkles-r07-v360-proxy-audit/1",
              "mode": "read-only; no media publication or original viewer access"}
    request = json.dumps({
        "query": Loupe360CertificateResolver._query,
        "variables": {"cert": REPORT},
    }, separators=(",", ":")).encode()
    response = client.post(
        Loupe360CertificateResolver.endpoint,
        timeout=20, content=request,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    output["provider_http"] = response.status_code
    if response.status_code != 200:
        output["outcome"] = "exact_report_lookup_unavailable"
        return output
    try:
        payload = json.loads(response.content)
        record = (payload.get("data") or {}).get("certificate_by_cert_number")
    except (ValueError, TypeError, AttributeError):
        output["outcome"] = "invalid_report_response"
        return output
    if payload.get("errors") or not isinstance(record, dict):
        output["outcome"] = "no_exact_report"
        return output
    if str(record.get("certNumber") or "").upper() != REPORT or str(record.get("lab") or "").upper() != "IGI":
        output["outcome"] = "lab_or_report_conflict"
        return output
    output["exact_report_matched"] = True
    video = record.get("video")
    output["provider_video_field_present"] = isinstance(video, str) and bool(video)
    output["provider_direct_video_candidate"] = (
        isinstance(video, str)
        and Loupe360CertificateResolver._is_direct_video_url(video)
    )
    v360 = record.get("v360")
    if not isinstance(v360, dict) or not isinstance(v360.get("url"), str):
        output["outcome"] = "no_provider_rotation_url"
        return output
    url = v360["url"]
    parts = urlsplit(url)
    output["provider_source_host"] = parts.hostname
    output["declared_frames"] = v360.get("frame_count")
    output["declared_top_index"] = v360.get("top_index")
    if (parts.scheme != "https" or parts.netloc != "assets-images.pixorac.com"
        or parts.query or parts.fragment or not _PROXY.fullmatch(parts.path)):
        output["outcome"] = "no_eligible_pixorac_wrapper"
        return output
    try:
        source = urlsplit(Loupe360CertificateResolver._unwrap_v360(url))
        expected = urlsplit(VIEWER)
    except ValueError:
        output["outcome"] = "invalid_encoded_source"
        return output
    if (source.scheme != "https" or source.netloc != expected.netloc
        or source.path != expected.path or source.fragment
        or parse_qs(source.query) != parse_qs(expected.query)):
        output["outcome"] = "different_viewer_not_authorized"
        return output
    output["exact_viewer_matched"] = True
    if v360.get("frame_count") != 256 or isinstance(v360.get("frame_count"), bool):
        output["outcome"] = "unsupported_frame_count"
        return output
    top = v360.get("top_index")
    if isinstance(top, bool) or not str(top).isdigit() or not (0 <= int(top) < 256):
        output["outcome"] = "invalid_face_up_index"
        return output
    output["proxy_root_sha256"] = hashlib.sha256(url.encode()).hexdigest()
    result = retrieve_reference_media(
        REF, lab="IGI", report_number=REPORT,
        media_sources=verify_manifest()["media_sources"], http_client=client,
        include_igi_pdf=False,
    )
    output["attempts"] = [
        {"kind": str(at.kind), "status": at.status.value,
         "source_host": (urlsplit(at.locator).hostname
                         if (at.locator or "").startswith("https://") else None)}
        for at in result.attempts
    ]
    rotations = [e for e in result.evidence
                 if e.kind == ROTATION and e.status == EvidenceStatus.SUCCESS]
    if len(rotations) != 1:
        output["outcome"] = "no_validated_motion"
        return output
    rotation = rotations[0]
    frames = rotation.frames
    hashes = [frame.sha256 for frame in frames]
    if (len(frames) != 256 or len(set(hashes)) != 256
        or [frame.source_index for frame in frames] != list(range(256))
        or rotation.metadata.get("supplier") != "loupe360-pixorac-proxy"
        or rotation.face_up_hint != int(top)
        or rotation.metadata.get("supplier_original_bytes_verified") is not False):
        output["outcome"] = "source_integrity_conflict"
        return output
    output.update({
        "outcome": "complete_256_proxy_rotation",
        "frame_count": 256, "distinct_sha256": len(set(hashes)),
        "dimensions": list(frames[0].dimensions),
        "all_dimensions_match": all(f.dimensions == frames[0].dimensions for f in frames),
        "byte_total": sum(len(f.payload) for f in frames),
        "face_up_index": rotation.face_up_hint,
        "first_sha256": hashes[0], "faceup_sha256": hashes[int(top)],
        "last_sha256": hashes[-1],
        "hash_chain": hashlib.sha256("".join(hashes).encode()).hexdigest(),
        "provenance": "certificate-matched_pixorac_proxy_not_supplier_byte_verified",
    })
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    verify_manifest()
    try:
        output = probe(UrllibHttpClient(max_bytes=1024*1024))
    except Exception as exc:
        output = {
            "schema": "sparkles-r07-v360-proxy-audit/1",
            "reference": REF, "outcome": "read_only_diagnostic_error",
            "error_type": type(exc).__name__,
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
