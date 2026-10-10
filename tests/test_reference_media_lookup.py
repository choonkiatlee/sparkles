"""Network-free tests of listing-independent reference evidence lookup (#196)."""
from __future__ import annotations

import io
import json
import unittest

from PIL import Image

from diamond_retrieval import (
    ROTATION, STILL, VIDEO, EvidenceStatus, HttpResponse,
    IdentityConflictError, IdentityObservation, ProvenanceStep,
    RetrievalConfig, retrieve_reference_media,
)
from diamond_retrieval.models import Evidence, RawEvidence
from tests.test_diamond_retrieval_motion import (
    AUDITS, _progressive_source_responses,
)

GRAPHQL = "https://g.nivoda.com/graphql-public-loupe360"
REPORT = "LG836619414"
VIDEO_URL = "https://media.example.test/example.mp4"
STILL_URL = "https://assets-images.pixorac.com/stone.jpg"
SUPPLIER = "https://unknown.example.test/not-a-supported-v360"
SUPPORTED = "https://vision.diajewel360.com/Vision360.html?d=VL-NEW123"
ROOT = "https://vision.diajewel360.com/imaged/VL-NEW123"
VIDEO_BYTES = bytes.fromhex("000000186674797069736f6d0000020069736f6d6d703431") + b"fixture"


def _jpeg():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), (210, 210, 210)).save(output, format="JPEG")
    return output.getvalue()


def _graphql(*, report=REPORT, lab="IGI", rotation=SUPPLIER, video=VIDEO_URL, image=STILL_URL):
    return json.dumps({
        "data": {
            "certificate_by_cert_number": {
                "id": "supplier-certificate-uuid",
                "certNumber": report,
                "lab": lab,
                "v360": {
                    "url": rotation, "id": "supplier-v360-uuid",
                    "frame_count": 256, "top_index": 250,
                } if rotation else None,
                "video": video,
                "image": image,
            },
        },
    }).encode()


class FakeHttp:
    def __init__(self, gets=None, *, graphql=None):
        self.gets = dict(gets or {})
        self.graphql = graphql
        self.calls = []

    def get(self, url, *, timeout, headers=None):
        self.calls.append(("GET", url))
        value = self.gets.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "text/plain"}, b"missing")
        return HttpResponse(200, url, {"Content-Type": value[1]}, value[0])

    def post(self, url, *, timeout, content, headers=None):
        self.calls.append(("POST", url))
        self.calls.append(("CERT", json.loads(content)["variables"]["cert"]))
        if url != GRAPHQL or self.graphql is None:
            return HttpResponse(404, url, {}, b"missing")
        return HttpResponse(200, url, {"Content-Type": "application/json"}, self.graphql)


