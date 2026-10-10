"""Read-only, bounded audit of two unresolved PriceScope reference identities.

The GraphQL endpoint and requested reports are fixed in reviewed source code.
No issue text, external URLs, arbitrary report inputs, media bytes or credentials.
Only a tiny allowlisted diagnostic is printed; never upstream raw responses.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.resolvers import Loupe360CertificateResolver

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("ps285166-r05", "IGI", "644442866"),
    ("ps285166-r07", "IGI", "625406458"),
)
_SAFE_REPORT = re.compile(r"(?:LG)?[0-9]{6,14}")
_SAFE_LAB = re.compile(r"[A-Z][A-Z0-9 -]{0,30}")


def _safe(value: object, *, kind: str) -> str:
    if not isinstance(value, str):
        return "<absent>"
    text = value.strip().upper()
    pattern = _SAFE_REPORT if kind == "report" else _SAFE_LAB
    return text if pattern.fullmatch(text) else "<invalid>"


def _digest(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]



def _safe_url_shape(value: object) -> dict:
    """Describe a public source contract without exposing paths or query tokens."""
    if not isinstance(value, str) or not value:
        return {"present": False}
    try:
        raw = Loupe360CertificateResolver._unwrap_v360(value)
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
    except (ValueError, UnicodeError):
        return {"present": True, "format": "malformed"}
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", host):
        host = "<invalid>"
    path = parsed.path.lower()
    return {
        "present": True, "scheme": parsed.scheme,
        "host": host,
        "path_format": "mp4" if path.endswith(".mp4") else
            "html" if path.endswith(".html") else
            "other",
        "supported_rotation": Loupe360CertificateResolver._is_supported_rotation_url(raw),
        "direct_video_suffix": Loupe360CertificateResolver._is_direct_video_url(raw),
    }


def audit_one(client, *, reference_id: str, lab: str, report: str, requested: str) -> dict:
    """Return sanitized source identity facts, never infer certified association."""
    output = {"reference": reference_id, "requested": requested}
    query = Loupe360CertificateResolver._query
    payload = json.dumps({
        "query": query, "variables": {"cert": requested},
    }, separators=(",", ":")).encode("utf-8")
    try:
        response = client.post(
            Loupe360CertificateResolver.endpoint, timeout=12,
            content=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except Exception:
        return {**output, "status": "transport_failure"}
    if response.status_code != 200:
        return {**output, "status": "http_failure", "http_status": response.status_code}
    try:
        decoded = json.loads(response.content)
        if not isinstance(decoded, dict):
            raise ValueError("not an object")
        if decoded.get("errors"):
            return {**output, "status": "graphql_error"}
        data = decoded.get("data")
        record = data.get("certificate_by_cert_number") if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError, TypeError):
        return {**output, "status": "invalid_payload"}
    if record is None:
        return {**output, "status": "not_found"}
    if not isinstance(record, dict):
        return {**output, "status": "invalid_payload"}
    returned = _safe(record.get("certNumber"), kind="report")
    returned_lab = _safe(record.get("lab"), kind="lab")
    if returned == requested.upper():
        match = "exact_request"
    elif returned in {report, "LG" + report}:
        match = "same_numeric_with_lg_difference"
    else:
        match = "different_or_missing"
    v360 = record.get("v360")
    v360_url = v360.get("url") if isinstance(v360, dict) else None
    return {
        **output, "status": "record_returned",
        "returned_report": returned, "returned_lab": returned_lab,
        "report_relation": match, "expected_lab_match": returned_lab == lab,
        "certificate_id_hash": _digest(record.get("id")),
        "v360_url_hash": _digest(v360_url),
        "v360_source_shape": _safe_url_shape(v360_url),
        "video_source_shape": _safe_url_shape(record.get("video")),
        "v360_present": isinstance(v360_url, str) and bool(v360_url),
        "video_present": isinstance(record.get("video"), str) and bool(record["video"]),
        "image_present": isinstance(record.get("image"), str) and bool(record["image"]),
        "response_sha256": hashlib.sha256(response.content).hexdigest(),
    }



def audit_media_readonly() -> None:
    """Use normal identity/source validators in-memory, without GitHub publication."""
    from diamond_retrieval import retrieve_reference_media
    from diamond_retrieval.models import IdentityOutcome

    for reference_id, lab, numeric_report in CASES:
        report = "LG" + numeric_report
        record = json.loads(
            (ROOT / "data" / "references" / (reference_id + ".json")).read_text("utf-8")
        )
        if (record["identity"]["lab"], record["identity"]["report_number"]) != (lab, report):
            raise SystemExit("Trusted reference identity changed; refuse live dry-run")
        try:
            result = retrieve_reference_media(
                reference_id, lab=lab, report_number=report,
                media_sources=record.get("media_sources", ()),
                include_igi_pdf=False,
            )
            conflicts = any(
                value.outcome == IdentityOutcome.CONFLICT
                for value in result.identity_comparisons
            )
            attempts = [
                {"kind": str(a.kind), "status": a.status.value}
                for a in result.attempts
            ]
            payload = {
                "reference": reference_id, "conflicts": conflicts,
                "rotation_frames": [len(r.frames) for r in result.rotations],
                "video_count": len(result.videos),
                "still_count": len(result.stills),
                "attempts": attempts,
            }
        except Exception:
            payload = {"reference": reference_id, "status": "unavailable_or_error"}
        print("MEDIA_DRY_RUN " + json.dumps(payload, sort_keys=True), flush=True)



def probe_source_pages_readonly() -> None:
    """Inspect only identity-matched exact source URLs (no link crawling)."""
    from diamond_retrieval.reference_media import _safe_source_url

    client = UrllibHttpClient(max_bytes=1_000_000)
    result = []
    ref = "ps285166-r05"
    report = "LG644442866"
    body = json.dumps({
        "query": Loupe360CertificateResolver._query,
        "variables": {"cert": report},
    }).encode()
    try:
        response = client.post(
            Loupe360CertificateResolver.endpoint, timeout=12, content=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        record = json.loads(response.content)["data"]["certificate_by_cert_number"]
        if (record.get("certNumber"), record.get("lab")) != (report, "IGI"):
            raise ValueError("identity mismatch in live probe")
        v360 = record.get("v360") or {}
        raw_viewer = Loupe360CertificateResolver._unwrap_v360(v360.get("url") or "")
        playback = record.get("video")
        sources = (("r05-viewer", raw_viewer, "www.filesonsky.com"),
                   ("r05-playback", playback, "loupe360.com"))
    except Exception:
        sources = ()

    r07 = json.loads((ROOT / "data/references/ps285166-r07.json").read_text("utf-8"))
    if r07["identity"]["report_number"] != "LG625406458":
        raise SystemExit("R07 trust anchor changed")
    exact = next((m["url"] for m in r07["media_sources"]
                  if m["provider"] == "v360.diamonds"), None)
    sources += (("r07-viewer", exact, "v360.diamonds"),)
    for name, raw, expected_host in sources:
        item = {"source": name}
        try:
            url = _safe_source_url(raw)
            if urlsplit(url).hostname != expected_host:
                raise ValueError("non-allowlisted source host")
            # Read source viewer text and/or playback endpoint only, no second-hop URLs.
            # A 1 MB response budget also prevents accidentally ingesting large media.
            received = client.get(url, timeout=10)
            payload = received.content
            text = payload[:1_000_000].decode("utf-8", "replace").lower()
            # These are boolean contract signals, not extracted URLs or media.
            item.update({
                "status": "response", "http": received.status_code,
                "bytes_read": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "type": "video_magic" if len(payload)>8 and payload[4:8]==b"ftyp"
                        else "html" if ("<html" in text or "<!doctype" in text) else "other",
                "contains_mp4_reference": ".mp4" in text,
                "contains_frame_json_reference": "0.json" in text or "1.json" in text,
                "contains_video_tag": "<video" in text,
                "contains_iframe": "<iframe" in text,
                "contains_images": "<img" in text,
                "contains_js_script": "<script" in text,
                "script_tags": text.count("<script"),
                "linked_script_hosts": sorted(set(
                    urlsplit(u).hostname or urlsplit(url).hostname
                    for u in re.findall(r"<script[^>]*src=['\"]([^'\"]+)", text)
                )),
                "url_mentions": len(re.findall(r'https?://', text)),
                "source_markers": sorted(term for term in (
                    "initviewer", "diamond", "video", "movie", "jpg",
                    "frames", "scramble", "json", "image", "webgl", "gif",
                    "cloudfront", "s3.amazonaws", "source", "rotation",
                ) if term in text),
            })
        except Exception:
            item["status"] = "blocked_or_unavailable"
        result.append(item)
    for item in result:
        print("VIEWER_PROBE " + json.dumps(item, sort_keys=True), flush=True)


def probe_filesonsky_bootstrap_readonly() -> None:
    """Check four exact known Vision360 bootstrap layouts; no frame downloads."""
    from diamond_retrieval.motion_sources import _bootstrap_contract

    # R05's source is https://www.filesonsky.com/v360/Vision360.HTML?d=659844.
    # These are bounded diagnostic hypotheses, not publication locators.
    reference = json.loads(
        (ROOT / "data/references/ps285166-r05.json").read_text("utf-8")
    )
    expected_viewer = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
    if (
        reference["identity"]["report_number"] != "LG644442866"
        or not any(
            attempt.get("locator") == expected_viewer
            and attempt.get("kind") == "rotation"
            for attempt in reference.get("enrichment_attempts", [])
        )
    ):
        raise SystemExit("R05 trusted resolved-viewer source changed; skip bootstrap probe")
    prefixes = ("https://www.filesonsky.com/v360/imaged/659844",
                "https://www.filesonsky.com/imaged/659844")
    client = UrllibHttpClient(max_bytes=300_000)
    for root in prefixes:
        for suffix in ("/0.json", "/0.json?version="):
            url = root + suffix
            output = {"root": "nested_v360" if "/v360/imaged/" in root else "site_root",
                      "version_query": suffix.endswith("version=")}
            try:
                response = client.get(url, timeout=10)
                output["http"] = response.status_code
                output["bytes"] = len(response.content)
                output["sha256"] = hashlib.sha256(response.content).hexdigest()
                if response.status_code == 200:
                    try:
                        data = json.loads(response.content)
                        dimensions, scramble, version = _bootstrap_contract(
                            data, source="filesonsky-diagnostic"
                        )
                        output["contract"] = "valid_progressive"
                        output["dimensions"] = list(dimensions)
                        output["version"] = version
                        output["scramble_count"] = len(scramble)
                    except (ValueError, TypeError):
                        output["contract"] = "not_a_supported_bootstrap"
            except Exception:
                output["status"] = "unavailable"
            print("BOOTSTRAP_PROBE " + json.dumps(output, sort_keys=True), flush=True)


def main() -> int:
    import sys
    media_mode = sys.argv[1:] == ["--media"]
    probe_mode = sys.argv[1:] == ["--probe"]
    bootstrap_mode = sys.argv[1:] == ["--bootstrap"]
    if sys.argv[1:] not in ([], ["--media"], ["--probe"], ["--bootstrap"]):
        raise SystemExit("Only --media or --probe is supported")
    if bootstrap_mode:
        probe_filesonsky_bootstrap_readonly()
        return 0
    if probe_mode:
        probe_source_pages_readonly()
        return 0
    if media_mode:
        audit_media_readonly()
        return 0
    client = UrllibHttpClient(max_bytes=150_000)
    for reference_id, lab, report in CASES:
        manifest = json.loads(
            (ROOT / "data" / "references" / (reference_id + ".json")).read_text("utf-8")
        )
        identity = manifest["identity"]
        if (manifest["id"] != reference_id or
                identity["lab"] != lab or
                identity["report_number"] != "LG" + report or
                identity["status"] != "reported"):
            raise SystemExit("Trusted reviewed identity changed; refuse stale diagnostic")
        for variant in (report, "LG" + report):
            print(json.dumps(audit_one(
                client, reference_id=reference_id, lab=lab,
                report=report, requested=variant,
            ), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
