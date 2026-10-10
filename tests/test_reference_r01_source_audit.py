"""Network-free guards for the R01 read-only identity hypothesis audit."""
import unittest

from tools import audit_reference_r01_source as r01


class R01AuditTests(unittest.TestCase):
    def test_exact_two_sku_derived_candidates_only(self):
        seen = []

        def lookup(candidate, *, extended):
            seen.append((candidate, extended))
            return {"certificate_record": "missing"}

        result = r01.audit(lookup=lookup)
        self.assertEqual(seen, [("LG566392177", False), ("566392177", False)])
        self.assertEqual(result["reference_id"], "ps285166-r01")
        self.assertEqual(result["schema"], "sparkles-r01-source-audit/1")
        self.assertFalse(result["same_stone_identity_verified"])
        self.assertFalse(result["publishing_performed"])
        self.assertFalse(result["media_bytes_downloaded"])

    def test_matching_candidate_does_not_claim_verified_stone(self):
        def lookup(candidate, *, extended):
            return {
                "certificate_record": "returned",
                "cert_matches": True,
                "lab": "IGI",
                "v360": {"url": {"host": "workshop.360view.link", "path": "/360viewer/360view.html"},
                         "frame_count": 256},
            }

        result = r01.audit(lookup=lookup)
        for row in result["candidate_reports"]:
            self.assertTrue(row["candidate_matches_returned_report"])
            self.assertTrue(row["candidate_igi_lab"])
        self.assertFalse(result["same_stone_identity_verified"])
        self.assertFalse(result["publishing_performed"])

    def test_other_lab_or_conflicting_report_not_misrepresented(self):
        def lookup(candidate, *, extended):
            return {"cert_matches": False, "lab": "GIA", "certificate_record": "returned"}

        result = r01.audit(lookup=lookup)
        for row in result["candidate_reports"]:
            self.assertFalse(row["candidate_matches_returned_report"])
            self.assertFalse(row["candidate_igi_lab"])
        self.assertFalse(result["same_stone_identity_verified"])


if __name__ == "__main__":
    unittest.main()
