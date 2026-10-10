"""Read-only live audit of the exact Gem360 source used by LG833634461."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.models import ROTATION, EvidenceReference, ProvenanceStep
from diamond_retrieval.motion import ProgressiveRotationProcessor
from diamond_retrieval.motion_sources import Gem360RotationDownloader


VIEWER = "https://view.gem360.in/gem360.html?d=2208261115-MV25-13A"


def audit() -> dict:
    reference = EvidenceReference(
        identifier="igi-lg833634461:gem360-live-audit",
        kind=ROTATION,
        retrieval_key=VIEWER,
        locator=VIEWER,
        provenance=(ProvenanceStep("loupe360_exact_certificate", VIEWER),),
        metadata={"lab": "IGI", "report_number": "LG833634461"},
    )
    raw = Gem360RotationDownloader(UrllibHttpClient(), timeout=20.0).download(reference)
    rotation = ProgressiveRotationProcessor().process(raw)[0]
    if len(rotation.frames) != 256:
        raise RuntimeError(f"expected 256 frames, got {len(rotation.frames)}")
    if [frame.source_index for frame in rotation.frames] != list(range(256)):
        raise RuntimeError("Gem360 source order is not the complete canonical 0..255 sequence")

    return {
        "schema": "sparkles-gem360-source-audit/1",
        "report_number": "LG833634461",
        "viewer": VIEWER,
        "source_root": raw.metadata.get("source_root"),
        "source_version": raw.metadata.get("source_version"),
        "frame_count": len(rotation.frames),
        "dimensions": list(rotation.frames[0].dimensions),
        "sequence_complete": rotation.metadata.get("sequence_complete"),
        "physical_angle_calibrated": rotation.metadata.get("physical_angle_calibrated"),
        "first_frame_sha256": rotation.frames[0].sha256,
        "last_frame_sha256": rotation.frames[-1].sha256,
        "source_responses": [
            {
                "source": response.source,
                "locator": response.locator,
                "media_type": response.media_type,
                "sha256": hashlib.sha256(response.body).hexdigest(),
                "byte_count": len(response.body),
            }
            for response in raw.source_responses
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
