"""Default evidence selection and completion semantics."""
from __future__ import annotations

from collections.abc import Sequence

from .models import (
    CERTIFICATE,
    ROTATION,
    STILL,
    VIDEO,
    CompletionAssessment,
    Evidence,
    EvidenceAttempt,
    EvidenceKind,
    EvidenceStatus,
    IdentityComparison,
    IdentityOutcome,
    ListingRecord,
)


class StandardRetrievalPolicy:
    """Request certificate, still and motion evidence; require certificate + motion."""

    requested_kinds: frozenset[EvidenceKind] = frozenset(
        (CERTIFICATE, STILL, ROTATION, VIDEO)
    )

    def select(self, listing: ListingRecord, reference) -> bool:
        return reference.kind in self.requested_kinds

    def assess_completion(
        self,
        listing: ListingRecord,
        evidence: Sequence[Evidence],
        attempts: Sequence[EvidenceAttempt],
        comparisons: Sequence[IdentityComparison],
    ) -> CompletionAssessment:
        kinds = {item.kind for item in evidence if item.status == EvidenceStatus.SUCCESS}
        reasons: list[str] = []
        certificates = [
            item
            for item in evidence
            if item.kind == CERTIFICATE and item.status == EvidenceStatus.SUCCESS
        ]
        if not certificates:
            reasons.append("missing successful certificate evidence")
        else:
            certificate_identity_fields = {
                observation.field
                for item in certificates
                for observation in item.identity_observations
            }
            comparison_outcomes = {item.field: item.outcome for item in comparisons}
            if (
                "report_number" not in certificate_identity_fields
                or comparison_outcomes.get("report_number")
                != IdentityOutcome.AGREEMENT
            ):
                reasons.append("certificate report number was not parsed and matched")
            if listing.metadata.lab is not None:
                if (
                    "lab" not in certificate_identity_fields
                    or comparison_outcomes.get("lab") != IdentityOutcome.AGREEMENT
                ):
                    reasons.append("certificate lab identity was not parsed and matched")
        if not ({ROTATION, VIDEO} & kinds):
            reasons.append("missing successful motion evidence")

        failure_statuses = {
            EvidenceStatus.UNSUPPORTED,
            EvidenceStatus.MISSING,
            EvidenceStatus.DOWNLOAD_FAILED,
            EvidenceStatus.PROCESSING_FAILED,
            EvidenceStatus.EXTRACTION_FAILED,
            EvidenceStatus.INVALID_PAYLOAD,
            EvidenceStatus.RESOLUTION_FAILED,
            EvidenceStatus.RESOLUTION_LIMIT,
        }
        if any(item.status in failure_statuses for item in attempts):
            reasons.append("one or more requested evidence assets failed")
        return CompletionAssessment(not reasons, tuple(reasons))
