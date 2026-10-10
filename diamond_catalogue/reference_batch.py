"""Select trusted 360-enrichment candidates from reviewed reference manifests.

Only existing default-branch manifests are eligible. Never read issue body
URLs or certificates into a write-credentialed enrichment workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

from diamond_retrieval.resolvers import Loupe360CertificateResolver

from .models import CatalogueError
from .references import REFERENCE_DIR, validate_reference


def batch_targets(directory: Path = REFERENCE_DIR) -> tuple[str, ...]:
    """Prefer exact lab/report lookup or an already-supported direct 360 viewer."""
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
        if (reported_report or directly_supported) and not already_has_motion:
            ids.append(manifest["id"])
    if len(ids) != len(set(ids)):
        raise CatalogueError("Duplicate reference ID in enrichment batch")
    return tuple(ids)


def main() -> int:
    for reference_id in batch_targets():
        print(reference_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
