"""Network-free redaction regressions for the R02 Chrome network audit."""
from __future__ import annotations

import json
import base64
import unittest

from tools.audit_r02_pixorac_browser import browser_cache_candidate, classify_resource, summarize_browser


class BrowserAuditTests(unittest.TestCase):
    def test_sanitizes_pixorac_wrapper_tokens_and_query_strings(self):
        token = "secret_encoded_supplier_identifier"
        item = {
            "resource": {
                "host": "assets-images.pixorac.com",
                "path": "/" + token + "/194.webp",
                "has_query": True,
            },
            "status": 200,
            "mime_type": "image/webp",
        }
        result = classify_resource(item)
        self.assertEqual(result["kind"], "indexed_webp")
        self.assertEqual(result["status"], 200)
        self.assertNotIn(token, json.dumps(result))
        self.assertNotIn("path", result)

    def test_compacts_distinct_routes_without_leaking_request_paths(self):
        data = summarize_browser([
            {
                "input_route": "landing",
                "requests_total": 3,
                "relevant_requests": [
                    {"resource": {"host": "assets-images.pixorac.com",
                                  "path": "/ENCoDed/0.jpg"}, "status": 200},
                    {"resource": {"host": "loupe360.com",
                                  "path": "/diamond/SENSITIVE_TOKEN/video/500/500"},
                     "status": 200},
                ],
            },
            {"input_route": "/video/500/500", "requests_total": 1,
             "relevant_requests": [], "browser_error_type": "TimeoutException"},
        ])
        serialized = json.dumps(data)
        self.assertEqual(data["pixorac_request_total"], 1)
        self.assertEqual(len(data["routes"]), 2)
        self.assertNotIn("SENSITIVE_TOKEN", serialized)
        self.assertNotIn("ENCoDed", serialized)
        self.assertIn("assets-images.pixorac.com", serialized)


    def test_single_browser_observed_root_is_exact_and_does_not_guess_id(self):
        supplier = "https://mediassests.s3.amazonaws.com/V360/Vision360.html"
        token = base64.urlsafe_b64encode(supplier.encode()).decode().rstrip("=")
        records = [{"input_route": "landing", "relevant_requests": [
            {"resource": {"host": "assets-images.pixorac.com",
                          "path": f"/{token}/{i}.webp", "has_query": False},
             "status": 200}
            for i in (0, 1, 213)
        ]}]
        lookup = {"cert_matches": True, "lab": "IGI",
                  "v360": {"frame_count": 256, "top_index": "213"}}
        root, top, verdict = browser_cache_candidate(records, lookup)
        self.assertEqual(root, "https://assets-images.pixorac.com/" + token)
        self.assertEqual(top, 213)
        self.assertEqual(verdict["outcome"], "one_exact_browser_observed_source")
        self.assertEqual(verdict["observed_distinct_indices"], 3)
        self.assertNotIn(token, json.dumps(verdict))
        for bad in ({**lookup, "cert_matches": False},
                    {**lookup, "lab": "GIA"},
                    {**lookup, "v360": {"frame_count": 128, "top_index": 213}}):
            candidate, _, result = browser_cache_candidate(records, bad)
            self.assertIsNone(candidate)
            self.assertNotEqual(result["outcome"], "one_exact_browser_observed_source")

    def test_multiple_browser_pixorac_roots_refused(self):
        one = "https://mediassests.s3.amazonaws.com/V360/Vision360.html"
        two = one + "?d=source-ref-2"
        tokens = [base64.urlsafe_b64encode(x.encode()).decode().rstrip("=")
                  for x in (one, two)]
        records = [{"input_route": "landing", "relevant_requests": [
            {"resource": {"host": "assets-images.pixorac.com",
                          "path": f"/{token}/0.webp"}, "status": 200}
            for token in tokens
        ]}]
        lookup = {"cert_matches": True, "lab": "IGI",
                  "v360": {"frame_count": 256, "top_index": 213}}
        source, _, verdict = browser_cache_candidate(records, lookup)
        self.assertIsNone(source)
        self.assertEqual(verdict["outcome"], "ambiguous_or_absent_observed_roots")

    def test_unrecognized_pixorac_encoded_supplier_is_refused(self):
        token = base64.urlsafe_b64encode(
            b"https://unrelated.example/V360/Vision360.html").decode().rstrip("=")
        records = [{"input_route": "landing", "relevant_requests": [
            {"resource": {"host": "assets-images.pixorac.com",
                          "path": f"/{token}/1.webp"}, "status": 200}
        ]}]
        lookup = {"cert_matches": True, "lab": "IGI",
                  "v360": {"frame_count": 256, "top_index": 213}}
        source, _, verdict = browser_cache_candidate(records, lookup)
        self.assertIsNone(source)
        self.assertEqual(verdict["outcome"],
                         "observed_root_does_not_wrap_known_r02_source")


if __name__ == "__main__":
    unittest.main()
