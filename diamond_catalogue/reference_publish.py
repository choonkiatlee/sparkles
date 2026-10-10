"""Trusted GitHub-native reference enrichment and atomic static publication (#197).

Only accepted manifests from master are source input. Media retrieval is
opt-in; original bytes live in GitHub Releases, never in Git history.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

from diamond_retrieval import retrieve_reference_media
from diamond_retrieval.models import IdentityOutcome, RotationEvidence

from .github_api import GitHubAPI, GitHubError
from .github_catalogue import MAX_COMMIT_ATTEMPTS
from .github_release import GitHubReleaseStorage
from .merge import _check_manifest
from .models import CatalogueError, PublicationPlan
from .planner import finalize_manifest, plan_evidence_assets
from .references import build_index, validate_reference
from .serialization import json_document

REF_DIR = "data/references/"
REF_INDEX = "data/reference-index.json"
CERT_DIR = "data/diamonds/"
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_CURATED_FIELDS = (
    "schema", "id", "label", "identity", "linked_diamond_id",
    "diamond_metadata", "commentary", "source_links", "media_sources", "topics",
)


@dataclass(frozen=True)
class ReferencePublishReceipt:
    reference_id: str
    manifest_path: str
    asset_count: int
    reference_count: int
    commit_sha: str
    changed: bool


def _curation(ref: dict) -> dict:
    return {field: copy.deepcopy(ref.get(field)) for field in _CURATED_FIELDS}


def _read_blob(api, blob_sha: str) -> dict:
    response = api.get_json(f"{api.prefix}/git/blobs/{blob_sha}")
    if response.get("encoding") != "base64":
        raise CatalogueError("Invalid published reference Git blob")
    try:
        raw = base64.b64decode(response["content"])
        obj = json.loads(raw)
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise CatalogueError("Malformed reference Git blob") from exc
    if not isinstance(obj, dict):
        raise CatalogueError("Invalid published reference JSON")
    return obj


class GitHubReferenceCatalogue:
    """Read the trusted master tree and commit one reference+index atomically."""

    def __init__(self, api):
        self.api = api

    def _snapshot(self, *, linked_diamond_id: str | None = None):
        api = self.api
        head = api.get_json(f"{api.prefix}/git/ref/heads/master")["object"]["sha"]
        tree_sha = api.get_json(f"{api.prefix}/git/commits/{head}")["tree"]["sha"]
        tree = api.get_json(f"{api.prefix}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise CatalogueError("Cannot regenerate index from truncated Git tree")
        entries = {e["path"]: e["sha"] for e in tree["tree"] if e.get("type") == "blob"}
        manifests = {}
        for path, sha in sorted(entries.items()):
            if not (path.startswith(REF_DIR) and path.endswith(".json")):
                continue
            if path == REF_DIR + "README.json":
                raise CatalogueError("Unexpected reference manifest")
            record = _read_blob(api, sha)
            validate_reference(record, expected_id=path[len(REF_DIR):-5])
            manifests[path] = record
        old_index = _read_blob(api, entries[REF_INDEX]) if REF_INDEX in entries else None
        certified = None
        if linked_diamond_id is not None:
            path = f"{CERT_DIR}{linked_diamond_id}.json"
            if path not in entries:
                raise CatalogueError("Linked certified manifest missing from trusted master")
            certified = _read_blob(api, entries[path])
            _check_manifest(certified)
            if certified.get("id") != linked_diamond_id:
                raise CatalogueError("Linked certified manifest identity mismatch")
        return head, tree_sha, manifests, old_index, certified

    def load_accepted(self, reference_id: str) -> dict:
        if not isinstance(reference_id, str) or not _ID.fullmatch(reference_id) or (
            len(reference_id) > 96 or reference_id.startswith("ref-")
        ):
            raise CatalogueError("Invalid reference ID")
        _, _, references, _, _ = self._snapshot()
        path = f"{REF_DIR}{reference_id}.json"
        if path not in references:
            raise CatalogueError("Reference not accepted on master")
        return copy.deepcopy(references[path])

    def commit(self, accepted: dict, *, incoming_evidence: list[dict],
               incoming_attempts: list[dict], asset_count: int) -> ReferencePublishReceipt:
        reference_id = accepted["id"]
        path = f"{REF_DIR}{reference_id}.json"
        for retry in range(MAX_COMMIT_ATTEMPTS):
            head, tree_sha, manifests, old_index, certified = self._snapshot(
                linked_diamond_id=accepted.get("linked_diamond_id")
            )
            current = manifests.get(path)
            if current is None or _curation(current) != _curation(accepted):
                raise CatalogueError("Curated reference changed on master; rerun enrichment")
            revised = copy.deepcopy(current)
            new_evidence = (
                copy.deepcopy(certified.get("evidence", []))
                if certified is not None else copy.deepcopy(incoming_evidence)
            )
            by_key = {e["record_key"]: copy.deepcopy(e) for e in current.get("evidence", [])}
            for item in new_evidence:
                key = item["record_key"]
                if key in by_key and by_key[key] != item:
                    raise CatalogueError("Conflicting saved reference evidence")
                by_key[key] = item
            revised["evidence"] = [by_key[key] for key in sorted(by_key)]

            # Retain one current status per deterministic candidate key.
            by_source = {
                (a["reference_identifier"], a["kind"], a["locator"]): copy.deepcopy(a)
                for a in current.get("enrichment_attempts", [])
            }
            for attempt in incoming_attempts:
                key = (attempt["reference_identifier"], attempt["kind"], attempt["locator"])
                by_source[key] = copy.deepcopy(attempt)
            if by_source:
                revised["enrichment_attempts"] = [by_source[key] for key in sorted(
                    by_source, key=lambda key: tuple(str(x or "") for x in key)
                )]
            validate_reference(revised)
            manifests[path] = revised
            index = build_index(list(manifests.values()))
            if revised == current and index == old_index:
                return ReferencePublishReceipt(
                    reference_id, path, asset_count, len(manifests), head, False
                )
            tree = self.api.post_json(f"{self.api.prefix}/git/trees", {
                "base_tree": tree_sha,
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob",
                     "content": json_document(revised)},
                    {"path": REF_INDEX, "mode": "100644", "type": "blob",
                     "content": json_document(index)},
                ],
            })
            commit = self.api.post_json(f"{self.api.prefix}/git/commits", {
                "message": f"References: enrich {reference_id}",
                "tree": tree["sha"], "parents": [head],
            })
            try:
                self.api.patch_json(f"{self.api.prefix}/git/refs/heads/master", {
                    "sha": commit["sha"], "force": False,
                })
            except GitHubError as exc:
                if exc.status not in {409, 422} or retry + 1 == MAX_COMMIT_ATTEMPTS:
                    raise
                continue
            return ReferencePublishReceipt(
                reference_id, path, asset_count, len(manifests), commit["sha"], True
            )
        raise CatalogueError("Reference commit retry budget exceeded")


def _attempts(result) -> list[dict]:
    return [{
        "reference_identifier": a.reference_identifier,
        "kind": str(a.kind),
        "status": a.status.value,
        "locator": a.locator,
    } for a in result.attempts]


def plan_reference_media(result, reference_id: str) -> PublicationPlan:
    """Use the same original-byte plan and media shape as certified diamonds."""
    if any(c.outcome == IdentityOutcome.CONFLICT for c in result.identity_comparisons):
        raise CatalogueError("Conflicting reference evidence identity")
    for entry in result.evidence:
        if isinstance(entry, RotationEvidence) and (
            entry.status.value != "success" or
            entry.metadata.get("sequence_complete") is not True or
            len(entry.frames) != 256 or
            [frame.source_index for frame in entry.frames] != list(range(256))
        ):
            raise CatalogueError("Refusing to publish incomplete reference rotation")
    evidence, assets = plan_evidence_assets(result, reference_id)
    return PublicationPlan(reference_id, {"evidence": evidence}, assets)


def publish_reference(reference_id: str, *, mode: str, api,
                      retrieve=retrieve_reference_media) -> ReferencePublishReceipt:
    """Retrieve only opt-in media for a trusted, currently accepted reference."""
    if mode not in {"metadata", "media", "all"}:
        raise ValueError("Reference enrichment mode must be metadata, media or all")
    catalogue = GitHubReferenceCatalogue(api)
    accepted = catalogue.load_accepted(reference_id)
    evidence, attempts, asset_count = [], [], 0

    # Verified links always use existing certified media and its storage URLs.
    # Do not duplicate Release assets; never infer a link from similar specs.
    if not accepted.get("linked_diamond_id") and mode in {"media", "all"}:
        identity = accepted["identity"]
        result = retrieve(
            reference_id,
            lab=identity["lab"],
            report_number=identity["report_number"],
            media_sources=accepted.get("media_sources", []),
            include_igi_pdf=(mode == "all"),
        )
        # A mismatching exact-report supplier response MUST NOT let an
        # unrelated direct-source success become misattributed evidence.
        for attempt in result.attempts:
            if attempt.status.value == "resolution_failed" and any(
                signal in (attempt.message or "")
                for signal in ("Loupe360 certificate mismatch:", "Loupe360 lab mismatch:")
            ):
                raise CatalogueError("Conflicting reference certificate lookup")
        plan = plan_reference_media(result, reference_id)
        if plan.assets:
            stored = GitHubReleaseStorage(
                api, release_prefix="sparkles-reference-"
            ).publish(plan.assets)
            evidence = finalize_manifest(plan, stored)["evidence"]
            asset_count = len(plan.assets)
        else:
            evidence = plan.manifest["evidence"]
        attempts = _attempts(result)
    return catalogue.commit(accepted, incoming_evidence=evidence,
                            incoming_attempts=attempts, asset_count=asset_count)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrich one accepted learning reference")
    parser.add_argument("--mode", choices=("metadata", "media", "all"),
                        default=os.environ.get("REFERENCE_MODE", "metadata"))
    args = parser.parse_args(argv)
    reference_id = os.environ.get("REFERENCE_ID", "").strip()
    if os.environ.get("GITHUB_REF") != "refs/heads/master":
        parser.error("Reference publishing is allowed only from master")
    if not reference_id:
        parser.error("REFERENCE_ID is required")
    try:
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""),
                        os.environ.get("GITHUB_REPOSITORY", ""))
        receipt = publish_reference(reference_id, mode=args.mode, api=api)
        print(f"Reference: {receipt.reference_id}")
        print(f"Assets: {receipt.asset_count}; references: {receipt.reference_count}")
        print(f"Manifest: {receipt.manifest_path}; changed: {receipt.changed}")
        print(f"Commit: {receipt.commit_sha}")
        return 0
    except Exception as exc:
        # Fixed diagnostics only. Never print untrusted source URLs,
        # upstream messages or repository tokens into public Actions logs.
        code = "identity_conflict" if (
            isinstance(exc, CatalogueError) and "Conflicting" in str(exc)
        ) else ("github_api_failure" if isinstance(exc, GitHubError) else
                "reference_publication_failed")
        print(f"::error title=Reference enrichment failed::{code}. Check trusted sources and CI.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
