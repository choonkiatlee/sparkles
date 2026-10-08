"""Public Actions failure summaries must be actionable without leaking input URLs."""
from __future__ import annotations

import io
import os
import socket
import ssl
import unittest
from decimal import InvalidOperation
from urllib.error import URLError
from contextlib import redirect_stderr
from unittest.mock import patch

from diamond_catalogue.github_api import GitHubError
from diamond_catalogue.publish import main, safe_failure
from diamond_retrieval.errors import (
    IdentityConflictError, RetrievalError, UnsupportedInputError,
)


def wrapped_retrieval_error(message: str) -> RetrievalError:
    """Match DiamondRetriever's 'raise RetrievalError(...) from exc' behavior."""
    try:
        raise RetrievalError(message)
    except RetrievalError as inner:
        try:
            raise RetrievalError(
                "Listing retrieval failed for https://example.com/secret?token=DO_NOT_LEAK"
            ) from inner
        except RetrievalError as outer:
            return outer


class IngestionDiagnosticTests(unittest.TestCase):
    def test_http_403_is_explicit_and_safe(self):
        code, hint = safe_failure(wrapped_retrieval_error("Diyona listing returned HTTP 403"))
        self.assertEqual(code, "listing_access_denied")
        self.assertIn("HTTP 403", hint)
        self.assertNotIn("example.com", hint)

    def test_missing_listing_reports_missing_not_upstream_bypass(self):
        code, hint = safe_failure(wrapped_retrieval_error("Diyona listing returned HTTP 404"))
        self.assertEqual(code, "listing_missing")
        self.assertIn("HTTP 404", hint)

    def test_unparseable_listing_reports_certificate_identity_required(self):
        code, hint = safe_failure(wrapped_retrieval_error(
            "Diyona exact listing no longer exposes certificate-bound diamond data"
        ))
        self.assertEqual(code, "listing_missing_identity")
        self.assertIn("report number", hint)

    def test_sku_mismatch_does_not_publish(self):
        code, _ = safe_failure(wrapped_retrieval_error(
            "Diyona listing SKU does not match the requested exact URL"
        ))
        self.assertEqual(code, "listing_identity_mismatch")

    def test_unrecognized_upstream_exception_does_not_leak_payload(self):
        code, hint = safe_failure(wrapped_retrieval_error(
            "secret=DO_NOT_LEAK&access_token=private https://example.com/private"
        ))
        self.assertEqual(code, "listing_retrieval_failure")
        self.assertNotIn("DO_NOT_LEAK", hint)
        self.assertNotIn("example.com", hint)

    def test_unsupported_url_uses_fixed_safe_hint(self):
        code, hint = safe_failure(UnsupportedInputError("private?token=DO_NOT_LEAK"))
        self.assertEqual(code, "unsupported_input")
        self.assertNotIn("DO_NOT_LEAK", hint)

    def test_github_denied_includes_status_not_token_or_api_url(self):
        code, hint = safe_failure(GitHubError(403, "POST release-with-secret"))
        self.assertEqual(code, "github_permission_denied")
        self.assertIn("HTTP 403", hint)
        self.assertNotIn("secret", hint)

    def test_cli_failing_retrieval_logs_stage_and_annotation_but_not_url(self):
        sensitive_url = "https://diyona.com/pages/diamond-detail?sku=SECRET_STONE"
        fake = wrapped_retrieval_error("Diyona listing returned HTTP 403")
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"DIAMOND_URL": sensitive_url,
                                    "GITHUB_REF": "refs/heads/master"}),
            patch("diamond_catalogue.publish.retrieve_diamond", side_effect=fake),
            redirect_stderr(output),
        ):
            result = main([])
        self.assertEqual(result, 1)
        text = output.getvalue()
        self.assertIn("listing retrieval", text)
        self.assertIn("listing_access_denied", text)
        self.assertIn("::error title=", text)
        self.assertNotIn("SECRET_STONE", text)
        self.assertNotIn("DO_NOT_LEAK", text)

    def test_cli_does_not_publish_on_identity_missing(self):
        output = io.StringIO()
        fake = wrapped_retrieval_error(
            "Diyona exact listing no longer exposes certificate-bound diamond data"
        )
        with (
            patch.dict(os.environ, {"DIAMOND_URL": "https://diyona.com/pages/diamond-detail?sku=A",
                                    "GITHUB_REF": "refs/heads/master"}),
            patch("diamond_catalogue.publish.retrieve_diamond", side_effect=fake),
            patch("diamond_catalogue.publish.publish_result") as publish,
            redirect_stderr(output),
        ):
            code = main([])
        self.assertEqual(code, 1)
        publish.assert_not_called()
        self.assertIn("listing_missing_identity", output.getvalue())


    def test_diyona_public_api_403_is_reported_without_url_or_token(self):
        code, hint = safe_failure(wrapped_retrieval_error(
            "Diyona public diamond lookup returned HTTP 403"
        ))
        self.assertEqual(code, "listing_access_denied")
        self.assertIn("HTTP 403", hint)
        self.assertNotIn("example.com", hint)

    def test_diyona_public_api_absent_sku_is_reported_as_missing(self):
        code, hint = safe_failure(wrapped_retrieval_error(
            "Diyona public diamond lookup has no unique exact SKU record"
        ))
        self.assertEqual(code, "listing_missing_identity")
        self.assertNotIn("DO_NOT_LEAK", hint)

    def test_diyona_source_change_is_not_silently_accepted(self):
        code, _ = safe_failure(wrapped_retrieval_error(
            "Diyona page advertises an unexpected diamond data source"
        ))
        self.assertEqual(code, "listing_api_source_changed")

    def test_quality_diamonds_known_parse_failure(self):
        issue = wrapped_retrieval_error(
            "Quality Diamonds exact listing does not expose certificate-bound diamond data"
        )
        code, hint = safe_failure(issue)
        self.assertEqual(code, "listing_missing_identity")
        self.assertNotIn("example.com", hint)

    @staticmethod
    def chained(cause):
        try:
            raise cause
        except Exception as inner:
            try:
                raise RetrievalError(
                    "Listing retrieval failed for https://example.com?access_token=DO_NOT_LEAK"
                ) from inner
            except RetrievalError as outer:
                return outer

    def test_dns_validation_value_error_is_actionable_and_safe(self):
        err = self.chained(ValueError("Unable to resolve public hostname: secret.internal"))
        code, hint = safe_failure(err)
        self.assertEqual(code, "listing_dns_failure")
        self.assertNotIn("secret.internal", hint)

    def test_public_destination_rejection_does_not_leak_hostname(self):
        err = self.chained(ValueError("Refusing non-public destination: secret.internal"))
        code, hint = safe_failure(err)
        self.assertEqual(code, "listing_unsafe_redirect")
        self.assertNotIn("secret.internal", hint)

    def test_size_limit_is_classified_without_echoing_metadata(self):
        err = self.chained(ValueError("HTTP response exceeds 26214400 bytes"))
        self.assertEqual(safe_failure(err)[0], "listing_response_too_large")

    def test_temporary_dns_error_classification(self):
        err = self.chained(socket.gaierror("secret-host DO_NOT_LEAK"))
        code, hint = safe_failure(err)
        self.assertEqual(code, "listing_dns_failure")
        self.assertNotIn("DO_NOT_LEAK", hint)

    def test_tls_failure_classification(self):
        err = self.chained(ssl.SSLError("certificate for secret.example invalid"))
        self.assertEqual(safe_failure(err)[0], "listing_tls_failure")

    def test_nested_urllib_error_classification(self):
        try:
            raise URLError("Authorization: DO_NOT_LEAK")
        except URLError as inner:
            try:
                raise ValueError("opaque") from inner
            except ValueError as outer:
                wrapped = self.chained(outer)
        code, hint = safe_failure(wrapped)
        self.assertEqual(code, "listing_network_failure")
        self.assertNotIn("DO_NOT_LEAK", hint)

    def test_numeric_parse_failure_is_specific(self):
        err = self.chained(InvalidOperation("private data"))
        self.assertEqual(safe_failure(err)[0], "listing_price_parse_failure")

    def test_keyerror_is_classified_but_never_quoted(self):
        err = self.chained(KeyError("Authorization=DO_NOT_LEAK"))
        code, hint = safe_failure(err)
        self.assertEqual(code, "listing_parser_error")
        self.assertNotIn("DO_NOT_LEAK", hint)

    def test_unexpected_valueerror_hides_secret(self):
        err = self.chained(ValueError("token=DO_NOT_LEAK"))
        code, hint = safe_failure(err)
        self.assertEqual(code, "listing_value_error")
        self.assertNotIn("DO_NOT_LEAK", hint)


if __name__ == "__main__":
    unittest.main()
