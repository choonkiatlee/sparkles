"""R07 source-only auditor must never attach mismatched or incomplete motion."""
import base64
import json
import unittest

from diamond_retrieval.models import HttpResponse
from tools.audit_r07_v360_proxy import REF, REPORT, VIEWER, probe, verify_manifest

ENDPOINT = "https://g.nivoda.com/graphql-public-loupe360"
ROOT = "https://assets-images.pixorac.com/" + base64.urlsafe_b64encode(VIEWER.encode()).decode().rstrip("=")


class FakeHTTP:
    def __init__(self, *, report=REPORT, lab="IGI", root=ROOT,
                 count=256, top="70", missing=False):
        self.report, self.lab, self.root = report, lab, root
        self.count, self.top, self.missing = count, top, missing
        self.calls = []

    def post(self, url, *, timeout, content, headers):
        self.calls.append(("POST", url))
        assert url == ENDPOINT
        assert json.loads(content)["variables"] == {"cert": REPORT}
        data = {"data": {"certificate_by_cert_number": {
            "certNumber": self.report, "lab": self.lab, "image": None,
            "video": None,
            "v360": {"url": self.root, "frame_count": self.count, "top_index": self.top},
        }}}
        return HttpResponse(200, url, {"Content-Type": "application/json"}, json.dumps(data).encode())

    def get(self, url, *, timeout, headers=None):
        self.calls.append(("GET", url))
        return HttpResponse(404, url, {}, b"not available")


class R07ExactSourceTests(unittest.TestCase):
    def test_manifest_pin_includes_still_and_reported_lab(self):
        data = verify_manifest()
        self.assertEqual(data["identity"]["status"], "reported")
        self.assertTrue(any(x["kind"] == "still" and x["status"] == "success"
                            for x in data["evidence"]))

    def test_wrong_lab_or_report_never_attempts_media(self):
        for options in ({"report": "LG000000000"}, {"lab": "GIA"}):
            with self.subTest(options=options):
                http = FakeHTTP(**options)
                r = probe(http)
                self.assertEqual(r["outcome"], "lab_or_report_conflict")
                self.assertEqual(len(http.calls), 1)

    def test_wrong_viewer_or_invalid_count_or_top_never_fetches_frames(self):
        wrong = "https://assets-images.pixorac.com/" + base64.urlsafe_b64encode(
            b"https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?m=i&a=other"
        ).decode().rstrip("=")
        for options, expected in (
            ({"root": wrong}, "different_viewer_not_authorized"),
            ({"root": "https://evil.example.test/foo"}, "no_eligible_pixorac_wrapper"),
            ({"count": 64}, "unsupported_frame_count"),
            ({"top": None}, "invalid_face_up_index"),
            ({"top": 256}, "invalid_face_up_index"),
        ):
            with self.subTest(options=options):
                http = FakeHTTP(**options)
                r = probe(http)
                self.assertEqual(r["outcome"], expected)
                self.assertEqual(len(http.calls), 1)
                self.assertNotIn("proxy_root_sha256", r if expected == "different_viewer_not_authorized" else {})

    def test_exact_viewer_does_not_claim_motion_when_first_frame_missing(self):
        http = FakeHTTP()
        result = probe(http)
        self.assertEqual(result["outcome"], "no_validated_motion")
        self.assertEqual(result["exact_viewer_matched"], True)
        self.assertEqual(result["declared_frames"], 256)
        self.assertFalse(any(at["status"] == "success" and at["kind"] == "rotation"
                             for at in result["attempts"]))
        self.assertIn(("GET", ROOT + "/0.jpg"), http.calls)
        self.assertNotIn(("GET", VIEWER), http.calls)


if __name__ == "__main__":
    unittest.main()
