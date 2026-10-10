#!/usr/bin/env python3
"""Read-only, bounded source-identity diagnostic for R01 (#257 / #212).

DreamStone labels the sold 1.97ct D VS1 Asscher as IGI and gives SKU
566392177/4H566392177. The first SKU component MIGHT be its report number
but is NOT verified. Query just the two report-number spellings through the
existing public Nivoda resolver diagnostic; do not update any reference
identity, derive arbitrary media URLs, or fetch/publish asset bytes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.audit_loupe360_browser_references import query_public_record

REFERENCE_ID = "ps285166-r01"
SKU_FIRST_COMPONENT = "566392177"
# These are hypotheses, not certified identities. Never widen this set.
CANDIDATES = ("LG566392177", "566392177")


def audit(*, lookup=query_public_record) -> dict:
    results = []
    for candidate in CANDIDATES:
        # The reused diagnostic prints only bounded response/status, sanitized
        # host/path information and report/lab match booleans, not raw media URLs.
        result = lookup(candidate, extended=False)
        results.append({
            "candidate": candidate,
            "lookup": result,
            "candidate_matches_returned_report": result.get("cert_matches") is True,
            "candidate_igi_lab": str(result.get("lab") or "").strip().upper() == "IGI",
        })
    return {
        "schema": "sparkles-r01-source-audit/1",
        "reference_id": REFERENCE_ID,
        "source": "DreamStone item 566392177/4H566392177 (IGI label, sold)",
        "candidate_basis": "unverified seller SKU pattern, not an IGI report",
        "candidate_reports": results,
        "same_stone_identity_verified": False,
        "reason_unverified": (
            "A candidate Nivoda match alone cannot establish that its report "
            "belongs to the PriceScope/DreamStone 1.97ct D VS1 Asscher. "
            "Obtain matching IGI report or direct supplier proof first."
        ),
        "publishing_performed": False,
        "media_bytes_downloaded": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only R01 SKU/report candidate lookup")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, indent=2, sort_keys=True)
    args.out.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
