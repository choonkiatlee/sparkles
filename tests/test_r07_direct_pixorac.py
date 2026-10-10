"""Fail-closed direct Pixorac cache *research* tests for R07."""
from __future__ import annotations

import hashlib
import io
import unittest
from urllib.parse import urlsplit
from PIL import Image

from diamond_retrieval.protocols import HttpResponse
from tools.audit_r07_direct_pixorac import (
    REF, VIEWER, check_rotation, encoded_root, exact_serializations,
    pinned_source, probe,
)


def make_jpeg(index):
    img = Image.new("RGB", (16, 16), (index % 255, index * 17 % 255, index * 31 % 255))
    img.putpixel((index % 16, index // 16), (255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    return out.getvalue()


class FakeHttp:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def get(self, url, *, timeout, headers=None):
        self.calls.append(url)
        code, content = self.responses.get(url, (404, b"missing"))
        return HttpResponse(code, url, {"Content-Type": "image/jpeg"}, content)


class DirectR07PixoracTests(unittest.TestCase):
    def test_original_issuer_identity_and_exact_buyer_viewer(self):
        self.assertEqual(pinned_source(), VIEWER)
        variants = exact_serializations()
        self.assertEqual([v for v, _ in variants], ["buyer_exact", "query_order_equivalent"])
        for _, value in variants:
            self.assertEqual(urlsplit(value).hostname, "v360.diamonds")
            self.assertEqual(urlsplit(value).path, urlsplit(VIEWER).path)
            self.assertIn("625406458", value)
        self.assertEqual(len({encoded_root(v) for _, v in variants}), 2)

    def test_empty_cache_proves_nothing_without_touching_origin(self):
        fake = FakeHttp()
        result = probe(fake)
        self.assertEqual(result["reference"], REF)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual([x["outcome"] for x in result["candidates"]],
                         ["frame_unavailable", "frame_unavailable"])
        self.assertTrue(all(x["failed_index"] == 0 for x in result["candidates"]))
        self.assertTrue(all(x["frame_http"] == 404 for x in result["candidates"]))
        self.assertTrue(all(urlsplit(v).hostname == "assets-images.pixorac.com"
                            for v in fake.calls))
        self.assertNotIn(VIEWER, str(result))
        self.assertFalse(any("frame_count" in x for x in result["candidates"]))

    def test_complete_distinct_jpegs_require_all_256_actual_images(self):
        root = encoded_root(VIEWER)
        responses = {
            f"{root}/{i}.jpg": (200, make_jpeg(i))
            for i in range(256)
        }
        result = check_rotation(FakeHttp(responses), variant="buyer_exact", viewer=VIEWER)
        self.assertEqual(result["outcome"], "complete_unattributed_proxy_rotation")
        self.assertEqual(result["frame_count"], 256)
        self.assertEqual(result["distinct_frame_sha256"], 256)
        self.assertEqual(list(result["dimensions"]), [16, 16])
        self.assertEqual(result["first_frame_sha256"], hashlib.sha256(make_jpeg(0)).hexdigest())
        self.assertFalse(result["source_from_verified_provider"])

    def test_missing_frame_does_not_accept_incomplete_rotation(self):
        root = encoded_root(VIEWER)
        responses = {
            f"{root}/{i}.jpg": (200, make_jpeg(i))
            for i in range(255)
        }
        response = check_rotation(FakeHttp(responses), variant="buyer_exact", viewer=VIEWER)
        self.assertEqual(response["outcome"], "frame_unavailable")
        self.assertEqual(response["failed_index"], 255)
        self.assertNotIn("frame_count", response)

    def test_html_does_not_masquerade_as_an_image(self):
        url = encoded_root(VIEWER) + "/0.jpg"
        resp = check_rotation(FakeHttp({url: (200, b"<html>no</html>")}),
                              variant="buyer_exact", viewer=VIEWER)
        self.assertEqual((resp["outcome"], resp["failed_index"]), ("invalid_jpeg", 0))


if __name__ == "__main__":
    unittest.main()
