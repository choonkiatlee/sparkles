"""Listing-independent, deterministic evidence retrieval for educational references.

Consumes an agent-curated reference identity and source hints. No retailer
HTML, LLM, disk writes or asset publication happen on this code path.
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from urllib.parse import urlsplit

from .composition import RetrievalConfig, default_config
from .http import UrllibHttpClient
from .models import (
    CERTIFICATE, ROTATION, STILL, VIDEO,
    CompletionAssessment, DiamondMetadata, DiamondResult,
    EvidenceReference, EvidenceStatus, ListingRecord, ProvenanceStep,
)
from .protocols import HttpClient
from .resolvers import IgiReportPdfResolver, Loupe360CertificateResolver

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_REPORT = re.compile(r"[A-Za-z0-9-]{5,64}\Z")
_FAILURE = {
    EvidenceStatus.UNSUPPORTED, EvidenceStatus.MISSING,
    EvidenceStatus.DOWNLOAD_FAILED, EvidenceStatus.PROCESSING_FAILED,
    EvidenceStatus.EXTRACTION_FAILED, EvidenceStatus.INVALID_PAYLOAD,
    EvidenceStatus.RESOLUTION_FAILED, EvidenceStatus.RESOLUTION_LIMIT,
}


def _safe_source_url(url: object) -> str:
    """Reject unsafe explicit inputs before any injected HTTP client can run.

    The production HTTP client additionally checks DNS and each redirect hop.
    """
    if not isinstance(url, str) or len(url) > 2048 or any(
        c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url
    ):
        raise ValueError("Reference media URL must be public HTTPS without whitespace")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid reference media URL") from exc
    if (
        parsed.scheme != "https" or not host or port not in (None, 443)
        or parsed.username is not None or parsed.password is not None
        or "." not in host or host.startswith(".")
        or host == "localhost" or host.endswith((".local", ".internal"))
    ):
        raise ValueError("Reference media URL must be public HTTPS")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Reference media cannot target an IP literal")
    return url


class ReferenceMediaPolicy:
    """A reference may lack any certificate, but never claim unvalidated motion."""

    def select(self, listing: ListingRecord, reference: EvidenceReference) -> bool:
        return reference.kind in {CERTIFICATE, STILL, ROTATION, VIDEO}

    def assess_completion(self, listing, evidence, attempts, comparisons):
        success = any(item.status == EvidenceStatus.SUCCESS for item in evidence)
        reasons = []
        if not success:
            reasons.append("no validated reference media recovered")
        if any(attempt.status in _FAILURE for attempt in attempts):
            reasons.append("one or more candidate sources could not be recovered")
        return CompletionAssessment(not reasons, tuple(reasons))


def retrieve_reference_media(
    reference_id: str,
    *,
    lab: str | None = None,
    report_number: str | None = None,
    media_sources: Sequence[Mapping[str, object]] = (),
    include_igi_pdf: bool = False,
    http_client: HttpClient | None = None,
    config: RetrievalConfig | None = None,
) -> DiamondResult:
    """Recover independently sourced evidence without a ListingProvider.

    Returns the existing typed DiamondResult with original evidence, metadata,
    provenance, identity comparisons and per-source attempts. Its listing_url is
    a local reference:<id> locator, NOT a supplier page or certified identity.

    A direct media URL is attempted before exact-report discovery. Unsupported
    viewer formats (including v360.diamonds and Loupe360 UUID/numeric pages)
    stay UNSUPPORTED, never guessed into a certified report. An exact IGI lab
    and report enable a best-effort Loupe/Nivoda lookup and optional IGI PDF.
    IdentityConflictError fails closed; callers must not publish a partial
    result after an identity conflict.
    """
    if not isinstance(reference_id, str) or len(reference_id) > 96 or not _ID.fullmatch(reference_id):
        raise ValueError("reference_id must be a stable unprefixed slug")
    if lab is not None and (not isinstance(lab, str) or not lab.strip()):
        raise ValueError("lab must be a nonempty string if supplied")
    if report_number is not None and (
        not isinstance(report_number, str)
        or not _REPORT.fullmatch(report_number.strip())
        or lab is None
    ):
        raise ValueError("report_number requires a full report and lab")
    if not isinstance(media_sources, (tuple, list)):
        raise ValueError("media_sources must be a sequence")

    norm_lab = lab.strip().upper() if lab is not None else None
    norm_report = report_number.strip().upper() if report_number is not None else None
    source_references: list[EvidenceReference] = []
    for index, source in enumerate(media_sources):
        if not isinstance(source, Mapping):
            raise ValueError("media_sources entries must be objects")
        kind = source.get("kind")
        if kind not in {"viewer", "still", "video"}:
            raise ValueError("Source kind must be viewer, still or video")
        if source.get("status", "linked_unverified") != "linked_unverified":
            raise ValueError("Curated source must be linked_unverified")
        provider = source.get("provider", "external")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("media source provider must be text")
        url = _safe_source_url(source.get("url"))
        if kind == "viewer":
            # An exact Pixorac wrapper can disclose a supported supplier URL.
            # A Loupe UUID or numeric viewer path is NOT a certificate number.
            if urlsplit(url).hostname == "assets-images.pixorac.com":
                url = _safe_source_url(Loupe360CertificateResolver._unwrap_v360(url))
            evidence_kind, extra = ROTATION, {}
        elif kind == "still":
            evidence_kind, extra = STILL, {}
        else:
            evidence_kind, extra = VIDEO, {"format": "video"}
        source_references.append(EvidenceReference(
            identifier=f"{reference_id}:source-{index}",
            kind=evidence_kind,
            retrieval_key=url,
            locator=url,
            provenance=(ProvenanceStep(
                "reference_media_source", url,
                {"reference_id": reference_id, "provider": provider},
            ),),
            metadata={"reference_id": reference_id, **extra},
        ))

    if norm_lab and norm_report:
        # Lookup is deliberately separate from user-supplied media. Exact
        # certificate metadata is never inferred from a Loupe viewer token.
        source_references.append(EvidenceReference(
            identifier=f"{reference_id}:loupe-report",
            kind=ROTATION,
            retrieval_key=f"loupe360-report:{norm_report}",
            locator=f"loupe360-report:{norm_report}",
            provenance=(ProvenanceStep(
                "curated_report", None,
                {"lab": norm_lab, "report_number": norm_report},
            ),),
            metadata={
                "resolver": "loupe360_certificate",
                "lab": norm_lab,
                "report_number": norm_report,
            },
        ))
        if norm_lab == "IGI" and include_igi_pdf:
            source_references.append(EvidenceReference(
                identifier=f"{reference_id}:igi-report",
                kind=CERTIFICATE,
                retrieval_key=f"igi-report:{norm_report}",
                locator=f"igi-report:{norm_report}",
                provenance=(ProvenanceStep(
                    "curated_report", None,
                    {"lab": norm_lab, "report_number": norm_report},
                ),),
                metadata={
                    "resolver": "igi_exact_report",
                    "lab": norm_lab,
                    "report_number": norm_report,
                },
            ))

    listing = ListingRecord(
        url=f"reference:{reference_id}",
        metadata=DiamondMetadata(lab=norm_lab, report_number=norm_report),
        references=tuple(source_references),
        provenance=(ProvenanceStep("curated_reference", f"reference:{reference_id}"),),
    )
    if config is None:
        client = http_client or UrllibHttpClient()
        base = default_config(client)
        config = replace(
            base,
            providers=(),
            resolvers=(
                IgiReportPdfResolver(),
                Loupe360CertificateResolver(client, include_image=True),
            ),
            policy=ReferenceMediaPolicy(),
        )
    return config.build_retriever().retrieve_record(listing)
