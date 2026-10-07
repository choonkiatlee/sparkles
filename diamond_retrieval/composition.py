"""Public configuration and default framework composition."""
from __future__ import annotations

from dataclasses import dataclass, field

from .assembler import StandardResultAssembler
from .identity import StrictIdentityValidator
from .policy import StandardRetrievalPolicy
from .protocols import (
    EvidenceDownloader,
    EvidenceProcessor,
    EvidenceResolver,
    IdentityValidator,
    ListingProvider,
    ResultAssembler,
    RetrievalPolicy,
)
from .retriever import DiamondRetriever


@dataclass(frozen=True)
class RetrievalConfig:
    providers: tuple[ListingProvider, ...] = ()
    resolvers: tuple[EvidenceResolver, ...] = ()
    policy: RetrievalPolicy = field(default_factory=StandardRetrievalPolicy)
    downloaders: tuple[EvidenceDownloader, ...] = ()
    processors: tuple[EvidenceProcessor, ...] = ()
    identity_validator: IdentityValidator = field(default_factory=StrictIdentityValidator)
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


def default_config() -> RetrievalConfig:
    """Return the framework composition. Real adapters are registered in later PRs."""
    return RetrievalConfig()
