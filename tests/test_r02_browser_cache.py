"""Network-free source and identity regressions for one audited R02 cache."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from diamond_retrieval import r02_browser_cache as cache
from diamond_retrieval.loupe360_proxy import Loupe360ProxyRotationDownloader
from diamond_retrieval.models import (
    ROTATION, DiamondMetadata, EvidenceReference, ListingRecord, ProvenanceStep,
)
from diamond_retrieval.resolvers import Loupe360CertificateResolver

TOKEN = base64.urlsafe_b64encode(cache.SUPPLIER_VIEWER.encode()).decode().rstrip("=")
ROOT = "https://assets-images.pixorac.com/" + TOKEN + "/500"
MOCK_HASH = hashlib.sha256(ROOT.encode()).hexdigest()


def reference(**extra):
    return EvidenceReference(
        identifier="ps285166-r02:loupe-report:r02-browser-cache",
        kind=ROTATION, locator=cache.CACHE_REF, retrieval_key=cache.CACHE_REF,
        provenance=(ProvenanceStep("loupe360_exact_certificate",
                                   Loupe360CertificateResolver.endpoint),),
        metadata={
            "reference_id": cache.REFERENCE_ID, "report_number": cache.REPORT,
            "lab": "IGI", "supplier_frame_count": 256,
            "supplier_top_index": 213, "r02_browser_observed_cache": True,
            **extra,
        },
    )


def mock_record(**changes):
    result = {
        "certNumber": cache.REPORT, "lab": "IGI", "id": "exact-record",
        "v360": {"url": cache.SUPPLIER_VIEWER, "frame_count": 256,
                 "top_index": 213},
    }
    result.update(changes)
    return result


class FakeClient:
    def __init__(self, record):
        self.record = record

    def post(self, url, **kwargs):
        return SimpleNamespace(
            status_code=200,
            content=json.dumps({"data": {"certificate_by_cert_number": self.record}}).encode(),
        )


class R02CacheContractTests(unittest.TestCase):
    def test_only_pinned_full_browser_root_is_accepted(self):
        with patch.object(cache, "EXPECTED_ROOT_SHA256", MOCK_HASH):
            self.assertEqual(cache.validate_root(ROOT), ROOT)
            invalid = [
                ROOT.replace("https://", "http://"),
                ROOT + "/extra",
                ROOT + "?any=1",
                ROOT.replace("/500", "/501"),
                ROOT.replace("assets-images.pixorac.com", "evil.example"),
                ROOT.replace(TOKEN, base64.urlsafe_b64encode(b"https://evil.example/").decode()),
                "https://assets-images.pixorac.com/" + TOKEN + "/../500",
            ]
            for url in invalid:
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        cache.validate_root(url)

    def test_cdp_requires_unique_http_200_indexed_browser_request(self):
        def req(ident, url, code):
            return [
                {"method": "Network.requestWillBeSent", "params": {
                    "requestId": ident, "request": {"url": url}}},
                {"method": "Network.responseReceived", "params": {
                    "requestId": ident, "response": {"status": code}}},
            ]
        with patch.object(cache, "EXPECTED_ROOT_SHA256", MOCK_HASH):
            events = req("a", ROOT + "/213.webp", 200)
            self.assertEqual(cache.observed_root_from_browser_events(events), ROOT)
            with self.assertRaises(ValueError):
                cache.observed_root_from_browser_events(req("b", ROOT + "/213.webp", 403))
            with self.assertRaises(ValueError):
                cache.observed_root_from_browser_events(
                    events + req("c", ROOT.replace("/500", "/501") + "/0.webp", 200)
                )

    def test_exact_report_and_generic_source_are_both_required(self):
        original = EvidenceReference(
            identifier="ps285166-r02:loupe-report", kind=ROTATION,
            retrieval_key="loupe360-report:" + cache.REPORT,
            locator="loupe360-report:" + cache.REPORT,
            metadata={"resolver": "loupe360_certificate", "lab": "IGI",
                      "report_number": cache.REPORT},
        )
        listing = ListingRecord(
            url="reference:ps285166-r02",
            metadata=DiamondMetadata(lab="IGI", report_number=cache.REPORT),
        )
        for rec, expected in (
            (mock_record(), True),
            (mock_record(v360={"url": cache.SUPPLIER_VIEWER + "?d=guessed",
                               "frame_count": 256, "top_index": 213}), False),
            (mock_record(v360={"url": cache.SUPPLIER_VIEWER,
                               "frame_count": 255, "top_index": 213}), False),
            (mock_record(v360={"url": cache.SUPPLIER_VIEWER,
                               "frame_count": 256, "top_index": 200}), False),
        ):
            resolver = Loupe360CertificateResolver(FakeClient(rec))
            refs = resolver.resolve(listing, original)
            matches = [r for r in refs if r.locator == cache.CACHE_REF]
            self.assertEqual(bool(matches), expected)
            if matches:
                self.assertEqual(matches[0].metadata["report_number"], cache.REPORT)
                self.assertEqual(matches[0].metadata["supplier_top_index"], 213)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            Loupe360CertificateResolver(
                FakeClient(mock_record(certNumber="LG634479986"))
            ).resolve(listing, original)

    def test_downloader_fails_closed_without_browser_or_valid_certificate(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(Loupe360ProxyRotationDownloader(object()).supports(reference()))
        with patch.dict(os.environ, {"R02_PIXORAC_ROOT": ROOT}):
            with patch.object(cache, "EXPECTED_ROOT_SHA256", MOCK_HASH):
                dl = Loupe360ProxyRotationDownloader(object())
                self.assertTrue(dl.supports(reference()))
                self.assertFalse(dl.supports(reference(lab="GIA")))
                self.assertFalse(dl.supports(reference(supplier_frame_count=255)))
                self.assertFalse(dl.supports(reference(r02_browser_observed_cache=False)))
        with patch.dict(os.environ, {"R02_PIXORAC_ROOT": ROOT.replace("/500", "/501")}):
            self.assertFalse(Loupe360ProxyRotationDownloader(object()).supports(reference()))


if __name__ == "__main__":
    unittest.main()
