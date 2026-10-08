"""First-party read-only Diyona Supabase exact-SKU integration, no browser."""
from __future__ import annotations

import json
import unittest
from urllib.parse import urlencode

from diamond_retrieval import (
    CERTIFICATE, STILL, ROTATION, VIDEO,
    HttpResponse, IdentityOutcome, default_config, retrieve_diamond,
)
from diamond_retrieval.errors import RetrievalError
from diamond_retrieval.retailers import DiyonaListingProvider
from tests.test_diamond_retrieval_retailers import (
    FakeHttpClient, _fixture, _jpeg_bytes, _pdf_bytes,
    _loupe_payload, _progressive_source_responses, MOTION_AUDITS, GRAPHQL_URL,
)

PAGE = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"
BASE = "https://ofjwrrqzzbcnmkkmlawl.supabase.co"
API = BASE + "/rest/v1/public_diamonds?" + urlencode(
    {"select":"*", "sku":"eq.A69835AA4", "limit":"2"}
)
ANON = "public-anon-test-key-with-no-privileged-access-1234567890"
REPORT = "LG816611062"
PDF = "https://dnyvsyhu34v1w.cloudfront.net/pdf/LG816611062.pdf"
IMAGE = "https://assets-images-saas.nivoda.com/test-diyona-stone.jpg"
LOUPE = "https://loupe360.com/diamond/LG816611062/video/500/500"
VIEWER = "https://vision.diajewel360.com/Vision360.html?d=TEST-DIYONA-816611062"
SOURCE = "https://vision.diajewel360.com/imaged/TEST-DIYONA-816611062"
SHELL = (
    "<html><body><span>Loading diamond details...</span>"
    "<script>var SUPABASE_URL = '" + BASE + "';"
    "var SUPABASE_ANON = '" + ANON + "';"
    "sb.from('public_diamonds').select('*').eq('sku',sku).limit(1);"
    "</script></body></html>"
).encode()
ROW = {
    "sku":"A69835AA4", "lab":"IGI", "certificate_number":REPORT,
    "shape":"Asscher", "carat":2.69, "color":"D", "clarity":"VS1",
    "length":7.2,"width":7.1,"depth_mm":5.05, "price_usd":749.77,
    "markup_price":None,"ratio":1.01, "table_percent":65.0,
    "depth_percent":70.1, "certificate_url":PDF,
    "image_url":IMAGE,"video_url":LOUPE,
}


class HTTP(FakeHttpClient):
    def __init__(self, rows=None, *, page=SHELL, status=200,
                 additional=None, post_responses=None):
        vals = {
            PAGE: (page, "text/html"),
            API: HttpResponse(status, API, {"Content-Type":"application/json"},
                              json.dumps([ROW] if rows is None else rows).encode()),
        }
        vals.update(additional or {})
        super().__init__(vals, post_responses=post_responses)
        self.auth_calls=[]

    def get(self, url, *, timeout, headers=None):
        if headers:
            self.auth_calls.append((url, dict(headers)))
        return super().get(url, timeout=timeout)


