"""Read-only exact-viewer motion investigation for PriceScope R03/R09 (#253).

The numbers in Loupe360 paths are opaque viewer IDs, NOT certificate numbers.
Never query certificates from them, infer report prefixes, change reference
identity, persist source media or publish anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.reference_media import _safe_source_url

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "R03": ("ps285166-r03", "https://loupe360.com/diamond/636493231"),
    "R09": ("ps285166-r09", "https://loupe360.com/diamond/1498922544"),
}
SUFFIXES = ("", "/video/500/500")


def validate_manifest(name: str, record: dict) -> str:
    """Refuse to audit after reviewed anchors or unverified identity change."""
    reference_id, url = CASES[name]
    expected_media = [{
        "kind": "viewer", "provider": "loupe360",
        "status": "linked_unverified", "url": url,
    }]
    if record.get("id") != reference_id:
        raise ValueError("Changed reference ID")
    if record.get("identity") != {
        "status": "unverified", "lab": None, "report_number": None,
    }:
        raise ValueError("Identity changed; do not interpret viewer ID as report")
    if record.get("media_sources") != expected_media:
        raise ValueError("Source link changed; fresh review required")
    if record.get("evidence") != []:
        raise ValueError("Reference already contains media evidence; review first")
    return url


def validate_route(name: str, suffix: str) -> str:
    """Only two pinned URLs and the already-existing Loupe fallback route."""
    if name not in CASES or suffix not in SUFFIXES:
        raise ValueError("Unreviewed source request")
    url = CASES[name][1] + suffix
    checked = _safe_source_url(url)
    parts = urlsplit(checked)
    if (parts.scheme != "https" or parts.hostname != "loupe360.com"
            or parts.port not in (None, 443) or parts.query or parts.fragment):
        raise ValueError("Untrusted viewer route")
    return checked


def wire_type(payload: bytes) -> str:
    """A 200 HTML response is not recovered motion."""
    if len(payload) >= 8 and payload[4:8] == b"ftyp":
        return "mp4_candidate_unverified"
    if payload.startswith(bytes.fromhex("ffd8ff")):
        return "jpeg_candidate_unverified"
    prefix = payload[:10000].decode("utf-8", errors="replace").lower()
    if "<html" in prefix or "<!doctype" in prefix:
        return "html_not_motion"
    return "other_not_verified"


def probe_http(client, name: str, suffix: str) -> dict:
    url = validate_route(name, suffix)
    item = {"route": "viewer" if suffix == "" else "existing-video-fallback"}
    try:
        response = client.get(url, timeout=12)
        content = response.content
        parts = urlsplit(response.url)
        item.update({
            "http": response.status_code,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "type": wire_type(content),
            "final_host": parts.hostname,
            "redirected": response.url != url,
        })
    except Exception as exc:
        # Includes over-budget responses; do not treat transport errors as motion.
        item.update({"status": "unavailable_or_bounded_transport_error",
                     "error_type": type(exc).__name__})
    return item


def inspect_exact_browser(name: str) -> list[dict]:
    """Browser network trace only; no bodies, cookies, query strings or downloads."""
    from tools.audit_loupe360_browser_references import inspect_browser
    original = validate_route(name, "")
    opaque_id = urlsplit(original).path.rsplit("/", 1)[-1]
    # The existing browser tracer reports sanitized host/path/status and drops
    # all query strings and headers. Do not retain its page-text sample.
    results = inspect_browser(opaque_id, seconds=4)
    for result in results:
        if isinstance(result.get("dom"), dict):
            result["dom"].pop("body_text_sample", None)
        result.pop("title", None)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-browser", action="store_true",
                        help="Only bounded public HTTP probes")
    args = parser.parse_args(argv)

    for name, (reference_id, _) in CASES.items():
        path = ROOT / "data" / "references" / (reference_id + ".json")
        validate_manifest(name, json.loads(path.read_text(encoding="utf-8")))

    result = {"schema": "sparkles-opaque-loupe-viewer-audit/1",
              "scope": "exact R03/R09 numeric viewer IDs only; no certified identity or local motion claimed",
              "cases": []}
    client = UrllibHttpClient(max_bytes=350_000)
    for name, (reference_id, _) in CASES.items():
        item = {"reference": reference_id, "identity": "unverified",
                "http": [probe_http(client, name, suffix) for suffix in SUFFIXES]}
        if not args.no_browser:
            try:
                item["browser"] = inspect_exact_browser(name)
            except Exception as exc:
                item["browser"] = [{"status": "browser_unavailable",
                                    "error_type": type(exc).__name__}]
        result["cases"].append(item)

    output = json.dumps(result, sort_keys=True, indent=2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output + "\n", encoding="utf-8")
    print("OPAQUE_LOUPE_AUDIT " + output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
