"""R12 read-only Loupe source and original-motion audit (no publication).

LG524247250 occurs in a curated Loupe URL, NOT an independently verified
IGI certificate. This probe never changes the reference's identity/status,
never infers a report from an opaque ID, and cannot publish local media.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval import retrieve_reference_media
from tools.reference_identity_audit import audit_one

ROOT = Path(__file__).resolve().parents[1]
REF = "ps282648-r12"
SOURCE = "https://loupe360.com/diamond/LG524247250"
CANDIDATES = ("LG524247250", "524247250")


def check_curated_source() -> None:
    """Fail if the reviewed, unverified source anchor changes."""
    record = json.loads((ROOT / "data/references/ps282648-r12.json").read_text(encoding="utf-8"))
    if record.get("id") != REF or record.get("identity") != {
        "status": "unverified", "lab": None, "report_number": None,
    }:
        raise RuntimeError("R12 identity contract changed; review before reusing this audit")
    if record.get("media_sources") != [{
        "kind": "viewer", "provider": "loupe360",
        "status": "linked_unverified", "url": SOURCE,
    }]:
        raise RuntimeError("R12 source changed; review before reusing this audit")


def exact_igi_candidate(result: dict) -> bool:
    """Provider-backed lookup candidate, NOT independent certificate proof."""
    return (
        result.get("status") == "record_returned"
        and result.get("requested") in CANDIDATES
        and result.get("returned_report") == result.get("requested")
        and result.get("returned_lab") == "IGI"
        and result.get("expected_lab_match") is True
        and (result.get("v360_present") or result.get("video_present"))
    )


def lookup(client) -> list[dict]:
    results = []
    for requested in CANDIDATES:
        record = audit_one(
            client, reference_id=REF, lab="IGI",
            report="524247250", requested=requested,
        )
        results.append(record)
        print("R12_IDENTITY_AUDIT " + json.dumps(record, sort_keys=True), flush=True)
    return results


def media_dry_run(report: str) -> None:
    """In-memory original-byte validation using the existing safe pipeline."""
    try:
        result = retrieve_reference_media(
            REF, lab="IGI", report_number=report, media_sources=(),
            include_igi_pdf=False,
        )
        rotations = []
        for rotation in result.rotations:
            frames = rotation.frames
            complete = (
                len(frames) == 256
                and [f.source_index for f in frames] == list(range(256))
                and rotation.metadata.get("sequence_complete") is True
            )
            rotations.append({
                "frames": len(frames), "complete": complete,
                "first_sha256": hashlib.sha256(frames[0].payload).hexdigest() if complete else None,
                "last_sha256": hashlib.sha256(frames[-1].payload).hexdigest() if complete else None,
            })
        report_out = {
            "status": "validated_read_only",
            "candidate_report": report, "rotations": rotations,
            "videos": len(result.videos), "stills": len(result.stills),
            "attempts": [{"kind": str(a.kind), "status": a.status.value} for a in result.attempts],
            "identity_comparisons": [str(c.outcome) for c in result.identity_comparisons],
        }
    except Exception as exc:
        report_out = {
            "status": "not_validated", "candidate_report": report,
            "reason_class": type(exc).__name__,
        }
    print("R12_MEDIA_AUDIT " + json.dumps(report_out, sort_keys=True), flush=True)




def probe_exact_loupe_viewer(client) -> list[dict]:
    """Bounded probe of only the reviewed viewer and existing resolver fallback.

    No external src extraction, script fetching, redirects to private networks,
    guessed supplier IDs, downloaded media or persistence.
    """
    from urllib.parse import urlsplit
    from diamond_retrieval.reference_media import _safe_source_url

    results = []
    for label, url in (
        ("reviewed-viewer", SOURCE),
        ("existing-resolver-fallback", SOURCE + "/video/500/500"),
    ):
        if urlsplit(_safe_source_url(url)).hostname != "loupe360.com":
            raise RuntimeError("Unreviewed Loupe host")
        item = {"source": label}
        try:
            response = client.get(url, timeout=12)
            data = response.content
            raw = data[:300_000].decode("utf-8", errors="replace").lower()
            item.update({
                "http_status": response.status_code,
                "byte_count": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "wire_format": (
                    "mp4" if len(data) > 8 and data[4:8] == b"ftyp"
                    else "jpeg" if data[:3] == b"\\xff\\xd8\\xff"
                    else "html" if "<html" in raw or "<!doctype" in raw
                    else "other"
                ),
                "mentions_mp4": ".mp4" in raw,
                "mentions_frame_json": "0.json" in raw,
                "mentions_video_element": "<video" in raw,
                "mentions_iframe": "<iframe" in raw,
            })
        except Exception:
            item["status"] = "bounded_transport_failure_or_unavailable"
        results.append(item)
        print("R12_VIEWER_AUDIT " + json.dumps(item, sort_keys=True), flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv not in ([], ["--media"]):
        raise SystemExit("Only --media is supported")
    check_curated_source()
    results = lookup(UrllibHttpClient(max_bytes=150_000))
    probe_exact_loupe_viewer(UrllibHttpClient(max_bytes=300_000))
    if argv == ["--media"]:
        match = next((r for r in results if exact_igi_candidate(r)), None)
        if match is None:
            print("R12_MEDIA_AUDIT " + json.dumps({
                "status": "blocked_unverified_identity",
                "note": "No matching exact IGI candidate with supplier media; no original fetched",
            }, sort_keys=True), flush=True)
        else:
            media_dry_run(match["requested"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
