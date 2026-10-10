"""Network-free redaction regressions for the R02 Chrome network audit."""
from __future__ import annotations

import json
import unittest

from tools.audit_r02_pixorac_browser import classify_resource, summarize_browser


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


if __name__ == "__main__":
    unittest.main()
