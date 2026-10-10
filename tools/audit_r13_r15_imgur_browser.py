"""Exact-album Selenium DOM/network *metadata* audit for PriceScope R12–R15.

Headless Chrome visits only two pinned public Imgur pages; browser media/image
URLs are blocked BEFORE navigation. No media bytes, screenshots, response bodies,
cookies, credentials, URL tokens, publication, or inferred stone identities.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from tools.audit_r13_r15_imgur import ALBUMS, check_manifest, validate_album

ALLOWED_HOSTS = frozenset({"imgur.com", "www.imgur.com", "i.imgur.com"})
# Chrome CDP blocked patterns: media body GETs are denied before network fetch.
# Include thumbnails/stills too so this audit cannot become a media downloader.
BLOCKED_MEDIA_PATTERNS = (
    "*.mp4*", "*.webm*", "*.m4v*", "*.mov*", "*.m3u8*", "*.mpd*",
    "*.gif*", "*.jpg*", "*.jpeg*", "*.png*", "*.webp*", "*.avif*",
)
MEDIA_SUFFIX = re.compile(r"\.(mp4|webm|m4v|mov|m3u8|mpd|gif|jpg|jpeg|png|webp|avif)$", re.I)
VIDEO_SUFFIX = frozenset({".mp4", ".webm", ".m4v", ".mov", ".m3u8", ".mpd"})
MAX_MEDIA_RECORDS = 36
MAX_DOM_ITEMS = 32
MAX_LOG_ROWS = 2400

# Pure DOM inspection, no fetches, navigation, element clicks, or video playback.
DOM_JS = r"""
(() => {
  const texts = el => (el?.textContent || "").trim().replace(/\s+/g, " ").slice(0,160);
  const albumItems = [...document.querySelectorAll(
    'figure, [data-testid="post-container"], [data-testid="gallery-item"], .Gallery-Item, .Post-item'
  )].slice(0,32);
  return {
    ready_state: document.readyState,
    title: (document.title || "").slice(0,160),
    body_block_message: /not available in your (country|region)|unavailable in your region|access to imgur is blocked|unavailable in the uk|error 403/i.test((document.body?.innerText || "").slice(0,3000)),
    video_elements: [...document.querySelectorAll("video")].slice(0,36).map(v => ({
      src: v.currentSrc || v.getAttribute("src") || "",
      poster: v.getAttribute("poster") || "",
      preload: v.preload || "",
      duration_known: Number.isFinite(v.duration) && v.duration > 0,
      video_width: v.videoWidth || 0, video_height: v.videoHeight || 0,
      title: v.getAttribute("title") || "", aria_label: v.getAttribute("aria-label") || ""
    })),
    sources: [...document.querySelectorAll("source")].slice(0,36).map(v => ({
      src: v.getAttribute("src") || "", type: v.getAttribute("type") || ""
    })),
    item_labels: albumItems.map(v => ({
      label: texts(v.querySelector("figcaption,[data-testid*='caption'],[aria-label]")),
      heading: texts(v.querySelector("h1,h2,h3")),
      video_count: v.querySelectorAll("video").length,
      source_count: v.querySelectorAll("source").length
    })),
    item_nodes_detected: albumItems.length,
    main_text_length: (document.querySelector("main")?.innerText || "").length
  };
})()
"""


def _url_details(url: object) -> dict | None:
    """Return only safe metadata for an observed request, never a complete URL."""
    if not isinstance(url, str) or len(url) > 4096:
        return None
    try:
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password:
            return None
        host = p.hostname.lower()
        ipaddress.ip_address(host)
        return None
    except ValueError:
        if "host" not in locals():
            return None
    suffix = ("." + p.path.rsplit(".", 1)[-1].lower()) if "." in p.path.rsplit("/", 1)[-1] else ""
    is_video = suffix in VIDEO_SUFFIX
    is_media = bool(MEDIA_SUFFIX.search(p.path))
    # A path/hash is public source metadata, but never persist tokens or full URLs.
    return {"host": host, "allowed_first_party": host in ALLOWED_HOSTS,
            "extension": suffix[:8] if is_media else "",
            "media_type": "video" if is_video else ("image" if is_media else "other"),
            "opaque_path_sha256": hashlib.sha256(p.path.encode()).hexdigest(),
            "query_present": bool(p.query)}


def media_url_details(url: object) -> dict | None:
    details = _url_details(url)
    if details is None or not details["allowed_first_party"] or details["media_type"] != "video":
        return None
    return details


def _label_signals(label: object) -> dict:
    """Record only stone/ordinal textual markers, never raw page text."""
    s = str(label or "")[:160].lower()
    return {
        "first": bool(re.search(r"\b(first|1st)\b", s)),
        "second": bool(re.search(r"\b(second|2nd)\b", s)),
        "r12_h_410": bool(re.search(r"\b4[.,]10\b|\b4[.,]1\s*(?:ct|carat)", s)),
        "r13_g_342": bool(re.search(r"\b3[.,]42\b", s)),
        "r14_or_r15_e_200": bool(re.search(r"\b2[.,]00\b|\b2\s*(?:ct|carat)", s)),
        "nonempty": bool(s.strip()),
    }


def summarize_dom(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"status": "dom_unavailable"}
    videos = payload.get("video_elements") if isinstance(payload.get("video_elements"), list) else []
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    items = payload.get("item_labels") if isinstance(payload.get("item_labels"), list) else []
    clips = []
    for entry in (videos[:MAX_MEDIA_RECORDS] + sources[:MAX_MEDIA_RECORDS]):
        if not isinstance(entry, dict):
            continue
        detail = media_url_details(entry.get("src"))
        clips.append({
            "media": detail,
            "poster_observed": bool(_url_details(entry.get("poster"))),
            "video_width": entry.get("video_width") if isinstance(entry.get("video_width"), int) else 0,
            "video_height": entry.get("video_height") if isinstance(entry.get("video_height"), int) else 0,
            "has_duration": entry.get("duration_known") is True,
            "label_signals": _label_signals(" ".join(str(entry.get(k) or "") for k in ("title", "aria_label"))),
        })
    return {
        "status": "dom_observed",
        "ready_state": str(payload.get("ready_state"))[:25],
        "region_block_message": payload.get("body_block_message") is True,
        "video_nodes": min(len(videos), MAX_MEDIA_RECORDS),
        "source_nodes": min(len(sources), MAX_MEDIA_RECORDS),
        "item_nodes": min(int(payload.get("item_nodes_detected") or 0), MAX_DOM_ITEMS),
        "item_signals": [
            {**_label_signals(item.get("label")), "heading_signals": _label_signals(item.get("heading")),
             "video_nodes": int(item.get("video_count") or 0)}
            for item in items[:MAX_DOM_ITEMS] if isinstance(item, dict)
        ],
        "dom_video_candidates": clips[:MAX_MEDIA_RECORDS],
        "title_signals": _label_signals(payload.get("title")),
    }


def summarize_network(rows: list[dict]) -> dict:
    requests = {}
    for row in rows[:MAX_LOG_ROWS]:
        try:
            m = row["message"]
            packet = json.loads(m)["message"] if isinstance(m, str) else m
            event, params = packet["method"], packet["params"]
            rid = str(params["requestId"])
            if event == "Network.requestWillBeSent":
                d = _url_details(params.get("request", {}).get("url"))
                if d and d["media_type"] != "other":
                    requests[rid] = {"candidate": d, "resource_type": str(params.get("type") or "")[:30],
                                     "http": None, "blocked": False}
            elif event == "Network.responseReceived" and rid in requests:
                response = params["response"]
                requests[rid]["http"] = int(response.get("status") or 0)
                requests[rid]["mime"] = str(response.get("mimeType") or "")[:60]
            elif event == "Network.loadingFailed" and rid in requests:
                text = str(params.get("errorText") or "")
                requests[rid]["blocked"] = "ERR_BLOCKED_BY_CLIENT" in text
                requests[rid]["failed"] = True
        except (KeyError, ValueError, TypeError):
            continue
    # Requests include media blocked by CDP: blocked URLs never become evidence of accessible bytes.
    found = list(requests.values())
    return {
        "media_requests_seen": len(found),
        "media_requests_truncated": len(found) > MAX_MEDIA_RECORDS or len(rows) > MAX_LOG_ROWS,
        "blocked_by_browser": sum(v.get("blocked", False) for v in found),
        "video_requests_seen": sum(v["candidate"]["media_type"] == "video" for v in found),
        "media_requests": found[:MAX_MEDIA_RECORDS],
    }


def disposition(group: str, dom: dict, net: dict) -> dict:
    """DOM/link discovery is insufficient to assign source bytes to diamonds."""
    blocked = dom.get("region_block_message") is True
    video_requests = net.get("video_requests_seen", 0)
    nodes = dom.get("video_nodes", 0)
    return {
        "status": "region_or_access_blocked" if blocked else (
            "video_hint_observed_not_attributed" if video_requests or nodes
            else "no_video_observed_not_evidence_of_absence"),
        "original_clip_count_verified": False,
        "per_stone_attribution": "unknown",
        "playable_motion_verified": False,
        "download_permission": "not_established",
        "rehosting_permission": "not_established",
        "composite_vs_separate": "unknown",
        "next_action": "human_review_source_labels_or_original_owner_media"
        if video_requests or nodes else "obtain_new_public_same_stone_evidence",
    }


def inspect_pair(group: str, driver, *, seconds=4) -> dict:
    url, refs = ALBUMS[group]
    validate_album(url)
    result = {"group": group, "album_url": url, "reference_ids": refs,
              "media_downloaded": False, "browser_policy": "block_all_media_extensions_before_navigation"}
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": list(BLOCKED_MEDIA_PATTERNS)})
        driver.get(url)
        time.sleep(min(max(seconds, 0), 6))
        current = _url_details(driver.current_url)
        result["final_host"] = current.get("host") if current else None
        result["final_album_page"] = driver.current_url == url
        if not result["final_album_page"]:
            # Redirects to login, blocked pages or another source cannot authorise media.
            result["status"] = "navigation_outside_exact_album"
        else:
            result["dom"] = summarize_dom(driver.execute_script(DOM_JS))
    except Exception as exc:
        result["status"] = "browser_error"
        result["error_type"] = type(exc).__name__
    try:
        network = summarize_network(driver.get_log("performance"))
    except Exception as exc:
        network = {"status": "performance_logs_unavailable", "error_type": type(exc).__name__}
    result["network"] = network
    result["decision"] = disposition(group, result.get("dom", {}), network)
    if result.get("status") in ("browser_error", "navigation_outside_exact_album"):
        result["decision"]["status"] = "no_trusted_page"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    for group in ALBUMS:
        check_manifest(group)

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for flag in (
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-background-networking", "--disable-extensions",
        "--blink-settings=imagesEnabled=false",
        "--autoplay-policy=user-gesture-required", "--window-size=1180,900",
    ):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(18)
    results = []
    try:
        for group in ALBUMS:  # R14/R15 first
            results.append(inspect_pair(group, driver))
    finally:
        driver.quit()
    payload = {"schema": "sparkles-r13-r15-imgur-browser-readonly/1",
               "no_media_download_or_publishing": True, "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("R13_R15_IMGUR_BROWSER " + json.dumps(payload, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
