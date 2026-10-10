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
        "v360_present": isinstance(v360_url, str) and bool(v360_url),
        "video_present": isinstance(record.get("video"), str) and bool(record["video"]),
        "image_present": isinstance(record.get("image"), str) and bool(record["image"]),
        "response_sha256": hashlib.sha256(response.content).hexdigest(),
    }


def main() -> int:
    client = UrllibHttpClient(max_bytes=150_000)
    for reference_id, lab, report in CASES:
        manifest = json.loads(
            (ROOT / "data" / "references" / (reference_id + ".json")).read_text("utf-8")
        )
        identity = manifest["identity"]
        if (manifest["id"] != reference_id or
                identity["lab"] != lab or
                identity["report_number"] != report or
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
