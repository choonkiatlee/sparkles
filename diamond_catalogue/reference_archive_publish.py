"""Publish original PriceScope #64 archive media into existing Learning Corner evidence.

This is an owner-triggered, fixed allowlist import of the *already archived*
byte-verified originals. No supplier scraping, arbitrary issue input, synthetic
rotation, certificate assignment, or second storage/publication mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from diamond360.external_media import adapt_archived_sequence
from diamond_retrieval.models import (
    ROTATION, VIDEO, EvidenceReference, ProvenanceStep, RawEvidence,
    RotationEvidence, RotationFrame,
)
from diamond_retrieval.video import DirectVideoProcessor

from .github_api import GitHubAPI, GitHubError
from .github_release import GitHubReleaseStorage
from .models import CatalogueError
from .planner import finalize_manifest
from .reference_publish import GitHubReferenceCatalogue, plan_reference_media

ARCHIVE_SHA256 = "379f411098e4d96df78d7c00fea5bb9fd18d5f37d890b873928c4003ba126da5"
BENCHMARK_PATH = Path(__file__).resolve().parents[1] / (
    "docs/360/external-benchmark/pricescope/benchmark-manifest.json"
)
# Only known forum examples, not a user-provided archive path or source URL.
APPROVED = {
    "ps281114-r17": ("asscher-eval-glittery", "rotation",
                      "https://d360.tech/view.html?d=79-BB-5159600"),
    "ps281114-r18": ("asscher-eval-crispest", "rotation",
                      "https://d360.tech/view.html?d=79-BT-5165227"),
    "ps281114-r20": ("asscher-eval-messy-arrows", "video",
                      "https://www.kashiimports.com/video/22957.mp4"),
    "ps281114-r22": ("asscher-eval-nice-dance", "video",
                      "https://www.kashiimports.com/video/27196.mp4"),
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _checked_relative(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise CatalogueError("Unsafe archived media path")
    if ".." in Path(relative).parts:
        raise CatalogueError("Unsafe archived media parent traversal")
    full = (root / relative).resolve()
    if not full.is_relative_to(root.resolve()) or not full.is_file():
        raise CatalogueError("Archived media path missing or unsafe")
    return full


def _validate_bytes(path: Path, digest: str, size: int) -> bytes:
    payload = path.read_bytes()
    if len(payload) != size or _digest(payload) != digest:
        raise CatalogueError("Original archived media hash or byte count mismatch")
    return payload


def _benchmark_record(benchmark: dict, sample_id: str) -> dict:
    if benchmark.get("schema_version") != "sparkles-external-benchmark/1":
        raise CatalogueError("Unexpected benchmark manifest schema")
    records = [item for item in benchmark.get("samples", [])
               if item.get("sample_id") == sample_id]
    if len(records) != 1 or not records[0].get("media", {}).get("full_original_verified"):
        raise CatalogueError("Missing verified exact PriceScope sample")
    return records[0]["media"]


def _validated_source(accepted: dict, kind: str, url: str) -> None:
    identity = accepted["identity"]
    if (identity != {"status": "unverified", "lab": None, "report_number": None}
            or accepted.get("linked_diamond_id") is not None):
        raise CatalogueError("Archived external example cannot be assigned a certificate")
    curated_kind = "viewer" if kind == "rotation" else "video"
    if not any(x.get("kind") == curated_kind and x.get("url") == url
               for x in accepted.get("media_sources", [])):
        raise CatalogueError("Archived media does not match curated original link")


def _rotation_evidence(reference_id: str, media: dict, source_url: str,
                       archive_root: Path) -> RotationEvidence:
    sequence = media.get("sequence")
    if not sequence or sequence.get("frame_count") != 256:
        raise CatalogueError("Archive lacks a complete original 256-frame rotation")
    manifest_path = _checked_relative(archive_root, sequence["manifest_path"])
    _validate_bytes(manifest_path, sequence["manifest_sha256"], sequence["manifest_bytes"])
    if sequence.get("dimensions") not in ([758, 597], [648, 511]):
        raise CatalogueError("Unexpected original sequence dimensions")
    # Reuse the already tested #64 adapter: validates all original source
    # frame hashes, source indices and image decodability, without resampling.
    with TemporaryDirectory(prefix="sparkles-archive-") as temp:
        out = Path(temp) / "normalized"
        report = adapt_archived_sequence(
            archive_root, sequence, out,
            provenance={"source": "pricescope-research-release-v3",
                        "sample_id": media["locator"]["sample_id"]},
        )
        if (report["source_frame_count"] != 256 or
                report["sequence_complete"] is not True or
                [row["source_index"] for row in report["frames"]] != list(range(256))):
            raise CatalogueError("Archived source frame ordering is incomplete")
        frames = []
        for row in report["frames"]:
            if [row["width"], row["height"]] != sequence["dimensions"]:
                raise CatalogueError("Archived original frame dimensions mismatch")
            data = _validate_bytes(_checked_relative(out, row["path"]),
                                   row["sha256"], row["bytes"])
            if not data.startswith(b"\\xff\\xd8\\xff"):
                raise CatalogueError("Archived rotation frame is not original JPEG")
            frames.append(RotationFrame(
                source_index=row["source_index"], payload=data,
                sha256=row["sha256"], dimensions=(row["width"], row["height"]),
            ))
    provenance = (ProvenanceStep(
        "pricescope_archived_original", source_url,
        {"archive_sha256": ARCHIVE_SHA256,
         "source_manifest_sha256": sequence["manifest_sha256"],
         "original_source": "d360.tech", "angles_calibrated": False},
    ),)
    return RotationEvidence(
        identifier=reference_id + ":archive-rotation", kind=ROTATION,
        provenance=provenance, payload=b"", frames=tuple(frames),
        metadata={"sequence_complete": True, "frame_count": 256,
                  "ordering": "archived_original_source_index",
                  "physical_angle_calibrated": False},
    )


def _video_evidence(reference_id: str, media: dict, source_url: str,
                    archive_root: Path):
    assets = media.get("assets", [])
    if len(assets) != 1 or assets[0].get("media_url") != source_url:
        raise CatalogueError("Archived video differs from curated Kashi source")
    asset = assets[0]
    if asset.get("media_type") != "mp4" or asset.get("byte_archive_status") != "archived_original":
        raise CatalogueError("Missing original archived MP4")
    data = _validate_bytes(_checked_relative(archive_root, asset["artifact_path"]),
                           asset["sha256"], asset["bytes"])
    provenance = (ProvenanceStep(
        "pricescope_archived_original", source_url,
        {"archive_sha256": ARCHIVE_SHA256, "original_sha256": asset["sha256"]},
    ),)
    reference = EvidenceReference(
        identifier=reference_id + ":archive-video", kind=VIDEO,
        retrieval_key=source_url, locator=source_url, provenance=provenance,
    )
    raw = RawEvidence(
        reference=reference, payload=data, media_type="video/mp4",
        format="video", metadata={"sha256": asset["sha256"]},
    )
    return DirectVideoProcessor().process(raw)[0]


def publish_archived_reference(reference_id: str, *, api, archive_root: Path,
                               benchmark_path: Path = BENCHMARK_PATH):
    if reference_id not in APPROVED:
        raise CatalogueError("Reference is not allowlisted for archive import")
    sample_id, kind, source_url = APPROVED[reference_id]
    catalogue = GitHubReferenceCatalogue(api)
    accepted = catalogue.load_accepted(reference_id)
    _validated_source(accepted, kind, source_url)
    if any(e.get("kind") in {"rotation", "video"} and e.get("status") == "success"
           for e in accepted.get("evidence", [])):
        return catalogue.commit(accepted, incoming_evidence=[],
                                incoming_attempts=[], asset_count=0)

    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    media = _benchmark_record(benchmark, sample_id)
    root = Path(archive_root).resolve()
    if not root.is_dir():
        raise CatalogueError("Archived media directory missing")
    if kind == "rotation":
        if media.get("locator", {}).get("url") != source_url:
            raise CatalogueError("Archived viewer provenance does not match reference")
        evidence = _rotation_evidence(reference_id, media, source_url, root)
    else:
        evidence = _video_evidence(reference_id, media, source_url, root)
    plan = plan_reference_media(
        SimpleNamespace(evidence=(evidence,), identity_comparisons=()),
        reference_id,
    )
    stored = GitHubReleaseStorage(api, release_prefix="sparkles-reference-").publish(plan.assets)
    published = finalize_manifest(plan, stored)["evidence"]
    return catalogue.commit(
        accepted, incoming_evidence=published, asset_count=len(plan.assets),
        incoming_attempts=[{
            "reference_identifier": reference_id + ":pricescope-archive-v3",
            "kind": kind, "status": "success", "locator": source_url,
        }],
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish verified PriceScope archive original")
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--reference-id", choices=tuple(APPROVED), required=True)
    args = parser.parse_args(argv)
    if os.environ.get("GITHUB_REF") != "refs/heads/master" or (
        os.environ.get("GITHUB_REPOSITORY") != "choonkiatlee/sparkles"
    ):
        parser.error("Archive publication requires trusted Sparkles master")
    try:
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""), os.environ["GITHUB_REPOSITORY"])
        receipt = publish_archived_reference(args.reference_id, api=api,
                                             archive_root=args.archive_root)
        print(f"Archived {receipt.reference_id}: {receipt.asset_count} source assets, "
              f"changed={receipt.changed}, commit={receipt.commit_sha}")
        return 0
    except (CatalogueError, GitHubError, ValueError, OSError) as exc:
        print("::error title=PriceScope archive import failed::"
              + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
