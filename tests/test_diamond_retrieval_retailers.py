import base64
import io
import json
import unittest
from pathlib import Path

from PIL import Image

from diamond_retrieval import (
    CERTIFICATE,
    ROTATION,
    STILL,
    VIDEO,
    StandardRetrievalPolicy,
    CompletionAssessment,
    EvidenceStatus,
    HttpResponse,
    IdentityConflictError,
    IdentityOutcome,
    ResultStatus,
    default_config,
    retrieve_diamond,
)
from diamond_retrieval.retailers import (
    DiyonaListingProvider,
    QualityDiamondsListingProvider,
)


FIXTURES = Path(__file__).parent / "fixtures" / "diamond_retrieval"
MOTION_AUDITS = json.loads((FIXTURES / "motion-audits.json").read_text())["audits"]
GRAPHQL_URL = "https://g.nivoda.com/graphql-public-loupe360"
DIRECT_VIDEO = "https://media.example.test/exact-stone.mp4"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp41fixture"
DIYONA_URL = "https://diyona.com/pages/diamond-detail?sku=B934F4533"
QD_URL = (
    "https://www.qualitydiamonds.co.uk/loose-diamonds/"
    "buy-loose-diamonds?d=133%2FF74D0EF67"
)
QD_STILL = (
    "https://assets-images-saas.nivoda.com/"
    "ba549dd3-96aa-4871-9a40-42e54d23ce72.jpg"
    "?c_id=95095175-f466-48c3-b90d-8979575bb8ae"
    "&d_id=8ea0dc8e-333f-48a1-a8a5-4881d40a4758"
    "&f_id=24c9640d-d795-498f-b870-f69e02eb85fa&type=csv"
)


class FakeHttpClient:
    def __init__(self, responses, *, post_responses=None):
        self.responses = dict(responses)
        self.post_responses = dict(post_responses or {})
        self.calls = []
        self.post_calls = []

    def get(self, url, *, timeout):
        self.calls.append(url)
        value = self.responses.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "text/plain"}, b"missing")
        if isinstance(value, HttpResponse):
            return value
        content, media_type = value
        return HttpResponse(200, url, {"Content-Type": media_type}, content)

    def post(self, url, *, timeout, content, headers=None):
        self.post_calls.append((url, content, dict(headers or {})))
        value = self.post_responses.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "application/json"}, b"{}")
        if isinstance(value, HttpResponse):
            return value
        payload, media_type = value
        return HttpResponse(200, url, {"Content-Type": media_type}, payload)


def _fixture(name):
    return (FIXTURES / name).read_bytes()


