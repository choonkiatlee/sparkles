"""Identity comparison and documented diamond normalization rules."""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
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
    """Compare exact normalized representations."""

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


_SHAPES = {
    "ROUND": "ROUND",
    "ROUND BRILLIANT": "ROUND",
    "ROUND BRILLIANT CUT": "ROUND",
    "OVAL": "OVAL",
    "OVAL BRILLIANT": "OVAL",
    "OVAL MODIFIED BRILLIANT": "OVAL",
    "EMERALD": "EMERALD",
    "EMERALD CUT": "EMERALD",
    "ASSCHER": "ASSCHER",
    "ASSCHER CUT": "ASSCHER",
    "CUSHION": "CUSHION",
    "CUSHION BRILLIANT": "CUSHION",
    "CUSHION MODIFIED BRILLIANT": "CUSHION",
    "PEAR": "PEAR",
    "PEAR BRILLIANT": "PEAR",
    "PRINCESS": "PRINCESS",
    "PRINCESS CUT": "PRINCESS",
    "RADIANT": "RADIANT",
    "RADIANT CUT": "RADIANT",
    "MARQUISE": "MARQUISE",
    "MARQUISE BRILLIANT": "MARQUISE",
    "HEART": "HEART",
    "HEART BRILLIANT": "HEART",
}


def _normalize(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "report_number":
        return re.sub(r"[^A-Z0-9]", "", str(value).upper())
    if field == "lab":
        text = re.sub(r"\s+", " ", str(value).strip().upper())
        if text in {"IGI", "INTERNATIONAL GEMOLOGICAL INSTITUTE"}:
            return "IGI"
        return text
    if field == "origin":
        text = re.sub(r"[^A-Z]+", " ", str(value).upper()).strip()
        if text in {
            "LAB GROWN",
            "LABORATORY GROWN",
            "LAB CREATED",
            "LABORATORY CREATED",
        }:
            return "LAB-GROWN"
        if text in {"NATURAL", "NATURAL DIAMOND", "MINED", "EARTH MINED"}:
            return "NATURAL"
        return text
    if field == "shape":
        text = re.sub(r"\s+", " ", str(value).upper().replace("-", " ")).strip()
        return _SHAPES.get(text, text)
    if field == "carat":
        try:
            return Decimal(str(value)).normalize()
        except InvalidOperation:
            return str(value).strip()
    if field in {"colour", "clarity"}:
        return str(value).strip().upper()
    if field == "dimensions":
        try:
            return tuple(Decimal(str(item)).normalize() for item in value)
        except (TypeError, InvalidOperation):
            return value
    return _canonical(value)


class DiamondIdentityValidator:
    """Compare listing and evidence identity with narrow documented equivalences."""

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
        for field in _IDENTITY_FIELDS:
            if field not in listing_values and field not in observed:
                continue
            values: list[Any] = []
            provenance: list[ProvenanceStep] = []
            listing_present = field in listing_values
            evidence_present = bool(observed.get(field))
            if listing_present:
                values.append(listing_values[field])
                provenance.extend(listing.provenance)
            for value, source in observed.get(field, []):
                values.append(value)
                provenance.extend(source)

            normalized = {_normalize(field, value) for value in values}
            if len(normalized) > 1:
                outcome = IdentityOutcome.CONFLICT
            elif listing_present and evidence_present:
                outcome = IdentityOutcome.AGREEMENT
            else:
                outcome = IdentityOutcome.MISSING
            comparisons.append(
                IdentityComparison(
                    field=field,
                    outcome=outcome,
                    values=tuple(values),
                    provenance=tuple(provenance),
                )
            )
        return tuple(comparisons)
