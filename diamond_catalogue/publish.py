"""GitHub Actions one-URL entry point. Do not print tokens or raw upstream data."""
from __future__ import annotations
import argparse
import os
import sys

from diamond_retrieval import retrieve_diamond
from .github_api import GitHubAPI
from .github_catalogue import publish_result
from .planner import plan_publication

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
    try:
        result = retrieve_diamond(url)
        plan = plan_publication(result)  # fail-closed gate before remote mutations
        kinds: dict[str, int] = {}
        for evidence in result.evidence:
            kinds[str(evidence.kind)] = kinds.get(str(evidence.kind), 0) + 1
        print(f"Certified diamond: {plan.diamond_id}")
        print(f"Retrieval: {result.status.value}; evidence counts: {kinds}")
        print(f"Original assets planned: {len(plan.assets)}")
        if result.completion_reasons:
            print(f"Partial reasons: {len(result.completion_reasons)} (see manifest)")
        if args.dry_run:
            print("Dry run: no published assets or catalogue writes")
            return 0
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""),
                        os.environ.get("GITHUB_REPOSITORY", ""))
        receipt = publish_result(result, api)
        print(f"Published manifest: {receipt.manifest_path}")
        print(f"Catalogue diamonds: {receipt.catalogue_count}")
        print(f"Commit: {receipt.commit_sha}; changed: {receipt.changed}")
        return 0
    except Exception as exc:
        # Never log arbitrary HTTP exception text or potentially tokenized URLs.
        print(f"Publication failed: {type(exc).__name__}; inspect upstream status and tests",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
