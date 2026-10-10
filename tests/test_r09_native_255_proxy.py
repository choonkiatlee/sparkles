"""Native 255-frame R09 Pixorac support; no padding or certificate invention."""
from __future__ import annotations

import json
import unittest

from diamond_catalogue.reference_publish import plan_reference_media
from diamond_catalogue.models import CatalogueError
from diamond_retrieval import HttpResponse, retrieve_reference_media
from diamond_retrieval.opaque_loupe_viewer import (
    R09_REFERENCE_ID, R09_VIEWER, R09_PROXY_ROOT,
)
from tests.test_loupe360_proxy_motion import frame

ENDPOINT = "https://g.nivoda.com/graphql-public-loupe360"
SOURCES = [{
    "kind": "viewer", "provider": "loupe360",
    "status": "linked_unverified", "url": R09_VIEWER,
}]


class FakeHttp:
    def __init__(self, *, count=255, proxy=R09_PROXY_ROOT, missing=None, extra_255=False):
        self.body = json.dumps({"data": {"certificate_by_cert_number": {
            "certNumber": "NOT-INDEPENDENTLY-VERIFIED", "lab": "IGI",
            "v360": {"url": proxy, "frame_count": count, "top_index": None},
        }}}).encode()
        self.missing = missing
        self.extra_255 = extra_255
        self.get_calls = []
        self.post_calls = []

    def post(self, url, *, timeout, content, headers):
        self.post_calls.append((url, json.loads(content)))
        return HttpResponse(200, url, {"Content-Type": "application/json"}, self.body)

    def get(self, url, *, timeout, headers=None):
        self.get_calls.append(url)
        if url.startswith(R09_PROXY_ROOT + "/") and url.endswith(".jpg"):
            index = int(url[len(R09_PROXY_ROOT) + 1:-4])
            if 0 <= index < 255 and index != self.missing:
                return HttpResponse(200, url, {"Content-Type": "image/jpeg"}, frame(index))
            if index == 255 and self.extra_255:
                return HttpResponse(200, url, {"Content-Type": "image/jpeg"}, frame(255))
        return HttpResponse(404, url, {}, b"missing")


class R09Native255Tests(unittest.TestCase):
    def test_exact_complete_native_255_no_synthetic_frame_or_certificate(self):
        client = FakeHttp()
        result = retrieve_reference_media(
            R09_REFERENCE_ID, media_sources=SOURCES, http_client=client)
        self.assertEqual(len(result.rotations), 1)
        rotation = result.rotations[0]
        self.assertEqual(len(rotation.frames), 255)
        self.assertEqual([x.source_index for x in rotation.frames], list(range(255)))
        self.assertEqual(len({x.sha256 for x in rotation.frames}), 255)
        self.assertIsNone(rotation.face_up_hint)
        self.assertIsNone(result.metadata.lab)
        self.assertIsNone(result.metadata.report_number)
        self.assertFalse(rotation.metadata["supplier_original_bytes_verified"])
        self.assertEqual(rotation.metadata["frame_count"], 255)
        self.assertEqual(rotation.metadata["ordering"],
                         "proxy indexed source positions 0..254")
        self.assertEqual(len(client.get_calls), 255)
        self.assertEqual(client.get_calls[-1], R09_PROXY_ROOT + "/254.jpg")
        self.assertEqual(client.post_calls[0][1]["variables"]["cert"], "1498922544")
        plan = plan_reference_media(result, R09_REFERENCE_ID)
        self.assertEqual(len(plan.manifest["evidence"][0]["frames"]), 255)
        self.assertEqual(len(plan.assets), 255)
        with self.assertRaises(CatalogueError):
            plan_reference_media(result, "ps285166-r03")

    def test_missing_native_frame_fails_closed(self):
        client = FakeHttp(missing=188)
        result = retrieve_reference_media(
            R09_REFERENCE_ID, media_sources=SOURCES, http_client=client)
        self.assertFalse(result.rotations)
        self.assertEqual(len(client.get_calls), 189)

    def test_exact_count_and_url_are_required(self):
        for kwargs in (
            {"count": 256}, {"count": 254},
            {"proxy": "https://assets-images.pixorac.com/different-stone"},
        ):
            with self.subTest(kwargs=kwargs):
                client = FakeHttp(**kwargs)
                result = retrieve_reference_media(
                    R09_REFERENCE_ID, media_sources=SOURCES, http_client=client)
                self.assertFalse(result.rotations)
                self.assertFalse(client.get_calls)

    def test_no_padding_even_when_index_255_happens_to_exist(self):
        client = FakeHttp(extra_255=True)
        result = retrieve_reference_media(
            R09_REFERENCE_ID, media_sources=SOURCES, http_client=client)
        self.assertEqual(len(result.rotations[0].frames), 255)
        self.assertNotIn(R09_PROXY_ROOT + "/255.jpg", client.get_calls)


if __name__ == "__main__":
    unittest.main()
