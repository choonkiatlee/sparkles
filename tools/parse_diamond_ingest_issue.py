"""Validate an owner-created, prefilled GitHub issue before dispatching ingestion.

This code must not accept arbitrary text as a shell argument or GitHub Actions
output. There is exactly one authorised request shape and retailer URL.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit

OWNER = "choonkiatlee"
REPOSITORY = "choonkiatlee/sparkles"
REQUEST_TITLE = "Ingest diamond"
REQUEST_MARKER = "<!-- sparkles-diamond-ingest/v1 -->"
_QD_ID = re.compile(r"[0-9]+/[A-Za-z0-9]+")
_DIYONA_SKU = re.compile(r"[A-Za-z0-9_-]+")


def validate_listing_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 2048:
        raise ValueError("Invalid diamond URL length")
    if any(ord(char) < 33 or ord(char) > 126 for char in raw):
        raise ValueError("Invalid diamond URL characters")
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or parsed.port is not None
                or parsed.fragment or not parsed.hostname):
            raise ValueError("Not a public HTTPS retailer listing")
    except ValueError as exc:
        raise ValueError("Invalid listing URL") from exc

    host = parsed.hostname.lower()
    query = parse_qsl(parsed.query, keep_blank_values=True)
    path = parsed.path.rstrip("/")
    if (
        host in {"diyona.com", "www.diyona.com"}
        and path == "/pages/diamond-detail"
        and len(query) == 1 and query[0][0] == "sku"
        and _DIYONA_SKU.fullmatch(query[0][1])
    ):
        return raw
    if (
        host in {"qualitydiamonds.co.uk", "www.qualitydiamonds.co.uk"}
        and path == "/loose-diamonds/buy-loose-diamonds"
        and len(query) == 1 and query[0][0] == "d"
        and _QD_ID.fullmatch(query[0][1])
    ):
        return raw
    raise ValueError("Unsupported exact diamond listing URL")


def url_from_issue_event(event: dict) -> str:
    if not isinstance(event, dict) or event.get("action") != "opened":
        raise ValueError("Issue request must be newly opened")
    if (event.get("repository") or {}).get("full_name") != REPOSITORY:
        raise ValueError("Unexpected repository")
    issue = event.get("issue") or {}
    if (issue.get("user") or {}).get("login") != OWNER:
        raise ValueError("Only the repository owner may request ingestion")
    if issue.get("title") != REQUEST_TITLE or issue.get("pull_request"):
        raise ValueError("Not an ingestion request")
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 2300:
        raise ValueError("Invalid ingestion issue body")
    lines = body.replace("\r\n", "\n").rstrip("\n").split("\n")
    if len(lines) != 2 or lines[0] != REQUEST_MARKER:
        raise ValueError("Invalid request format")
    prefix = "Diamond URL: "
    if not lines[1].startswith(prefix):
        raise ValueError("Missing diamond URL")
    return validate_listing_url(lines[1][len(prefix):])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        url = url_from_issue_event(event)
    except (ValueError, OSError, TypeError, json.JSONDecodeError):
        parser.error("Invalid authorised diamond ingestion issue")
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write("diamond_url=" + url + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
