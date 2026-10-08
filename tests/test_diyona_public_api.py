"""Regression coverage for API-primary, no-browser Diyona exact-SKU ingestion."""
from __future__ import annotations

import json
import unittest
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from diamond_retrieval.errors import RetrievalError
from diamond_retrieval.protocols import HttpResponse
from diamond_retrieval.retailers import DiyonaListingProvider

SKU = "A69835AA4"
REPORT = "LG816611062"
URL = f"https://diyona.com/pages/diamond-detail?sku={SKU}"
API_BASE = "https://ofjwrrqzzbcnmkkmlawl.supabase.co"
TEST_ANON = "public-testing-anon-key-not-a-secret-abcdefghijklmnopqrstuvwxyz123"
SHELL = (
    f"<html><script>var SUPABASE_URL = '{API_BASE}';"
    f"var SUPABASE_ANON = '{TEST_ANON}';</script>"
    "<body>Loading 360 View</body></html>"
).encode()
STONE = {
    "sku": SKU, "certificate_number": REPORT,
    "certificate_url": f"https://dnyvsyhu34v1w.cloudfront.net/pdf/{REPORT}.pdf",
    "lab": "IGI", "carat": 2.07, "shape": "Asscher",
    "color": "E", "clarity": "VS1", "cut": None,
    "polish": "EX", "symmetry": "EX", "fluorescence": "NONE",
    "length": 7.11, "width": 7.08, "depth_mm": 4.75,
    "depth_percent": 67.1, "table_percent": 61, "ratio": 1.00,
    "markup_price": 829.99,
    "image_url": "https://example.com/exact-stone.jpg",
    "video_url": "https://vision.diajewel360.com/Vision360.html?d=EXACT-STONE",
}


class PublicApiHttp:
    def __init__(self, rows=None, *, html=SHELL, api_status=200, api_content=None):
        self.rows = [STONE] if rows is None else rows
        self.html = html
        self.api_status = api_status
        self.api_content = api_content
        self.calls = []

    def get(self, url, *, timeout, headers=None):
        self.calls.append((url, dict(headers or {})))
        if url == URL:
            return HttpResponse(200, url, {"Content-Type": "text/html"}, self.html)
        parsed = urlsplit(url)
        if parsed.hostname != "ofjwrrqzzbcnmkkmlawl.supabase.co":
            raise AssertionError("Unexpected URL")
        args = parse_qs(parsed.query)
        assert parsed.path == "/rest/v1/public_diamonds"
        assert args.get("sku") == ["eq."+SKU]
        assert args.get("limit") == ["2"]
        assert "certificate_number" in args.get("select", [""])[0]
        assert headers.get("apikey") == TEST_ANON
        assert headers.get("Authorization") == "Bearer "+TEST_ANON
        data = self.api_content if self.api_content is not None else json.dumps(self.rows).encode()
        return HttpResponse(self.api_status, url, {"Content-Type": "application/json"}, data)


