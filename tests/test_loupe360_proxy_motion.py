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
        for count, top in ((127, "12"), (256, "999"), (256, None)):
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


class Gem360CertificateProxyTests(unittest.TestCase):
    """R01 source contract: exact seller item is not an arbitrary Gem360 URL."""

    GEM360_VIEWER = "https://videos.gem360.in/Vision360.html?d=566392177"
    GEM360_PROXY_ROOT = (
        "https://assets-images.pixorac.com/"
        + base64.urlsafe_b64encode(GEM360_VIEWER.encode()).decode().rstrip("=")
    )
    GEM360_REPORT = "LG566392177"

    def test_only_exact_secure_gem360_viewer_transport_is_supported(self):
        from diamond_retrieval.resolvers import Loupe360CertificateResolver

        supported = Loupe360CertificateResolver._is_supported_rotation_url
        self.assertTrue(supported(self.GEM360_VIEWER))
        for unsafe in (
            "http://videos.gem360.in/Vision360.html?d=566392177",
            "https://videos.gem360.in.evil.test/Vision360.html?d=566392177",
            "https://127.0.0.1/Vision360.html?d=566392177",
            "https://videos.gem360.in/other.html?d=566392177",
            "https://videos.gem360.in/Vision360.html?d=566392177&ref=another",
            "https://videos.gem360.in/Vision360.html?d=566392177&ref=",
            "https://videos.gem360.in/Vision360.html?d=%35%36%36%33%39%32%31%37%37",
            "https://videos.gem360.in/Vision360.html?d=anything",
            "https://videos.gem360.in/Vision360.html?d=566392177#frag",
            "https://videos.gem360.in/Vision360.html?d=",
            "https://videos.gem360.in:443/Vision360.html?d=566392177",
        ):
            with self.subTest(viewer=unsafe):
                self.assertFalse(supported(unsafe))

    def test_r01_source_passes_exact_certificate_proxy_contract(self):
        from diamond_retrieval.loupe360_proxy import validated_proxy_root

        root = self.GEM360_PROXY_ROOT
        ref = EvidenceReference(
            identifier="ps285166-r01:proxy",
            kind=ROTATION, retrieval_key=root, locator=root,
            provenance=(ProvenanceStep("loupe360_exact_certificate", ENDPOINT),),
            metadata={
                "loupe360_proxy_exact_certificate": True,
                "lab": "IGI", "report_number": self.GEM360_REPORT,
                "supplier_frame_count": 256, "supplier_top_index": "244",
            },
        )
        self.assertEqual(validated_proxy_root(ref), root)

    def test_r01_complete_proxy_retrieval_reuses_existing_256_frame_checks(self):
        proxy = self.GEM360_PROXY_ROOT
        report = self.GEM360_REPORT

        class FakeGem360Http(FakeHttp):
            def get(self, url, *, timeout, headers=None):
                if url.startswith(proxy + "/") and url.endswith(".jpg"):
                    self.calls.append(("GET", url))
                    try:
                        index = int(url[len(proxy) + 1:-4])
                    except ValueError:
                        index = -1
                    if 0 <= index < 256:
                        return HttpResponse(
                            200, url, {"Content-Type": "image/jpeg"}, frame(index),
                        )
                return super().get(url, timeout=timeout, headers=headers)

        http = FakeGem360Http(graphql=certificate(
            report=report, proxy_root=proxy, top="244",
        ))
        result = retrieve_reference_media(
            "ps285166-r01", lab="IGI", report_number=report, http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        rotation = result.rotations[0]
        self.assertEqual(rotation.face_up_hint, 244)
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual(len({x.sha256 for x in rotation.frames}), 256)
        self.assertEqual([x.source_index for x in rotation.frames], list(range(256)))
        self.assertEqual(rotation.metadata["supplier"], "loupe360-pixorac-proxy")
        self.assertFalse(rotation.metadata["supplier_original_bytes_verified"])
        self.assertEqual(len([
            x for x in http.calls if x[0] == "GET" and x[1].startswith(proxy + "/")
        ]), 256)
        self.assertTrue(any(
            x.locator == proxy and x.status == EvidenceStatus.SUCCESS
            for x in result.attempts
        ))

    def test_report_mismatch_never_fetches_proxy(self):
        report = self.GEM360_REPORT
        root = self.GEM360_PROXY_ROOT
        http = FakeHttp(graphql=certificate(
            report="LG000000001", proxy_root=root, top="244",
        ))
        result = retrieve_reference_media(
            "ps285166-r01", lab="IGI", report_number=report, http_client=http,
        )
        self.assertFalse(result.rotations)
        self.assertFalse(any(
            x[0] == "GET" and x[1].startswith(root) for x in http.calls
        ))


if __name__ == "__main__":
    unittest.main()


class V360DiamondsCertificateProxyTests(unittest.TestCase):
    """Reusable certificate-bound v360.diamonds indexed JPEG bridge.

    No direct V360 browser access, undocumented API, or guessed report alias:
    only a verified exact-provider wrapper with all actual 256 images.
    """

    REPORT = "LG715575610"
    VIEWER = (
        "https://v360.diamonds/c/22971515-3849-41bb-ae0a-3bb31e3a7ae9"
        "?m=i&a=FA-121"
    )
    ROOT = (
        "https://assets-images.pixorac.com/"
        + base64.urlsafe_b64encode(VIEWER.encode()).decode().rstrip("=")
    )

    def _http(self, *, missing=None, report=REPORT, lab="IGI"):
        root = self.ROOT

        class Client(FakeHttp):
            def get(self, url, *, timeout, headers=None):
                if url.startswith(root + "/") and url.endswith(".jpg"):
                    self.calls.append(("GET", url))
                    suffix = url[len(root) + 1:-4]
                    if suffix.isdigit():
                        index = int(suffix)
                        if 0 <= index < 256 and index != missing:
                            return HttpResponse(
                                200, url, {"Content-Type": "image/jpeg"}, self.frames[index]
                            )
                    return HttpResponse(404, url, {}, b"missing")
                return super().get(url, timeout=timeout, headers=headers)

        return Client(graphql=certificate(
            report=report, lab=lab, proxy_root=root, count=256, top="212"
        ))

    def test_only_exact_v360_public_viewer_pattern_is_eligible(self):
        from diamond_retrieval.resolvers import Loupe360CertificateResolver as Resolver

        self.assertTrue(Resolver._is_supported_rotation_url(self.VIEWER))
        for url in (
            self.VIEWER.replace("https://", "http://"),
            self.VIEWER.replace("v360.diamonds/", "v360.diamonds.evil.test/"),
            self.VIEWER.replace("/c/", "/u/"),
            self.VIEWER.replace("m=i", "m=d"),
            self.VIEWER + "&url=http://127.0.0.1",
            self.VIEWER + "#other",
            self.VIEWER.replace("a=FA-121", "a="),
            self.VIEWER.replace("a=FA-121", "a=FA-121&a=other"),
        ):
            with self.subTest(url=url):
                self.assertFalse(Resolver._is_supported_rotation_url(url))

    def test_complete_exact_report_proxy_rotation_uses_existing_pipeline(self):
        http = self._http()
        result = retrieve_reference_media(
            "owner-igi-lg715575610", lab="IGI",
            report_number=self.REPORT, http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        rotation = result.rotations[0]
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual(len({f.sha256 for f in rotation.frames}), 256)
        self.assertEqual(rotation.face_up_hint, 212)
        self.assertEqual(rotation.metadata["supplier"], "loupe360-pixorac-proxy")
        self.assertFalse(rotation.metadata["supplier_original_bytes_verified"])
        self.assertEqual([f.source_index for f in rotation.frames], list(range(256)))
        self.assertTrue(any(
            a.locator == self.VIEWER and a.status == EvidenceStatus.UNSUPPORTED
            for a in result.attempts
        ))
        self.assertTrue(any(
            a.locator == self.ROOT and a.status == EvidenceStatus.SUCCESS
            for a in result.attempts
        ))

    def test_missing_frame_and_identity_conflict_fail_closed(self):
        missing = self._http(missing=88)
        result = retrieve_reference_media(
            "owner-igi-lg715575610", lab="IGI",
            report_number=self.REPORT, http_client=missing,
        )
        self.assertFalse(result.rotations)
        self.assertTrue(any(
            a.locator == self.ROOT and a.status == EvidenceStatus.MISSING
            for a in result.attempts
        ))
        for bad in (self._http(report="LG000000000"), self._http(lab="GIA")):
            with self.subTest():
                result = retrieve_reference_media(
                    "owner-igi-lg715575610", lab="IGI",
                    report_number=self.REPORT, http_client=bad,
                )
                self.assertFalse(result.rotations)
                self.assertFalse(any(
                    key.startswith(self.ROOT + "/") for _, key in bad.calls
                ))

class DiamondAssetCertificateProxyTests(unittest.TestCase):
    """Certificate-bound DiamondAsset viewers may use the existing Pixorac cache."""

    REPORT = "LG728537967"
    VIEWER = "https://video.diamondasset.in/photo/appVideo.jsp?idv=728537967"
    ROOT = (
        "https://assets-images.pixorac.com/"
        + base64.urlsafe_b64encode(VIEWER.encode()).decode().rstrip("=")
    )

    def _http(self, *, missing=None, report=REPORT, lab="IGI"):
        root = self.ROOT

        class Client(FakeHttp):
            def get(self, url, *, timeout, headers=None):
                if url.startswith(root + "/") and url.endswith(".jpg"):
                    self.calls.append(("GET", url))
                    suffix = url[len(root) + 1:-4]
                    if suffix.isdigit():
                        index = int(suffix)
                        if 0 <= index < 128 and index != missing:
                            return HttpResponse(
                                200, url, {"Content-Type": "image/jpeg"}, self.frames[index]
                            )
                    return HttpResponse(404, url, {}, b"missing")
                return super().get(url, timeout=timeout, headers=headers)

        return Client(graphql=certificate(
            report=report,
            lab=lab,
            proxy_root=root,
            count=128,
            top="114",
        ))

    def test_only_exact_diamondasset_viewer_pattern_is_eligible(self):
        from diamond_retrieval.resolvers import Loupe360CertificateResolver as Resolver

        self.assertTrue(Resolver._is_supported_rotation_url(self.VIEWER))
        for url in (
            self.VIEWER.replace("https://", "http://"),
            self.VIEWER.replace("video.diamondasset.in/", "video.diamondasset.in.evil.test/"),
            self.VIEWER.replace("/photo/appVideo.jsp", "/photo/other.jsp"),
            self.VIEWER.replace("idv=728537967", "idv=not-a-number"),
            self.VIEWER + "&other=1",
            self.VIEWER + "#other",
            self.VIEWER.replace("video.diamondasset.in", "video.diamondasset.in:443"),
        ):
            with self.subTest(url=url):
                self.assertFalse(Resolver._is_supported_rotation_url(url))

    def test_lg728537967_exact_report_proxy_uses_existing_pipeline(self):
        http = self._http()
        result = retrieve_reference_media(
            "owner-igi-lg728537967", lab="IGI",
            report_number=self.REPORT, http_client=http,
        )
        self.assertEqual(len(result.rotations), 1)
        rotation = result.rotations[0]
        self.assertEqual(len(rotation.frames), 128)
        self.assertEqual(len({f.sha256 for f in rotation.frames}), 128)
        self.assertEqual(rotation.face_up_hint, 114)
        self.assertEqual(rotation.metadata["supplier"], "loupe360-pixorac-proxy")
        self.assertFalse(rotation.metadata["supplier_original_bytes_verified"])
        self.assertEqual([f.source_index for f in rotation.frames], list(range(128)))
        self.assertTrue(any(
            a.locator == self.VIEWER and a.status == EvidenceStatus.UNSUPPORTED
            for a in result.attempts
        ))
        self.assertTrue(any(
            a.locator == self.ROOT and a.status == EvidenceStatus.SUCCESS
            for a in result.attempts
        ))

    def test_missing_frame_and_identity_conflict_fail_closed(self):
        missing = self._http(missing=88)
        result = retrieve_reference_media(
            "owner-igi-lg728537967", lab="IGI",
            report_number=self.REPORT, http_client=missing,
        )
        self.assertFalse(result.rotations)
        self.assertTrue(any(
            a.locator == self.ROOT and a.status == EvidenceStatus.MISSING
            for a in result.attempts
        ))
        for bad in (self._http(report="LG000000000"), self._http(lab="GIA")):
            with self.subTest():
                result = retrieve_reference_media(
                    "owner-igi-lg728537967", lab="IGI",
                    report_number=self.REPORT, http_client=bad,
                )
                self.assertFalse(result.rotations)
                self.assertFalse(any(
                    key.startswith(self.ROOT + "/") for _, key in bad.calls
                ))

