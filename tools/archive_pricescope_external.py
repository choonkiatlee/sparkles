#!/usr/bin/env python3
"""Fetch and hash the PriceScope inputs for issue #64.

Raw third-party media are written only to an output directory (normally a CI
artifact), never to the repository. The committed archive manifest records the
URLs, byte counts, hashes and retrieval status needed to reproduce the archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36 SparklesArchive/1"
)
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"}
THREAD_URL = (
    "https://www.pricescope.com/community/threads/"
    "why-cut-asschers-with-small-corners-and-windmills.78433/"
)


class ThreadMediaParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.in_article = False
        self.article_depth = 0
        self.post_number = 0
        self.by_post: dict[int, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "article" and "message--post" in classes:
            self.in_article = True
            self.article_depth = 1
            self.post_number += 1
            self.by_post.setdefault(self.post_number, [])
            return

        if self.in_article:
            if tag == "article":
                self.article_depth += 1
            candidates: list[str] = []
            if tag in {"img", "source"}:
                for key in ("src", "data-src", "data-url"):
                    if attrs.get(key):
                        candidates.append(attrs[key])
            if tag == "a" and attrs.get("href"):
                candidates.append(attrs["href"])
            for value in candidates:
                url = urljoin(self.base_url, value)
                if is_content_media(url):
                    self.by_post[self.post_number].append(url)

    def handle_endtag(self, tag):
        if self.in_article and tag == "article":
            self.article_depth -= 1
            if self.article_depth <= 0:
                self.in_article = False
                self.article_depth = 0


def is_content_media(url: str) -> bool:
    parsed = urlparse(url)
    if "pricescope.com" not in parsed.netloc.lower():
        return False
    path = parsed.path.lower()
    excluded = (
        "/data/avatars/",
        "/styles/",
        "/idealbb/images/smilies/",
        "/favicon",
        "/logo",
        "/ads/",
    )
    if any(x in path for x in excluded):
        return False
    suffix = Path(path).suffix
    return suffix in MEDIA_EXTENSIONS or "/attachments/" in path


def fetch(url: str, *, attempts: int = 3) -> tuple[bytes, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                    "Referer": "https://www.pricescope.com/",
                },
            )
            with urlopen(req, timeout=45) as response:
                data = response.read()
                headers = {k.lower(): v for k, v in response.headers.items()}
                return data, headers
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def safe_name(sample_id: str, url: str, default_ext: str = ".bin") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in MEDIA_EXTENSIONS:
        suffix = default_ext
    return f"{sample_id}{suffix}"


def digest_record(sample_id: str, url: str, out_dir: Path) -> dict:
    record = {"sample_id": sample_id, "source_url": url}
    try:
        data, headers = fetch(url)
        content_type = headers.get("content-type", "").split(";")[0].strip()
        guessed_ext = mimetypes.guess_extension(content_type) or ".bin"
        name = safe_name(sample_id, url, guessed_ext)
        media_dir = out_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        path = media_dir / name
        path.write_bytes(data)
        record.update(
            {
                "retrieval_status": "ok",
                "artifact_path": f"media/{name}",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": content_type or None,
                "last_modified": headers.get("last-modified"),
                "etag": headers.get("etag"),
            }
        )
    except Exception as exc:  # archive should record failures rather than erase them
        record.update(
            {
                "retrieval_status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return record


def explicit_samples(catalog: dict) -> list[tuple[str, str]]:
    found = []
    for source in catalog["sources"]:
        for group in source.get("groups", []):
            for sample in group.get("samples", []):
                url = sample.get("media_url")
                if url:
                    found.append((sample["sample_id"], url))
    return found


def discover_thread_media(catalog: dict) -> tuple[dict[int, list[str]], list[dict]]:
    target_posts = {}
    for source in catalog["sources"]:
        if source["source_id"] != "pricescope-windmill-thread":
            continue
        for group in source["groups"]:
            for sample in group["samples"]:
                target_posts[sample["post_number"]] = sample["sample_id"]

    target_pages = sorted({((post - 1) // 30) + 1 for post in target_posts})
    selected: dict[int, list[str]] = {post: [] for post in target_posts}
    page_records = []

    for page_number in target_pages:
        page_url = THREAD_URL if page_number == 1 else f"{THREAD_URL}page-{page_number}"
        page_data, headers = fetch(page_url)
        parser = ThreadMediaParser(page_url)
        parser.feed(page_data.decode("utf-8", errors="replace"))
        offset = (page_number - 1) * 30

        for local_post, media_urls in parser.by_post.items():
            post_number = offset + local_post
            if post_number not in selected:
                continue
            seen = set()
            urls = []
            for url in media_urls:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
            selected[post_number] = urls

        page_records.append(
            {
                "page_number": page_number,
                "source_url": page_url,
                "bytes": len(page_data),
                "sha256": hashlib.sha256(page_data).hexdigest(),
                "content_type": headers.get("content-type"),
                "target_post_count": sum(
                    1 for post in target_posts
                    if ((post - 1) // 30) + 1 == page_number
                ),
                "parsed_post_count": len(parser.by_post),
            }
        )

    return selected, page_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        default="docs/360/external-benchmark/pricescope/source-catalog.json",
    )
    parser.add_argument("--out", default="/tmp/pricescope-archive")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(catalog_path.read_text())

    records = []
    for sample_id, url in explicit_samples(catalog):
        records.append(digest_record(sample_id, url, out_dir))

    thread_discovery_error = None
    try:
        thread_media, thread_pages = discover_thread_media(catalog)
    except Exception as exc:
        thread_media, thread_pages = {}, []
        thread_discovery_error = f"{type(exc).__name__}: {exc}"

    sample_id_by_post = {}
    for source in catalog["sources"]:
        if source["source_id"] == "pricescope-windmill-thread":
            for group in source["groups"]:
                for sample in group["samples"]:
                    sample_id_by_post[sample["post_number"]] = sample["sample_id"]

    thread_records = []
    for post_number, sample_id in sorted(sample_id_by_post.items()):
        urls = thread_media.get(post_number, [])
        item = {
            "sample_id": sample_id,
            "post_number": post_number,
            "discovered_media_urls": urls,
            "media": [],
        }
        for i, url in enumerate(urls, 1):
            item["media"].append(
                digest_record(f"{sample_id}-{i}", url, out_dir)
            )
        thread_records.append(item)

    manifest = {
        "schema_version": "sparkles-external-archive/1",
        "benchmark_id": catalog["benchmark_id"],
        "raw_media_policy": "downloaded into CI artifact only; not committed to git",
        "explicit_media": records,
        "thread_pages": thread_pages,
        "thread_discovery_error": thread_discovery_error,
        "thread_samples": thread_records,
    }
    manifest_path = out_dir / "archive-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    summary = {
        "explicit_ok": sum(x.get("retrieval_status") == "ok" for x in records),
        "explicit_total": len(records),
        "thread_samples_with_media": sum(bool(x["discovered_media_urls"]) for x in thread_records),
        "thread_sample_total": len(thread_records),
        "thread_media_ok": sum(
            m.get("retrieval_status") == "ok"
            for x in thread_records
            for m in x["media"]
        ),
    }
    print("ARCHIVE_SUMMARY=" + json.dumps(summary, sort_keys=True))
    print("ARCHIVE_MANIFEST_BEGIN")
    print(manifest_path.read_text())
    print("ARCHIVE_MANIFEST_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
