"""Exact Imgur album Chromium DOM/network-metadata audit for PriceScope R13-R15.

Research only: no media GETs issued by our code; block first-party image/video
origins and common video extensions in Chromium before navigation. Never save
page HTML, asset bytes, cookies, screenshots, or secrets. No per-stone attribution
unless independently evidenced outside this automatic diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from tools.audit_r13_r15_imgur import ALBUMS, check_manifest, validate_album

ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXT = re.compile(r"\.(?:mp4|webm|mov|m4v|m3u8)(?:$|[?#])", re.I)
MEDIA_BLOCK_PATTERNS = [
    "*://i.imgur.com/*",          # first-party image, animation and video CDN
    "*://*.imgur.com/*.mp4*",
    "*://*.imgur.com/*.webm*",
    "*://*.imgur.com/*.gifv*",
    "*://*/*.mp4*",              # prevent other direct video GET transports
    "*://*/*.webm*",
    "*://*/*.m4v*",
    "*://*/*.mov*",
    "*://*/*.m3u8*",
]
MAX_REQUESTS = 75
MAX_LABELS = 18


def safe_location(url: str) -> dict:
    """Store host/path digest only; never store query or unreviewed URLs."""
    try:
        part = urlsplit(url)
        host = (part.hostname or "").lower()
        if part.scheme != "https" or not host or part.username or part.password:
            return {"valid_https": False}
        if part.port not in (None, 443):
            return {"valid_https": False}
        path = part.path or "/"
        source = "imgur" if host == "imgur.com" or host.endswith(".imgur.com") else "other"
        return {
            "valid_https": True,
            "provider": source,
            "host": host if source == "imgur" else "other",
            "path_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest(),
            "looks_like_video": bool(VIDEO_EXT.search(path)),
            "query_present": bool(part.query),
        }
    except (ValueError, TypeError, AttributeError):
        return {"valid_https": False}


def sanitise_labels(labels) -> list[dict]:
    """Visible caption/title *hints* do not establish per-clip identity."""
    if not isinstance(labels, list):
        return []
    out = []
    for obj in labels[:MAX_LABELS]:
        if not isinstance(obj, dict):
            continue
        text = obj.get("text")
        role = obj.get("role")
        if not isinstance(text, str) or not isinstance(role, str):
            continue
        # One short, public visible label; controls stripped, no page dumps.
        clean = " ".join(text.split())[:140]
        if clean and role in {"h1", "h2", "h3", "figcaption", "caption", "title"}:
            out.append({"role": role, "visible_label": clean})
    return out


def classify_browser(page: dict, network: list[dict], *, current_url: str, expected_url: str = "") -> dict:
    """Classify reachability while deliberately *abstaining* on stone mapping."""
    final = urlsplit(current_url)
    exact_host = final.scheme == "https" and final.hostname in {"imgur.com", "www.imgur.com"}
    exact_album = exact_host and final.path == urlsplit(expected_url).path if expected_url else exact_host
    values = page if isinstance(page, dict) else {}
    title = str(values.get("title") or "")[:120]
    body_signals = values.get("body_signals") or {}
    restricted = bool(body_signals.get("geo_restriction") or body_signals.get("access_denied"))
    error_page = bool(body_signals.get("not_found"))
    videos = values.get("video_nodes") or []
    if not exact_host:
        status = "redirected_outside_reviewed_album_host"
    elif not exact_album:
        status = "browser_navigated_away_from_reviewed_album"
    elif restricted:
        status = "region_or_access_restricted"
    elif error_page:
        status = "page_not_found"
    elif title.startswith("Imgur: The magic of the Internet") and not any(
        "asscher" in x.get("text", "").lower() for x in values.get("labels", []) if isinstance(x, dict)
    ):
        status = "generic_homepage_no_album_identity"
    elif videos or values.get("figure_nodes", 0) or values.get("image_nodes", 0):
        status = "browser_dom_media_elements_observed"
    else:
        status = "browser_page_no_visible_media_elements"

    return {
        "status": status,
        "exact_album_path_preserved": exact_album,
        "page_title": title,
        "ready_state": values.get("ready_state"),
        "dom": {
            "video_nodes": min(len(videos), 50),
            "image_nodes": values.get("image_nodes", 0),
            "figure_nodes": values.get("figure_nodes", 0),
            "video_source_hints": [
                safe_location(node.get("source", ""))
                for node in videos[:12] if isinstance(node, dict) and node.get("source")
            ],
            "labels": sanitise_labels(values.get("labels", [])),
        },
        "network": network[:MAX_REQUESTS],
        "network_truncated": len(network) > MAX_REQUESTS,
        "media_original_bytes_downloaded": False,
        "clip_count_verified": False,
        "per_stone_clip_mapping": "unknown",
        "review_note": "DOM/metadata requests cannot prove clip authorship or stone attribution",
    }


def summarize_performance(rows: list[dict]) -> list[dict]:
    requests: dict[str, dict] = {}
    for row in rows:
        try:
            message = json.loads(row["message"])["message"]
            method = message["method"]
            params = message["params"]
            request_id = params.get("requestId")
        except (KeyError, TypeError, ValueError):
            continue
        if method == "Network.requestWillBeSent":
            source = safe_location((params.get("request") or {}).get("url", ""))
            if not source.get("valid_https"):
                continue
            typ = str(params.get("type") or "unknown")
            if not (source["provider"] == "imgur" or source["looks_like_video"]
                    or typ in {"Media", "XHR", "Fetch"}):
                continue
            requests[request_id] = {"location": source, "resource_type": typ}
        elif method == "Network.responseReceived" and request_id in requests:
            response = params.get("response") or {}
            requests[request_id]["http_status"] = response.get("status")
            requests[request_id]["mime_type"] = str(response.get("mimeType") or "")[:70]
        elif method == "Network.loadingFailed" and request_id in requests:
            requests[request_id]["request_failed_or_blocked"] = True
    # Do not persist arbitrary script/style traffic; relevant observed metadata only.
    return [item for item in requests.values()
            if item["location"]["looks_like_video"]
            or item["resource_type"] in {"Media", "XHR", "Fetch"}
            or item.get("mime_type", "").startswith("video/")][:MAX_REQUESTS + 1]



def _metadata_items(data: object) -> list[dict]:
    """Public JSON keys only; never persist raw API documents or media locators."""
    found = []
    seen = set()

    def visit(node: object, depth: int) -> None:
        if depth > 7 or len(found) >= 16:
            return
        if isinstance(node, dict):
            # Album media may be nested under data / media / images. Only emit
            # metadata from records that explicitly describe media objects.
            keys = set(node)
            if (("id" in keys or "hash" in keys)
                    and ({"type", "mime_type", "is_animated", "animated",
                          "width", "height", "size", "duration"} & keys)):
                label = node.get("title") or node.get("description") or node.get("caption")
                ident = str(node.get("id") or node.get("hash") or "")
                if ident and ident not in seen:
                    seen.add(ident)
                    found.append({
                        "opaque_media_id_sha256": hashlib.sha256(ident.encode()).hexdigest(),
                        "mime_type": str(node.get("mime_type") or node.get("type") or "")[:40],
                        "width": node.get("width") if type(node.get("width")) is int else None,
                        "height": node.get("height") if type(node.get("height")) is int else None,
                        "label": " ".join(label.split())[:120] if isinstance(label, str) else None,
                    })
            for value in list(node.values())[:100]:
                visit(value, depth + 1)
        elif isinstance(node, list):
            for value in node[:50]:
                visit(value, depth + 1)

    visit(data, 0)
    return found


def inspect_observed_album_json(browser, events: list[dict], album: str) -> list[dict]:
    """Read ONLY small, already-delivered, public same-album JSON via CDP.

    No new HTTP call, no video/image response body, no request-header/cookie
    reads, and no guessed API routes. Omit responses without declared small size.
    """
    album_token = urlsplit(album).path.rsplit("/", 1)[-1]
    out = []
    seen = set()
    for row in events:
        if len(out) >= 4:
            break
        try:
            event = json.loads(row["message"])["message"]
            if event["method"] != "Network.responseReceived":
                continue
            params = event["params"]
            response = params["response"]
            url = response["url"]
            part = urlsplit(url)
            if part.hostname != "api.imgur.com" or album_token not in part.path:
                continue
            if response.get("status") != 200:
                continue
            mime = str(response.get("mimeType") or "").lower()
            if not ("json" in mime):
                continue
            headers = {k.lower(): v for k, v in (response.get("headers") or {}).items()}
            length = headers.get("content-length", "")
            if not str(length).isdigit() or int(length) > 150_000:
                continue
            request_id = params["requestId"]
            if request_id in seen:
                continue
            seen.add(request_id)
            raw = browser.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            if raw.get("base64Encoded"):
                continue
            content = raw.get("body", "")
            if len(content) > 150_000:
                continue
            parsed = json.loads(content)
            out.append({"json_size": len(content), "observed_api_album": True,
                        "media_item_hints": _metadata_items(parsed)})
        except (KeyError, ValueError, TypeError, AttributeError, Exception):
            continue
    return out


# Script only queries bounded public visible metadata; it does not fetch.
DOM_SCRIPT = r"""
const selected = [];
for (const selector of [
  ['h1','h1'],['h2','h2'],['h3','h3'],
  ['figcaption','figcaption'],
  ['[class*="caption"]','caption'],
  ['[data-testid*="title"]','title']]) {
  for (const el of document.querySelectorAll(selector[0])) {
    if (selected.length >= 18) break;
    selected.push({role: selector[1], text: (el.innerText || el.textContent || '').slice(0,140)});
  }
}
const body = (document.body?.innerText || '').slice(0,3000).toLowerCase();
return {
  title: (document.title || '').slice(0,120),
  ready_state: document.readyState,
  video_nodes: [...document.querySelectorAll('video')].slice(0,12).map(el=>({
    source: (el.currentSrc || el.src || '').slice(0,2048),
    have_metadata: el.readyState >= 1
  })),
  image_nodes: document.querySelectorAll('img, picture').length,
  figure_nodes: document.querySelectorAll('figure').length,
  labels: selected,
  body_signals: {
    geo_restriction: /not available in (your|this) (region|country)|not available in the uk|unavailable in (your|this) (region|country)/.test(body),
    access_denied: /access denied|unavailable from your region/.test(body),
    not_found: /page (was not|is not) found|content (has been|was) deleted|couldn't find that page/.test(body)
  }
};
"""


def run_browser_audit(*, dwell: float = 5.0) -> list[dict]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for arg in (
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1280,900", "--autoplay-policy=user-gesture-required",
        "--disable-background-networking",
    ):
        options.add_argument(arg)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    browser = webdriver.Chrome(options=options)
    try:
        browser.set_page_load_timeout(20)
        browser.execute_cdp_cmd("Network.enable", {})
        browser.execute_cdp_cmd("Network.setBlockedURLs", {"urls": MEDIA_BLOCK_PATTERNS})
        records = []
        for group, (album, refs) in ALBUMS.items():
            validate_album(album)
            check_manifest(group)
            report = {
                "group": group, "references": refs, "album": album,
                "first_order": "R14 first, R15 second" if group == "R14_R15" else "R12 H, R13 G",
                "media_original_bytes_downloaded": False, "per_stone_clip_mapping": "unknown",
            }
            try:
                browser.get(album)
                time.sleep(dwell)
                page = browser.execute_script(DOM_SCRIPT)
                events = browser.get_log("performance")
                report.update(classify_browser(page, summarize_performance(events),
                                               current_url=browser.current_url, expected_url=album))
                report["album_api_metadata"] = inspect_observed_album_json(browser, events, album)
            except Exception as exc:
                report.update({
                    "status": "browser_page_unavailable",
                    "error_class": type(exc).__name__,
                    "media_original_bytes_downloaded": False,
                    "per_stone_clip_mapping": "unknown",
                })
                # Discard unsanitized network events after partial navigation.
                try:
                    browser.get_log("performance")
                except Exception:
                    pass
            records.append(report)
        return records
    finally:
        browser.quit()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    for group in ALBUMS:
        check_manifest(group)
    result = {
        "schema": "sparkles-r13-r15-imgur-browser-readonly/1",
        "scope": "exact two album Chromium DOM+network metadata; media CDN and direct video URL patterns blocked",
        "cases": [],
    }
    try:
        result["cases"] = run_browser_audit()
    except Exception as exc:
        result["browser_status"] = "unavailable"
        result["error_class"] = type(exc).__name__
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("R13_R15_IMGUR_BROWSER " + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result.get("cases") else 2


if __name__ == "__main__":
    raise SystemExit(main())
