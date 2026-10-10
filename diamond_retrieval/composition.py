"""Public configuration and default production composition."""
from __future__ import annotations

from dataclasses import dataclass, field

from .assembler import StandardResultAssembler
from .downloaders import LinkedEvidenceDownloader
from .http import UrllibHttpClient
from .motion import ProgressiveRotationProcessor
from .motion_sources import (
    Core360RotationDownloader,
    D360RotationDownloader,
    D360LegacyCanonicalRotationDownloader,
    DiajewelRotationDownloader,
    FilesOnSkyRotationDownloader,
    Labgrowns3RotationDownloader,
    RemoteV360RotationDownloader,
    WorkshopRotationDownloader,
)
from .loupe360_proxy import Loupe360ProxyRotationDownloader, IndexedProxyRotationProcessor
from .identity import DiamondIdentityValidator
from .policy import StandardRetrievalPolicy
from .processors import PdfCertificateProcessor, StillImageProcessor
from .protocols import (
    EvidenceDownloader,
    EvidenceProcessor,
    EvidenceResolver,
    HttpClient,
    IdentityValidator,
    ListingProvider,
    ResultAssembler,
    RetrievalPolicy,
)
from .resolvers import IgiReportPdfResolver, Loupe360CertificateResolver
from .retailers import DiyonaListingProvider, QualityDiamondsListingProvider
from .video import DirectVideoDownloader, DirectVideoProcessor
from .retriever import DiamondRetriever


@dataclass(frozen=True)
class RetrievalConfig:
    providers: tuple[ListingProvider, ...] = ()
    resolvers: tuple[EvidenceResolver, ...] = ()
    policy: RetrievalPolicy = field(default_factory=StandardRetrievalPolicy)
    downloaders: tuple[EvidenceDownloader, ...] = ()
    processors: tuple[EvidenceProcessor, ...] = ()
    identity_validator: IdentityValidator = field(default_factory=DiamondIdentityValidator)
    assembler: ResultAssembler = field(default_factory=StandardResultAssembler)
    max_resolution_depth: int = 8

    def build_retriever(self) -> DiamondRetriever:
        return DiamondRetriever(
            providers=self.providers,
            resolvers=self.resolvers,
            policy=self.policy,
            downloaders=self.downloaders,
            processors=self.processors,
            identity_validator=self.identity_validator,
            assembler=self.assembler,
            max_resolution_depth=self.max_resolution_depth,
        )


def default_config(http_client: HttpClient | None = None) -> RetrievalConfig:
    """Compose the currently supported public retailer/certificate adapters."""
    client = http_client or UrllibHttpClient()
    return RetrievalConfig(
        providers=(
            DiyonaListingProvider(client),
            QualityDiamondsListingProvider(client),
        ),
        resolvers=(
            IgiReportPdfResolver(),
            Loupe360CertificateResolver(client),
        ),
        policy=StandardRetrievalPolicy(),
        downloaders=(
            LinkedEvidenceDownloader(client),
            DiajewelRotationDownloader(client),
            Labgrowns3RotationDownloader(client),
            FilesOnSkyRotationDownloader(client),
            WorkshopRotationDownloader(client),
            Loupe360ProxyRotationDownloader(client),
            Core360RotationDownloader(client),
            RemoteV360RotationDownloader(client),
            D360LegacyCanonicalRotationDownloader(client),
            D360RotationDownloader(client),
            DirectVideoDownloader(client),
        ),
        processors=(
            PdfCertificateProcessor(),
            StillImageProcessor(),
            ProgressiveRotationProcessor(),
            IndexedProxyRotationProcessor(),
            DirectVideoProcessor(),
        ),
        identity_validator=DiamondIdentityValidator(),
        assembler=StandardResultAssembler(),
    )
