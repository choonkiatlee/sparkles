"""R03 source-pinned non-certificate proxy recovery safety contracts."""
from __future__ import annotations

import json
import unittest

from diamond_retrieval import HttpResponse, retrieve_reference_media
from diamond_retrieval.loupe360_proxy import Loupe360ProxyRotationDownloader
from diamond_retrieval.models import ROTATION, EvidenceReference, ProvenanceStep
from diamond_retrieval.opaque_loupe_viewer import (
    R03_REFERENCE_ID, R03_PROXY_ROOT, R03_VIEWER,
    PinnedOpaqueLoupeViewerResolver,
)
from tests.test_loupe360_proxy_motion import frame

SOURCES = [{
    "kind": "viewer", "provider": "loupe360",
    "status": "linked_unverified", "url": R03_VIEWER,
}]
ENDPOINT = "https://g.nivoda.com/graphql-public-loupe360"


class FakeHttp:
    def __init__(self, *, proxy=R03_PROXY_ROOT, count=256, top=None, missing=None):
        self.metadata = json.dumps({"data": {"certificate_by_cert_number": {
            # Provider fields do not certify that the old PriceScope stone is
            # the same physical stone. Never import these into curated identity.
            "certNumber": "NOT-A-VERIFIED-REFERENCE",
            "lab": "IGI",
            "v360": {"url": proxy, "frame_count": count, "top_index": top},
        }}}).encode()
        self.missing = missing
        self.get_calls = []
        self.post_calls = []

    def post(self, url, *, timeout, content, headers):
        self.post_calls.append((url, json.loads(content)))
        return HttpResponse(200, url, {"Content-Type": "application/json"}, self.metadata)

    def get(self, url, *, timeout, headers=None):
        self.get_calls.append(url)
        if url.startswith(R03_PROXY_ROOT + "/") and url.endswith(".jpg"):
            index = int(url[len(R03_PROXY_ROOT) + 1:-4])
            if 0 <= index < 256 and index != self.missing:
                return HttpResponse(200, url, {"Content-Type": "image/jpeg"}, frame(index))
        return HttpResponse(404, url, {}, b"missing")


class R03PinnedProxyTests(unittest.TestCase):
    def test_source_linked_256_jpegs_without_fabricated_certificate_or_orientation(self):
        http = FakeHttp()
        result = retrieve_reference_media(R03_REFERENCE_ID, media_sources=SOURCES, http_client=http)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(len({x.sha256 for x in result.rotations[0].frames}), 256)
        self.assertIsNone(result.metadata.lab)
        self.assertIsNone(result.metadata.report_number)
        self.assertIsNone(result.rotations[0].face_up_hint)
        self.assertFalse(result.rotations[0].metadata["supplier_original_bytes_verified"])
        self.assertEqual(result.rotations[0].metadata["source_transport"],
                         "pinned_unverified_viewer_indexed_proxy_jpeg")
        self.assertTrue(any(x.source == "loupe360_pinned_exact_viewer_proxy"
                            for x in result.rotations[0].provenance))
        self.assertEqual(len(http.get_calls), 256)
        self.assertEqual(http.post_calls[0][1]["variables"]["cert"], "636493231")

    def test_mismatched_proxy_metadata_must_not_download(self):
        for kwargs in (
            {"proxy": "https://assets-images.pixorac.com/other"},
            {"count": 255},
            {"count": True},
        ):
            with self.subTest(kwargs=kwargs):
                http = FakeHttp(**kwargs)
                result = retrieve_reference_media(
                    R03_REFERENCE_ID, media_sources=SOURCES, http_client=http)
                self.assertFalse(result.rotations)
                self.assertFalse(http.get_calls)

    def test_missing_frame_aborts_without_partial_publication(self):
        http = FakeHttp(missing=47)
        result = retrieve_reference_media(R03_REFERENCE_ID, media_sources=SOURCES, http_client=http)
        self.assertFalse(result.rotations)
        self.assertEqual(len(http.get_calls), 48)

    def test_other_unverified_numeric_viewers_remain_unsupported(self):
        http = FakeHttp()
        other = [{"kind": "viewer", "provider": "loupe360", "status": "linked_unverified",
                  "url": "https://loupe360.com/diamond/999999999"}]
        result = retrieve_reference_media("ps285166-r09", media_sources=other, http_client=http)
        self.assertFalse(result.rotations)
        self.assertFalse(http.post_calls)
        self.assertFalse(http.get_calls)

    def test_reject_ad_hoc_proxy_reference_or_wrong_curated_source(self):
        http = FakeHttp()
        downloader = Loupe360ProxyRotationDownloader(http)
        for spoof in (
            EvidenceReference(
                identifier="spoof", kind=ROTATION,
                retrieval_key=R03_PROXY_ROOT, locator=R03_PROXY_ROOT,
                provenance=(),
                metadata={"loupe360_proxy_exact_viewer": True, "reference_id": R03_REFERENCE_ID,
                          "loupe360_viewer_source": R03_VIEWER, "identity_status": "unverified",
                          "supplier_frame_count": 256, "supplier_top_index": None},
            ),
            EvidenceReference(
                identifier="spoof", kind=ROTATION,
                retrieval_key=R03_PROXY_ROOT, locator=R03_PROXY_ROOT,
                provenance=(ProvenanceStep("loupe360_pinned_exact_viewer_proxy",
                                           "https://loupe360.com/diamond/999"),),
                metadata={"loupe360_proxy_exact_viewer": True, "reference_id": R03_REFERENCE_ID,
                          "loupe360_viewer_source": R03_VIEWER, "identity_status": "unverified",
                          "supplier_frame_count": 256, "supplier_top_index": None},
            ),
        ):
            self.assertFalse(downloader.supports(spoof))
        self.assertEqual(http.get_calls, [])

    def test_wrong_source_identity_cannot_invoke_pinned_resolver(self):
        resolver = PinnedOpaqueLoupeViewerResolver(FakeHttp())
        ref = EvidenceReference(
            identifier="other", kind=ROTATION, retrieval_key=R03_VIEWER,
            locator=R03_VIEWER,
            provenance=(ProvenanceStep(
                "reference_media_source", R03_VIEWER, {"provider": "loupe360"}),),
            metadata={"reference_id": "ps285166-r09"},
        )
        self.assertFalse(resolver.supports(ref))


if __name__ == "__main__":
    unittest.main()
