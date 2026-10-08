"""Domain models for modular single-URL diamond retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, NewType

EvidenceKind = NewType("EvidenceKind", str)
CERTIFICATE = EvidenceKind("certificate")
STILL = EvidenceKind("still")
ROTATION = EvidenceKind("rotation")
VIDEO = EvidenceKind("video")


class EvidenceStatus(str, Enum):
    SUCCESS = "success"
    NOT_REQUESTED = "not_requested"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"
    DOWNLOAD_FAILED = "download_failed"
    PROCESSING_FAILED = "processing_failed"
    EXTRACTION_FAILED = "extraction_failed"
    INVALID_PAYLOAD = "invalid_payload"
    RESOLUTION_FAILED = "resolution_failed"
    RESOLUTION_LIMIT = "resolution_limit"
    RESOLVED = "resolved"
    DUPLICATE = "duplicate"


class ResultStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class IdentityOutcome(str, Enum):
    AGREEMENT = "agreement"
    MISSING = "missing"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ProvenanceStep:
    source: str
    locator: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldAttribution:
    source: str
    locator: str | None = None


@dataclass(frozen=True)
class SourceResponse:
    source: str
    body: bytes | str
    locator: str | None = None
    media_type: str | None = None
    sanitized: bool = True


@dataclass(frozen=True)
class DiamondMetadata:
    report_number: str | None = None
    lab: str | None = None
    retailer_sku: str | None = None
    origin: str | None = None
    shape: str | None = None
    carat: Decimal | float | None = None
    colour: str | None = None
    clarity: str | None = None
    dimensions: tuple[float, ...] | None = None
    reported_proportions: Mapping[str, str | float] = field(default_factory=dict)
    price: Decimal | None = None
    currency: str | None = None
    tax_basis: str | None = None
    attribution: Mapping[str, FieldAttribution] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def identity_values(self) -> Mapping[str, Any]:
        names = (
            "report_number",
            "lab",
            "origin",
            "shape",
            "carat",
            "colour",
            "clarity",
            "dimensions",
        )
        return {name: getattr(self, name) for name in names if getattr(self, name) is not None}


@dataclass(frozen=True)
class EvidenceReference:
    identifier: str
    kind: EvidenceKind
    retrieval_key: str
    locator: str | None = None
    provenance: tuple[ProvenanceStep, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ListingRecord:
    url: str
    metadata: DiamondMetadata
    references: tuple[EvidenceReference, ...] = ()
    provenance: tuple[ProvenanceStep, ...] = ()
    raw_responses: tuple[SourceResponse, ...] = ()


@dataclass(frozen=True)
class RawEvidence:
    reference: EvidenceReference
    payload: bytes
    media_type: str | None = None
    format: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_responses: tuple[SourceResponse, ...] = ()


@dataclass(frozen=True)
class IdentityObservation:
    field: str
    value: Any
    provenance: tuple[ProvenanceStep, ...] = ()


@dataclass(frozen=True)
class IdentityComparison:
    field: str
    outcome: IdentityOutcome
    values: tuple[Any, ...] = ()
    provenance: tuple[ProvenanceStep, ...] = ()


@dataclass(frozen=True)
class Evidence:
    identifier: str
    kind: EvidenceKind
    provenance: tuple[ProvenanceStep, ...]
    payload: bytes
    identity_observations: tuple[IdentityObservation, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_responses: tuple[SourceResponse, ...] = ()
    status: EvidenceStatus = EvidenceStatus.SUCCESS


@dataclass(frozen=True)
class CertificateEvidence(Evidence):
    extracted_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StillEvidence(Evidence):
    dimensions: tuple[int, int] | None = None


@dataclass(frozen=True)
class RotationFrame:
    source_index: int
    payload: bytes
    dimensions: tuple[int, int]
    sha256: str
    stored_position: int | None = None
    source_batch: str | None = None


@dataclass(frozen=True)
class RotationEvidence(Evidence):
    frames: tuple[RotationFrame, ...] = ()
    face_up_hint: Any | None = None


@dataclass(frozen=True)
class VideoEvidence(Evidence):
    media_type: str | None = None


@dataclass(frozen=True)
class EvidenceAttempt:
    reference_identifier: str
    kind: EvidenceKind
    retrieval_key: str
    status: EvidenceStatus
    provenance: tuple[ProvenanceStep, ...] = ()
    message: str | None = None
    locator: str | None = None


@dataclass(frozen=True)
class CompletionAssessment:
    complete: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiamondResult:
    listing_url: str
    metadata: DiamondMetadata
    evidence: tuple[Evidence, ...]
    provenance: tuple[ProvenanceStep, ...]
    raw_responses: tuple[SourceResponse, ...]
    attempts: tuple[EvidenceAttempt, ...]
    identity_comparisons: tuple[IdentityComparison, ...]
    status: ResultStatus
    completion_reasons: tuple[str, ...]
    retrieved_at: datetime

    def evidence_of_kind(self, kind: EvidenceKind) -> tuple[Evidence, ...]:
        return tuple(item for item in self.evidence if item.kind == kind)

    @property
    def certificate_link(self) -> str | None:
        """Original linked verification URL, or attempted PDF URL if none was linked.

        This is an unverified reference, NOT evidence that the PDF was recovered.
        """
        for attempt in self.attempts:
            if (
                attempt.kind == CERTIFICATE
                and attempt.locator
                and attempt.locator.startswith(("https://", "http://"))
            ):
                return attempt.locator
        return None

    @property
    def certificates(self) -> tuple[Evidence, ...]:
        return self.evidence_of_kind(CERTIFICATE)

    @property
    def stills(self) -> tuple[Evidence, ...]:
        return self.evidence_of_kind(STILL)

    @property
    def rotations(self) -> tuple[Evidence, ...]:
        return self.evidence_of_kind(ROTATION)

    @property
    def videos(self) -> tuple[Evidence, ...]:
        return self.evidence_of_kind(VIDEO)
