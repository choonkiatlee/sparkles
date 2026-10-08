"""Fixture-driven checks for client-rendered Diyona exact-listing fallback.

These tests do not pretend to have captured the live page for SKU A69835AA4.
The synthetic response deliberately models a JS shell and a rendered DOM
containing the certified SKU + IGI report shown in a browser.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from diamond_catalogue.diyona_browser import (
    RenderedDiyonaListingProvider, _is_safe_request,
)
from diamond_catalogue.publish import retrieve_for_publication, safe_failure
from diamond_retrieval.errors import RetrievalError
from diamond_retrieval.protocols import HttpResponse
from diamond_retrieval.retailers import DiyonaListingProvider
from tests.test_diamond_retrieval_retailers import DIYONA_URL

URL = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"
IDENTITY_ONLY = (
    "<html><body><span>SKU: A69835AA4  ·  IGI LG816611062</span>"
    "<div>Lab Grown</div><div>360° View</div></body></html>"
).encode("utf-8")
FULL_RENDERED = (
    "<html><body><h1>2.02ct Asscher Lab Diamond</h1>"
    "<span>SKU: A69835AA4  ·  IGI LG816611062</span>"
    "<div>Color D</div><div>Clarity VS1</div>"
    "<div>Dimensions 7.10 x 7.10 x 4.20 mm</div>"
    "</body></html>"
).encode("utf-8")
SHELL = (
    b"<html><body><h1>Diamond Detail</h1>"
    b"<div id='diamond-root'>Loading...</div></body></html>"
)

class Http:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(url)
        return HttpResponse(
            status_code=self.status, url=url,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=self.payload,
        )


class RenderedListingTests(unittest.TestCase):
    def test_explicit_igi_sku_identity_without_heading_is_retrievable(self):
        result = DiyonaListingProvider(Http(IDENTITY_ONLY)).fetch(URL)
        self.assertEqual(result.metadata.lab, "IGI")
        self.assertEqual(result.metadata.report_number, "LG816611062")
        self.assertEqual(result.metadata.retailer_sku, "A69835AA4")
        self.assertIsNone(result.metadata.shape)
        self.assertIsNone(result.metadata.carat)
        self.assertEqual(result.references[0].metadata["report_number"], "LG816611062")

    def test_static_html_preserved_without_invoking_browser(self):
        renders = []
        def render(url, *, timeout):
            renders.append(url)
            return FULL_RENDERED
        result = RenderedDiyonaListingProvider(Http(IDENTITY_ONLY), renderer=render).fetch(URL)
        self.assertEqual(result.metadata.report_number, "LG816611062")
        self.assertEqual(renders, [])

    def test_javascript_shell_is_recovered_from_rendered_dom_snapshot(self):
        renders = []
        def render(url, *, timeout):
            renders.append(url)
            return FULL_RENDERED
        http = Http(SHELL)
        result = RenderedDiyonaListingProvider(http, renderer=render).fetch(URL)
        self.assertEqual(renders, [URL])
        self.assertEqual(result.metadata.report_number, "LG816611062")
        self.assertEqual(result.metadata.retailer_sku, "A69835AA4")
        self.assertEqual(result.metadata.shape, "Asscher")
        self.assertEqual(str(result.metadata.carat), "2.02")
        self.assertIn("SKU: A69835AA4", result.raw_responses[0].body)
        self.assertEqual(http.calls, [URL])

    def test_rendered_page_missing_identity_remains_rejected(self):
        provider = RenderedDiyonaListingProvider(Http(SHELL), renderer=lambda url, timeout: SHELL)
        with self.assertRaisesRegex(RetrievalError, "certificate-bound"):
            provider.fetch(URL)

    def test_rendered_page_other_sku_fails_closed(self):
        mismatch = FULL_RENDERED.replace(b"A69835AA4", b"WRONG3333")
        provider = RenderedDiyonaListingProvider(Http(SHELL), renderer=lambda url, timeout: mismatch)
        with self.assertRaisesRegex(RetrievalError, "SKU does not match"):
            provider.fetch(URL)

    def test_http_403_not_bypassed_by_browser(self):
        renders = []
        provider = RenderedDiyonaListingProvider(
            Http(SHELL, status=403),
            renderer=lambda url, timeout: renders.append(url),
        )
        with self.assertRaisesRegex(RetrievalError, "HTTP 403"):
            provider.fetch(URL)
        self.assertEqual(renders, [])

    def test_browser_fallback_limited_to_exact_diyona_url(self):
        for url in (
            "https://127.0.0.1/secret",
            "http://localhost/internal",
            "https://169.254.169.254/latest/meta-data",
            "file:///etc/passwd",
        ):
            self.assertFalse(_is_safe_request(url))
        self.assertTrue(_is_safe_request("https://diyona.com/pages/diamond-detail?sku=X"))

    def test_publisher_public_retriever_injects_diyona_provider_only_for_diyona(self):
        with patch("diamond_catalogue.publish.retrieve_diamond", return_value="result") as retrieve:
            self.assertEqual(retrieve_for_publication(URL), "result")
            args, kwargs = retrieve.call_args
            self.assertEqual(args, (URL,))
            self.assertTrue(any(isinstance(x, RenderedDiyonaListingProvider)
                                for x in kwargs["config"].providers))
            self.assertEqual(retrieve_for_publication("https://example.com/unrecognized"), "result")
            args, kwargs = retrieve.call_args
            self.assertNotIn("config", kwargs)

    def test_browser_timeout_has_safe_fixed_diagnostic(self):
        from diamond_catalogue.diyona_browser import _NO_IDENTITY
        cause = RetrievalError(_NO_IDENTITY)
        try:
            raise RetrievalError("Listing retrieval failed for /secret?token=redact") from cause
        except RetrievalError as exc:
            code, hint = safe_failure(exc)
        self.assertEqual(code, "listing_render_missing_identity")
        self.assertNotIn("token", hint)


if __name__ == "__main__":
    unittest.main()
