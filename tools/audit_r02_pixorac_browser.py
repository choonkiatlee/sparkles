"""Browser read-only check: does R02's Loupe viewer request Pixorac frames?

Reuses the existing bounded Chrome audit, but saves only sanitized host,
resource format, HTTP status and counts. Raw paths, queries and tokenized
Pixorac wrappers must never be persisted as CI artifacts.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from tools.audit_loupe360_browser_references import inspect_browser, query_public_record
from tools.audit_r02_pixorac import REPORT, trust_anchor


def classify_resource(item: dict) -> dict:
    raw = item.get("resource") or {}
    host = raw.get("host", "")
    path = (raw.get("path") or "").lower()
    if host == "assets-images.pixorac.com":
        kind = ("indexed_jpeg" if path.endswith(".jpg")
                else "indexed_webp" if path.endswith(".webp")
                else "pixorac_other")
    elif path.endswith((".mp4", ".mov", ".m4v", ".webm")):
        kind = "direct_video"
    elif path.endswith(".json"):
        kind = "frame_or_metadata_json"
    elif path.endswith(".html"):
        kind = "html_viewer"
    else:
        kind = "other"
    return {
        "host": host[:120],
        "kind": kind,
        "status": item.get("status"),
        "mime_type": str(item.get("mime_type") or "")[:80],
        "failed": item.get("failed", False),
    }


def summarize_browser(records: list[dict]) -> dict:
    summary = []
    for record in records:
        resources = [classify_resource(x) for x in record.get("relevant_requests", [])]
        hosts = Counter(x["host"] for x in resources)
        pixorac = [x for x in resources if x["host"] == "assets-images.pixorac.com"]
        video = [x for x in resources if x["kind"] == "direct_video"]
        dom = record.get("dom") or {}
        summary.append({
            "route": record.get("input_route"),
            "ready_state": dom.get("ready_state"),
            "canvas_count": dom.get("canvas_count"),
            "requests_total": record.get("requests_total"),
            "requests_recorded": len(resources),
            "relevant_requests_truncated": record.get("relevant_requests_truncated"),
            "host_counts": dict(hosts),
            "pixorac_requests": len(pixorac),
            "pixorac_indexed": sum(x["kind"] in ("indexed_jpeg", "indexed_webp") for x in pixorac),
            "pixorac_statuses": [x.get("status") for x in pixorac[:12]],
            "video_requests": len(video),
            "video_statuses": [x.get("status") for x in video[:12]],
            "error_type": record.get("browser_error_type"),
        })
    return {"routes": summary, "pixorac_request_total": sum(x["pixorac_requests"] for x in summary)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    trust_anchor()
    output = {
        "reference": "ps285166-r02", "report": REPORT,
        "scope": "exact Loupe360 public browser routes; sanitized metadata only",
        "publication": False,
    }
    try:
        current = query_public_record(REPORT, extended=False)
        output["lookup"] = {
            "certificate_record": current.get("certificate_record"),
            "cert_matches": current.get("cert_matches"),
            "v360": current.get("v360"),
            "video": current.get("video"),
        }
        # query_public_record describes decoded host but not raw queries.
        output["lookup"].get("v360") and output["lookup"]["v360"].pop("url", None)
        output["lookup"].get("v360") and output["lookup"]["v360"].pop("dl_link", None)
        output["lookup"].get("v360") and output["lookup"]["v360"].pop("unwrapped_url", None)
        output["lookup"]["video"] = (
            {"host": (current.get("video") or {}).get("host"),
             "path_format": (current.get("video") or {}).get("path", "").rsplit(".", 1)[-1]
              if (current.get("video") or {}).get("path", "").endswith((".mp4", ".webm")) else "other"}
            if isinstance(current.get("video"), dict) else None
        )
    except Exception as exc:
        output["lookup_error_type"] = type(exc).__name__
    try:
        output["browser"] = summarize_browser(inspect_browser(REPORT, seconds=6))
    except Exception as exc:
        output["browser_error_type"] = type(exc).__name__
    data = json.dumps(output, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(data + "\n", encoding="utf-8")
    print(data, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
