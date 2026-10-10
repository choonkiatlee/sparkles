"""Offline safety tests for exact R08/R11 Workshop audit and bootstrap fallback."""
from __future__ import annotations

import unittest

from diamond_retrieval import HttpResponse, ProgressiveRotationProcessor
from diamond_retrieval.motion_sources import WorkshopRotationDownloader
from tests.test_diamond_retrieval_motion import (
    AUDITS, FakeHttpClient, _progressive_source_responses, _reference,
)
from tools.audit_workshop_references import EXACT, audit_one, checked_source


class WorkshopAuditTests(unittest.TestCase):
    def test_accepted_sources_are_exact_and_keep_report_identity(self):
        for reference_id in EXACT:
            with self.subTest(reference_id=reference_id):
                ref, root = checked_source(reference_id)
                self.assertEqual(ref.identifier, reference_id)
                self.assertTrue(root.startswith("https://data1.360view.link/data/1/imaged/"))
                self.assertEqual(
                    WorkshopRotationDownloader(None)._source(ref)[2],
                    root + "/0.json?version=",
                )

    def test_r08_bare_bootstrap_fallback_recovers_all_original_frames(self):
        ref, root = checked_source("ps285166-r08")
        data = _progressive_source_responses(AUDITS[1], root, version=2)
        data[root + "/0.json"] = data.pop(root + "/0.json?version=")
        http = FakeHttpClient(data)
        output = audit_one(ref.identifier, http=http)
        self.assertEqual(output["bootstrap_variant"], "bare_bootstrap")
        self.assertEqual(output["result"], "verified_256_original_frames")
        self.assertEqual(output["frame_count"], 256)
        self.assertEqual(output["dimensions"], [8, 8])
        self.assertEqual(
            http.calls[:4],
            [root + "/0.json?version=", root + "/0.json",
             root + "/0.json?version=", root + "/0.json"],
        )

    def test_r11_normal_bootstrap_recovers_without_fallback(self):
        ref, root = checked_source("ps285166-r11")
        http = FakeHttpClient(_progressive_source_responses(AUDITS[1], root, version=2))
        result = audit_one(ref.identifier, http=http)
        self.assertEqual(result["result"], "verified_256_original_frames")
        self.assertEqual(result["bootstrap_variant"], "empty_version_query")
        self.assertEqual(result["frame_count"], 256)
        self.assertNotIn(root + "/0.json", http.calls)

    def test_both_known_bootstrap_missing_is_not_synthetic_motion(self):
        ref, root = checked_source("ps285166-r08")
        http = FakeHttpClient({})
        result = audit_one(ref.identifier, http=http)
        self.assertEqual(result["result"], "both_known_bootstrap_variants_404")
        self.assertEqual(http.calls, [root + "/0.json?version=", root + "/0.json"])
        self.assertNotIn("frame_count", result)

    def test_forbidden_does_not_try_other_bootstrap_or_retry(self):
        ref, root = checked_source("ps285166-r11")

        class Forbidden(FakeHttpClient):
            def get(self, url, *, timeout):
                self.calls.append(url)
                return HttpResponse(403, url, {}, b"Forbidden")

        http = Forbidden({})
        result = audit_one(ref.identifier, http=http)
        self.assertEqual(result["result"], "source_forbidden")
        self.assertEqual(http.calls, [root + "/0.json?version="])

    def test_batch_missing_never_claims_256_frames(self):
        ref, root = checked_source("ps285166-r11")
        data = _progressive_source_responses(AUDITS[1], root, version=1)
        del data[root + "/4.json?version=1"]
        http = FakeHttpClient(data)
        result = audit_one(ref.identifier, http=http)
        self.assertEqual(result["result"], "complete_rotation_failed")
        self.assertEqual(result["failure_type"], "MissingEvidenceError")
        self.assertNotIn("frame_count", result)

    def test_unsupported_url_is_rejected_by_supplier_adapter(self):
        a = WorkshopRotationDownloader(FakeHttpClient({}))
        for url in (
            "https://workshop.360view.link/view/../../secret",
            "http://workshop.360view.link/view/0410243-YDC-13680",
            "https://127.0.0.1/view/0410243-YDC-13680",
        ):
            self.assertFalse(a.supports(_reference("workshop", url)))


if __name__ == "__main__":
    unittest.main()
