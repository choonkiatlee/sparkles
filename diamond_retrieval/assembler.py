"""Default in-memory result assembly."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .models import (
    CompletionAssessment,
    DiamondResult,
    Evidence,
    EvidenceAttempt,
    IdentityComparison,
    ListingRecord,
    ResultStatus,
)


class StandardResultAssembler:
    def assemble(
        self,
        listing: ListingRecord,
        evidence: Sequence[Evidence],
        comparisons: Sequence[IdentityComparison],
        attempts: Sequence[EvidenceAttempt],
        completion: CompletionAssessment,
        retrieved_at: datetime,
    ) -> DiamondResult:
        raw_responses = list(listing.raw_responses)
        for item in evidence:
            raw_responses.extend(item.source_responses)
        return DiamondResult(
            listing_url=listing.url,
            metadata=listing.metadata,
            evidence=tuple(evidence),
            provenance=listing.provenance,
            raw_responses=tuple(raw_responses),
            attempts=tuple(attempts),
            identity_comparisons=tuple(comparisons),
            status=ResultStatus.COMPLETE if completion.complete else ResultStatus.PARTIAL,
            completion_reasons=completion.reasons,
            retrieved_at=retrieved_at,
        )
