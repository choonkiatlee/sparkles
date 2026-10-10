"""Browser read-only check: does R02's Loupe viewer request Pixorac frames?

Reuses the existing bounded Chrome audit, but saves only sanitized host,
resource format, HTTP status and counts. Raw paths, queries and tokenized
Pixorac wrappers must never be persisted as CI artifacts.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import re
from collections import Counter
from pathlib import Path

from tools.audit_loupe360_browser_references import inspect_browser, query_public_record
from tools.audit_r02_pixorac import REPORT, MAX_FRAME_BYTES, proxy_source, trust_anchor, verify_frames
from diamond_retrieval.http import UrllibHttpClient


def classify_resource(item: dict) -> dict:
    raw = item.get("resource") or {}
    host = raw.get("host", "")
    path = (raw.get("path") or "").lower()
    if host == "assets-images.pixorac.com":
        matched = _INDEXED.fullmatch(path)
        kind = ("indexed_jpeg" if matched and path.endswith(".jpg")
                else "indexed_webp" if matched and path.endswith(".webp")
                else "standalone_image" if path.endswith((".jpg", ".webp"))
                else "pixorac_other")
    elif path.endswith((".mp4", ".mov", ".m4v", ".webm")):
        kind = "direct_video"
    elif path.endswith(".json"):
        kind = "frame_or_metadata_json"
    elif path.endswith(".html"):
        kind = "html_viewer"
    else:
        kind = "other"
    pieces = [x for x in path.split("/") if x]
    last = pieces[-1] if pieces else ""
    path_shape = {
        "depth": len(pieces),
        "first_component_length": len(pieces[0]) if pieces else 0,
        "middle_component_length": len(pieces[1]) if len(pieces) > 2 else 0,
        "middle_component_numeric": bool(len(pieces) > 2 and pieces[1].isdigit()),
        "has_query": bool(raw.get("has_query")),
        "last_numeric_image": bool(re.fullmatch(r"[0-9]{1,3}\.(?:jpg|webp)", last)),
        "suffix": "webp" if last.endswith(".webp") else "jpg" if last.endswith(".jpg") else "other",
    }
    return {
        "path_shape": path_shape,
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
            "pixorac_path_shapes": [x.get("path_shape") for x in pixorac[:12]],
            "pixorac_kinds": dict(Counter(x["kind"] for x in pixorac)),
            "video_requests": len(video),
            "video_statuses": [x.get("status") for x in video[:12]],
            "error_type": record.get("browser_error_type"),
        })
    return {"routes": summary, "pixorac_request_total": sum(x["pixorac_requests"] for x in summary)}



_INDEXED = re.compile(r"^/([A-Za-z0-9_-]{20,1024}={0,2})(?:/([A-Za-z0-9_-]{1,24}))?/([0-9]{1,3})\.(jpg|webp)$")


def browser_cache_candidate(records: list[dict], lookup: dict) -> tuple[str | None, int | None, dict]:
    """Recover *observed* Pixorac roots, only for an exact IGI Loupe browser.

    A URL is never generated from a certificate or supplier inventory ID.
    Exactly one root must be seen on the exact viewer's successful requests.
    """
    if (lookup.get("cert_matches") is not True or lookup.get("lab") != "IGI"):
        return None, None, {"outcome": "certificate_identity_not_matched"}
    v360 = lookup.get("v360")
    if not isinstance(v360, dict) or str(v360.get("frame_count")) != "256":
        return None, None, {"outcome": "missing_256_frame_metadata"}
    top_value = v360.get("top_index")
    if isinstance(top_value, bool) or not str(top_value).isdigit():
        return None, None, {"outcome": "missing_top_index"}
    top = int(top_value)
    if top < 0 or top >= 256:
        return None, None, {"outcome": "invalid_top_index"}

    roots: dict[tuple[str, str | None], set[int]] = {}
    pixorac_total = 0
    for record in records:
        if record.get("input_route") not in ("landing", "/video/500/500"):
            continue
        for item in record.get("relevant_requests", ()):
            source = item.get("resource") or {}
            if source.get("host") != "assets-images.pixorac.com":
                continue
            pixorac_total += 1
            if item.get("status") != 200 or source.get("has_query"):
                continue
            match = _INDEXED.fullmatch(source.get("path") or "")
            if not match:
                continue
            index = int(match.group(3))
            if index >= 256:
                continue
            # Both the token and optional media-size segment were observed
            # verbatim in the trusted exact report's browser request. Neither
            # is derived from a guessed stone ID or an inventory search.
            key = (match.group(1), match.group(2))
            roots.setdefault(key, set()).add(index)
    output = {"indexed_requests_observed": pixorac_total,
              "distinct_indexed_roots": len(roots)}
    if len(roots) != 1:
        return None, None, {**output, "outcome": "ambiguous_or_absent_observed_roots"}
    (token, media_variant), indices = next(iter(roots.items()))
    base_root = "https://assets-images.pixorac.com/" + token
    exact_root = base_root + ("/" + media_variant if media_variant else "")
    try:
        _, _, viewer_kind = proxy_source({
            "url": base_root, "frame_count": 256, "top_index": top,
        })
    except (ValueError, TypeError):
        return None, None, {**output, "outcome": "observed_root_does_not_wrap_known_r02_source"}
    return exact_root, top, {
        **output, "outcome": "one_exact_browser_observed_source",
        "proxy_root_sha256": hashlib.sha256(exact_root.encode()).hexdigest(),
        "observed_distinct_indices": len(indices),
        "media_variant_present": media_variant is not None,
        "top_index_observed": top in indices,
        "supplier_viewer_kind": viewer_kind,
        "top_index": top,
    }


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
        browser_records = inspect_browser(REPORT, seconds=6)
        output["browser"] = summarize_browser(browser_records)
        if "current" in locals():
            root, top, source = browser_cache_candidate(browser_records, current)
            output["browser_cache"] = source
            if root is not None and top is not None:
                # Read only source bytes in memory; never attach frames to a
                # manifest merely because a few Chrome requests succeeded.
                output["browser_cache"]["frame_audit"] = verify_frames(
                    UrllibHttpClient(max_bytes=MAX_FRAME_BYTES), root, top,
                )
    except Exception as exc:
        output["browser_error_type"] = type(exc).__name__
    data = json.dumps(output, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(data + "\n", encoding="utf-8")
    print(data, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
