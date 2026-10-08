import json
import unittest

from diamond_retrieval import (
    ROTATION,
    VIDEO,
    DiamondMetadata,
    EvidenceReference,
    HttpResponse,
    InvalidPayloadError,
    ListingRecord,
    ProvenanceStep,
)
from diamond_retrieval.resolvers import Loupe360CertificateResolver
from diamond_retrieval.video import DirectVideoDownloader, DirectVideoProcessor


GRAPHQL_URL = "https://g.nivoda.com/graphql-public-loupe360"
REPORT = "LG836619414"
PIXORAC_V360 = (
    "https://assets-images.pixorac.com/"
    "aHR0cHM6Ly92aXNpb24uZGlhamV3ZWwzNjAuY29tL1Zpc2lvbjM2MC5odG1sP2Q9UEQtMjQ5MjAz"
)
DIAJEWEL_VIEWER = "https://vision.diajewel360.com/Vision360.html?d=PD-249203"


class FakeHttpClient:
    def __init__(self, *, posts=None, gets=None):
        self.posts = dict(posts or {})
        self.gets = dict(gets or {})
        self.calls = []

    def post(self, url, *, timeout, content, headers=None):
        self.calls.append(("POST", url, content, dict(headers or {})))
        value = self.posts.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "application/json"}, b"{}")
        payload, media_type = value
        return HttpResponse(200, url, {"Content-Type": media_type}, payload)

    def get(self, url, *, timeout):
        self.calls.append(("GET", url, None, {}))
        value = self.gets.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "text/plain"}, b"missing")
        payload, media_type = value
        return HttpResponse(200, url, {"Content-Type": media_type}, payload)


def _listing():
    return ListingRecord(
        url="https://retailer.test/exact-stone",
        metadata=DiamondMetadata(report_number=REPORT, lab="IGI"),
        references=(),
        provenance=(ProvenanceStep("fixture_listing", "https://retailer.test/exact-stone"),),
    )


def _loupe_reference():
    return EvidenceReference(
        identifier="fixture:rotation",
        kind=ROTATION,
        retrieval_key=f"loupe360-report:{REPORT}",
        locator=f"loupe360-report:{REPORT}",
        provenance=(ProvenanceStep("fixture_listing", "https://retailer.test/exact-stone"),),
        metadata={
            "lab": "IGI",
            "report_number": REPORT,
            "resolver": "loupe360_certificate",
        },
    )


def _graphql_payload(*, cert_number=REPORT, v360_url=PIXORAC_V360, video=None):
    return json.dumps(
        {
            "data": {
                "certificate_by_cert_number": {
                    "id": "a09f5540-676a-5ca2-8720-223107508271",
                    "certNumber": cert_number,
                    "lab": "IGI",
                    "image": "https://assets-images.pixorac.com/stone.jpg",
                    "video": video
                    or "https://loupe360.com/diamond/a09f5540-676a-5ca2-8720-223107508271/video/500/500",
                    "pdfUrl": f"https://example.test/{REPORT}.pdf",
                    "v360": (
                        {
                            "url": v360_url,
                            "frame_count": 256,
                            "top_index": "252",
                            "id": "4e75fe23-3153-4746-a7ff-e29e2636e6dd",
                        }
                        if v360_url is not None
                        else None
                    ),
                }
            }
        },
        separators=(",", ":"),
    ).encode()


class LoupeResolutionTests(unittest.TestCase):
    def test_exact_certificate_resolves_pixorac_wrapper_to_supplier_viewer(self):
        http = FakeHttpClient(
            posts={GRAPHQL_URL: (_graphql_payload(), "application/json")}
        )
        resolver = Loupe360CertificateResolver(http)
        children = resolver.resolve(_listing(), _loupe_reference())

        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertEqual(child.kind, ROTATION)
        self.assertEqual(child.locator, DIAJEWEL_VIEWER)
        self.assertEqual(child.retrieval_key, DIAJEWEL_VIEWER)
        self.assertEqual(child.metadata["report_number"], REPORT)
        self.assertEqual(child.metadata["loupe360_certificate_id"], "a09f5540-676a-5ca2-8720-223107508271")
        self.assertEqual(child.metadata["supplier_frame_count"], 256)
        self.assertEqual(child.metadata["supplier_top_index"], "252")
        self.assertEqual(child.provenance[-1].source, "loupe360_exact_certificate")
        self.assertEqual(child.provenance[-1].locator, GRAPHQL_URL)

        method, url, body, headers = http.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, GRAPHQL_URL)
        request = json.loads(body)
        self.assertEqual(request["variables"], {"cert": REPORT})
        self.assertIn("certificate_by_cert_number", request["query"])
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_resolver_rejects_returned_certificate_mismatch(self):
        http = FakeHttpClient(
            posts={
                GRAPHQL_URL: (
                    _graphql_payload(cert_number="LG999999999"),
                    "application/json",
                )
            }
        )
        with self.assertRaises(ValueError, msg="certificate mismatch"):
            Loupe360CertificateResolver(http).resolve(_listing(), _loupe_reference())

    def test_direct_video_is_used_only_when_no_supported_v360_exists(self):
        direct = "https://media.example.test/exact-stone.mp4"
        http = FakeHttpClient(
            posts={
                GRAPHQL_URL: (
                    _graphql_payload(v360_url=None, video=direct),
                    "application/json",
                )
            }
        )
        child = Loupe360CertificateResolver(http).resolve(
            _listing(), _loupe_reference()
        )[0]
        self.assertEqual(child.kind, VIDEO)
        self.assertEqual(child.locator, direct)
        self.assertEqual(child.retrieval_key, direct)
        self.assertEqual(child.metadata["format"], "video")


class DirectVideoTests(unittest.TestCase):
    def test_direct_mp4_bytes_are_preserved_and_hashed(self):
        url = "https://media.example.test/exact-stone.mp4"
        payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp41fixture"
        ref = EvidenceReference(
            identifier="fixture:video",
            kind=VIDEO,
            retrieval_key=url,
            locator=url,
            provenance=(ProvenanceStep("fixture", url),),
            metadata={"format": "video", "report_number": REPORT},
        )
        http = FakeHttpClient(gets={url: (payload, "video/mp4")})
        raw = DirectVideoDownloader(http).download(ref)
        evidence = DirectVideoProcessor().process(raw)[0]
        self.assertEqual(evidence.payload, payload)
        self.assertEqual(evidence.media_type, "video/mp4")
        self.assertEqual(evidence.metadata["container"], "mp4")
        self.assertEqual(len(evidence.metadata["sha256"]), 64)
        self.assertEqual(http.calls[0][0:2], ("GET", url))

    def test_invalid_direct_video_payload_fails_closed(self):
        url = "https://media.example.test/exact-stone.mp4"
        ref = EvidenceReference(
            identifier="fixture:video",
            kind=VIDEO,
            retrieval_key=url,
            locator=url,
            provenance=(ProvenanceStep("fixture", url),),
            metadata={"format": "video"},
        )
        http = FakeHttpClient(gets={url: (b"not-video", "video/mp4")})
        raw = DirectVideoDownloader(http).download(ref)
        with self.assertRaises(InvalidPayloadError):
            DirectVideoProcessor().process(raw)


if __name__ == "__main__":
    unittest.main()
