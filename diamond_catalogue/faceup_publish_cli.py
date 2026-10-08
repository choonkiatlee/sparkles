"""Workflow-only explicit thumbnail approval entry point."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re

from .faceup_thumbnail import retrieve_frame_bytes
from .faceup_publish import publish_reviewed_thumbnail
from .github_api import GitHubAPI
from .github_catalogue import GitHubCatalogue
from .github_release import GitHubReleaseStorage


def main(argv=None):
    p=argparse.ArgumentParser(description="Upload manually reviewed Asscher thumbnail")
    p.add_argument("--diamond-id",required=True)
    p.add_argument("--approved-image-sha",required=True)
    p.add_argument("--approved-source-sha",required=True)
    p.add_argument("--manual-review-ack",required=True)
    a=p.parse_args(argv)
    if os.getenv("GITHUB_REF") != "refs/heads/master":
        p.error("Cannot publish thumbnail outside master")
    if a.manual_review_ack != "I_REVIEWED_THE_CROWN_VIEW":
        p.error("Human review must be explicitly acknowledged")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*",a.diamond_id):
        p.error("Invalid stable diamond id")
    if not all(re.fullmatch(r"[0-9a-f]{64}",d) for d in
               (a.approved_image_sha,a.approved_source_sha)):
        p.error("Approval and source SHA-256 must be lowercase 64-digit hexadecimal")
    path=Path(__file__).resolve().parents[1]/"data"/"diamonds"/(a.diamond_id+".json")
    doc=json.loads(path.read_text(encoding="utf-8"))
    if doc.get("id") != a.diamond_id:
        p.error("Certified manifest does not match the requested identity")
    api=GitHubAPI(os.environ.get("GITHUB_TOKEN",""),
                  os.environ.get("GITHUB_REPOSITORY",""))
    receipt=publish_reviewed_thumbnail(
        doc,fetch_bytes=retrieve_frame_bytes,
        storage=GitHubReleaseStorage(api),catalogue=GitHubCatalogue(api),
        approved_image_sha=a.approved_image_sha,
        approved_source_sha=a.approved_source_sha,
        reviewer=os.environ.get("GITHUB_ACTOR",""),
    )
    print(f"Reviewed thumbnail: {receipt.diamond_id}; "
          f"changed={receipt.changed}; commit={receipt.commit_sha}")


if __name__ == "__main__":
    main()
