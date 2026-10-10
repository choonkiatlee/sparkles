#!/usr/bin/env python3
"""Exact, read-only source audit for reference LG715575610's v360.diamonds viewer.

The V360 viewer is *not* a downloadable frame source until its actual public
transport is independently observed. This diagnostic never guesses API routes,
uses credentials, downloads assets, or publishes anything. The browser may
naturally load its own media; only sanitized network metadata is retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.reference_media import _safe_source_url
from diamond_retrieval.resolvers import Loupe360CertificateResolver

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = "owner-igi-lg715575610"
REPORT = "LG715575610"
VIEWER = "https://v360.diamonds/c/22971515-3849-41bb-ae0a-3bb31e3a7ae9?m=i&a=FA-121"
ASSET_SUFFIX = re.compile(r"\.(?:jpe?g|webp|png|mp4|webm|m3u8|json)$", re.I)


def assert_source_pinned():
    record = json.loads((ROOT / "data/references" / (REFERENCE_ID + ".json")).read_text())
    if record["id"] != REFERENCE_ID or record["identity"] != {
        "lab": "IGI", "report_number": REPORT, "status": "reported"
    }:
        raise ValueError("Reference identity drift: exact audit must be reviewed")
    if not any(
        attempt.get("kind") == "rotation"
        and attempt.get("locator") == VIEWER
        and attempt.get("status") == "unsupported"
        for attempt in record.get("enrichment_attempts", [])
    ):
        raise ValueError("Reference's original discovered v360 viewer changed")
    if not any(ev.get("kind") == "still" and ev.get("status") == "success"
               for ev in record.get("evidence", [])):
        raise ValueError("Expected existing still missing")
    _safe_source_url(VIEWER)


def sanitized_url(url):
    """Suppress URL parameters and opaque identifiers/tokens in diagnostic logs."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            return None
        path = parts.path
        return {
            "host": parts.hostname.lower(),
            "path_sha256": hashlib.sha256(path.encode()).hexdigest()[:16],
            "path_segments": len([part for part in path.split("/") if part]),
            "extension": ASSET_SUFFIX.search(path).group(0).lower() if ASSET_SUFFIX.search(path) else None,
            "query_keys": sorted({item.split("=", 1)[0] for item in parts.query.split("&") if item})[:12],
        }
    except ValueError:
        return None


