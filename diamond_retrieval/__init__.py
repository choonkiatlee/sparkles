"""Modular in-memory single-URL diamond retrieval."""
from __future__ import annotations

from .assembler import StandardResultAssembler
from .composition import RetrievalConfig, default_config
from .downloaders import LinkedEvidenceDownloader
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
from .http import UrllibHttpClient, validate_public_http_url
from .identity import DiamondIdentityValidator, StrictIdentityValidator
from .motion import ProgressiveRotationProcessor, decode_vision360_scramble
from .loupe360_proxy import Loupe360ProxyRotationDownloader, IndexedProxyRotationProcessor
from .motion_sources import (
    Core360RotationDownloader,
    D360RotationDownloader,
    DiajewelRotationDownloader,
    Labgrowns3RotationDownloader,
    RemoteV360RotationDownloader,
    WorkshopRotationDownloader,
)
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
from .processors import PdfCertificateProcessor, StillImageProcessor
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
from .resolvers import IgiReportPdfResolver, Loupe360CertificateResolver
from .retailers import DiyonaListingProvider, QualityDiamondsListingProvider
from .retriever import DiamondRetriever
from .reference_media import retrieve_reference_media, ReferenceMediaPolicy
from .video import DirectVideoDownloader, DirectVideoProcessor


def retrieve_diamond(url: str, config: RetrievalConfig | None = None) -> DiamondResult:
    """Retrieve one diamond into one self-contained in-memory result."""
    return (config or default_config()).build_retriever().retrieve(url)


__all__ = [
    "AmbiguousRegistrationError",
    "CERTIFICATE",
    "CertificateEvidence",
    "CompletionAssessment",
    "ConfigurationError",
    "Core360RotationDownloader",
    "DiamondIdentityValidator",
    "DiamondMetadata",
    "DiamondResult",
    "DiamondRetrievalError",
    "DiamondRetriever",
    "D360RotationDownloader",
    "DiajewelRotationDownloader",
    "Labgrowns3RotationDownloader",
    "RemoteV360RotationDownloader",
    "DirectVideoDownloader",
    "DirectVideoProcessor",
    "DiyonaListingProvider",
    "Evidence",
    "EvidenceAttempt",
    "EvidenceDownloader",
    "EvidenceKind",
    "EvidenceProcessor",
    "EvidenceReference",
    "EvidenceResolver",
    "EvidenceStatus",
    "FieldAttribution",
    "HttpClient",
    "HttpResponse",
    "IdentityComparison",
    "IdentityConflictError",
    "IdentityObservation",
    "IdentityOutcome",
    "IdentityValidator",
    "IgiReportPdfResolver",
    "IndexedProxyRotationProcessor",
    "InvalidPayloadError",
    "LinkedEvidenceDownloader",
    "ListingProvider",
    "ListingRecord",
    "Loupe360CertificateResolver",
    "Loupe360ProxyRotationDownloader",
    "MissingEvidenceError",
    "PdfCertificateProcessor",
    "ProgressiveRotationProcessor",
    "ProvenanceStep",
    "QualityDiamondsListingProvider",
    "ROTATION",
    "RawEvidence",
    "ResultAssembler",
    "ResultStatus",
    "RetrievalConfig",
    "RetrievalError",
    "RetrievalPolicy",
    "ReferenceMediaPolicy",
    "RotationEvidence",
    "RotationFrame",
    "STILL",
    "SourceResponse",
    "StandardResultAssembler",
    "StandardRetrievalPolicy",
    "StillEvidence",
    "StillImageProcessor",
    "StrictIdentityValidator",
    "UnsupportedEvidenceError",
    "UnsupportedInputError",
    "UrllibHttpClient",
    "VIDEO",
    "VideoEvidence",
    "decode_vision360_scramble",
    "default_config",
    "retrieve_diamond",
    "retrieve_reference_media",
    "validate_public_http_url",
    "WorkshopRotationDownloader",
]
