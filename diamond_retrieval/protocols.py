"""Small injectable component contracts for diamond retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Sequence

from .models import (
    CompletionAssessment,
    DiamondResult,
    Evidence,
    EvidenceAttempt,
    EvidenceReference,
    IdentityComparison,
    ListingRecord,
    RawEvidence,
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    url: str
    headers: Mapping[str, str]
    content: bytes


class HttpClient(Protocol):
    def get(self, url: str, *, timeout: float) -> HttpResponse: ...
    def post(
        self,
        url: str,
        *,
        timeout: float,
        content: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse: ...


class ListingProvider(Protocol):
    def supports(self, url: str) -> bool: ...
    def fetch(self, url: str) -> ListingRecord: ...


class EvidenceResolver(Protocol):
    def supports(self, reference: EvidenceReference) -> bool: ...
    def resolve(
        self, listing: ListingRecord, reference: EvidenceReference
    ) -> Sequence[EvidenceReference]: ...


class RetrievalPolicy(Protocol):
    def select(self, listing: ListingRecord, reference: EvidenceReference) -> bool: ...
    def assess_completion(
        self,
        listing: ListingRecord,
        evidence: Sequence[Evidence],
        attempts: Sequence[EvidenceAttempt],
        comparisons: Sequence[IdentityComparison],
    ) -> CompletionAssessment: ...


class EvidenceDownloader(Protocol):
    def supports(self, reference: EvidenceReference) -> bool: ...
    def download(self, reference: EvidenceReference) -> RawEvidence: ...


class EvidenceProcessor(Protocol):
    def supports(self, raw: RawEvidence) -> bool: ...
    def process(self, raw: RawEvidence) -> Sequence[Evidence]: ...


class IdentityValidator(Protocol):
    def validate(
        self, listing: ListingRecord, evidence: Sequence[Evidence]
    ) -> Sequence[IdentityComparison]: ...


class ResultAssembler(Protocol):
    def assemble(
        self,
        listing: ListingRecord,
        evidence: Sequence[Evidence],
        comparisons: Sequence[IdentityComparison],
        attempts: Sequence[EvidenceAttempt],
        completion: CompletionAssessment,
        retrieved_at: datetime,
    ) -> DiamondResult: ...
