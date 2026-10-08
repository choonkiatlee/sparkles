"""Byte-preserving download and validation for direct public video media."""
from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from .errors import InvalidPayloadError, MissingEvidenceError
from .models import (
    VIDEO,
    EvidenceReference,
    ProvenanceStep,
    RawEvidence,
    SourceResponse,
    VideoEvidence,
)
from .protocols import HttpClient


_VIDEO_SUFFIXES = (".mp4", ".m4v", ".mov", ".webm")


class DirectVideoDownloader:
    """Download an exact public video URL without decoding or transcoding it."""

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind != VIDEO or not reference.locator:
            return False
        parts = urlsplit(reference.locator)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return False
        return (
            reference.metadata.get("format") == "video"
            or parts.path.lower().endswith(_VIDEO_SUFFIXES)
        )

    def download(self, reference: EvidenceReference) -> RawEvidence:
        response = self.http_client.get(reference.locator, timeout=self.timeout)
        if response.status_code == 404:
            raise MissingEvidenceError(
                f"Video returned HTTP 404: {reference.locator}"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"Video returned HTTP {response.status_code}: {reference.locator}"
            )
        if not response.content:
            raise InvalidPayloadError("Video endpoint returned empty bytes")
        media_type = response.headers.get("Content-Type")
        return RawEvidence(
            reference=reference,
            payload=response.content,
            media_type=media_type,
            format="video",
            metadata=dict(reference.metadata),
            source_responses=(
                SourceResponse(
                    source="direct_video",
                    body=response.content,
                    locator=response.url,
                    media_type=media_type,
                    sanitized=True,
                ),
            ),
        )


def _video_container(payload: bytes) -> str:
    if len(payload) >= 12 and payload[4:8] == b"ftyp":
        return "mp4"
    if payload.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    raise InvalidPayloadError("Video bytes are not a supported MP4/QuickTime or WebM container")


class DirectVideoProcessor:
    """Validate a direct video container while retaining original bytes."""

    def supports(self, raw: RawEvidence) -> bool:
        return raw.reference.kind == VIDEO and raw.format == "video"

    def process(self, raw: RawEvidence) -> tuple[VideoEvidence, ...]:
        container = _video_container(raw.payload)
        digest = hashlib.sha256(raw.payload).hexdigest()
        metadata = dict(raw.metadata)
        metadata.update(
            {
                "container": container,
                "sha256": digest,
                "bytes": len(raw.payload),
                "decoded_frames": False,
            }
        )
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                "direct_video_validation",
                raw.reference.locator,
                {"container": container, "sha256": digest},
            ),
        )
        return (
            VideoEvidence(
                identifier=raw.reference.identifier,
                kind=VIDEO,
                provenance=provenance,
                payload=raw.payload,
                metadata=metadata,
                source_responses=raw.source_responses,
                media_type=raw.media_type,
            ),
        )
