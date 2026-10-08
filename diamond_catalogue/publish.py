"""GitHub Actions one-URL entry point with safe, actionable failure diagnostics."""
from __future__ import annotations

import argparse
import os
import re
import sys
import socket
import ssl
from decimal import InvalidOperation
from urllib.error import URLError, HTTPError

from dataclasses import replace

from diamond_retrieval import default_config, retrieve_diamond
from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.retailers import DiyonaListingProvider
from .diyona_report_hint import ReportHintDiyonaProvider, normalize_report_hint, require_independent_report_corroboration
from diamond_retrieval.errors import (
    IdentityConflictError, RetrievalError, UnsupportedInputError,
)
from .github_api import GitHubAPI, GitHubError
from .github_catalogue import publish_result
from .models import CatalogueError
from .planner import plan_publication

_HTTP_LISTING_ERROR = re.compile(
    r"^(?:(?:Diyona|Quality Diamonds) listing|Diyona public diamond lookup) returned HTTP ([1-5][0-9][0-9])$"
)

# Deliberately match only messages emitted by our own adapter. Never render
# arbitrary upstream exception text, URLs, HTML, tokens or response bodies.
_KNOWN_LISTING_ERRORS = {
    "Diyona explicit IGI report differs from the returned listing":
        ("report_hint_mismatch",
         "The supplied IGI report conflicts with the exact retailer listing."),
    "Report hint only supports an exact Diyona listing":
        ("report_hint_unsupported",
         "An explicit IGI report hint is allowed only for an exact Diyona URL."),
    "Diyona public diamond lookup has no unique exact SKU record":
        ("listing_missing_identity",
         "The retailer public API returned no unique record for the exact SKU."),
    "Diyona public diamond lookup SKU mismatch":
        ("listing_identity_mismatch",
         "The retailer public API returned a different SKU."),
    "Diyona public diamond lookup lacks a valid IGI certificate":
        ("listing_missing_identity",
         "The retailer public API did not provide a valid IGI certificate."),
    "Diyona page does not advertise its public diamond lookup":
        ("listing_api_configuration_missing",
         "The retailer no longer advertises a supported public diamond lookup."),
    "Diyona page advertises an unexpected diamond data source":
        ("listing_api_source_changed",
         "The retailer public API source changed and must be reviewed before ingestion."),
    "Diyona public diamond lookup returned invalid JSON":
        ("listing_api_invalid_response",
         "The retailer public diamond API did not return valid JSON."),
    "Diyona public lookup result exceeds size limit":
        ("listing_api_invalid_response",
         "The retailer public diamond API response exceeded the permitted size."),
    "Diyona SKU is not a valid exact public lookup key":
        ("listing_invalid_url",
         "The requested Diyona SKU is not a valid exact public lookup key."),
    "Diyona exact listing no longer exposes certificate-bound diamond data":
        ("listing_missing_identity",
         "Diyona did not expose the report number and SKU required for safe publication."),
    "Quality Diamonds exact listing does not expose certificate-bound diamond data":
        ("listing_missing_identity",
         "Quality Diamonds did not expose the report number and listing ID."),
    "Diyona listing SKU does not match the requested exact URL":
        ("listing_identity_mismatch",
         "The returned Diyona listing belongs to a different SKU."),
    "Quality Diamonds listing ID does not match the requested exact URL":
        ("listing_identity_mismatch",
         "The returned Quality Diamonds listing belongs to a different listing ID."),
}


# Only exact, in-repository CatalogueError messages are safe to expose. These
# identify the failed invariant without printing arbitrary URLs, raw metadata,
# release payloads or API response bodies.
_KNOWN_CATALOGUE_ERRORS = {
    "Conflicting catalogue entries share a logical key":
        ("catalogue_observation_conflict",
         "Previously stored evidence or an observation has the same identity key but different content."),
    "GitHub Release asset digest mismatch":
        ("catalogue_asset_digest_mismatch",
         "A previously uploaded Release asset does not match the expected SHA-256."),
    "GitHub Release asset byte count mismatch":
        ("catalogue_asset_size_mismatch",
         "A previously uploaded Release asset does not match the expected byte count."),
    "GitHub Release asset is not successfully uploaded":
        ("catalogue_asset_incomplete",
         "A Release asset is not in the uploaded state."),
    "GitHub Release would exceed its 1,000-asset limit; use R2 or sharded storage":
        ("catalogue_release_capacity",
         "The stone's Release is at capacity; use sharded storage or R2."),
    "Cannot regenerate index from truncated Git tree":
        ("catalogue_tree_truncated",
         "GitHub returned a truncated repository tree; index regeneration is unsafe."),
    "Invalid stored catalogue JSON":
        ("catalogue_stored_json_invalid",
         "Previously committed catalogue JSON cannot be parsed."),
    "Cannot decode existing Git catalogue JSON":
        ("catalogue_stored_json_invalid",
         "Previously committed catalogue JSON cannot be decoded."),
    "Unpublished or untraceable overview thumbnail":
        ("catalogue_thumbnail_invalid",
         "An existing or incoming overview thumbnail is missing its traceable asset reference."),
    "Unpublished evidence asset in catalogue manifest":
        ("catalogue_manifest_asset_missing",
         "A stored or incoming manifest references evidence without a public asset URL."),
    "GitHub Release contains duplicate asset names":
        ("catalogue_release_duplicates",
         "The stone's Release has duplicate asset names."),
    "Release asset enumeration exceeded safe bound":
        ("catalogue_release_inventory",
         "The Release asset listing exceeded the supported enumeration limit."),
    "Diamond manifest identity/ID mismatch":
        ("catalogue_identity_mismatch",
         "A stored or incoming manifest's report identity does not match its stable ID."),
    "Refusing to merge different certified diamonds":
        ("catalogue_identity_mismatch",
         "Existing and incoming manifests refer to different certified diamonds."),
}
_REPORTED_PROPORTION_FIELDS = frozenset((
    "table_percent", "depth_percent", "length_width_ratio", "cut", "polish",
    "symmetry", "fluorescence", "girdle", "culet",
))
_CERTIFIED_CONFLICT_FIELDS = frozenset((
    "shape", "origin", "carat", "colour", "clarity", "dimensions",
    "reported_proportions",
))


