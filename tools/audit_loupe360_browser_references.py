#!/usr/bin/env python3
"""Read-only, exact-identity Loupe360 browser/media audit for #221.

No credentials, arbitrary URLs, source-ID guessing, downloads, or publication.
Public request URLs are reduced to host/path/status to avoid logging session tokens.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

EXACT = {
    "R08": "LG657468099",
    "R11": "LG636432256",
}
PUBLIC_ENDPOINT = "https://g.nivoda.com/graphql-public-loupe360"


def brief_url(url):
    if not isinstance(url, str) or not url:
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return {"valid_http_url": False}
        return {
            "host": (parts.hostname or "").lower(),
            "path": parts.path[:180],
            "has_query": bool(parts.query),
            "media_extension": bool(re.search(r"\.(?:mp4|mov|webm|m4v|jpg|jpeg)(?:$|/)", parts.path, re.I)),
        }
    except ValueError:
        return {"valid_http_url": False}


def query_public_record(report, *, extended):
    fields = "url frame_count top_index id dl_link" if extended else "url frame_count top_index id"
    query = (
        "query($cert:String!){certificate_by_cert_number(cert_number:$cert) "
        "{id certNumber lab image video pdfUrl v360 {" + fields + "}}}"
    )
    body = json.dumps({"query": query, "variables": {"cert": report}}).encode()
    request = urllib.request.Request(
        PUBLIC_ENDPOINT, data=body, method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "Sparkles-source-audit/1"},
    )
    result = {"query_variant": "extended_dl_link" if extended else "current_contract"}
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result["http_status"] = response.status
            payload = json.loads(response.read(256 * 1024))
    except urllib.error.HTTPError as error:
        result["http_status"] = error.code
        return result
    except Exception as error:
        result["error_type"] = type(error).__name__
        return result
    if payload.get("errors"):
        # Error messages may contain backend details, so record only recognized
        # schema rejection vs other errors.
        messages = [str(item.get("message", "")) for item in payload["errors"]]
        result["graphql_error_types"] = [
            "field_unsupported" if "Cannot query field" in message else "other"
            for message in messages[:3]
        ]
        return result
    record = (payload.get("data") or {}).get("certificate_by_cert_number")
    if not isinstance(record, dict):
        result["certificate_record"] = "missing"
        return result
    result["certificate_record"] = "returned"
    result["cert_matches"] = str(record.get("certNumber") or "").strip().upper() == report
    result["lab"] = record.get("lab")
    result["video"] = brief_url(record.get("video"))
    result["image"] = brief_url(record.get("image"))
    v360 = record.get("v360")
    if isinstance(v360, dict):
        result["v360"] = {
            "url": brief_url(v360.get("url")),
            "frame_count": v360.get("frame_count"),
            "top_index": v360.get("top_index"),
            "dl_link": brief_url(v360.get("dl_link")),
            "dl_link_present": bool(v360.get("dl_link")),
        }
        # The v360 URL can be an encoded wrapper, so reveal only decoded host
        # and path to compare against actual player requests.
        try:
            from diamond_retrieval.resolvers import Loupe360CertificateResolver
            result["v360"]["unwrapped_url"] = brief_url(
                Loupe360CertificateResolver._unwrap_v360(v360.get("url") or "")
            )
        except Exception as error:
            result["v360"]["unwrap_error_type"] = type(error).__name__
    return result


def inspect_browser(report, *, seconds=9):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for argument in (
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1280,900", "--autoplay-policy=no-user-gesture-required",
    ):
        options.add_argument(argument)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(25)
        results = []
        for suffix in ("", "/video/500/500"):
            url = "https://loupe360.com/diamond/" + report + suffix
            record = {"input_route": suffix or "landing", "page": brief_url(url)}
            try:
                driver.execute_cdp_cmd("Network.enable", {})
                driver.get(url)
                time.sleep(seconds)
                record["current_page"] = brief_url(driver.current_url)
                record["title"] = driver.title[:120]
                dom = driver.execute_script("""
                    return {
                      ready_state: document.readyState,
                      iframe_urls: [...document.querySelectorAll('iframe')].map(x=>x.src).slice(0,10),
                      video: [...document.querySelectorAll('video')].map(x=>({
                        src: x.currentSrc || x.src || '',
                        ready_state: x.readyState,
                        network_state: x.networkState,
                        video_width: x.videoWidth,
                        video_height: x.videoHeight
                      })).slice(0,8),
                      canvas_count: document.querySelectorAll('canvas').length,
                      body_text_sample: (document.body?.innerText || '').slice(0,160)
                    };
                """)
                record["dom"] = {
                    "ready_state": dom.get("ready_state"),
                    "iframe_urls": [brief_url(x) for x in dom.get("iframe_urls", [])],
                    "video": [{**{k: v for k, v in x.items() if k != "src"},
                               "src": brief_url(x.get("src"))} for x in dom.get("video", [])],
                    "canvas_count": dom.get("canvas_count"),
                    "body_text_sample": dom.get("body_text_sample"),
                }
            except Exception as error:
                record["browser_error_type"] = type(error).__name__

            # CDP performance logs include child frame navigation and video
            # resource requests. Never retain query strings, headers, bodies or cookies.
            requests = {}
            failures = []
            for row in driver.get_log("performance"):
                try:
                    item = json.loads(row["message"])["message"]
                    kind, data = item["method"], item["params"]
                except (KeyError, ValueError, TypeError):
                    continue
                if kind == "Network.requestWillBeSent":
                    url_detail = brief_url(data.get("request", {}).get("url"))
                    if url_detail:
                        requests[data.get("requestId")] = {
                            "resource": url_detail, "resource_type": data.get("type")
                        }
                if kind == "Network.responseReceived":
                    current = requests.get(data.get("requestId"))
                    if current:
                        current["status"] = data.get("response", {}).get("status")
                        current["mime_type"] = data.get("response", {}).get("mimeType")
                if kind == "Network.loadingFailed":
                    current = requests.get(data.get("requestId"))
                    if current:
                        current["failed"] = True
                        failures.append(current)
            important = []
            for value in requests.values():
                info = value["resource"]
                host = info.get("host", "")
                path = info.get("path", "").lower()
                if (any(part in host for part in (
                        "loupe360", "nivoda", "pixorac", "360view", "workshop", "s3.amazonaws",
                        "ritani", "medialink", "v360"))
                        or path.endswith((".mp4", ".m3u8", ".jpg", ".webm", ".json"))):
                    important.append(value)
            record["requests_total"] = len(requests)
            record["relevant_requests"] = important[:100]
            record["relevant_requests_truncated"] = len(important) > 100
            record["relevant_failures"] = [
                x for x in failures if x in important
            ][:20]
            results.append(record)
        return results
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for name, report in EXACT.items():
        value = {"reference": name, "report": report, "lookup": []}
        for extended in (False, True):
            value["lookup"].append(query_public_record(report, extended=extended))
        try:
            value["browser"] = inspect_browser(report)
        except Exception as error:
            value["browser_error_type"] = type(error).__name__
        records.append(value)
    payload = {"schema": "sparkles-loupe360-browser-audit/1",
               "scope": "R08/R11 exact public reports only; no media downloaded", "records": records}
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized + "\n")
    print(serialized)


if __name__ == "__main__":
    main()
