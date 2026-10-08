"""Certified diamond primary key. Never use retailer listing/SKU as identity."""
from __future__ import annotations

import re

from .models import CatalogueError

LAB_ALIASES = {
    "IGI": "IGI",
    "INTERNATIONAL GEMOLOGICAL INSTITUTE": "IGI",
    "GIA": "GIA",
    "GEMOLOGICAL INSTITUTE OF AMERICA": "GIA",
}


def normalize_identity(lab: str | None, report_number: str | None) -> tuple[str, str]:
    if not lab or not report_number:
        raise CatalogueError("Certified lab and full report number are required")
    lab_text = re.sub(r"\s+", " ", str(lab).strip().upper())
    lab_text = LAB_ALIASES.get(lab_text, lab_text)
    report = re.sub(r"[\s-]", "", str(report_number).upper())
    # Restrict primary-key canonicalisation: don't strip meaningful punctuation.
    if not re.fullmatch(r"[A-Z0-9]+", lab_text) or not re.fullmatch(r"[A-Z0-9]+", report):
        raise CatalogueError("Unsupported characters in certified identity")
    if not any(c.isdigit() for c in report):
        raise CatalogueError("Full certified report number must contain digits")
    return lab_text, report


def diamond_id(lab: str | None, report_number: str | None) -> str:
    normalized_lab, normalized_report = normalize_identity(lab, report_number)
    return f"{normalized_lab.lower()}-{normalized_report.lower()}"
