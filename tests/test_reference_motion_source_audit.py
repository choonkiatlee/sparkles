"""Network-free, fail-closed R07/R23 source audit tests."""
import json
import unittest

from diamond_retrieval.protocols import HttpResponse
from tools.reference_motion_source_audit import (
    R07_VIEWER, R23_ROOT, audit_r07, audit_r23,
    classify_d360_preflight, response_shape,
)


class FakeHttp:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
    def get(self, url, *, timeout):
        self.calls.append(url)
        value = self.responses.get(url, (404, b"missing", "text/plain"))
        status, payload, typ = value
        return HttpResponse(status, url, {"Content-Type": typ}, payload)


def reply(name, status, content, typ="application/json"):
    return HttpResponse(status, R23_ROOT + "/" + name, {"Content-Type": typ}, content)


class ReferenceOriginalAuditTests(unittest.TestCase):
    def test_r07_402_blocks_without_following_other_urls(self):
        http = FakeHttp({R07_VIEWER: (402, b"<html><script>secret</script></html>", "text/html")})
        out = audit_r07(http)
        self.assertEqual(out[0]["state"], "http_402_blocked")
        self.assertEqual(out[0]["http"], 402)
        self.assertEqual(http.calls, [R07_VIEWER])
        self.assertNotIn("secret", str(out))

    def test_r07_html_200_is_not_motion(self):
        http = FakeHttp({R07_VIEWER: (200, b"<html>viewer</html>", "text/html")})
        self.assertEqual(audit_r07(http)[0]["state"], "page_not_original_media")

    def test_response_shape_no_html_content(self):
        sample = reply("0.json", 200, b"top secret", "text/plain")
        out = response_shape(sample)
        self.assertEqual(out["http"], 200)
        self.assertNotIn("top secret", str(out))

    def test_r23_missing_metadata_stops_cleanly(self):
        http = FakeHttp({})
        result = audit_r23(http)
        self.assertEqual(result[-1]["preflight"], "missing_source")
        self.assertEqual(result[-1]["first_blocker"], "metadata.json")
        self.assertEqual(http.calls, [R23_ROOT + "/" + p for p in (
            "metadata.json", "0.json", "still.jpg",
        )])

    def test_r23_invalid_bootstrap_identifies_stage(self):
        refs = {
            "metadata.json": reply("metadata.json", 200, b'{}'),
            "0.json": reply("0.json", 200, b"not json"),
            "still.jpg": reply("still.jpg", 200, b"\xff\xd8\xff"),
        }
        self.assertEqual(classify_d360_preflight(refs)["preflight"], "invalid_bootstrap_json")
        refs["0.json"] = reply("0.json", 200, json.dumps({
            "width": 778, "height": 778, "image": "aGVsbG8="
        }).encode())
        self.assertEqual(classify_d360_preflight(refs)["preflight"], "missing_scramble")

    def test_r23_invalid_scramble_never_fetches_batches(self):
        http = FakeHttp({
            R23_ROOT + "/metadata.json": (200, b'{}', "application/json"),
            R23_ROOT + "/0.json": (200, json.dumps({
                "width": 778, "height": 778,
                "scramble": "notvalid!", "image": "aGVsbG8="
            }).encode(), "application/json"),
            R23_ROOT + "/still.jpg": (200, b"\xff\xd8\xff", "image/jpeg"),
        })
        out = audit_r23(http)
        self.assertEqual(next(row["preflight"] for row in out if row["source"] == "contract"), "invalid_scramble")
        self.assertEqual(http.calls, [R23_ROOT + "/" + p for p in (
            "metadata.json", "0.json", "still.jpg",
        )])
        self.assertEqual(len(out), 6)


if __name__ == "__main__":
    unittest.main()
