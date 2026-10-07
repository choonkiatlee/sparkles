"""Modular in-memory single-URL diamond retrieval."""
from __future__ import annotations

from .assembler import StandardResultAssembler
from .composition import RetrievalConfig, default_config
from .errors import (
    AmbiguousRegistrationError,
    ConfigurationError,
    DiamondRetrievalError,
    IdentityConflictError,
    InvalidPayloadError,
    MissingEvidenceError,
    RetrievalError,
    UnsupportedEvidenceError,
    UnsupportedInputError,
)
from .identity import StrictIdentityValidator
from .models import (
    CERTIFICATE,
    ROTATION,
    STILL,
    VIDEO,
    CertificateEvidence,
    CompletionAssessment,
    DiamondMetadata,
    DiamondResult,
    Evidence,
    EvidenceAttempt,
    EvidenceKind,
    EvidenceReference,
    EvidenceStatus,
    FieldAttribution,
    IdentityComparison,
    IdentityObservation,
    IdentityOutcome,
    ListingRecord,
    ProvenanceStep,
    RawEvidence,
    ResultStatus,
    RotationEvidence,
    RotationFrame,
    SourceResponse,
    StillEvidence,
    VideoEvidence,
)
from .policy import StandardRetrievalPolicy
from .protocols import (
    EvidenceDownloader,
    EvidenceProcessor,
    EvidenceResolver,
    HttpClient,
    HttpResponse,
    IdentityValidator,
    ListingProvider,
    ResultAssembler,
    RetrievalPolicy,
)
from .retriever import DiamondRetriever


def retrieve_diamond(url: str, config: RetrievalConfig | None = None) -> DiamondResult:
    """Retrieve one diamond into one self-contained in-memory result."""
    return (config or default_config()).build_retriever().retrieve(url)


__all__ = [
    "AmbiguousRegistrationError",
    "CERTIFICATE",
    "CertificateEvidence",
    "CompletionAssessment",
    "ConfigurationError",
    "DiamondMetadata",
    "DiamondResult",
    "DiamondRetrievalError",
    "DiamondRetriever",
    "Evidence",
    "EvidenceAttempt",
    "EvidenceKind",
    "EvidenceReference",
    "EvidenceStatus",
    "EvidenceDownloader",
    "EvidenceProcessor",
    "EvidenceResolver",
    "HttpClient",
    "HttpResponse",
    "IdentityValidator",
    "ListingProvider",
    "FieldAttribution",
    "IdentityComparison",
    "IdentityConflictError",
    "IdentityObservation",
    "IdentityOutcome",
    "InvalidPayloadError",
    "ListingRecord",
    "MissingEvidenceError",
    "ProvenanceStep",
    "ROTATION",
    "RawEvidence",
    "ResultAssembler",
    "ResultStatus",
    "RetrievalPolicy",
    "RetrievalConfig",
    "RetrievalError",
    "RotationEvidence",
    "RotationFrame",
    "STILL",
    "SourceResponse",
    "StandardResultAssembler",
    "StandardRetrievalPolicy",
    "StillEvidence",
    "StrictIdentityValidator",
    "UnsupportedEvidenceError",
    "UnsupportedInputError",
    "VIDEO",
    "VideoEvidence",
    "default_config",
    "retrieve_diamond",
]
