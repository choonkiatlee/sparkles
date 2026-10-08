"""Automatically backfill stored thumbnail icons without ever re-ingesting sources.

Can be run after new ingestion, on master push, or via workflow_dispatch.
All work is bounded to published manifests and verified original media.
Individual failed thumbnails leave the default retailer image in place.
"""
from __future__ import annotations
import argparse
import os

from .faceup_thumbnail import retrieve_frame_bytes
from .faceup_publish import publish_generated_thumbnail
from .github_api import GitHubAPI
from .github_catalogue import GitHubCatalogue
from .github_release import GitHubReleaseStorage


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=50)
    p.add_argument("--diamond-id",help="Optional exact saved certified ID")
    a=p.parse_args(argv)
    if os.environ.get("GITHUB_REF") != "refs/heads/master":
        p.error("Production backfill requires master")
    if a.limit < 1 or a.limit > 100:
        p.error("Limit must be between 1 and 100")
    api=GitHubAPI(os.environ.get("GITHUB_TOKEN",""),
                  os.environ.get("GITHUB_REPOSITORY",""))
    catalogue=GitHubCatalogue(api)
    _,_,manifests,_=catalogue._snapshot()
    storage=GitHubReleaseStorage(api)
    pending = [v for v in manifests.values()
               if not (v.get("derived_media") or {}).get("overview_thumbnail")
               and (a.diamond_id is None or v["id"] == a.diamond_id)]
    changed=0
    skipped=0
    for manifest in sorted(pending,key=lambda x:x["id"])[:a.limit]:
        try:
            receipt=publish_generated_thumbnail(
                manifest,fetch_bytes=retrieve_frame_bytes,
                storage=storage,catalogue=catalogue,
            )
            if receipt and receipt.changed:
                changed+=1
                print(f"Overview icon published: {manifest['id']}; commit={receipt.commit_sha}",
                      flush=True)
            else:
                skipped+=1
                print(f"Overview icon not available: {manifest['id']} (using saved original)",
                      flush=True)
        except (ValueError, RuntimeError, OSError) as exc:
            skipped+=1
            # Do not print raw media URL/HTTP response in public Actions logs.
            print(f"::warning title=Overview icon skipped::{manifest['id']} "
                  f"could not generate an icon ({type(exc).__name__}); "
                  f"the original thumbnail remains available.",flush=True)
    print(f"Overview icons: generated={changed} unchanged_or_fallback={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
