"""Network-free guards for exact-report R02 Pixorac read-only audit."""
from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from tools.audit_r02_pixorac import (
    LAB, REPORT, REFERENCE, audit, proxy_source, report_matches, trust_anchor,
)


def wrapped(url: str) -> str:
    token = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return "https://assets-images.pixorac.com/" + token


class R02PixoracAuditTests(unittest.TestCase):
    def test_curated_record_remains_unchanged_and_still_only(self):
        trust_anchor()
        self.assertEqual(REFERENCE, "ps285166-r02")
        self.assertEqual(REPORT, "LG634479985")

    def test_lab_and_report_must_match_exactly(self):
        good = {"certNumber": REPORT, "lab": LAB}
        self.assertTrue(report_matches(good))
        for bad in (
            None, {}, {"certNumber": REPORT, "lab": "GIA"},
            {"certNumber": "634479985", "lab": LAB},
            {"certNumber": "LG634479986", "lab": LAB},
        ):
            self.assertFalse(report_matches(bad))

    def test_only_exact_pixorac_encoded_known_supplier_and_full_metadata(self):
        generic = "https://mediassests.s3.amazonaws.com/V360/Vision360.html"
        specific = generic + "?d=verified-supplier-token_12"
        for supplier, label in ((generic, "generic_no_d_key"),
                                (specific, "supplied_d_key")):
            candidate = {
                "url": wrapped(supplier),
                "frame_count": 256, "top_index": 42,
            }
            self.assertEqual(proxy_source(candidate), (candidate["url"], 42, label))

        good = {"url": wrapped(generic), "frame_count": 256, "top_index": 5}
        bad_variants = (
            {"url": wrapped("https://evil.example/V360/Vision360.html")},
            {"url": wrapped("http://mediassests.s3.amazonaws.com/V360/Vision360.html")},
            {"url": wrapped(generic + "?q=unreviewed")},
            {"url": "https://other.example/" + good["url"].rsplit("/", 1)[1]},
            {"url": good["url"] + "?any=thing"},
            {"url": "https://assets-images.pixorac.com/abc"},
            {"frame_count": 128}, {"frame_count": True},
            {"top_index": None}, {"top_index": 256}, {"top_index": True},
        )
        for change in bad_variants:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    proxy_source({**good, **change})

    @patch("tools.audit_r02_pixorac.verify_frames")
    @patch("tools.audit_r02_pixorac.query_record")
    def test_mismatch_or_missing_prefixed_report_never_fetches_frames(self, lookup, frames):
        for prefixed in (
            None,
            {"certNumber": "LG634479986", "lab": "IGI"},
            {"certNumber": REPORT, "lab": "GIA"},
        ):
            with self.subTest(prefixed=prefixed):
                lookup.side_effect = [None, prefixed]
                self.assertEqual(
                    audit(object())["outcome"],
                    "exact_igi_report_not_confirmed_by_provider",
                )
                frames.assert_not_called()
                frames.reset_mock()

    @patch("tools.audit_r02_pixorac.verify_frames")
    @patch("tools.audit_r02_pixorac.query_record")
    def test_exact_report_must_also_supply_eligible_cache(self, lookup, frames):
        lookup.side_effect = [None, {
            "certNumber": REPORT, "lab": LAB,
            "v360": {"url": "https://mediassests.s3.amazonaws.com/V360/Vision360.html",
                     "frame_count": 256, "top_index": 4},
        }]
        result = audit(object())
        self.assertEqual(result["outcome"], "no_eligible_exact_pixorac_cache")
        frames.assert_not_called()

    @patch("tools.audit_r02_pixorac.verify_frames")
    @patch("tools.audit_r02_pixorac.query_record")
    def test_exact_eligible_cache_only_runs_read_only_frame_audit(self, lookup, frames):
        exact = wrapped("https://mediassests.s3.amazonaws.com/V360/Vision360.html")
        lookup.side_effect = [None, {
            "certNumber": REPORT, "lab": LAB,
            "image": "https://example.org/image.jpg",
            "v360": {"url": exact, "frame_count": 256, "top_index": 7},
        }]
        frames.return_value = {"outcome": "complete_indexed_proxy_frames"}
        client = object()
        result = audit(client)
        self.assertEqual(result["outcome"], "complete_indexed_proxy_frames")
        self.assertTrue(result["exact_report_match"])
        self.assertFalse(result["publication"])
        self.assertNotIn("proxy_url", result)
        frames.assert_called_once_with(client, exact, 7)


if __name__ == "__main__":
    unittest.main()
