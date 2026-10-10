"""Network-free guardrails for the non-publishing R12 source audit."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.audit_r12_reference import (
    REF, SOURCE, CANDIDATES, check_curated_source,
    exact_igi_candidate, main,
)


class R12AuditTests(unittest.TestCase):
    def test_curated_source_is_still_unverified(self):
        check_curated_source()
        self.assertEqual(CANDIDATES, ("LG524247250", "524247250"))
        self.assertEqual(SOURCE, "https://loupe360.com/diamond/LG524247250")

    def test_requires_exact_igi_provider_report_and_media(self):
        valid = {
            "status": "record_returned", "reference": REF,
            "requested": "LG524247250", "returned_report": "LG524247250",
            "returned_lab": "IGI", "expected_lab_match": True,
            "v360_present": True, "video_present": False,
        }
        self.assertTrue(exact_igi_candidate(valid))
        for changed in (
            {"returned_report": "LG999999999"},
            {"returned_lab": "GIA"},
            {"requested": "LG999999999"},
            {"status": "not_found"},
            {"v360_present": False},
            {"expected_lab_match": False},
        ):
            with self.subTest(changed=changed):
                candidate = {**valid, **changed}
                if changed == {"v360_present": False}:
                    candidate["video_present"] = False
                self.assertFalse(exact_igi_candidate(candidate))

    def test_numeric_exact_report_is_a_distinct_eligible_probe(self):
        self.assertTrue(exact_igi_candidate({
            "status": "record_returned", "requested": "524247250",
            "returned_report": "524247250", "returned_lab": "IGI",
            "expected_lab_match": True, "video_present": True,
        }))

    def test_media_is_not_attempted_after_identity_mismatch(self):
        with patch("tools.audit_r12_reference.lookup", return_value=[{
            "status": "record_returned", "requested": "LG524247250",
            "returned_report": "LG000000000", "returned_lab": "IGI",
            "expected_lab_match": True, "v360_present": True,
        }]), patch("tools.audit_r12_reference.media_dry_run") as download:
            self.assertEqual(main(["--media"]), 0)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