def categorize(status, mime, body=b""):
    """HTTP success and image/video magic must both be present for media claims."""
    if status in (401, 402, 403, 429):
        return "access_blocked"
    if status != 200:
        return "not_available"
    mime = (mime or "").split(";", 1)[0].lower()
    if body[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if len(body) > 8 and body[4:8] == b"ftyp":
        return "mp4"
    if b"<html" in body[:1024].lower() or b"<!doctype html" in body[:1024].lower():
        return "html_not_motion"
    if mime in ("text/html", "application/xhtml+xml"):
        return "html_not_motion"
    return "unknown_not_proven_motion"


def audit_exact_certificate_lookup(client=None):
    """Inspect only exact IGI lab/report Nivoda media metadata, without media bytes."""
    client = client or UrllibHttpClient(max_bytes=512_000)
    endpoint = Loupe360CertificateResolver.endpoint
    request = json.dumps({
        "query": Loupe360CertificateResolver._query,
        "variables": {"cert": REPORT},
    }, separators=(",", ":")).encode()
    response = client.post(
        endpoint, timeout=18, content=request,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    output = {"http_status": response.status_code, "bytes": len(response.content)}
    if response.status_code != 200:
        output["outcome"] = "lookup_unavailable"
        return output
    try:
        payload = json.loads(response.content)
        record = (payload.get("data") or {}).get("certificate_by_cert_number")
    except (ValueError, TypeError, AttributeError):
        output["outcome"] = "invalid_json"
        return output
    if not isinstance(record, dict) or payload.get("errors"):
        output["outcome"] = "no_exact_record"
        return output
    if str(record.get("certNumber") or "").upper() != REPORT or str(record.get("lab") or "").upper() != "IGI":
        output["outcome"] = "identity_conflict"
        return output
    output["outcome"] = "exact_provider_report"
    output["image"] = sanitized_url(record.get("image"))
    output["video"] = sanitized_url(record.get("video"))
    v360 = record.get("v360")
    if isinstance(v360, dict):
        url = v360.get("url")
        output["v360"] = {
            "url": sanitized_url(url),
            "frame_count": v360.get("frame_count"),
            "top_index": v360.get("top_index"),
            "direct_video_url": (
                isinstance(url, str) and Loupe360CertificateResolver._is_direct_video_url(url)
            ),
            "proxy_wrapper": bool(
                isinstance(url, str) and urlsplit(url).hostname == "assets-images.pixorac.com"
            ),
        }
    return output


def audit_exact_http(client=None):
    client = client or UrllibHttpClient(max_bytes=512_000)
    response = client.get(VIEWER, timeout=18)
    return {
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", "").split(";", 1)[0][:80],
        "bytes": len(response.content),
        "body_sha256": hashlib.sha256(response.content).hexdigest(),
        "classification": categorize(
            response.status_code, response.headers.get("Content-Type"), response.content
        ),
        "final_url": sanitized_url(response.url),
    }


def audit_exact_browser(seconds=9):
    """Observe ONLY exact public viewer navigation and requests it initiates.

    Browser network requests may include private-looking opaque URLs: never
    persist the raw URLs, query values, headers, response bodies or cookies.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                 "--window-size=1200,850", "--disable-background-networking",
                 "--autoplay-policy=no-user-gesture-required"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(25)
        driver.execute_cdp_cmd("Network.enable", {})
        navigation_error = None
        try:
            driver.get(VIEWER)
        except Exception as exc:
            navigation_error = type(exc).__name__
        import time
        time.sleep(seconds)
        browser = {"navigation_error_type": navigation_error}
        try:
            browser["current_url"] = sanitized_url(driver.current_url)
            browser["dom"] = driver.execute_script("""
                return {
                    title: (document.title || '').slice(0,90),
                    ready_state: document.readyState,
                    videos: [...document.querySelectorAll('video')].slice(0,4).map(v => ({
                        has_src: Boolean(v.currentSrc || v.src),
                        width: v.videoWidth, height: v.videoHeight,
                        ready_state: v.readyState,
                        source: v.currentSrc || v.src
                    })),
                    iframes: [...document.querySelectorAll('iframe')].slice(0,4).map(v=>v.src),
                    canvas_count: document.querySelectorAll('canvas').length
                };
            """)
            browser["dom"]["videos"] = [
                {**{k: value for k, value in v.items() if k != "source"},
                 "source": sanitized_url(v.get("source"))}
                for v in browser["dom"]["videos"]
            ]
            browser["dom"]["iframes"] = [
                sanitized_url(src) for src in browser["dom"]["iframes"]
            ]
        except Exception as exc:
            browser["dom_error_type"] = type(exc).__name__

        requests = {}
        for item in driver.get_log("performance"):
            try:
                message = json.loads(item["message"])["message"]
                method, params = message["method"], message["params"]
                req_id = params.get("requestId")
                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url")
                    detail = sanitized_url(url)
                    if detail:
                        requests[req_id] = {
                            "url": detail, "resource_type": params.get("type")
                        }
                elif method == "Network.responseReceived" and req_id in requests:
                    response = params["response"]
                    requests[req_id].update({
                        "http_status": response.get("status"),
                        "mime": str(response.get("mimeType", ""))[:75],
                        "encoded_bytes": response.get("encodedDataLength"),
                    })
                elif method == "Network.loadingFailed" and req_id in requests:
                    requests[req_id]["failed"] = True
            except (ValueError, TypeError, KeyError):
                continue
        relevant = [
            v for v in requests.values()
            if v["url"]["host"] == "v360.diamonds"
            or v["url"]["extension"] in (".mp4", ".webm", ".jpg", ".jpeg", ".webp", ".json", ".m3u8")
            or v["resource_type"] in ("Media", "Image", "XHR", "Fetch")
        ]
        browser["requests_total"] = len(requests)
        browser["relevant_requests"] = relevant[:80]
        browser["truncated"] = len(relevant) > 80
        browser["media_responses"] = sum(
            v.get("http_status") == 200 and
            (v["url"]["extension"] in (".mp4", ".webm", ".jpg", ".jpeg", ".webp")
             or v.get("mime", "") in ("image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"))
            for v in relevant
        )
        return browser
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert_source_pinned()
    output = {
        "schema": "sparkles-v360-diamonds-exact-audit/1",
        "reference_id": REFERENCE_ID,
        "scope": "read-only exact public viewer; no source guessing, media download or publication",
    }
    try:
        output["certificate_lookup"] = audit_exact_certificate_lookup()
    except Exception as exc:
        output["certificate_lookup_error_type"] = type(exc).__name__
    try:
        output["http"] = audit_exact_http()
    except Exception as exc:
        output["http_error_type"] = type(exc).__name__
    try:
        output["browser"] = audit_exact_browser()
    except Exception as exc:
        output["browser_error_type"] = type(exc).__name__
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