class ReferenceMediaLookupTests(unittest.TestCase):
    def test_igi_only_finds_exact_loupe_v360_video_and_still_candidates(self):
        http = FakeHttp(
            {VIDEO_URL: (VIDEO_BYTES, "video/mp4"), STILL_URL: (_jpeg(), "image/jpeg")},
            graphql=_graphql(),
        )
        result = retrieve_reference_media(
            "ps285166-r02", lab="IGI", report_number=REPORT, http_client=http,
        )
        self.assertEqual(result.listing_url, "reference:ps285166-r02")
        self.assertEqual(result.metadata.report_number, REPORT)
        self.assertEqual([item.kind for item in result.evidence], [VIDEO, STILL])
        self.assertEqual(result.evidence[0].payload, VIDEO_BYTES)
        self.assertEqual(result.evidence[1].dimensions, (8, 8))
        self.assertTrue(all(e.metadata["report_number"] == REPORT for e in result.evidence))
        self.assertTrue(any(
            a.kind == ROTATION and a.locator == SUPPLIER and
            a.status == EvidenceStatus.UNSUPPORTED for a in result.attempts
        ))
        self.assertEqual(http.calls[0], ("POST", GRAPHQL))
        self.assertIn(("CERT", REPORT), http.calls)
        self.assertFalse(any("retailer" in url for _, url in http.calls if _ == "GET"))

    def test_loupe_v360_direct_mp4_uses_video_path_not_fake_rotation(self):
        # Reproduces the R21 / GIA 2135242286 source shape: the Nivoda
        # exact-certificate v360.url points straight to an original MP4.
        source = "https://idealbrilliant.s3.amazonaws.com/imaged/P970-3/video.mp4"
        http = FakeHttp(
            {source: (VIDEO_BYTES, "video/mp4"), STILL_URL: (_jpeg(), "image/jpeg")},
            graphql=_graphql(
                report="2135242286", lab="GIA", rotation=source,
                video=None,
            ),
        )
        result = retrieve_reference_media(
            "ps281114-r21", lab="GIA", report_number="2135242286",
            http_client=http,
        )
        self.assertEqual([e.kind for e in result.evidence], [VIDEO, STILL])
        self.assertEqual(result.evidence[0].payload, VIDEO_BYTES)
        self.assertFalse(result.rotations)
        self.assertEqual(result.evidence[0].metadata["format"], "video")
        self.assertNotIn("supplier_frame_count", result.evidence[0].metadata)
        self.assertEqual(http.calls.count(("GET", source)), 1)
        self.assertTrue(any(
            a.locator == source and a.kind == VIDEO and
            a.status == EvidenceStatus.SUCCESS for a in result.attempts
        ))
        self.assertFalse(any(
            a.kind == ROTATION and a.locator == source for a in result.attempts
        ))

    def test_loupe_v360_direct_video_invalid_bytes_fail_closed(self):
        source = "https://idealbrilliant.s3.amazonaws.com/imaged/P970-3/video.mp4"
        http = FakeHttp(
            {source: (b"not-video", "video/mp4")},
            graphql=_graphql(rotation=source, video=None, image=None),
        )
        result = retrieve_reference_media(
            "invalid-video", lab="IGI", report_number=REPORT,
            http_client=http,
        )
        self.assertFalse(result.evidence)
        self.assertTrue(any(
            a.kind == VIDEO and a.locator == source and
            a.status == EvidenceStatus.INVALID_PAYLOAD for a in result.attempts
        ))
        self.assertFalse(result.rotations)

    def test_explicit_direct_still_precedes_certificate_lookup(self):
        direct = "https://assets.example.test/my-still.jpg"
        http = FakeHttp(
            {direct: (_jpeg(), "image/jpeg")}, graphql=_graphql(rotation=None, video=None, image=None),
        )
        result = retrieve_reference_media(
            "one", lab="IGI", report_number=REPORT,
            media_sources=[{"kind": "still", "url": direct, "provider": "agent"}],
            http_client=http,
        )
        self.assertEqual(http.calls[0], ("GET", direct))
        self.assertEqual(len(result.stills), 1)

    def test_unsupported_v360_diamonds_is_preserved_without_fetching(self):
        url = "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i"
        http = FakeHttp()
        result = retrieve_reference_media(
            "ps285166-r07", media_sources=[{
                "kind": "viewer", "provider": "v360.diamonds", "url": url,
                "status": "linked_unverified",
            }], http_client=http,
        )
        self.assertEqual(result.evidence, ())
        self.assertEqual(result.attempts[0].status, EvidenceStatus.UNSUPPORTED)
        self.assertEqual(result.attempts[0].locator, url)
        self.assertEqual(http.calls, [])

    def test_numeric_loupe_viewer_is_not_treated_as_certificate(self):
        url = "https://loupe360.com/diamond/1498922544"
        http = FakeHttp()
        result = retrieve_reference_media(
            "ps285166-r09", media_sources=[{
                "kind": "viewer", "provider": "loupe360", "url": url,
            }], http_client=http,
        )
        self.assertIsNone(result.metadata.report_number)
        self.assertIsNone(result.metadata.lab)
        # This exact URL is now independently source-pinned for native R09.
        # The fixture has no matching proxy response, so it fails closed after
        # one source lookup and never treats viewer digits as a certificate.
        self.assertEqual(result.attempts[0].status, EvidenceStatus.RESOLUTION_FAILED)
        self.assertEqual(http.calls[0], ("POST", GRAPHQL))
        self.assertFalse(any(call[0] == "GET" for call in http.calls))
        unrelated = FakeHttp()
        other = retrieve_reference_media(
            "ps285166-r09", media_sources=[{
                "kind": "viewer", "provider": "loupe360",
                "url": "https://loupe360.com/diamond/999999999",
            }], http_client=unrelated,
        )
        self.assertEqual(other.attempts[0].status, EvidenceStatus.UNSUPPORTED)
        self.assertFalse(unrelated.calls)

    def test_missing_match_and_conflicting_report_or_lab_never_attach_evidence(self):
        for payload in (
            b'{"data":{"certificate_by_cert_number":null}}',
            _graphql(report="LG999999999"),
            _graphql(lab="GIA"),
        ):
            http = FakeHttp(graphql=payload)
            result = retrieve_reference_media(
                "test-match", lab="IGI", report_number=REPORT, http_client=http,
            )
            self.assertEqual(result.evidence, ())
            self.assertEqual(result.attempts[0].status, EvidenceStatus.RESOLUTION_FAILED)
            self.assertEqual(http.calls[0], ("POST", GRAPHQL))
            self.assertFalse(any(call[0] == "GET" for call in http.calls))

    def test_duplicate_urls_are_downloaded_once_with_provenance(self):
        url = "https://media.example.test/stone.jpg"
        http = FakeHttp({url: (_jpeg(), "image/jpeg")})
        result = retrieve_reference_media("dup", media_sources=[
            {"kind": "still", "url": url, "provider": "first"},
            {"kind": "still", "url": url, "provider": "second"},
        ], http_client=http)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual([x.status for x in result.attempts],
                         [EvidenceStatus.SUCCESS, EvidenceStatus.DUPLICATE])
        self.assertEqual(http.calls, [("GET", url)])
        self.assertIn("second", str(result.evidence[0].provenance))

    def test_absent_and_invalid_bytes_are_structured_and_do_not_hide_success(self):
        good = "https://media.example.test/good.jpg"
        missing = "https://media.example.test/missing.jpg"
        bad = "https://media.example.test/bad.mp4"
        http = FakeHttp({good: (_jpeg(), "image/jpeg"), bad: (b"not-video", "video/mp4")})
        result = retrieve_reference_media("partial", media_sources=[
            {"kind": "still", "url": good},
            {"kind": "still", "url": missing},
            {"kind": "video", "url": bad},
        ], http_client=http)
        self.assertEqual(len(result.stills), 1)
        self.assertEqual([a.status for a in result.attempts], [
            EvidenceStatus.SUCCESS, EvidenceStatus.MISSING, EvidenceStatus.INVALID_PAYLOAD,
        ])

    def test_direct_supported_viewer_recovers_complete_rotation_without_a_report(self):
        responses = _progressive_source_responses(AUDITS[0], ROOT, version=1)
        http = FakeHttp(responses)
        result = retrieve_reference_media("direct-spin", media_sources=[
            {"kind": "viewer", "url": SUPPORTED, "provider": "diajewel"},
        ], http_client=http)
        self.assertIsNone(result.metadata.report_number)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(result.attempts[0].status, EvidenceStatus.SUCCESS)
        self.assertEqual(result.rotations[0].frames[0].source_index, 0)

    def test_labgrowns3_curated_reference_with_report_retains_256_frames(self):
        host = "https://labgrowns3.s3.ap-southeast-1.amazonaws.com"
        item = "1210811_B2C"
        root = f"{host}/imaged/{item}"
        viewer = f"{host}/stoneimages360.html?d={item}"
        responses = _progressive_source_responses(AUDITS[0], root, version=2)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        http = FakeHttp(responses)
        result = retrieve_reference_media(
            "ps285166-r06", lab="IGI", report_number="LG659462667",
            media_sources=[{
                "kind": "viewer", "provider": "labgrowns3",
                "url": viewer, "status": "linked_unverified",
            }],
            http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(result.metadata.report_number, "LG659462667")
        self.assertEqual(result.rotations[0].metadata["supplier"], "labgrowns3")
        self.assertEqual(result.attempts[0].status, EvidenceStatus.SUCCESS)
        self.assertEqual(http.calls[0], ("GET", root + "/0.json?version="))

    def test_incomplete_rotation_does_not_become_successful_motion(self):
        responses = _progressive_source_responses(AUDITS[0], ROOT, version=1)
        responses[f"{ROOT}/4.json?version=1"] = (b"[]", "application/json")
        good = "https://media.example.test/good.jpg"
        responses[good] = (_jpeg(), "image/jpeg")
        http = FakeHttp(responses)
        result = retrieve_reference_media("incomplete", media_sources=[
            {"kind": "viewer", "url": SUPPORTED},
            {"kind": "still", "url": good},
        ], http_client=http)
        self.assertFalse(result.rotations)
        self.assertEqual(len(result.stills), 1)
        self.assertEqual(result.attempts[0].status, EvidenceStatus.INVALID_PAYLOAD)
        self.assertEqual(result.attempts[1].status, EvidenceStatus.SUCCESS)

    def test_identity_conflict_fails_closed_before_result_is_returned(self):
        class Downloader:
            def supports(self, reference):
                return reference.kind == STILL

            def download(self, reference):
                return RawEvidence(reference=reference, payload=b"fixture", format="fixture")

        class Processor:
            def supports(self, raw):
                return True

            def process(self, raw):
                return (Evidence(
                    identifier=raw.reference.identifier,
                    kind=STILL,
                    provenance=raw.reference.provenance,
                    payload=raw.payload,
                    identity_observations=(IdentityObservation(
                        "report_number", "LG999999999",
                        provenance=(ProvenanceStep("conflicting_report"),),
                    ),),
                ),)

        config = RetrievalConfig(
            providers=(), downloaders=(Downloader(),), processors=(Processor(),),
        )
        with self.assertRaises(IdentityConflictError):
            retrieve_reference_media(
                "conflict", lab="IGI", report_number=REPORT,
                media_sources=[{"kind": "still", "url": "https://media.example.test/x.jpg"}],
                config=config,
            )

    def test_invalid_media_urls_rejected_before_network(self):
        http = FakeHttp()
        for url in (
            "http://example.test/image.jpg",
            "https://localhost/secret.jpg",
            "https://127.0.0.1/x",
            "https://example.com@127.0.0.1/x",
            "https://example.test/x y",
            "https://example.test:8080/x",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                retrieve_reference_media("safe", media_sources=[
                    {"kind": "still", "url": url},
                ], http_client=http)
        self.assertEqual(http.calls, [])

    def test_optional_igi_pdf_and_no_pdf_for_gia(self):
        http = FakeHttp(graphql=b'{"data":{"certificate_by_cert_number":null}}')
        igi = retrieve_reference_media("pdf", lab="IGI", report_number=REPORT,
                                       include_igi_pdf=True, http_client=http)
        self.assertTrue(any(a.kind == "certificate" for a in igi.attempts))
        gia = retrieve_reference_media("gia", lab="GIA", report_number="2496852830",
                                       include_igi_pdf=True, http_client=http)
        self.assertFalse(any(a.kind == "certificate" for a in gia.attempts))


if __name__ == "__main__":
    unittest.main()
