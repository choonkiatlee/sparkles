"""Read-only exact-source audit for learning references R08/R11 (#221).

No supplier HTML, dynamic URL input, broad host scanning or publication.
An HTTP 403 is a hard stop. Print only structural/status diagnostics.
"""
from __future__ import annotations

import argparse
import json
from urllib.parse import urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.models import ROTATION, EvidenceReference
from diamond_retrieval.motion_sources import (
    WorkshopRotationDownloader,
    _bootstrap_contract,
)
from diamond_retrieval.motion import ProgressiveRotationProcessor

SOURCES = {
    "ps285166-r08": "https://workshop.360view.link/360viewer/360view.html?d=0410243-YDC-13680",
    "ps285166-r11": "https://workshop.360view.link/360viewer/360view.html?d=2905248-YDC-6456",
}
ALLOWED_MEDIA_HOST = "data1.360view.link"
HISTORICAL_CONTROL = "https://workshop.360view.link/view/2612250-YK-808"


def audit(client, reference_id, viewer):
    """Probe precisely the currently supported metadata variants, no guesses."""
    ref = EvidenceReference(
        identifier=reference_id, kind=ROTATION,
        retrieval_key=viewer, locator=viewer,
    )
    adapter = WorkshopRotationDownloader(client, timeout=14)
    if not adapter.supports(ref):
        raise ValueError("Approved Workshop source no longer satisfies exact adapter contract")
    _, root, bootstrap = adapter._source(ref)
    if urlsplit(root).hostname != ALLOWED_MEDIA_HOST:
        raise ValueError("Unexpected Workshop data host")
    rows = []
    for candidate in (bootstrap, root + "/0.json"):
        try:
            response = client.get(candidate, timeout=14)
        except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
            rows.append({"variant": "empty_version" if candidate == bootstrap else "no_query",
                         "transport_error": type(exc).__name__})
            continue
        row = {
            "variant": "empty_version" if candidate == bootstrap else "no_query",
            "status": response.status_code,
            "bytes": len(response.content),
            "media_type": response.headers.get("Content-Type", "").split(";", 1)[0],
            "same_endpoint": response.url == candidate,
        }
        if response.status_code == 200 and response.url == candidate:
            try:
                obj = json.loads(response.content)
                dims, scramble, version = _bootstrap_contract(obj, source="workshop")
                row.update({
                    "valid_progressive_contract": True, "dimensions": list(dims),
                    "version": version, "scramble_tiers": len(scramble),
                })
            except (ValueError, KeyError, TypeError):
                row["valid_progressive_contract"] = False
        rows.append(row)
        # Respect explicit source blocking. In particular never follow 403 with
        # filename guesses or probes of alternate hosts.
        if response.status_code == 403:
            break
        if row.get("valid_progressive_contract"):
            break
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-motion", action="store_true",
                        help="Only when the exact original bootstrap is valid")
    args = parser.parse_args(argv)
    client = UrllibHttpClient(max_bytes=1024 * 1024)
    for name, viewer in [*SOURCES.items(), ("historical-control-2026", HISTORICAL_CONTROL)]:
        print("REFERENCE", name, flush=True)
        rows = audit(client, name, viewer)
        for row in rows:
            print("BOOTSTRAP", json.dumps(row, sort_keys=True), flush=True)
        if (args.validate_motion and rows and
            rows[0].get("valid_progressive_contract") is True):
            ref = EvidenceReference(
                identifier=name, kind=ROTATION, retrieval_key=viewer, locator=viewer,
            )
            try:
                raw = WorkshopRotationDownloader(
                    UrllibHttpClient(max_bytes=25*1024*1024), timeout=20,
                ).download(ref)
                result = ProgressiveRotationProcessor().process(raw)[0]
                print("ROTATION", json.dumps({
                    "validated": True, "frame_count": len(result.frames),
                    "dimensions": result.metadata.get("dimensions"),
                    "first_original_sha256": result.frames[0].sha256,
                }, sort_keys=True), flush=True)
            except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                print("ROTATION", json.dumps({
                    "validated": False, "failure_kind": type(exc).__name__,
                }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