def _listing_exception(exc: RetrievalError) -> tuple[str, str]:
    """Walk provider/network exception chains without exposing message contents.

    DiamondRetriever wraps exceptions and includes the listing URL in its text.
    Classify only known exception *types* and exact in-repo messages.
    Do not render unknown upstream strings, redirects, tokens or HTML.
    """
    cause: BaseException = exc
    for _ in range(8):
        if isinstance(cause, RetrievalError):
            message = str(cause)
            if message in _KNOWN_LISTING_ERRORS:
                return _KNOWN_LISTING_ERRORS[message]
            match = _HTTP_LISTING_ERROR.fullmatch(message)
            if match:
                status = int(match.group(1))
                if status in {404, 410}:
                    return ("listing_missing",
                            f"Retailer returned HTTP {status}; the exact listing may be gone.")
                if status in {401, 403, 429}:
                    return ("listing_access_denied",
                            f"Retailer returned HTTP {status}; do not bypass upstream access controls.")
                return ("listing_http_failure",
                        f"Retailer returned HTTP {status}; the listing cannot be retrieved.")
        if cause.__cause__ is None or cause.__cause__ is cause:
            break
        cause = cause.__cause__

    # Categorize the deepest cause, not its potentially sensitive message.
    if isinstance(cause, HTTPError):
        return ("listing_http_failure", f"Listing HTTP request returned status {cause.code}.")
    if isinstance(cause, (socket.gaierror,)):
        return ("listing_dns_failure", "Public listing hostname DNS resolution failed.")
    if isinstance(cause, (ssl.SSLError,)):
        return ("listing_tls_failure", "The listing connection failed TLS verification/negotiation.")
    if isinstance(cause, (URLError, TimeoutError, ConnectionError, OSError)):
        return ("listing_network_failure", "Network/connection failure while fetching listing.")
    if isinstance(cause, InvalidOperation):
        return ("listing_price_parse_failure", "Retailer supplied an invalid numeric field.")
    if isinstance(cause, ValueError):
        error = str(cause)
        if error.startswith("Unable to resolve public hostname:"):
            return ("listing_dns_failure", "Public listing hostname DNS resolution failed.")
        if error.startswith("Refusing non-public destination:"):
            return ("listing_unsafe_redirect",
                    "Public-URL guard rejected a non-public resolved address or redirect.")
        if error.startswith("HTTP response exceeds "):
            return ("listing_response_too_large",
                    "Listing HTML exceeded the configured download limit.")
        if error in {
            "Only public http(s) URLs are supported",
            "URL must include a hostname",
            "Credential-bearing URLs are not allowed",
            "Invalid URL port",
        }:
            return ("listing_invalid_url",
                    "The requested listing URL or redirect failed public-URL validation.")
        return ("listing_value_error",
                "Listing parsing/validation raised ValueError (message withheld).")
    if isinstance(cause, (KeyError, IndexError, TypeError, AttributeError)):
        return ("listing_parser_error",
                f"Retailer adapter raised {type(cause).__name__} while parsing listing.")
    return ("listing_retrieval_failure",
            f"Listing retrieval failed with {type(cause).__name__ if type(cause) in {RuntimeError, AssertionError, LookupError} else 'an unclassified exception'}.")


