"""Framework identity comparison without retailer-specific normalization."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from .models import (
    Evidence,
    IdentityComparison,
    IdentityOutcome,
    ListingRecord,
    ProvenanceStep,
)


_IDENTITY_FIELDS = (
    "report_number",
    "lab",
    "origin",
    "shape",
    "carat",
    "colour",
    "clarity",
    "dimensions",
)


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value.normalize()
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, str):
        return value.strip()
    return value


class StrictIdentityValidator:
    """Compare exact normalized representations; domain equivalences arrive in PR B."""

    def validate(
        self, listing: ListingRecord, evidence: Sequence[Evidence]
    ) -> Sequence[IdentityComparison]:
        listing_values = listing.metadata.identity_values()
        observed: dict[str, list[tuple[Any, tuple[ProvenanceStep, ...]]]] = defaultdict(list)
        for item in evidence:
            for observation in item.identity_observations:
                if observation.field in _IDENTITY_FIELDS:
                    observed[observation.field].append(
                        (observation.value, observation.provenance or item.provenance)
                    )

        comparisons: list[IdentityComparison] = []
        fields = [field for field in _IDENTITY_FIELDS if field in listing_values or field in observed]
        for field in fields:
            values: list[Any] = []
            provenance: list[ProvenanceStep] = []
            if field in listing_values:
                values.append(listing_values[field])
                provenance.extend(listing.provenance)
            for value, source in observed.get(field, []):
                values.append(value)
                provenance.extend(source)

            canonical = {_canonical(value) for value in values}
            if field not in listing_values or not observed.get(field):
                outcome = IdentityOutcome.MISSING
            elif len(canonical) == 1:
                outcome = IdentityOutcome.AGREEMENT
            else:
                outcome = IdentityOutcome.CONFLICT
            comparisons.append(
                IdentityComparison(
                    field=field,
                    outcome=outcome,
                    values=tuple(values),
                    provenance=tuple(provenance),
                )
            )
        return tuple(comparisons)
