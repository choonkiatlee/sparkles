"""Select trusted 360-enrichment candidates from reviewed reference manifests.

Only existing default-branch manifests are eligible. Never read issue body
URLs or certificates into a write-credentialed enrichment workflow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from diamond_retrieval.resolvers import Loupe360CertificateResolver
from diamond_retrieval.motion_sources import Labgrowns3RotationDownloader
from diamond_retrieval.models import ROTATION, EvidenceReference

from .models import CatalogueError
from .references import REFERENCE_DIR, validate_reference


def _exact_labgrowns3_candidate(manifest: dict) -> bool:
    """Filter only curated links or persisted resolver results on master."""
    urls = [
        item["url"] for item in manifest.get("media_sources", [])
        if item["kind"] == "viewer"
    ] + [
        attempt["locator"] for attempt in manifest.get("enrichment_attempts", [])
        if attempt.get("kind") == "rotation" and attempt.get("locator")
    ]
    adapter = Labgrowns3RotationDownloader(None)
    return any(adapter.supports(EvidenceReference(
        identifier=manifest["id"], kind=ROTATION,
        retrieval_key=url, locator=url,
    )) for url in urls)


def batch_targets(directory: Path = REFERENCE_DIR, *,
                  supplier: str | None = None) -> tuple[str, ...]:
    """Prefer exact lab/report lookup or supported direct 360 viewer."""
    if supplier not in {None, "labgrowns3"}:
        raise CatalogueError("Unsupported batch supplier filter")
    ids: list[str] = []
    for path in sorted(directory.glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validate_reference(manifest, expected_id=path.stem)
        identity = manifest["identity"]
        reported_report = (
            identity["status"] in {"reported", "linked"}
            and bool(identity["lab"])
            and bool(identity["report_number"])
        )
        directly_supported = any(
            media["kind"] == "viewer"
            and Loupe360CertificateResolver._is_supported_rotation_url(media["url"])
            for media in manifest.get("media_sources", [])
        )
        already_has_motion = any(
            evidence.get("kind") == "rotation"
            and evidence.get("status") == "success"
            and len(evidence.get("frames", [])) == 256
            for evidence in manifest.get("evidence", [])
        )
        if (
            (reported_report or directly_supported)
            and not already_has_motion
            and (supplier is None or _exact_labgrowns3_candidate(manifest))
        ):
            ids.append(manifest["id"])
    if len(ids) != len(set(ids)):
        raise CatalogueError("Duplicate reference ID in enrichment batch")
    return tuple(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select trusted references for enrichment")
    parser.add_argument("--supplier", choices=("labgrowns3",))
    args = parser.parse_args()
    for reference_id in batch_targets(supplier=args.supplier):
        print(reference_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
