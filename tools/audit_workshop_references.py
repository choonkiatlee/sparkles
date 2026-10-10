#!/usr/bin/env python3
"""Bounded, read-only source audit for accepted R08/R11 Workshop references.

No supplier listing HTML, guessed item identifiers, arbitrary request URLs,
write tokens or publication side effects. Reports source HTTP statuses and
validated 256-frame outcomes without embedding upstream media bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from diamond_retrieval import (
    ROTATION, EvidenceReference, ProgressiveRotationProcessor, UrllibHttpClient,
)
from diamond_retrieval.motion_sources import WorkshopRotationDownloader, _bootstrap_contract
from diamond_retrieval.errors import InvalidPayloadError

ROOT = Path(__file__).resolve().parents[1]
EXACT = {
    "ps285166-r08": (
        "LG657468099", "0410243-YDC-13680",
        "https://workshop.360view.link/360viewer/360view.html?d=0410243-YDC-13680",
    ),
    "ps285166-r11": (
        "LG636432256", "2905248-YDC-6456",
        "https://workshop.360view.link/360viewer/360view.html?d=2905248-YDC-6456",
    ),
}


def checked_source(reference_id: str, base: Path = ROOT) -> tuple[EvidenceReference, str]:
    report_number, item_id, url = EXACT[reference_id]
    doc = json.loads((base / "data/references" / (reference_id + ".json")).read_text())
    if (
        doc.get("id") != reference_id
        or doc.get("identity") != {
            "status": "reported", "lab": "IGI", "report_number": report_number,
        }
        or doc.get("linked_diamond_id") is not None
        or not any(
            x.get("kind") == "rotation" and x.get("locator") == url
            and x.get("status") == "missing"
            for x in doc.get("enrichment_attempts", [])
        )
    ):
        raise ValueError("Expected accepted reference identity/source/status changed")
    ref = EvidenceReference(identifier=reference_id, kind=ROTATION,
                            locator=url, retrieval_key=url)
    _, root, bootstrap = WorkshopRotationDownloader(None)._source(ref)
    if (root != "https://data1.360view.link/data/1/imaged/" + item_id
            or bootstrap != root + "/0.json?version="):
        raise ValueError("Workshop adapter path differs from accepted exact source")
    return ref, root


def _probe_response(http, url: str):
    try:
        response = http.get(url, timeout=12)
    except Exception as exc:
        # Network failure is not evidence of absent source.
        return {"status": "transport_error", "error_type": type(exc).__name__}, None
    record = {"status": response.status_code, "bytes": len(response.content)}
    if response.status_code != 200:
        return record, None
    try:
        bootstrap = json.loads(response.content)
        dimensions, _, version = _bootstrap_contract(bootstrap, source="workshop")
    except (ValueError, InvalidPayloadError, UnicodeError, TypeError) as exc:
        record["contract"] = "invalid"
        record["error_type"] = type(exc).__name__
        return record, None
    record.update({
        "contract": "valid", "dimensions": list(dimensions),
        "version": version, "sha256": hashlib.sha256(response.content).hexdigest(),
    })
    return record, bootstrap


def audit_one(reference_id: str, *, http, base: Path = ROOT) -> dict:
    ref, root = checked_source(reference_id, base)
    output = {"reference_id": reference_id, "expected_source_root": root,
              "probes": [], "result": "not_recovered"}
    primary = root + "/0.json?version="
    bare = root + "/0.json"
    for url, variant in ((primary, "empty_version_query"), (bare, "bare_bootstrap")):
        probe, parsed = _probe_response(http, url)
        output["probes"].append({"variant": variant, **probe})
        if parsed is not None:
            output["bootstrap_variant"] = variant
            try:
                rotation = ProgressiveRotationProcessor().process(
                    WorkshopRotationDownloader(http, timeout=12).download(ref)
                )[0]
            except Exception as exc:
                output["result"] = "complete_rotation_failed"
                output["failure_type"] = type(exc).__name__
            else:
                output.update({
                    "result": "verified_256_original_frames",
                    "frame_count": len(rotation.frames),
                    "dimensions": list(rotation.frames[0].dimensions),
                    "first_frame_sha256": rotation.frames[0].sha256,
                    "last_frame_sha256": rotation.frames[-1].sha256,
                })
            break
        # Never retry a 403, malformed 200, network failure or non-404.
        if probe["status"] != 404:
            output["result"] = (
                "source_forbidden" if probe["status"] == 403
                else "transport_or_invalid_source"
            )
            break
    else:
        output["result"] = "both_known_bootstrap_variants_404"
    return output


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    client = UrllibHttpClient(max_bytes=25 * 1024 * 1024)
    cases = []
    for item in EXACT:
        try:
            cases.append(audit_one(item, http=client))
        except Exception as exc:
            cases.append({
                "reference_id": item, "result": "diagnostic_error",
                "error_type": type(exc).__name__,
            })
    summary = {"schema": "sparkles-workshop-source-audit/1", "cases": cases}
    payload = json.dumps(summary, indent=2, sort_keys=True)
    print(payload)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n")
    return 0 if all(c["result"] != "diagnostic_error" for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
