"""GitHub Actions one-URL entry point with safe, actionable failure diagnostics."""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.error import URLError

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
    r"^(?:Diyona|Quality Diamonds) listing returned HTTP ([1-5][0-9][0-9])$"
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
        cause = exc.__cause__ or exc
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
        if isinstance(cause, (URLError, TimeoutError)):
            return ("listing_network_failure",
                    "The listing request failed at network or transport level.")
        return ("listing_retrieval_failure",
                "Listing retrieval failed before a certified diamond identity was established.")
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
