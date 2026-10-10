"""Network-free guards around R05/R07 read-only identity diagnostics."""
import json
import unittest

from diamond_retrieval.protocols import HttpResponse
from tools.reference_identity_audit import audit_one, _safe, CASES


class FakeHttp:
    def __init__(self, body=None, code=200):
        self.body = body
        self.code = code
        self.calls = []

    def post(self, url, *, timeout, content, headers):
        self.calls.append((url, json.loads(content)["variables"]["cert"]))
        return HttpResponse(
            self.code, url, {"Content-Type": "application/json"},
            self.body if self.body is not None else b"",
        )


def record(cert, *, lab="IGI", v360=True):
    return json.dumps({"data": {"certificate_by_cert_number": {
        "id": "private-opaque-record-id",
        "certNumber": cert, "lab": lab, "image": "https://external/img.jpg",
        "video": None,
        "v360": {"url": "https://external/some-untrusted-source"} if v360 else None,
    }}}).encode()


class ReferenceIdentityAuditTests(unittest.TestCase):
    def test_only_two_fixed_trusted_reports(self):
        self.assertEqual(CASES, (
            ("ps285166-r05", "IGI", "644442866"),
            ("ps285166-r07", "IGI", "625406458"),
        ))

    def test_prefix_variant_is_evidence_not_automatic_identity_merger(self):
        client = FakeHttp(record("LG644442866"))
        output = audit_one(client, reference_id="ps285166-r05",
                           lab="IGI", report="644442866",
                           requested="644442866")
        self.assertEqual(output["report_relation"], "same_numeric_with_lg_difference")
        self.assertTrue(output["expected_lab_match"])
        self.assertTrue(output["v360_present"])
        self.assertEqual(client.calls[0][1], "644442866")
        self.assertNotIn("private-opaque-record-id", str(output))
        self.assertNotIn("https://external/", str(output))

    def test_exact_and_wrong_report_are_distinct(self):
        ok = audit_one(FakeHttp(record("LG625406458")),
                       reference_id="ps285166-r07", lab="IGI",
                       report="625406458", requested="LG625406458")
        self.assertEqual(ok["report_relation"], "exact_request")
        bad = audit_one(FakeHttp(record("LG999999999")),
                        reference_id="ps285166-r07", lab="IGI",
                        report="625406458", requested="LG625406458")
        self.assertEqual(bad["report_relation"], "different_or_missing")
        self.assertEqual(bad["returned_report"], "LG999999999")

    def test_fail_closed_untrusted_values_and_responses(self):
        self.assertEqual(_safe("evil\\nsecret", kind="report"), "<invalid>")
        for body, code, status in [
            (b'{"errors":[{"message":"secret"}]}', 200, "graphql_error"),
            (b'{"data":{"certificate_by_cert_number":null}}', 200, "not_found"),
            (b"secret", 200, "invalid_payload"),
            (b"secret", 403, "http_failure"),
        ]:
            output = audit_one(FakeHttp(body, code), reference_id="ps285166-r05",
                               lab="IGI", report="644442866",
                               requested="644442866")
            self.assertEqual(output["status"], status)
            self.assertNotIn("secret", str(output))


if __name__ == "__main__":
    unittest.main()
