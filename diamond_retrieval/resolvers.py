"""Deterministic exact-report resolvers used by retailer adapters."""
from __future__ import annotations

from urllib.parse import parse_qs, quote, urlsplit

from .models import (
    CERTIFICATE,
    ROTATION,
    VIDEO,
    EvidenceReference,
    ListingRecord,
    ProvenanceStep,
)


def _report_number(reference: EvidenceReference) -> str | None:
    value = reference.metadata.get("report_number")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    if reference.locator:
        parts = urlsplit(reference.locator)
        query = parse_qs(parts.query)
        value = query.get("r", [None])[0]
        if value:
            return value.strip().upper()
        if reference.locator.startswith("igi-report:"):
            return reference.locator.split(":", 1)[1].strip().upper()
        if reference.locator.startswith("loupe360-report:"):
            return reference.locator.split(":", 1)[1].strip().upper()
    return None


class IgiReportPdfResolver:
    """Resolve an exact IGI report number to IGI's public report-PDF endpoint."""

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind != CERTIFICATE:
            return False
        if reference.metadata.get("resolver") == "igi_exact_report":
            return True
        if not reference.locator:
            return False
        parts = urlsplit(reference.locator)
        return (
            parts.netloc.lower() in {"igi.org", "www.igi.org"}
            and "verify-your-report" in parts.path
        )

    def resolve(
        self, listing: ListingRecord, reference: EvidenceReference
    ) -> tuple[EvidenceReference, ...]:
        report = _report_number(reference)
        if not report:
            raise ValueError("IGI exact-report resolver requires a report number")
        metadata = dict(reference.metadata)
        metadata.pop("resolver", None)
        metadata["format"] = "pdf"
        metadata["report_number"] = report
        locator = f"https://api.igi.org/viewpdf.php?r={quote(report, safe='')}"
        return (
            EvidenceReference(
                identifier=f"{reference.identifier}:pdf",
                kind=CERTIFICATE,
                retrieval_key=f"igi-pdf:{report}",
                locator=locator,
                provenance=(
                    ProvenanceStep(
                        "igi_exact_report",
                        locator,
                        {"report_number": report},
                    ),
                ),
                metadata=metadata,
            ),
        )


class Loupe360CertificateResolver:
    """Resolve only an exact certificate identity to Loupe360's public viewer route."""

    def supports(self, reference: EvidenceReference) -> bool:
        return (
            reference.kind in {ROTATION, VIDEO}
            and reference.metadata.get("resolver") == "loupe360_certificate"
        )

    def resolve(
        self, listing: ListingRecord, reference: EvidenceReference
    ) -> tuple[EvidenceReference, ...]:
        report = _report_number(reference)
        if not report:
            raise ValueError("Loupe360 exact-certificate resolver requires a report number")
        metadata = dict(reference.metadata)
        metadata.pop("resolver", None)
        metadata["report_number"] = report
        metadata["lab"] = metadata.get("lab") or "IGI"
        locator = (
            "https://loupe360.com/diamond/"
            f"{quote(report, safe='')}/video/500/500"
        )
        return (
            EvidenceReference(
                identifier=f"{reference.identifier}:loupe360",
                kind=reference.kind,
                retrieval_key=f"loupe360:{report}:video",
                locator=locator,
                provenance=(
                    ProvenanceStep(
                        "loupe360_exact_certificate",
                        locator,
                        {"report_number": report, "lab": metadata["lab"]},
                    ),
                ),
                metadata=metadata,
            ),
        )