class ApiPrimaryDiyonaTests(unittest.TestCase):
    def test_exact_stone_and_igi_recovered_without_rendered_html(self):
        http = PublicApiHttp()
        record = DiyonaListingProvider(http).fetch(URL)
        self.assertEqual(len(http.calls), 2)
        self.assertEqual(record.metadata.retailer_sku, SKU)
        self.assertEqual(record.metadata.report_number, REPORT)
        self.assertEqual(record.metadata.lab, "IGI")
        self.assertEqual(record.metadata.shape, "Asscher")
        self.assertEqual(record.metadata.carat, Decimal("2.07"))
        self.assertEqual(record.metadata.colour, "E")
        self.assertEqual(record.metadata.clarity, "VS1")
        self.assertEqual(record.metadata.dimensions, (7.11, 7.08, 4.75))
        self.assertEqual(record.metadata.price, Decimal("829.99"))
        self.assertEqual(record.metadata.reported_proportions["table_percent"], 61.0)
        self.assertEqual(record.metadata.attribution["report_number"].source,
                         "diyona_public_diamonds")
        self.assertIsNone(record.metadata.origin)  # No unsupported lab-grown inference.
        self.assertEqual([str(r.kind) for r in record.references],
                         ["certificate", "still", "rotation"])
        self.assertEqual(record.references[0].locator, STONE["certificate_url"])
        self.assertEqual(record.references[2].locator, STONE["video_url"])

    def test_does_not_store_public_key_or_shopify_html(self):
        record = DiyonaListingProvider(PublicApiHttp()).fetch(URL)
        self.assertEqual(len(record.raw_responses), 2)
        all_text = "\n".join(str(x.body) for x in record.raw_responses)
        self.assertNotIn(TEST_ANON, all_text)
        self.assertNotIn("SUPABASE_ANON", all_text)
        self.assertIn(REPORT, all_text)
        self.assertNotIn("apikey", str(record.metadata.attribution))

    def test_api_path_is_primary_even_when_html_has_confusing_header(self):
        html = SHELL.replace(b"Loading 360 View",
                             b"<h1>9ct Round Lab Diamond</h1>"
                             b"<div>SKU: A69835AA4 - IGI LG999999999</div>")
        record = DiyonaListingProvider(PublicApiHttp(html=html)).fetch(URL)
        self.assertEqual(record.metadata.report_number, REPORT)
        self.assertEqual(record.metadata.shape, "Asscher")

    def test_missing_row_rejected_no_guesses(self):
        with self.assertRaisesRegex(RetrievalError, "exactly one"):
            DiyonaListingProvider(PublicApiHttp(rows=[])).fetch(URL)

    def test_duplicate_rows_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "exactly one"):
            DiyonaListingProvider(PublicApiHttp(rows=[STONE, STONE])).fetch(URL)

    def test_wrong_sku_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "SKU does not match"):
            DiyonaListingProvider(PublicApiHttp(rows=[{**STONE, "sku": "WRONG"}])).fetch(URL)

    def test_bad_certificate_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "full IGI report"):
            DiyonaListingProvider(PublicApiHttp(rows=[{**STONE, "certificate_number": ""}])).fetch(URL)

    def test_wrong_lab_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "incompatible"):
            DiyonaListingProvider(PublicApiHttp(rows=[{**STONE, "lab": "GIA"}])).fetch(URL)

    def test_invalid_json_rejected(self):
        with self.assertRaisesRegex(RetrievalError, "invalid JSON"):
            DiyonaListingProvider(PublicApiHttp(api_content=b"not-json")).fetch(URL)

    def test_access_denied_remains_denied(self):
        with self.assertRaisesRegex(RetrievalError, "HTTP 403"):
            DiyonaListingProvider(PublicApiHttp(api_status=403)).fetch(URL)

    def test_refuses_unapproved_api_host(self):
        html = SHELL.replace(b"ofjwrrqzzbcnmkkmlawl.supabase.co", b"evil.example.test")
        record_url = PublicApiHttp(html=html)
        with self.assertRaisesRegex(RetrievalError, "certificate-bound"):
            DiyonaListingProvider(record_url).fetch(URL)
        self.assertEqual(len(record_url.calls), 1)

    def test_nan_and_bad_numeric_fields_are_not_guessed(self):
        stone = {**STONE, "markup_price": "NaN", "carat": "garbage",
                 "length": "oops", "depth_percent": "Infinity"}
        record = DiyonaListingProvider(PublicApiHttp(rows=[stone])).fetch(URL)
        self.assertIsNone(record.metadata.price)
        self.assertIsNone(record.metadata.carat)
        self.assertIsNone(record.metadata.dimensions)
        self.assertNotIn("depth_percent", record.metadata.reported_proportions)

    def test_unverified_pdf_locator_uses_exact_igi_resolver(self):
        stone = {**STONE, "certificate_url": "https://example.com/different.pdf"}
        record = DiyonaListingProvider(PublicApiHttp(rows=[stone])).fetch(URL)
        self.assertEqual(record.references[0].retrieval_key, "igi-report:"+REPORT)
        self.assertEqual(record.references[0].metadata["resolver"], "igi_exact_report")

    def test_api_without_settings_falls_back_to_legacy_static_parser(self):
        old = (
            "<h1>1.01ct Asscher Lab Diamond</h1>"
            "<div>SKU: A69835AA4 · IGI LG816611062</div>"
        ).encode()
        http = PublicApiHttp(html=old)
        record = DiyonaListingProvider(http).fetch(URL)
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(record.metadata.report_number, REPORT)
        self.assertEqual(record.metadata.shape, "Asscher")


if __name__ == "__main__":
    unittest.main()