class DiyonaPublicAPITests(unittest.TestCase):
    def test_primary_lookup_matches_exact_cert_and_retains_media(self):
        http=HTTP()
        result=DiyonaListingProvider(http).fetch(PAGE)
        self.assertEqual(result.metadata.retailer_sku, "A69835AA4")
        self.assertEqual(result.metadata.report_number, REPORT)
        self.assertEqual(result.metadata.shape, "Asscher")
        self.assertEqual(str(result.metadata.carat), "2.69")
        self.assertEqual(str(result.metadata.price), "749.77")
        self.assertEqual(result.metadata.dimensions, (7.2,7.1,5.05))
        self.assertIn("not verified", result.metadata.tax_basis)
        self.assertEqual(result.metadata.attribution["report_number"].source,
                         "diyona_public_supabase")
        self.assertEqual([x.kind for x in result.references],
                         [CERTIFICATE, STILL, ROTATION, VIDEO])
        self.assertEqual(result.references[0].locator, PDF)
        self.assertEqual(result.references[1].locator, IMAGE)
        self.assertEqual(http.calls, [PAGE,API])
        self.assertEqual(http.auth_calls[0][0], API)
        self.assertEqual(http.auth_calls[0][1]["apikey"], ANON)

    def test_shell_with_misleading_html_identity_uses_api_first(self):
        page=SHELL.replace(b"</body>",b"SKU: WRONG9999 . IGI LG999999999</body>")
        result=DiyonaListingProvider(HTTP(page=page)).fetch(PAGE)
        self.assertEqual(result.metadata.report_number, REPORT)
        self.assertEqual(result.metadata.retailer_sku, "A69835AA4")

    def test_anon_key_is_never_retained_in_source_snapshot(self):
        record=DiyonaListingProvider(HTTP()).fetch(PAGE)
        concatenated=" ".join(str(x.body) for x in record.raw_responses)
        self.assertNotIn(ANON,concatenated)
        self.assertIn("[redacted]",concatenated)

    def test_wrong_sku_from_supabase_fails_closed(self):
        row={**ROW,"sku":"NOTTHISSKU"}
        with self.assertRaisesRegex(RetrievalError,"SKU mismatch"):
            DiyonaListingProvider(HTTP(rows=[row])).fetch(PAGE)

    def test_duplicate_or_missing_exact_record_fails_closed(self):
        for records in ([],[ROW,ROW]):
            with self.subTest(rows=len(records)):
                with self.assertRaisesRegex(RetrievalError,"no unique exact"):
                    DiyonaListingProvider(HTTP(rows=records)).fetch(PAGE)

    def test_missing_report_and_wrong_lab_fail_closed(self):
        for row in ({**ROW,"certificate_number":None},
                    {**ROW,"lab":"GIA"}):
            with self.subTest(row=row):
                with self.assertRaisesRegex(RetrievalError,"valid IGI"):
                    DiyonaListingProvider(HTTP(rows=[row])).fetch(PAGE)

    def test_public_api_denial_does_not_make_up_certificate(self):
        with self.assertRaisesRegex(RetrievalError,"HTTP 403"):
            DiyonaListingProvider(HTTP(status=403)).fetch(PAGE)

    def test_unknown_supabase_project_rejected(self):
        bad=SHELL.replace(BASE.encode(), b"https://unknown-project.supabase.co")
        with self.assertRaisesRegex(RetrievalError, "unexpected diamond data source"):
            DiyonaListingProvider(HTTP(page=bad)).fetch(PAGE)

    def test_untrusted_pdf_link_uses_exact_igi_verification(self):
        row={**ROW,"certificate_url":"https://attacker.example/other.pdf"}
        rec=DiyonaListingProvider(HTTP(rows=[row])).fetch(PAGE)
        self.assertEqual(rec.references[0].retrieval_key,f"igi-report:{REPORT}")

    def test_existing_html_fixture_preserved_for_snapshots(self):
        legacy="https://diyona.com/pages/diamond-detail?sku=B934F4533"
        fake=HTTP(additional={legacy:(_fixture("diyona-detail.html"),"text/html")})
        rec=DiyonaListingProvider(fake).fetch(legacy)
        self.assertEqual(rec.metadata.report_number,"LG800667394")
        self.assertEqual(fake.calls,[legacy])

    def test_full_retrieval_with_exact_report_and_256_original_frames(self):
        pdf=_pdf_bytes(report=REPORT,shape="ASSCHER",carat="2.69",
                       colour="D",clarity="VS1",
                       dimensions=("7.2","7.1","5.05"))
        media={
            PDF:(pdf,"application/pdf"),
            IMAGE:(_jpeg_bytes(),"image/jpeg"),
            **_progressive_source_responses(MOTION_AUDITS[0], SOURCE,version=1),
        }
        client=HTTP(additional=media,post_responses={
            GRAPHQL_URL:(_loupe_payload(REPORT,VIEWER,cert_id="diyona-public-api"),
                         "application/json")
        })
        result=retrieve_diamond(PAGE,config=default_config(client))
        self.assertEqual(result.metadata.report_number, REPORT)
        self.assertEqual(len(result.rotations),1)
        self.assertEqual(len(result.rotations[0].frames),256)
        self.assertEqual(len(result.stills),1)
        self.assertEqual(len(result.certificates),1)
        checks={c.field:c.outcome for c in result.identity_comparisons}
        self.assertEqual(checks["report_number"],IdentityOutcome.AGREEMENT)
        self.assertEqual(checks["shape"],IdentityOutcome.AGREEMENT)
        self.assertEqual(checks["carat"],IdentityOutcome.AGREEMENT)


if __name__=="__main__":
    unittest.main()
