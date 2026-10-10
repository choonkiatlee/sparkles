#!/usr/bin/env python3
"""Read-only exact IGI PDF attempt for R01's unresolved DreamStone SKU.

Only the known IGI endpoint and the single Nivoda-matched report candidate
are requested. No content is saved, sent to other sites or used to mutate
reference identity. Failure/missing data is an inconclusive result, not proof.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from pypdf import PdfReader

REPORT = "LG566392177"
PDF_URL = "https://api.igi.org/viewpdf.php?r=LG566392177"
LIMIT = 4 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def extract_matches(text: str) -> dict:
    normalized = re.sub(r"\s+", " ", text).upper()
    compact = re.sub(r"\s+", "", text).upper()
    return {
        "report_present": REPORT in compact,
        "weight_1_97_present": bool(re.search(r"(?<!\d)1\.97\s*(?:CT|CARAT|\b)", normalized)),
        "asscher_description_present": bool(re.search(r"\bASSCHER\b|SQUARE\s+EMERALD", normalized)),
        "color_d_label_present": bool(re.search(r"COL(?:OR|OUR)(?:\s+GRADE)?\s*[:\-]?\s*D\b", normalized)),
        "clarity_vs1_label_present": bool(re.search(r"CLARITY(?:\s+GRADE)?\s*[:\-]?\s*VS\s*1\b", normalized)),
    }


def audit() -> dict:
    result = {
        "reference_id": "ps285166-r01",
        "candidate": REPORT,
        "source": "api.igi.org exact-report public PDF endpoint",
        "pdf_stored": False,
        "identity_changed": False,
    }
    request = urllib.request.Request(
        PDF_URL, headers={"Accept": "application/pdf", "User-Agent": "Sparkles-R01-audit/1"}
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            result["status"] = response.status
            data = response.read(LIMIT + 1)
            result["byte_count"] = len(data)
    except urllib.error.HTTPError as error:
        result["status"] = error.code
        result["outcome"] = "unavailable_or_redirect"
        return result
    except Exception as error:
        result["outcome"] = "transport_error"
        result["error_type"] = type(error).__name__
        return result

    if len(data) > LIMIT or not data.startswith(b"%PDF-"):
        result["outcome"] = "not_a_bounded_pdf"
        return result
    result["sha256"] = hashlib.sha256(data).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if len(reader.pages) > 5:
            result["outcome"] = "too_many_pages"
            return result
        text = " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception as error:
        result["outcome"] = "pdf_parse_error"
        result["error_type"] = type(error).__name__
        return result
    result["extracted_characters"] = len(text)
    result["matches"] = extract_matches(text)
    result["outcome"] = (
        "matching_igi_document"
        if all(result["matches"].values())
        else "partial_or_unreadable_igi_document"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2, sort_keys=True)
    args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
