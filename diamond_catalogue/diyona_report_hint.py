"""Optional *explicit* IGI report hint for an exact Diyona listing.

The SKU is already supplied by the URL. When Diyona's public HTML omits its
JavaScript-loaded certificate details, the user may supply the IGI report
number themselves. This is an assertion, never portrayed as retailer proof.
The publisher requires independent exact-report corroboration before commit.
No browser, scraping of search results, or guessed SKU->report lookup.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from diamond_retrieval.errors import RetrievalError
from diamond_retrieval.models import (
    CERTIFICATE, ROTATION, VIDEO, DiamondMetadata, EvidenceReference,
    FieldAttribution, ListingRecord, ProvenanceStep, IdentityOutcome,
    EvidenceStatus,
)
from diamond_retrieval.retailers import DiyonaListingProvider

from .models import CatalogueError

_NO_IDENTITY = "Diyona exact listing no longer exposes certificate-bound diamond data"
_MISMATCH = "Diyona explicit IGI report differs from the returned listing"


def normalize_report_hint(value: str) -> str:
    """Only accept a complete LG report number, not an unqualified stone ID."""
    text = value.strip().upper()
    if text.startswith("IGI "):
        text = text[4:].strip()
    if not re.fullmatch(r"LG[0-9]{8,12}", text):
        raise ValueError("IGI report input must be a full LG report number")
    return text


class ReportHintDiyonaProvider(DiyonaListingProvider):
    def __init__(self, http_client, *, report_hint: str, timeout: float = 20.0):
        super().__init__(http_client, timeout=timeout)
        self.report_hint = normalize_report_hint(report_hint)

    def fetch(self, url: str) -> ListingRecord:
        if not self.supports(url):
            raise RetrievalError("Report hint only supports an exact Diyona listing")
        try:
            listing = super().fetch(url)
        except RetrievalError as error:
            if str(error) != _NO_IDENTITY:
                raise
        else:
            if listing.metadata.report_number != self.report_hint:
                raise RetrievalError(_MISMATCH)
            return listing

        # HTTP returned a valid page but the exact listing's certificate was
        # not in static HTML. Record the user's explicit claim; never pretend
        # the retailer gave us this mapping.
        sku = parse_qs(urlsplit(url).query)["sku"][0]
        assertion = ProvenanceStep(
            "user_supplied_igi_report", url,
            {"report_number": self.report_hint, "retailer_sku": sku,
             "verified_against_listing": False},
        )
        metadata = DiamondMetadata(
            lab="IGI", report_number=self.report_hint, retailer_sku=sku,
            attribution={
                "lab": FieldAttribution("user_supplied_igi_report", url),
                "report_number": FieldAttribution("user_supplied_igi_report", url),
            },
            extra={"identity_provenance": "user_supplied_igi_report"},
        )
        report = self.report_hint
        refs = (
            EvidenceReference(
                identifier=f"diyona:{sku}:certificate",
                kind=CERTIFICATE,
                retrieval_key=f"igi-report:{report}",
                locator=f"igi-report:{report}",
                provenance=(assertion,),
                metadata={"lab": "IGI", "report_number": report,
                          "resolver": "igi_exact_report"},
            ),
            EvidenceReference(
                identifier=f"diyona:{sku}:loupe360:rotation",
                kind=ROTATION,
                retrieval_key=f"loupe360-report:{report}",
                locator=f"loupe360-report:{report}",
                provenance=(assertion,),
                metadata={"lab": "IGI", "report_number": report,
                          "resolver": "loupe360_certificate"},
            ),
            EvidenceReference(
                identifier=f"diyona:{sku}:loupe360:video",
                kind=VIDEO,
                retrieval_key=f"loupe360-report:{report}",
                locator=f"loupe360-report:{report}",
                provenance=(assertion,),
                metadata={"lab": "IGI", "report_number": report,
                          "resolver": "loupe360_certificate"},
            ),
        )
        return ListingRecord(
            url=url, metadata=metadata, references=refs, provenance=(assertion,),
        )


def require_independent_report_corroboration(result) -> None:
    """A manual hint must lead to independently retrieved matching evidence.

    IGI PDF evidence with a parsed matching certificate or successful motion
    downloaded from Loupe's exact certificate-bound resolver counts.
    A typed report number by itself never authorises a catalogue write.
    """
    if not any(p.source == "user_supplied_igi_report" for p in result.provenance):
        return
    report = result.metadata.report_number
    outcomes = {c.field: c.outcome for c in result.identity_comparisons}
    has_certificate = (
        outcomes.get("report_number") == IdentityOutcome.AGREEMENT and
        any(
            e.kind == CERTIFICATE and e.status == EvidenceStatus.SUCCESS and
            any(o.field == "report_number" and
                re.sub(r"[^A-Z0-9]", "", str(o.value).upper()) == report
                for o in e.identity_observations)
            for e in result.evidence
        )
    )
    has_loupe_motion = any(
        e.kind in {ROTATION, VIDEO} and e.status == EvidenceStatus.SUCCESS and
        any(
            p.source == "loupe360_exact_certificate" and
            p.details.get("report_number") == report
            for p in e.provenance
        )
        for e in result.evidence
    )
    if not (has_certificate or has_loupe_motion):
        raise CatalogueError(
            "Explicit IGI hint lacks independent certificate-bound corroboration"
        )
