"""Read-only public Imgur metadata audit for the two R12-R15 PriceScope pairs.

Only two pinned album HTML GETs and optional HEAD probes of their observed
first-party direct-video URLs. Never downloads videos, guesses album asset IDs,
follows redirects, changes reference records, or attaches a group clip to a stone.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ALBUMS = {
    "R14_R15": ("https://imgur.com/a/mKh7jTv", ("ps282648-r14", "ps282648-r15")),
    "R12_R13": ("https://imgur.com/a/GyYZOSZ", ("ps282648-r12", "ps282648-r13")),
}
MAX_HTML = 600_000
MAX_CANDIDATES = 24
MEDIA = re.compile(r"https://i\.imgur\.com/[A-Za-z0-9]{5,16}\.(?:mp4|webm)\Z", re.I)
OBSERVED = re.compile(r"https://i\.imgur\.com/[A-Za-z0-9]{5,16}\.(?:mp4|webm)(?![\w./?])", re.I)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class AlbumMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property", a.get("name", "")).lower() in {
            "og:video", "og:video:secure_url", "twitter:player:stream"
        }:
            self.urls.add(a.get("content", ""))
        if tag in {"video", "source"}:
            self.urls.add(a.get("src", ""))


def validate_album(url: str) -> str:
    if url not in {entry[0] for entry in ALBUMS.values()}:
        raise ValueError("unreviewed album URL")
    return url


def validate_media(url: str) -> str:
    if not isinstance(url, str) or not MEDIA.fullmatch(url):
        raise ValueError("not an observed first-party direct MP4/WebM URL")
    parts = urlsplit(url)
    if parts.hostname != "i.imgur.com" or parts.scheme != "https" or parts.query or parts.fragment:
        raise ValueError("media must be first-party public HTTPS and query-free")
    return url


def candidates_from_html(content: str) -> list[str]:
    parser = AlbumMetadata()
    parser.feed(content)
    candidates = parser.urls | set(OBSERVED.findall(content))
    return sorted(validate_media(url) for url in candidates if MEDIA.fullmatch(url))[:MAX_CANDIDATES]


def _request(url: str, method: str, *, max_bytes: int = 0, opener=None) -> tuple[int, dict, bytes]:
    opener = opener or build_opener(HTTPSHandler(), NoRedirect())
    req = Request(url, headers={
        "User-Agent": "Sparkles-ReadOnly-Album-Metadata/1.0",
        "Accept": "text/html" if method == "GET" else "*/*",
    }, method=method)
    try:
        with opener.open(req, timeout=12) as response:
            data = response.read(max_bytes + 1) if method == "GET" else b""
            if len(data) > max_bytes:
                raise ValueError("bounded HTML response exceeded limit")
            return response.status, dict(response.headers.items()), data
    except HTTPError as err:
        # Redirect/denied responses fail closed; never follow to another host.
        return err.code, dict(err.headers.items()), b""


def analyze_html(status: int, headers: dict, data: bytes) -> dict:
    ctype = headers.get("Content-Type", headers.get("content-type", "")).split(";", 1)[0].strip().lower()
    result = {
        "http_status": status, "content_type": ctype, "html_bytes": len(data),
        "candidate_count": 0, "candidate_clips": [],
        "attribution": "unverified", "clip_count_verified": False,
    }
    if status != 200:
        result["status"] = "redirect_blocked" if status in (301, 302, 303, 307, 308) else "http_denied_or_unavailable"
        return result
    if ctype not in ("text/html", "application/xhtml+xml") or not data.lstrip().lower().startswith(
        (b"<!doctype html", b"<html")
    ):
        result["status"] = "not_album_html"
        return result
    urls = candidates_from_html(data.decode("utf-8", errors="replace"))
    result["status"] = "public_album_html_with_media_hints" if urls else "public_album_html_no_media_hints"
    result["candidate_count"] = len(urls)
    result["candidate_clips"] = [
        {"opaque_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
         "extension": url.rsplit(".", 1)[-1].lower()}
        for url in urls
    ]
    # A public HTML hint is not an exhaustive clip inventory or per-stone mapping.
    return result


def check_manifest(group: str) -> None:
    url, refs = ALBUMS[group]
    for ref in refs:
        path = ROOT / "data" / "references" / (ref + ".json")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("id") != ref or record.get("identity") != {
            "status": "unverified", "lab": None, "report_number": None
        } or record.get("media_sources") != []:
            raise ValueError("Reference identity or reviewed media scope changed")
        if not any(link.get("kind") == "comparison_video" and link.get("url") == url
                   for link in record.get("source_links", [])):
            raise ValueError("Exact curated album link changed")
        if any(e.get("kind") in ("video", "rotation") and e.get("status") == "success"
               for e in record.get("evidence", [])):
            raise ValueError("Reference already has motion; review again")


def audit_one(group: str, *, opener=None) -> dict:
    url, refs = ALBUMS[group]
    validate_album(url)
    out = {
        "group": group, "references": refs, "album_url": url,
        "stone_order": "R14 first, R15 second" if group == "R14_R15" else "R12 H, R13 G",
        "original_clip_count": "unknown", "per_stone_clip_mapping": "unknown",
        "rehosting_permission": "not_established", "media_downloaded": False,
    }
    try:
        status, headers, html = _request(url, "GET", max_bytes=MAX_HTML, opener=opener)
        out.update(analyze_html(status, headers, html))
        if out["status"] == "public_album_html_with_media_hints":
            # Only HEAD the exact media paths already observed in this same HTML.
            candidates = candidates_from_html(html.decode("utf-8", errors="replace"))
            for item, candidate in zip(out["candidate_clips"], candidates):
                try:
                    code, mh, _ = _request(candidate, "HEAD", opener=opener)
                    declared = mh.get("Content-Type", mh.get("content-type", "")).split(";", 1)[0].lower()
                    item.update({
                        "head_http": code, "declared_media_type": declared,
                        "declared_bytes": int(mh["Content-Length"])
                        if mh.get("Content-Length", "").isdigit() else None,
                        "candidate_wire_status": "metadata_only_not_downloaded",
                    })
                except (OSError, ValueError) as exc:
                    item.update({"candidate_wire_status": "head_unavailable",
                                 "error_class": type(exc).__name__})
    except (OSError, ValueError, URLError) as exc:
        out.update({"status": "bounded_transport_error", "error_class": type(exc).__name__,
                    "candidate_count": 0, "candidate_clips": []})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    for group in ALBUMS:
        check_manifest(group)
    findings = {
        "schema": "sparkles-r13-r15-imgur-readonly/1",
        "scope": "two pinned public album HTML pages; no media GET or publication",
        "uk_access_note": "Imgur stopped serving UK viewers in September 2025; external embeds are not reliable in the UK",
        "groups": [audit_one(group) for group in ALBUMS],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("R13_R15_IMGUR_READONLY " + json.dumps(findings, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