def _jpeg_bytes():
    buffer = io.BytesIO()
    image = Image.new("RGB", (3, 2), (230, 230, 230))
    image.putpixel((1, 0), (80, 80, 80))
    image.putpixel((1, 1), (120, 120, 120))
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _motion_jpeg(index):
    buffer = io.BytesIO()
    image = Image.new(
        "RGB",
        (8, 8),
        (index % 251, (index * 7) % 251, (index * 13) % 251),
    )
    image.putpixel((index % 8, (index // 8) % 8), (255, 255, 255))
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _progressive_source_responses(audit, source_root, *, version, workshop=False):
    by_batch = {}
    for frame in audit["frames"]:
        by_batch.setdefault(frame["batch"], []).append(frame)
    bootstrap = {
        "width": 8,
        "height": 8,
        "quality": 4,
        "version": version,
        "scramble": audit["encrypted_scramble"],
        "image": base64.b64encode(_motion_jpeg(0)).decode("ascii"),
    }
    metadata_url = source_root + "/0.json" + ("?version=" if workshop else "")
    responses = {
        metadata_url: (
            json.dumps(bootstrap, separators=(",", ":")).encode(),
            "application/json",
        )
    }
    for batch in range(1, 8):
        frames = sorted(by_batch[batch], key=lambda item: item["stored_position"])
        encoded = [
            base64.b64encode(_motion_jpeg(frame["source_index"])).decode("ascii")
            for frame in frames
        ]
        responses[f"{source_root}/{batch}.json?version={version}"] = (
            json.dumps(encoded, separators=(",", ":")).encode(),
            "application/json",
        )
    return responses


def _loupe_payload(report, viewer, *, cert_id):
    return json.dumps(
        {
            "data": {
                "certificate_by_cert_number": {
                    "id": cert_id,
                    "certNumber": report,
                    "lab": "IGI",
                    "image": None,
                    "video": f"https://loupe360.com/diamond/{cert_id}/video/500/500",
                    "pdfUrl": f"https://example.test/{report}.pdf",
                    "v360": {
                        "url": viewer,
                        "frame_count": 256,
                        "top_index": "252",
                        "id": f"motion-{cert_id}",
                    },
                }
            }
        },
        separators=(",", ":"),
    ).encode()


def _pdf_bytes(
    *,
    report,
    shape,
    carat,
    colour,
    clarity,
    dimensions,
    include_report=True,
):
    lines = [
        "INTERNATIONAL GEMOLOGICAL INSTITUTE",
        "LABORATORY GROWN DIAMOND REPORT",
    ]
    if include_report:
        lines.append(f"REPORT NUMBER {report}")
    lines.extend(
        [
            f"SHAPE AND CUT {shape}",
            "MEASUREMENTS " + " x ".join(str(value) for value in dimensions) + " mm",
            f"CARAT WEIGHT {carat} Carats",
            f"COLOR GRADE {colour}",
            f"CLARITY GRADE {clarity}",
        ]
    )
    stream = ["BT", "/F1 10 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            stream.append("0 -16 Td")
        stream.append(f"({escaped}) Tj")
    stream.append("ET")
    stream_bytes = "\n".join(stream).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream_bytes)
        + stream_bytes
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def _diyona_pdf(report="LG800667394", include_report=True):
    return _pdf_bytes(
        report=report,
        shape="ROUND BRILLIANT",
        carat="3.05",
        colour="E",
        clarity="VVS2",
        dimensions=("9.23", "9.28", "5.74"),
        include_report=include_report,
    )


def _qd_pdf(report="LG713574578", include_report=True):
    return _pdf_bytes(
        report=report,
        shape="OVAL BRILLIANT",
        carat="3.32",
        colour="D",
        clarity="VVS1",
        dimensions=("12.00", "8.46", "5.13"),
        include_report=include_report,
    )


class CertificateOnlyPolicy:
    def select(self, listing, reference):
        return reference.kind == CERTIFICATE

    def assess_completion(self, listing, evidence, attempts, comparisons):
        outcomes = {item.field: item.outcome for item in comparisons}
        certificate_ok = any(
            item.kind == CERTIFICATE and item.status == EvidenceStatus.SUCCESS
            for item in evidence
        )
        complete = (
            certificate_ok
            and outcomes.get("report_number") == IdentityOutcome.AGREEMENT
            and outcomes.get("lab") == IdentityOutcome.AGREEMENT
        )
        return CompletionAssessment(
            complete,
            () if complete else ("matched certificate required",),
        )


class RetailerProviderTests(unittest.TestCase):
    def test_diyona_exact_url_fixture(self):
        http = FakeHttpClient(
            {
                DIYONA_URL: (
                    _fixture("diyona-detail.html"),
                    "text/html; charset=utf-8",
                )
            }
        )
        record = DiyonaListingProvider(http).fetch(DIYONA_URL)
        self.assertEqual(record.metadata.retailer_sku, "B934F4533")
        self.assertEqual(record.metadata.report_number, "LG800667394")
        self.assertEqual(record.metadata.shape, "Round")
        self.assertEqual(str(record.metadata.carat), "3.05")
        self.assertEqual(record.metadata.colour, "E")
        self.assertEqual(record.metadata.clarity, "VVS2")
        self.assertEqual(record.metadata.dimensions, (9.23, 9.28, 5.74))
        self.assertEqual(str(record.metadata.price), "724.45")
        self.assertEqual(record.metadata.currency, "USD")
        self.assertEqual(
            record.metadata.tax_basis, "displayed price; tax basis not stated"
        )
        self.assertEqual(
            [ref.kind for ref in record.references],
            [CERTIFICATE, ROTATION, VIDEO],
        )
        self.assertIn("[redacted]", record.raw_responses[0].body)
        self.assertNotIn("fixture-public-key", record.raw_responses[0].body)

    def test_quality_diamonds_exact_url_fixture(self):
        http = FakeHttpClient(
            {
                QD_URL: (
                    _fixture("quality-diamonds-detail.html"),
                    "text/html; charset=utf-8",
                )
            }
        )
        record = QualityDiamondsListingProvider(http).fetch(QD_URL)
        self.assertEqual(record.metadata.retailer_sku, "133/F74D0EF67")
        self.assertEqual(record.metadata.report_number, "LG713574578")
        self.assertEqual(record.metadata.shape, "Oval")
        self.assertEqual(str(record.metadata.carat), "3.32")
        self.assertEqual(record.metadata.origin, "lab-grown")
        self.assertEqual(record.metadata.dimensions, (12.0, 8.46, 5.13))
        self.assertEqual(str(record.metadata.price), "1330.00")
        self.assertEqual(record.metadata.currency, "GBP")
        self.assertEqual(record.metadata.tax_basis, "inc. VAT")
        self.assertEqual(str(record.metadata.extra["price_ex_vat_gbp"]), "1108.33")
        self.assertEqual(
            [ref.kind for ref in record.references],
            [CERTIFICATE, STILL, ROTATION, VIDEO],
        )
        self.assertEqual(record.references[1].locator, QD_STILL)

    def test_direct_supplier_viewer_on_listing_is_preserved_without_loupe_inference(self):
        direct = "https://d360.tech/view.html?d=DIRECT-D360-1"
        html = _fixture("diyona-detail.html").decode().replace(
            "</body>",
            f'<iframe src="{direct}"></iframe></body>',
        ).encode()
        http = FakeHttpClient(
            {DIYONA_URL: (html, "text/html; charset=utf-8")}
        )
        record = DiyonaListingProvider(http).fetch(DIYONA_URL)
        motion = next(ref for ref in record.references if ref.kind == ROTATION)
        self.assertEqual(motion.locator, direct)
        self.assertEqual(motion.retrieval_key, direct)
        self.assertNotEqual(
            motion.metadata.get("resolver"),
            "loupe360_certificate",
        )

    def test_providers_reject_non_exact_routes(self):
        http = FakeHttpClient({})
        diyona = DiyonaListingProvider(http)
        quality = QualityDiamondsListingProvider(http)
        self.assertFalse(diyona.supports("https://diyona.com/pages/diamond-detail"))
        self.assertFalse(diyona.supports("https://diyona.com/search?sku=B934F4533"))
        self.assertFalse(
            quality.supports("https://www.qualitydiamonds.co.uk/loose-diamonds")
        )


class RetailerEndToEndTests(unittest.TestCase):
    def qd_http(self, *, pdf=None, pdf_status=200):
        pdf_url = "https://api.igi.org/viewpdf.php?r=LG713574578"
        viewer = "https://v3603703.v360.in/vision360.html?d=QD-TEST-713574578"
        root = "https://v3603703.v360.in/imaged/QD-TEST-713574578"
        responses = {
            QD_URL: (
                _fixture("quality-diamonds-detail.html"),
                "text/html; charset=utf-8",
            ),
            QD_STILL: (_jpeg_bytes(), "image/jpeg"),
            **_progressive_source_responses(
                MOTION_AUDITS[1], root, version=2, workshop=True
            ),
        }
        if pdf_status == 200:
            responses[pdf_url] = (pdf if pdf is not None else _qd_pdf(), "application/pdf")
        else:
            responses[pdf_url] = HttpResponse(
                pdf_status, pdf_url, {"Content-Type": "text/plain"}, b"missing"
            )
        return FakeHttpClient(
            responses,
            post_responses={
                GRAPHQL_URL: (
                    _loupe_payload(
                        "LG713574578",
                        viewer,
                        cert_id="qd-fixture-certificate",
                    ),
                    "application/json",
                )
            },
        )

    def diyona_http(self, *, pdf=None):
        pdf_url = "https://api.igi.org/viewpdf.php?r=LG800667394"
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-TEST-800667394"
        root = "https://vision.diajewel360.com/imaged/VL-TEST-800667394"
        responses = {
            DIYONA_URL: (
                _fixture("diyona-detail.html"),
                "text/html; charset=utf-8",
            ),
            pdf_url: (
                pdf if pdf is not None else _diyona_pdf(),
                "application/pdf",
            ),
            **_progressive_source_responses(
                MOTION_AUDITS[0], root, version=1
            ),
        }
        return FakeHttpClient(
            responses,
            post_responses={
                GRAPHQL_URL: (
                    _loupe_payload(
                        "LG800667394",
                        viewer,
                        cert_id="diyona-fixture-certificate",
                    ),
                    "application/json",
                )
            },
        )

    @staticmethod
    def add_listing_media(http, *tags):
        html, media_type = http.responses[QD_URL]
        http.responses[QD_URL] = (
            html.replace(b"</body>", ("".join(tags) + "</body>").encode()),
            media_type,
        )

    def test_two_direct_supplier_rotations_are_retained(self):
        http = self.qd_http()
        dia_viewer = "https://vision.diajewel360.com/Vision360.html?d=MULTI-A-1"
        dia_root = "https://vision.diajewel360.com/imaged/MULTI-A-1"
        core_viewer = "https://v3603703.v360.in/vision360.html?d=MULTI-B-1"
        core_root = "https://v3603703.v360.in/imaged/MULTI-B-1"
        self.add_listing_media(
            http,
            f'<iframe src="{dia_viewer}"></iframe>',
            f'<iframe src="{core_viewer}"></iframe>',
            f'<a href="{dia_viewer}">duplicate link</a>',
        )
        http.responses.update(
            _progressive_source_responses(MOTION_AUDITS[0], dia_root, version=1)
        )
        http.responses.update(
            _progressive_source_responses(
                MOTION_AUDITS[1], core_root, version=2, workshop=True
            )
        )
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 2)
        self.assertEqual([x.metadata["supplier"] for x in result.rotations], ["diajewel", "core360"])
        self.assertTrue(all(len(x.frames) == 256 for x in result.rotations))
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(len(http.post_calls), 0)
        self.assertEqual(http.calls.count(dia_root + "/0.json"), 1)

    def test_direct_rotation_and_video_are_both_preserved_and_independently_selectable(self):
        http = self.qd_http()
        viewer = "https://vision.diajewel360.com/Vision360.html?d=ROT-VIDEO-1"
        root = "https://vision.diajewel360.com/imaged/ROT-VIDEO-1"
        self.add_listing_media(
            http,
            f'<iframe src="{viewer}"></iframe>',
            f'<video src="{DIRECT_VIDEO}"></video>',
        )
        http.responses.update(
            _progressive_source_responses(MOTION_AUDITS[0], root, version=1)
        )
        http.responses[DIRECT_VIDEO] = (VIDEO_BYTES, "video/mp4")
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.videos), 1)
        self.assertEqual(result.videos[0].payload, VIDEO_BYTES)
        self.assertEqual(result.videos[0].media_type, "video/mp4")
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(http.calls.count(DIRECT_VIDEO), 1)
        self.assertEqual(len(http.post_calls), 0)

        class ExcludeVideoPolicy(StandardRetrievalPolicy):
            def select(self, listing, reference):
                return reference.kind != VIDEO and super().select(listing, reference)

        other_http = self.qd_http()
        self.add_listing_media(
            other_http,
            f'<iframe src="{viewer}"></iframe>',
            f'<video src="{DIRECT_VIDEO}"></video>',
        )
        other_http.responses.update(
            _progressive_source_responses(MOTION_AUDITS[0], root, version=1)
        )
        config = default_config(other_http)
        from dataclasses import replace
        filtered = retrieve_diamond(
            QD_URL, config=replace(config, policy=ExcludeVideoPolicy())
        )
        self.assertEqual(filtered.status, ResultStatus.COMPLETE)
        self.assertEqual(len(filtered.rotations), 1)
        self.assertEqual(filtered.videos, ())
        self.assertNotIn(DIRECT_VIDEO, other_http.calls)
        self.assertTrue(
            any(x.kind == VIDEO and x.status == EvidenceStatus.NOT_REQUESTED for x in filtered.attempts)
        )

    def test_loupe_record_with_rotation_and_video_downloads_both(self):
        http = self.qd_http()
        payload = json.loads(http.post_responses[GRAPHQL_URL][0])
        payload["data"]["certificate_by_cert_number"]["video"] = DIRECT_VIDEO
        http.post_responses[GRAPHQL_URL] = (
            json.dumps(payload).encode(), "application/json"
        )
        http.responses[DIRECT_VIDEO] = (VIDEO_BYTES, "video/mp4")
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.videos), 1)
        self.assertEqual(result.videos[0].payload, VIDEO_BYTES)
        self.assertEqual(len(http.post_calls), 1)

    def test_video_only_policy_resolves_loupe_without_downloading_rotation(self):
        http = self.qd_http()
        payload = json.loads(http.post_responses[GRAPHQL_URL][0])
        payload["data"]["certificate_by_cert_number"]["video"] = DIRECT_VIDEO
        http.post_responses[GRAPHQL_URL] = (
            json.dumps(payload).encode(), "application/json"
        )
        http.responses[DIRECT_VIDEO] = (VIDEO_BYTES, "video/mp4")

        class VideoOnlyMotionPolicy(StandardRetrievalPolicy):
            def select(self, listing, reference):
                return reference.kind in {CERTIFICATE, VIDEO}

        from dataclasses import replace
        result = retrieve_diamond(
            QD_URL,
            config=replace(default_config(http), policy=VideoOnlyMotionPolicy()),
        )
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(len(result.videos), 1)
        self.assertEqual(result.rotations, ())
        self.assertEqual(len(http.post_calls), 1)
        self.assertFalse(any("/0.json" in url for url in http.calls))
        self.assertEqual(http.calls.count(DIRECT_VIDEO), 1)
        self.assertTrue(
            any(x.kind == ROTATION and x.status == EvidenceStatus.NOT_REQUESTED for x in result.attempts)
        )

    def test_listing_and_loupe_duplicate_asset_download_once_and_keep_both_sources(self):
        http = self.qd_http()
        core_viewer = "https://v3603703.v360.in/vision360.html?d=QD-TEST-713574578"
        root = "https://v3603703.v360.in/imaged/QD-TEST-713574578"
        loupe = "https://loupe360.com/diamond/qd-fixture-certificate"
        self.add_listing_media(
            http,
            f'<iframe src="{core_viewer}"></iframe>',
            f'<a href="{loupe}">Loupe</a>',
        )
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(http.calls.count(root + "/0.json?version="), 1)
        self.assertTrue(
            any(x.status == EvidenceStatus.DUPLICATE and x.kind == ROTATION for x in result.attempts)
        )
        sources = {step.source for step in result.rotations[0].provenance}
        self.assertIn("quality_diamonds_listing", sources)
        self.assertIn("loupe360_exact_certificate", sources)

    def test_second_supported_media_failure_keeps_first_and_marks_partial(self):
        http = self.qd_http()
        core_viewer = "https://v3603703.v360.in/vision360.html?d=QD-TEST-713574578"
        self.add_listing_media(
            http,
            f'<iframe src="{core_viewer}"></iframe>',
            f'<video src="{DIRECT_VIDEO}"></video>',
        )
        # Deliberately no video response; fake HTTP returns 404.
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(result.videos, ())
        failures = [
            x for x in result.attempts
            if x.kind == VIDEO and x.status == EvidenceStatus.DOWNLOAD_FAILED or
            x.kind == VIDEO and x.status == EvidenceStatus.MISSING
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].locator, DIRECT_VIDEO)

    def test_default_composition_quality_diamonds_returns_complete_ordered_motion(self):
        http = self.qd_http()
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(len(result.stills), 1)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(result.certificates[0].payload, _qd_pdf())
        self.assertEqual(result.stills[0].payload, _jpeg_bytes())
        self.assertEqual(result.stills[0].dimensions, (3, 2))
        rotation = result.rotations[0]
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual(
            [frame.source_index for frame in rotation.frames],
            list(range(256)),
        )
        self.assertEqual(rotation.metadata["supplier"], "core360")
        self.assertEqual(len(http.post_calls), 1)
        outcomes = {item.field: item.outcome for item in result.identity_comparisons}
        for field in (
            "report_number",
            "lab",
            "origin",
            "shape",
            "carat",
            "colour",
            "clarity",
            "dimensions",
        ):
            self.assertEqual(outcomes[field], IdentityOutcome.AGREEMENT)

    def test_default_composition_diyona_returns_complete_ordered_motion(self):
        http = self.diyona_http()
        result = retrieve_diamond(DIYONA_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(result.certificates[0].extracted_fields["report_number"], "LG800667394")
        self.assertEqual(result.rotations[0].metadata["supplier"], "diajewel")
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(len(http.post_calls), 1)
        outcomes = {item.field: item.outcome for item in result.identity_comparisons}
        self.assertEqual(outcomes["shape"], IdentityOutcome.AGREEMENT)
        self.assertEqual(outcomes["report_number"], IdentityOutcome.AGREEMENT)

    def test_certificate_only_policy_is_complete_and_never_fetches_still_or_motion(self):
        http = self.qd_http()
        config = default_config(http)
        config = type(config)(
            providers=config.providers,
            resolvers=config.resolvers,
            policy=CertificateOnlyPolicy(),
            downloaders=config.downloaders,
            processors=config.processors,
            identity_validator=config.identity_validator,
            assembler=config.assembler,
            max_resolution_depth=config.max_resolution_depth,
        )
        result = retrieve_diamond(QD_URL, config=config)
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(
            http.calls,
            [
                QD_URL,
                "https://api.igi.org/viewpdf.php?r=LG713574578",
            ],
        )
        statuses = {item.kind: item.status for item in result.attempts if item.status == EvidenceStatus.NOT_REQUESTED}
        self.assertEqual(statuses[STILL], EvidenceStatus.NOT_REQUESTED)
        self.assertEqual(statuses[ROTATION], EvidenceStatus.NOT_REQUESTED)

    def test_mismatched_certificate_raises_source_linked_identity_error(self):
        http = self.qd_http(pdf=_qd_pdf(report="LG999999999"))
        with self.assertRaises(IdentityConflictError) as caught:
            retrieve_diamond(QD_URL, config=default_config(http))
        report = next(
            item for item in caught.exception.comparisons if item.field == "report_number"
        )
        self.assertEqual(report.outcome, IdentityOutcome.CONFLICT)
        locators = {step.locator for step in report.provenance}
        self.assertIn(QD_URL, locators)
        self.assertIn(
            "https://api.igi.org/viewpdf.php?r=LG713574578",
            locators,
        )

    def test_valid_unparseable_pdf_bytes_are_retained_with_extraction_failure(self):
        http = self.qd_http(pdf=_qd_pdf(include_report=False))
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(len(result.certificates), 1)
        self.assertEqual(
            result.certificates[0].status,
            EvidenceStatus.EXTRACTION_FAILED,
        )
        self.assertTrue(result.certificates[0].payload.startswith(b"%PDF-"))
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertIn(
            EvidenceStatus.EXTRACTION_FAILED,
            [attempt.status for attempt in result.attempts],
        )

    def test_igi_403_preserves_verification_link_and_partial_status(self):
        http = self.qd_http(pdf_status=403)
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertEqual(result.certificates, ())
        self.assertEqual(
            result.certificate_link,
            "https://www.igi.org/verify-your-report/?r=LG713574578",
        )
        self.assertEqual(len(result.stills), 1)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        failed = [
            attempt
            for attempt in result.attempts
            if attempt.kind == CERTIFICATE and attempt.status == EvidenceStatus.DOWNLOAD_FAILED
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(
            failed[0].locator,
            "https://api.igi.org/viewpdf.php?r=LG713574578",
        )
        self.assertIn("HTTP 403", failed[0].message)

    def test_direct_listing_motion_skips_loupe_resolution(self):
        http = self.qd_http()
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-DIRECT-713574578"
        root = "https://vision.diajewel360.com/imaged/VL-DIRECT-713574578"
        html, content_type = http.responses[QD_URL]
        http.responses[QD_URL] = (
            html.replace(b"</body>", f'<iframe src="{viewer}"></iframe></body>'.encode()),
            content_type,
        )
        http.responses.update(_progressive_source_responses(MOTION_AUDITS[0], root, version=1))
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(result.rotations[0].metadata["supplier"], "diajewel")
        self.assertEqual(len(http.post_calls), 0)

    def test_missing_pdf_preserves_useful_partial_listing_and_still(self):
        http = self.qd_http(pdf_status=404)
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.metadata.report_number, "LG713574578")
        self.assertEqual(len(result.certificates), 0)
        self.assertEqual(len(result.stills), 1)
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertEqual(
            result.certificate_link,
            "https://www.igi.org/verify-your-report/?r=LG713574578",
        )
        self.assertIn(
            EvidenceStatus.MISSING,
            [attempt.status for attempt in result.attempts],
        )


if __name__ == "__main__":
    unittest.main()
