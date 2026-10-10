"""Conservative, read-only LG715575610 v360.diamonds audit contracts."""
import base64
import json
import unittest

from diamond_retrieval.protocols import HttpResponse

from tools.audit_v360_diamonds_reference import (
    VIEWER, assert_source_pinned, categorize, sanitized_url,
    audit_exact_certificate_lookup, audit_indexed_proxy,
)


class V360ExactAuditTests(unittest.TestCase):
    def test_pinned_reference_is_unchanged(self):
        assert_source_pinned()
        self.assertEqual(
            VIEWER,
            "https://v360.diamonds/c/22971515-3849-41bb-ae0a-3bb31e3a7ae9?m=i&a=FA-121",
        )

    def test_no_query_parameters_or_opaque_path_values_in_logs(self):
        info = sanitized_url(VIEWER)
        self.assertEqual(info["host"], "v360.diamonds")
        self.assertEqual(info["query_keys"], ["a", "m"])
        self.assertNotIn("FA-121", str(info))
        self.assertNotIn("22971515-", str(info))
        self.assertNotIn("secret", str(sanitized_url(
            "https://cdn.example.test/opaque/private-token.jpg?token=secret"
        )))

    def test_html_is_not_360_and_access_block_is_explicit(self):
        for status in (401, 402, 403, 429):
            self.assertEqual(categorize(status, "text/html", b"error"), "access_blocked")
        self.assertEqual(
            categorize(200, "text/html", b"<!doctype html><html></html>"),
            "html_not_motion",
        )
        self.assertEqual(categorize(200, "video/mp4", b"<html>fake"), "html_not_motion")
        self.assertEqual(categorize(404, "video/mp4", b""), "not_available")
        self.assertEqual(categorize(200, "video/mp4", b"fake"), "unknown_not_proven_motion")

    def test_exact_certificate_lookup_never_trusts_other_report(self):
        class FakeClient:
            def __init__(self, payload):
                self.payload = payload
            def post(self, url, *, timeout, content, headers):
                self_url = "https://g.nivoda.com/graphql-public-loupe360"
                if url != self_url:
                    raise AssertionError("unexpected endpoint")
                assert json.loads(content)["variables"] == {"cert": "LG715575610"}
                return HttpResponse(200, url, {"Content-Type": "application/json"}, self.payload)
        def record(report):
            return json.dumps({"data": {"certificate_by_cert_number": {
                "certNumber": report, "lab": "IGI", "image": None, "video": None,
                "v360": {"url": VIEWER, "frame_count": 256, "top_index": 121}
            }}}).encode()
        valid = audit_exact_certificate_lookup(FakeClient(record("LG715575610")))
        self.assertEqual(valid["outcome"], "exact_provider_report")
        self.assertFalse(valid["v360"]["direct_video_url"])
        self.assertNotIn("FA-121", str(valid))
        other = audit_exact_certificate_lookup(FakeClient(record("LG000000000")))
        self.assertEqual(other["outcome"], "identity_conflict")
        self.assertNotIn("v360", other)

    def test_indexed_proxy_requires_exact_igi_and_actual_frames(self):
        root = ("https://assets-images.pixorac.com/"
                + base64.urlsafe_b64encode(VIEWER.encode()).decode().rstrip("="))
        class FakeClient:
            def __init__(self, report="LG715575610", source=root):
                self.report, self.source, self.get_calls = report, source, []
            def post(self, url, *, timeout, content, headers):
                obj = {"data": {"certificate_by_cert_number": {
                    "certNumber": self.report, "lab": "IGI",
                    "v360": {"url": self.source, "frame_count": 256, "top_index": "212"}
                }}}
                return HttpResponse(200, url, {}, json.dumps(obj).encode())
            def get(self, url, *, timeout, headers=None):
                self.get_calls.append(url)
                return HttpResponse(404, url, {}, b"not found")
        wrong_report = FakeClient(report="LG000000000")
        self.assertEqual(audit_indexed_proxy(wrong_report)["outcome"], "identity_conflict")
        self.assertEqual(wrong_report.get_calls, [])
        wrong_viewer = FakeClient(source="https://assets-images.pixorac.com/"
            + base64.urlsafe_b64encode(b"https://v360.diamonds/c/other?m=i&a=FA-121").decode().rstrip("="))
        self.assertEqual(audit_indexed_proxy(wrong_viewer)["outcome"], "proxy_source_mismatch")
        self.assertEqual(wrong_viewer.get_calls, [])
        missing = FakeClient()
        result = audit_indexed_proxy(missing)
        self.assertEqual((result["outcome"], result["failed_index"]), ("frame_unavailable", 0))
        self.assertEqual(missing.get_calls, [root + "/0.jpg"])

    def test_valid_media_magic_is_not_confused_with_html(self):
        self.assertEqual(categorize(200, "image/jpeg", b"\xff\xd8\xffjpeg"), "jpeg")
        self.assertEqual(
            categorize(200, "video/mp4", b"\x00\x00\x00\x18ftypisom"),
            "mp4",
        )


if __name__ == "__main__":
    unittest.main()
