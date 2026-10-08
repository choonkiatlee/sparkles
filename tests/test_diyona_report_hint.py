"""A visible IGI report is a lightweight, explicitly user-supplied fallback.

No Chromium: exact SKU is in listing URL; full report number is input by user.
Only matched independent IGI certificate or exact Loupe motion can permit
publication when retailer's static page does not contain certified identity.
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from diamond_catalogue.diyona_report_hint import (
    ReportHintDiyonaProvider, normalize_report_hint,
    require_independent_report_corroboration,
)
from diamond_catalogue.models import CatalogueError
from diamond_catalogue.publish import main, retrieve_for_publication, safe_failure
from diamond_retrieval import (
    CERTIFICATE, ROTATION, DiamondMetadata, IdentityComparison,
    IdentityOutcome, ProvenanceStep, EvidenceStatus, default_config, retrieve_diamond,
)
from diamond_retrieval.errors import RetrievalError, UnsupportedInputError
from diamond_retrieval import HttpResponse
from diamond_retrieval.retailers import DiyonaListingProvider
from tests.test_diamond_retrieval_retailers import (
    GRAPHQL_URL, RetailerEndToEndTests, _diyona_pdf, _loupe_payload
)
from tests.test_diamond_catalogue import result as sample_result

URL = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"
REPORT = "LG816611062"
SHELL = b"<html><body><div id='diamond'>Loading...</div></body></html>"
VISIBLE = ("<html><body><span>SKU: A69835AA4 · IGI LG816611062</span>"
           "<div>IGI Certified</div></body></html>").encode()


class FakeHttp:
    def __init__(self, payload=SHELL, status=200):
        self.payload = payload
        self.status = status
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(url)
        return HttpResponse(status_code=self.status, url=url,
                            headers={"Content-Type": "text/html"},
                            content=self.payload)


class ManualIgiHintTests(unittest.TestCase):
    def test_normalize_full_igi_number_not_sku(self):
        self.assertEqual(normalize_report_hint("igi lg816611062"), REPORT)
        for invalid in ("", "A69835AA4", "LG", "LG8166", "IGI 123", "https://example.com"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    normalize_report_hint(invalid)

    def test_page_with_exact_report_needs_no_hint_and_no_heading(self):
        listing = DiyonaListingProvider(FakeHttp(VISIBLE)).fetch(URL)
        self.assertEqual(listing.metadata.report_number, REPORT)
        self.assertIsNone(listing.metadata.carat)
        self.assertIsNone(listing.metadata.shape)
        self.assertEqual(listing.metadata.retailer_sku, "A69835AA4")

    def test_manual_hint_produces_report_bound_references_and_honest_provenance(self):
        http = FakeHttp()
        listing = ReportHintDiyonaProvider(http, report_hint=REPORT).fetch(URL)
        self.assertEqual(http.calls, [URL])
        self.assertEqual(listing.metadata.report_number, REPORT)
        self.assertEqual(listing.metadata.retailer_sku, "A69835AA4")
        self.assertEqual(listing.metadata.attribution["report_number"].source,
                         "user_supplied_igi_report")
        self.assertEqual(listing.provenance[0].details["verified_against_listing"], False)
        self.assertEqual([r.kind for r in listing.references],
                         [CERTIFICATE, ROTATION, "video"])
        self.assertEqual(listing.references[0].retrieval_key, f"igi-report:{REPORT}")
        self.assertEqual(listing.references[1].retrieval_key,
                         listing.references[2].retrieval_key)
        self.assertFalse(listing.raw_responses)

    def test_manual_mismatch_refused_when_static_identity_present(self):
        http = FakeHttp(VISIBLE)
        with self.assertRaisesRegex(RetrievalError, "differs"):
            ReportHintDiyonaProvider(http, report_hint="LG999999999").fetch(URL)

    def test_access_denial_not_bypassed_by_hinted_report(self):
        with self.assertRaisesRegex(RetrievalError, "HTTP 403"):
            ReportHintDiyonaProvider(FakeHttp(status=403), report_hint=REPORT).fetch(URL)

    def test_hint_not_accepted_for_non_diyona_listing(self):
        with self.assertRaisesRegex(UnsupportedInputError, "exact Diyona"):
            retrieve_for_publication("https://example.com/invalid", igi_report=REPORT)

    def test_public_retriever_is_injected_only_with_hint(self):
        with patch("diamond_catalogue.publish.retrieve_diamond", return_value="done") as fetch:
            self.assertEqual(retrieve_for_publication(URL, igi_report=REPORT), "done")
            args, kwargs = fetch.call_args
            self.assertEqual(args, (URL,))
            self.assertTrue(any(isinstance(p, ReportHintDiyonaProvider)
                                for p in kwargs["config"].providers))
            self.assertEqual(retrieve_for_publication(URL), "done")
            self.assertNotIn("config", fetch.call_args.kwargs)

    def test_manual_unverified_identity_blocks_publication(self):
        sample = replace(sample_result(), metadata=DiamondMetadata(
            lab="IGI", report_number=REPORT, retailer_sku="A69835AA4"
        ), provenance=(ProvenanceStep("user_supplied_igi_report", URL),),
            evidence=(), identity_comparisons=())
        with self.assertRaisesRegex(CatalogueError, "lacks independent"):
            require_independent_report_corroboration(sample)
        self.assertEqual(safe_failure(CatalogueError(
            "Explicit IGI hint lacks independent certificate-bound corroboration"
        ))[0], "report_hint_unverified")

    def test_ordinary_listing_is_not_subject_to_manual_hint_gate(self):
        require_independent_report_corroboration(sample_result())

    def test_full_fixture_256_frame_motion_corrobates_manual_report(self):
        test_fixture = RetailerEndToEndTests()
        http = test_fixture.diyona_http()
        http.responses[URL] = (SHELL, "text/html")
        http.responses[f"https://api.igi.org/viewpdf.php?r={REPORT}"] = (
            _diyona_pdf(report=REPORT), "application/pdf"
        )
        viewer = ("https://vision.diajewel360.com/Vision360.html"
                  "?d=VL-TEST-800667394")
        http.post_responses[GRAPHQL_URL] = (
            _loupe_payload(REPORT, viewer, cert_id="manual-report-hint"),
            "application/json"
        )
        config = default_config(http)
        providers = tuple(ReportHintDiyonaProvider(http, report_hint=REPORT)
                          if isinstance(p, DiyonaListingProvider) else p
                          for p in config.providers)
        resolved = retrieve_diamond(URL, config=replace(config, providers=providers))
        self.assertEqual(resolved.metadata.report_number, REPORT)
        self.assertEqual(len(resolved.rotations), 1)
        self.assertEqual(len(resolved.rotations[0].frames), 256)
        require_independent_report_corroboration(resolved)

    def test_igi_blocked_but_exact_loupe_motion_still_corrobates(self):
        fixture = RetailerEndToEndTests()
        http = fixture.diyona_http()
        http.responses[URL] = (SHELL, "text/html")
        old = "https://api.igi.org/viewpdf.php?r=LG800667394"
        new = f"https://api.igi.org/viewpdf.php?r={REPORT}"
        http.responses[new] = HttpResponse(403, new, {"Content-Type": "text/plain"}, b"blocked")
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-TEST-800667394"
        http.post_responses[GRAPHQL_URL] = (
            _loupe_payload(REPORT, viewer, cert_id="manual-report-hint"),
            "application/json"
        )
        config = default_config(http)
        providers = tuple(ReportHintDiyonaProvider(http, report_hint=REPORT)
                          if isinstance(p, DiyonaListingProvider) else p
                          for p in config.providers)
        resolved = retrieve_diamond(URL, config=replace(config, providers=providers))
        self.assertFalse(resolved.certificates)
        self.assertEqual(len(resolved.rotations[0].frames), 256)
        require_independent_report_corroboration(resolved)

    def test_cli_rejects_unverified_report_before_publish_without_url_leak(self):
        sample = replace(sample_result(), metadata=DiamondMetadata(
            lab="IGI", report_number=REPORT
        ), provenance=(ProvenanceStep("user_supplied_igi_report", URL),),
            evidence=(), identity_comparisons=())
        errors = io.StringIO()
        with (
            patch.dict(os.environ, {"DIAMOND_URL": URL, "IGI_REPORT": REPORT,
                                    "GITHUB_REF": "refs/heads/master"}),
            patch("diamond_catalogue.publish.retrieve_for_publication", return_value=sample),
            patch("diamond_catalogue.publish.publish_result") as publish,
            redirect_stderr(errors),
        ):
            code = main([])
        self.assertEqual(code, 1)
        publish.assert_not_called()
        self.assertIn("report_hint_unverified", errors.getvalue())
        self.assertNotIn(URL, errors.getvalue())

    def test_workflow_has_no_browser_install(self):
        workflow = Path(".github/workflows/diamond-catalogue-ingest.yml").read_text()
        self.assertIn("IGI_REPORT:", workflow)
        self.assertNotIn("playwright", workflow.lower())
        self.assertNotIn("chromium", workflow.lower())


if __name__ == "__main__":
    unittest.main()
