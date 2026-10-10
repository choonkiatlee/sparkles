"""R12–R15 exact public Imgur video HEAD metadata audit.

Visits only the two reviewed album URLs. Browser-blocked media requests are
matched against opaque IDs in already-delivered same-album API JSON; only those
observed original HTTPS MP4 URLs may receive HEAD (never GET). No downloads,
stones assigned, media publication, cookies, thumbnails or response-body dumps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from tools.audit_r13_r15_imgur import ALBUMS, check_manifest, validate_album
from tools.audit_r13_r15_imgur_browser import MEDIA_BLOCK_PATTERNS

_ID = re.compile(r"[A-Za-z0-9]{5,16}\Z")
_MP4_PATH = re.compile(r"/([A-Za-z0-9]{5,16})\.mp4\Z")
MAX_HEAD = 4
MAX_PUBLIC_JSON = 150_000
MAX_DECLARED_MP4 = 30_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_observed_mp4(url: str, original_media_id: str) -> str:
    """Prevent guessing a URL from an album item ID alone."""
    if not isinstance(url, str) or not isinstance(original_media_id, str):
        raise ValueError("invalid observed media")
    if not _ID.fullmatch(original_media_id):
        raise ValueError("invalid media ID")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "i.imgur.com"
            or parts.port not in (None, 443) or parts.username or parts.password
            or parts.query or parts.fragment or not _MP4_PATH.fullmatch(parts.path)
            or _MP4_PATH.fullmatch(parts.path).group(1) != original_media_id):
        raise ValueError("video must be exact observed first-party MP4 from album")
    return url


def ordered_media_items(tree: object) -> list[dict]:
    """Traverse bounded public JSON in original album response order.

    Source metadata isn't physical stone identity. Item ordinals are recorded
    only as album position; no R14/R15 or R12/R13 attribution is made.
    """
    items: list[dict] = []
    seen: set[str] = set()
    def visit(node: object, depth: int):
        if depth > 7 or len(items) >= 30:
            return
        if isinstance(node, dict):
            ident = node.get("id") or node.get("hash")
            media_type = node.get("type") or node.get("mime_type")
            if (isinstance(ident, str) and _ID.fullmatch(ident)
                    and isinstance(media_type, str)
                    and media_type.lower().split(";", 1)[0] in {"video/mp4", "image/jpeg"}
                    and ident not in seen):
                seen.add(ident)
                label = node.get("title") or node.get("description") or node.get("caption")
                items.append({
                    "original_id": ident, "media_type": media_type.lower().split(";", 1)[0],
                    "album_item_position": len(items),
                    "width": node.get("width") if type(node.get("width")) is int else None,
                    "height": node.get("height") if type(node.get("height")) is int else None,
                    "source_caption": " ".join(label.split())[:100] if isinstance(label, str) else None,
                })
            for val in list(node.values())[:80]:
                visit(val, depth + 1)
        elif isinstance(node, list):
            for val in node[:50]:
                visit(val, depth + 1)
    visit(tree, 0)
    return items


def observed_album_json(browser, events: list[dict], album: str,
                        diagnostic: dict | None = None) -> list[dict]:
    """Use only already-delivered same-album JSON; no new API calls."""
    token = urlsplit(validate_album(album)).path.rsplit("/", 1)[-1]
    stats = diagnostic if diagnostic is not None else {}
    stats.update({"same_album_api_responses": 0, "json_candidates": 0,
                  "response_body_attempts": 0, "media_entries_parsed": 0,
                  "body_error_classes": []})
    for row in events:
        try:
            event = json.loads(row["message"])["message"]
            if event["method"] != "Network.responseReceived":
                continue
            params = event["params"]
            response = params["response"]
            parts = urlsplit(response["url"])
            if (parts.scheme != "https" or parts.hostname != "api.imgur.com"
                    or token not in parts.path):
                continue
            stats["same_album_api_responses"] += 1
            if response.get("status") != 200 or "json" not in str(response.get("mimeType", "")).lower():
                continue
            stats["json_candidates"] += 1
            headers = {k.lower(): v for k, v in response.get("headers", {}).items()}
            length = headers.get("content-length", "")
            if not str(length).isdigit() or int(length) > MAX_PUBLIC_JSON:
                continue
            stats["response_body_attempts"] += 1
            raw = browser.execute_cdp_cmd("Network.getResponseBody", {
                "requestId": params["requestId"],
            })
            content = raw.get("body", "")
            if raw.get("base64Encoded") or len(content) > MAX_PUBLIC_JSON:
                continue
            matches = ordered_media_items(json.loads(content))
            stats["media_entries_parsed"] = max(stats["media_entries_parsed"], len(matches))
            if matches:
                return matches
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            if type(exc).__name__ not in stats["body_error_classes"]:
                stats["body_error_classes"].append(type(exc).__name__)
            continue
        except Exception as exc:
            if type(exc).__name__ not in stats["body_error_classes"]:
                stats["body_error_classes"].append(type(exc).__name__)
            continue
    return []


def observed_mp4_requests(events: list[dict]) -> dict[str, str]:
    """Observed blocked CDN requests only; no URL construction from metadata."""
    matches = {}
    for row in events:
        try:
            event = json.loads(row["message"])["message"]
            if event["method"] != "Network.requestWillBeSent":
                continue
            raw = event["params"]["request"]["url"]
            parts = urlsplit(raw)
            match = _MP4_PATH.fullmatch(parts.path)
            if (parts.scheme != "https" or parts.hostname != "i.imgur.com"
                    or not match or parts.query or parts.fragment):
                continue
            media_id = match.group(1)
            if media_id not in matches:
                matches[media_id] = validate_observed_mp4(raw, media_id)
        except (KeyError, ValueError, TypeError):
            continue
    return matches


def _head(url: str, *, opener=None) -> tuple[int, dict]:
    opener = opener or build_opener(HTTPSHandler(), NoRedirect())
    request = Request(url, method="HEAD", headers={
        "User-Agent": "Sparkles-Exact-Album-HEAD-Only/1",
        "Accept": "video/mp4",
    })
    try:
        with opener.open(request, timeout=12) as response:
            return response.status, dict(response.headers.items())
    except HTTPError as error:
        return error.code, dict(error.headers.items())


def check_video_head(url: str, original_media_id: str, *, opener=None) -> dict:
    validate_observed_mp4(url, original_media_id)
    out = {"media_id_sha256": hashlib.sha256(original_media_id.encode()).hexdigest(),
           "no_body_download": True}
    try:
        status, headers = _head(url, opener=opener)
        canonical = {k.lower(): v for k, v in headers.items()}
        mime = str(canonical.get("content-type") or "").split(";", 1)[0].lower().strip()
        size = canonical.get("content-length", "")
        number = int(size) if str(size).isdigit() else None
        out.update({
            "head_http": status, "mime_type": mime, "declared_bytes": number,
            "status": ("accessible_mp4_metadata" if status == 200 and mime == "video/mp4"
                       and number is not None and 0 < number <= MAX_DECLARED_MP4
                       else "unverified_or_unavailable"),
        })
    except (OSError, ValueError, URLError) as error:
        out.update({"status": "head_transport_error", "error_class": type(error).__name__})
    return out


def summarize_album_items(items: list[dict], urls: dict[str, str], *, remaining: int,
                          check=check_video_head) -> tuple[list[dict], int]:
    out = []
    used = 0
    for item in items:
        # Allow photos as *album metadata* only: no HEAD or image download.
        result = {
            "album_item_position": item["album_item_position"],
            "media_type": item["media_type"],
            "media_id_sha256": hashlib.sha256(item["original_id"].encode()).hexdigest(),
            "dimensions": [item["width"], item["height"]],
            "caption": item["source_caption"],
            "per_stone_identity": "unknown",
        }
        if item["media_type"] == "video/mp4":
            url = urls.get(item["original_id"])
            if url and used < remaining:
                result["head"] = check(url, item["original_id"])
                used += 1
            else:
                result["head"] = {"status": "no_exact_observed_matching_media_request"}
        out.append(result)
    return out, used


def run_browser() -> list[dict]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                 "--window-size=1280,900", "--autoplay-policy=user-gesture-required"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    browser = webdriver.Chrome(options=options)
    try:
        browser.set_page_load_timeout(22)
        browser.execute_cdp_cmd("Network.enable", {})
        browser.execute_cdp_cmd("Network.setBlockedURLs", {"urls": MEDIA_BLOCK_PATTERNS})
        outcomes = []
        total_head = 0
        for group, (album, refs) in ALBUMS.items():
            check_manifest(group)
            validate_album(album)
            case = {"album_group": group, "references": refs, "pinned_album": album,
                    "clip_attribution": "unverified", "video_bytes_downloaded": False,
                    "republication_rights": "not_established"}
            try:
                browser.get(album)
                time.sleep(5)
                events = browser.get_log("performance")
                stats = {}
                items = observed_album_json(browser, events, album, diagnostic=stats)
                case["album_api_diagnostic"] = stats
                observed = observed_mp4_requests(events)
                case["source"] = "same_album_first_party_public_json_and_observed_blocked_CDN_requests"
                case["album_metadata_count"] = len(items)
                case["observed_mp4_request_count"] = len(observed)
                case["media"], added = summarize_album_items(
                    items, observed, remaining=MAX_HEAD-total_head)
                total_head += added
                case["head_request_count"] = added
                case["status"] = "media_metadata_only" if items else "album_metadata_unavailable"
            except Exception as exc:
                case.update({"status": "bounded_browser_or_head_error",
                             "error_class": type(exc).__name__, "media": []})
                try:
                    browser.get_log("performance")
                except Exception:
                    pass
            outcomes.append(case)
        return outcomes
    finally:
        browser.quit()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    for group in ALBUMS:
        check_manifest(group)
    result = {"schema": "sparkles-r13-r15-observed-video-head-only/1",
              "policy": "exact public first-party same-album metadata; four HEAD-only observed MP4s; zero media GET or publishing",
              "cases": run_browser()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("R13_R15_FOUR_HEAD " + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