def safe_failure(exc: Exception) -> tuple[str, str]:
    """Return only fixed, non-secret public diagnostics."""
    if isinstance(exc, ValueError) and str(exc) == "IGI report input must be a full LG report number":
        return ("invalid_report_hint", "Supply the complete IGI LG report number.")
    if isinstance(exc, UnsupportedInputError):
        return ("unsupported_input",
                "Use one exact supported Diyona or Quality Diamonds listing URL.")
    if isinstance(exc, IdentityConflictError):
        return ("identity_conflict",
                "Certified diamond identity observations disagree; publication was stopped.")
    if isinstance(exc, RetrievalError):
        return _listing_exception(exc)
    if isinstance(exc, GitHubError):
        if exc.status in {401, 403}:
            return ("github_permission_denied",
                    f"GitHub API returned HTTP {exc.status}; review Actions contents:write permissions.")
        if exc.status in {409, 422}:
            return ("github_conflict",
                    f"GitHub API returned HTTP {exc.status}; verify asset/ref concurrency and rerun.")
        return ("github_api_failure",
                f"GitHub API returned HTTP {exc.status}; inspect repo permissions and retry.")
    if isinstance(exc, CatalogueError):
        if str(exc) == "Explicit IGI hint lacks independent certificate-bound corroboration":
            return ("report_hint_unverified",
                    "IGI report was supplied manually but no matching certificate or "
                    "certificate-bound motion was recovered; nothing was published.")
        message = str(exc)
        if message in _KNOWN_CATALOGUE_ERRORS:
            return _KNOWN_CATALOGUE_ERRORS[message]
        field_prefix = "Conflicting certified metadata: "
        if message.startswith(field_prefix):
            field = message[len(field_prefix):]
            if field in _CERTIFIED_CONFLICT_FIELDS:
                return ("catalogue_metadata_conflict",
                        f"Previously stored and newly retrieved {field} disagree; no changes were committed.")
        proportion_prefix = "Conflicting reported proportion: "
        if message.startswith(proportion_prefix):
            field = message[len(proportion_prefix):]
            if field in _REPORTED_PROPORTION_FIELDS:
                return ("catalogue_proportion_conflict",
                        f"Two observations disagree on {field}; publication was stopped without replacing either value.")
        return ("catalogue_validation_failure",
                "Asset hashes, identity, capacity, or stored manifest failed a safety check.")
    return ("unexpected_failure",
            "An unexpected error occurred; inspect the failing stage without sharing secrets.")


def retrieve_for_publication(url: str, *, igi_report: str | None = None):
    """Use the public retrieval composition with an optional explicit IGI hint."""
    if not igi_report:
        return retrieve_diamond(url)
    if not DiyonaListingProvider(None).supports(url):
        raise UnsupportedInputError("Manual IGI report hint requires an exact Diyona listing")
    client = UrllibHttpClient()
    config = default_config(client)
    providers = tuple(
        ReportHintDiyonaProvider(client, report_hint=igi_report)
        if isinstance(provider, DiyonaListingProvider) else provider
        for provider in config.providers
    )
    return retrieve_diamond(url, config=replace(config, providers=providers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish one certificate-bound listing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan only; do not create Releases or commit catalogue")
    args = parser.parse_args(argv)
    url = os.environ.get("DIAMOND_URL", "").strip()
    if not url:
        parser.error("DIAMOND_URL is required (one supported public listing URL)")
    if os.environ.get("GITHUB_REF", "refs/heads/master") != "refs/heads/master":
        parser.error("Production publication is allowed only from master")

    stage = "listing retrieval"
    try:
        raw_report = os.environ.get("IGI_REPORT", "").strip()
        report_hint = normalize_report_hint(raw_report) if raw_report else None
        result = retrieve_for_publication(url, igi_report=report_hint)
        stage = "publishability validation"
        require_independent_report_corroboration(result)
        plan = plan_publication(result)  # fail-closed gate before remote mutations
        kinds: dict[str, int] = {}
        for evidence in result.evidence:
            kinds[str(evidence.kind)] = kinds.get(str(evidence.kind), 0) + 1
        print(f"Certified diamond: {plan.diamond_id}", flush=True)
        print(f"Retrieval: {result.status.value}; evidence counts: {kinds}", flush=True)
        print(f"Original assets planned: {len(plan.assets)}", flush=True)
        if result.completion_reasons:
            print(f"Partial reasons: {len(result.completion_reasons)} (see manifest)", flush=True)
        if args.dry_run:
            print("Dry run: no published assets or catalogue writes", flush=True)
            return 0

        stage = "GitHub publication"
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""),
                        os.environ.get("GITHUB_REPOSITORY", ""))
        receipt = publish_result(result, api)
        print(f"Published manifest: {receipt.manifest_path}")
        print(f"Catalogue diamonds: {receipt.catalogue_count}")
        print(f"Commit: {receipt.commit_sha}; changed: {receipt.changed}")
        return 0
    except Exception as exc:
        # The upstream wrapper includes full URLs; only fixed allowlisted
        # diagnostics are safe for public GitHub Actions logs.
        code, hint = safe_failure(exc)
        message = f"{code}: {hint}"
        print(f"Publication failed during {stage}: {message}", file=sys.stderr)
        print(f"::error title=Diamond ingestion failed ({stage})::{message}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
