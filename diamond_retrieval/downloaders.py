"""Reusable in-memory downloaders for certificate and still evidence."""
from __future__ import annotations

from urllib.parse import urlsplit

from .errors import InvalidPayloadError, MissingEvidenceError
from .models import (
    CERTIFICATE,
    STILL,
    EvidenceReference,
    RawEvidence,
    SourceResponse,
)
from .protocols import HttpClient


class LinkedEvidenceDownloader:
    """Download exact linked PDF and still assets; motion remains a PR C concern."""

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind not in {CERTIFICATE, STILL} or not reference.locator:
            return False
        parts = urlsplit(reference.locator)
        return parts.scheme in {"http", "https"} and bool(parts.netloc)

    def download(self, reference: EvidenceReference) -> RawEvidence:
        response = self.http_client.get(reference.locator, timeout=self.timeout)
        if response.status_code == 404:
            raise MissingEvidenceError(f"Evidence returned HTTP 404: {reference.locator}")
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"Evidence returned HTTP {response.status_code}: {reference.locator}"
            )
        payload = response.content
        if reference.kind == CERTIFICATE and not payload.startswith(b"%PDF-"):
            raise InvalidPayloadError("Certificate endpoint did not return PDF bytes")

        media_type = response.headers.get("Content-Type")
        format_name = "pdf" if reference.kind == CERTIFICATE else "image"
        return RawEvidence(
            reference=reference,
            payload=payload,
            media_type=media_type,
            format=format_name,
            source_responses=(
                SourceResponse(
                    source="linked_evidence",
                    body=payload,
                    locator=response.url,
                    media_type=media_type,
                    sanitized=True,
                ),
            ),
        )
