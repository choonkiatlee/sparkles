"""Contract tests for exact-certificate Loupe360 indexed JPEG fallback (#221)."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import unittest

from PIL import Image

from diamond_retrieval import (
    ROTATION, EvidenceStatus, HttpResponse,
    Loupe360ProxyRotationDownloader, IndexedProxyRotationProcessor,
    retrieve_reference_media,
)
from diamond_retrieval.models import EvidenceReference, ProvenanceStep
from tests.test_diamond_retrieval_motion import (
    AUDITS, _progressive_source_responses,
)

ENDPOINT = "https://g.nivoda.com/graphql-public-loupe360"
REPORT = "LG657468099"
VIEWER = "https://workshop.360view.link/360viewer/360view.html?d=0410243-YDC-13680"
SOURCE_ROOT = "https://data1.360view.link/data/1/imaged/0410243-YDC-13680"
TOKEN = base64.urlsafe_b64encode(VIEWER.encode()).decode().rstrip("=")
PROXY_ROOT = "https://assets-images.pixorac.com/" + TOKEN


def frame(index: int, *, size=(8, 8)) -> bytes:
    image = Image.new("RGB", size, (index % 251, index * 7 % 251, index * 13 % 251))
    image.putpixel((index % size[0], index % size[1]), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def certificate(*, report=REPORT, lab="IGI", proxy_root=PROXY_ROOT, count=256,
                top="194", supplier_video=None):
    return json.dumps({"data": {"certificate_by_cert_number": {
        "id": "matched-cert-uuid",
        "certNumber": report,
        "lab": lab,
        "image": None,
        "video": supplier_video,
        "v360": {
            "url": proxy_root, "id": "matched-v360-uuid",
            "frame_count": count, "top_index": top,
        },
    }}}).encode()


class FakeHttp:
    def __init__(self, *, graphql=None, frames=None, originals=None):
        self.graphql = graphql if graphql is not None else certificate()
        self.frames = frames if frames is not None else {i: frame(i) for i in range(256)}
        self.originals = originals or {}
        self.calls = []

    def post(self, url, *, timeout, content, headers):
        self.calls.append(("POST", url))
        if url != ENDPOINT:
            return HttpResponse(404, url, {}, b"missing")
        return HttpResponse(200, url, {"Content-Type": "application/json"}, self.graphql)

    def get(self, url, *, timeout, headers=None):
        self.calls.append(("GET", url))
        if url in self.originals:
            data, mime = self.originals[url]
            return HttpResponse(200, url, {"Content-Type": mime}, data)
        if url.startswith(PROXY_ROOT + "/") and url.endswith(".jpg"):
            try:
                index = int(url[len(PROXY_ROOT) + 1:-4])
            except ValueError:
                index = -1
            data = self.frames.get(index)
            if data is not None:
                return HttpResponse(200, url, {"Content-Type": "image/jpeg"}, data)
        return HttpResponse(404, url, {"Content-Type": "text/plain"}, b"missing")


def proxy_attempts(result):
    return [a for a in result.attempts if a.locator == PROXY_ROOT]


class Loupe360ProxyContractTests(unittest.TestCase):
    def test_both_actual_igi_report_source_forms_pass_exact_contract(self):
        for report, viewer, top in (
            ("LG657468099", VIEWER, "194"),
            ("LG636432256", "https://workshop.360view.link/360viewer/360view.html?d=2905248-YDC-6456", "12"),
        ):
            with self.subTest(report=report):
                root = "https://assets-images.pixorac.com/" + base64.urlsafe_b64encode(
                    viewer.encode()
                ).decode().rstrip("=")
                ref = EvidenceReference(
                    identifier="test:proxy", kind=ROTATION,
                    retrieval_key=root, locator=root,
                    provenance=(ProvenanceStep("loupe360_exact_certificate", ENDPOINT),),
                    metadata={
                        "loupe360_proxy_exact_certificate": True,
                        "lab": "IGI", "report_number": report,
                        "supplier_frame_count": 256, "supplier_top_index": top,
                    },
                )
                self.assertTrue(Loupe360ProxyRotationDownloader(FakeHttp()).supports(ref))

    def test_complete_fallback_recovers_exact_256_indexed_jpegs(self):
        http = FakeHttp()
        result = retrieve_reference_media(
            "ps285166-r08", lab="IGI", report_number=REPORT, http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        rotation = result.rotations[0]
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual([f.source_index for f in rotation.frames], list(range(256)))
        self.assertEqual(rotation.frames[194].payload, frame(194))
        self.assertEqual(rotation.frames[255].sha256, hashlib.sha256(frame(255)).hexdigest())
        self.assertEqual(rotation.face_up_hint, 194)
        self.assertEqual(rotation.metadata["supplier"], "loupe360-pixorac-proxy")
        self.assertFalse(rotation.metadata["supplier_original_bytes_verified"])
        self.assertEqual(rotation.metadata["ordering"], "proxy indexed source positions 0..255")
        self.assertEqual(len({f.sha256 for f in rotation.frames}), 256)
        self.assertEqual(len([x for x in http.calls if x[0] == "GET" and x[1].startswith(PROXY_ROOT)]), 256)
        self.assertTrue(any(
            a.locator == VIEWER and a.status == EvidenceStatus.MISSING
            for a in result.attempts
        ))
        self.assertEqual(proxy_attempts(result)[0].status, EvidenceStatus.SUCCESS)
        self.assertTrue(any("loupe360_pixorac_proxy_indexed_jpeg" == p.source
                            for p in rotation.provenance))

    def test_missing_frame_fails_without_publishing_partial_rotation(self):
        frames = {i: frame(i) for i in range(256) if i != 128}
        http = FakeHttp(frames=frames)
        result = retrieve_reference_media(
            "ps285166-r08", lab="IGI", report_number=REPORT, http_client=http,
        )
        self.assertFalse(result.rotations)
        self.assertEqual(proxy_attempts(result)[0].status, EvidenceStatus.MISSING)

    def test_corrupt_or_dimension_changed_frame_is_fail_closed(self):
        for changed in (b"not-jpeg", frame(77, size=(9, 8))):
            with self.subTest(changed=changed[:8]):
                frames = {i: frame(i) for i in range(256)}
                frames[77] = changed
                result = retrieve_reference_media(
                    "ps285166-r08", lab="IGI", report_number=REPORT,
                    http_client=FakeHttp(frames=frames),
                )
                self.assertFalse(result.rotations)
                self.assertEqual(proxy_attempts(result)[0].status, EvidenceStatus.INVALID_PAYLOAD)

    def test_static_placeholder_frames_fail_closed(self):
        client = FakeHttp(frames={i: frame(0) for i in range(256)})
        result = retrieve_reference_media(
            "ps285166-r08", lab="IGI", report_number=REPORT, http_client=client,
        )
        self.assertFalse(result.rotations)
        self.assertEqual(proxy_attempts(result)[0].status, EvidenceStatus.INVALID_PAYLOAD)

    def test_exact_supplier_original_success_skips_proxy(self):
        responses = _progressive_source_responses(AUDITS[1], SOURCE_ROOT, version=2)
        http = FakeHttp(originals=responses)
        result = retrieve_reference_media(
            "ps285166-r08", lab="IGI", report_number=REPORT, http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(result.rotations[0].metadata["supplier"], "workshop")
        self.assertFalse(any(x[0] == "GET" and x[1].startswith(PROXY_ROOT) for x in http.calls))
        self.assertEqual(proxy_attempts(result)[0].status, EvidenceStatus.NOT_REQUESTED)

    def test_wrong_report_or_lab_never_emits_proxy(self):
        for bad in (certificate(report="LG000000000"), certificate(lab="GIA")):
            with self.subTest(bad=bad[:50]):
                client = FakeHttp(graphql=bad)
                result = retrieve_reference_media(
                    "ps285166-r08", lab="IGI", report_number=REPORT, http_client=client,
                )
                self.assertFalse(result.rotations)
                self.assertFalse(proxy_attempts(result))
                self.assertFalse(any(x[0] == "GET" for x in client.calls))

    def test_unsafe_non_certificate_proxy_urls_are_never_accepted(self):
        client = FakeHttp()
        downloader = Loupe360ProxyRotationDownloader(client)
        for root in (
            "http://" + PROXY_ROOT.removeprefix("https://"),
            PROXY_ROOT.replace("assets-images.pixorac.com", "assets-images.pixorac.com.evil.test"),
            "https://127.0.0.1/" + TOKEN,
            "https://assets-images.pixorac.com/x",
            PROXY_ROOT + "/../../etc",
            PROXY_ROOT + "?src=http://localhost",
        ):
            with self.subTest(root=root):
                ref = EvidenceReference(
                    identifier="bad:proxy", kind=ROTATION, retrieval_key=root, locator=root,
                    provenance=(ProvenanceStep("loupe360_exact_certificate", ENDPOINT),),
                    metadata={
                        "loupe360_proxy_exact_certificate": True,
                        "lab": "IGI", "report_number": REPORT,
                        "supplier_frame_count": 256, "supplier_top_index": "194",
                    },
                )
                self.assertFalse(downloader.supports(ref))
        ref = EvidenceReference(
            identifier="fake:proxy", kind=ROTATION,
            locator=PROXY_ROOT, retrieval_key=PROXY_ROOT,
            metadata={
                "loupe360_proxy_exact_certificate": True, "lab": "IGI",
                "report_number": REPORT, "supplier_frame_count": 256,
                "supplier_top_index": 194,
            },
        )
        self.assertFalse(downloader.supports(ref))
        self.assertEqual(client.calls, [])

    def test_no_proxy_if_frame_count_or_top_index_invalid(self):
        for count, top in ((128, "12"), (256, "999"), (256, None)):
            with self.subTest(count=count, top=top):
                client = FakeHttp(graphql=certificate(count=count, top=top))
                result = retrieve_reference_media(
                    "ps285166-r08", lab="IGI", report_number=REPORT, http_client=client,
                )
                self.assertFalse(proxy_attempts(result))
                self.assertFalse(result.rotations)

    def test_processors_do_not_accept_incomplete_or_corrupted_bundle(self):
        http = FakeHttp()
        result = retrieve_reference_media(
            "ps285166-r08", lab="IGI", report_number=REPORT, http_client=http,
        )
        rotation = result.rotations[0]
        raw = type("Raw", (), {})()
        raw.reference = EvidenceReference(
            identifier="one", kind=ROTATION, retrieval_key=PROXY_ROOT, locator=PROXY_ROOT,
        )
        raw.format = "indexed-proxy-rotation-json"
        raw.metadata = {}
        raw.payload = rotation.payload
        processor = IndexedProxyRotationProcessor()
        data = json.loads(raw.payload)
        data["frames"].pop()
        raw.payload = json.dumps(data).encode()
        from diamond_retrieval.errors import InvalidPayloadError
        with self.assertRaises(InvalidPayloadError):
            processor.process(raw)


if __name__ == "__main__":
    unittest.main()
