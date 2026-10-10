"""Owner-authorised issue changes: validate, compare-and-swap and atomically commit.

No issue text is used as a shell command. Only an allowlisted diamond ID + boolean
field transition can be applied. GitHub credentials remain in the runner.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from diamond_catalogue.github_api import GitHubAPI, GitHubError

REPOSITORY = "choonkiatlee/sparkles"
OWNER = "choonkiatlee"
TITLE = "Save diamond curation"
MARKER = "<!-- sparkles-diamond-curation-request/v1 -->"
REQUEST_SCHEMA = "sparkles-diamond-curation-request/1"
CURATION_SCHEMA = "sparkles-diamond-curation/1"
MAX_CHANGES = 20
CURATION_PATH = "data/diamond-curation.json"
INDEX_PATH = "data/catalog.json"
FIELDS = frozenset({"starred", "archived"})


class InvalidCurationRequest(ValueError):
    pass


class CurationConflict(ValueError):
    pass


@dataclass(frozen=True)
class Change:
    id: str
    field: str
    before: bool
    after: bool


def _keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def curation_digest(data: dict) -> str:
    canonical = [
        [id, flags.get("starred") is True, flags.get("archived") is True]
        for id, flags in sorted(data["diamonds"].items())
    ]
    payload = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_request(event: dict) -> tuple[str, tuple[Change, ...]]:
    if not isinstance(event, dict) or event.get("action") != "opened":
        raise InvalidCurationRequest("Only newly opened issues are accepted")
    if (event.get("repository") or {}).get("full_name") != REPOSITORY:
        raise InvalidCurationRequest("Unexpected repository")
    issue = event.get("issue") or {}
    if (issue.get("user") or {}).get("login") != OWNER or issue.get("title") != TITLE or issue.get("pull_request"):
        raise InvalidCurationRequest("Not an owner-authored curation issue")
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 4500:
        raise InvalidCurationRequest("Invalid issue body")
    lines = body.replace("\r\n", "\n").rstrip("\n").split("\n")
    if len(lines) != 2 or lines[0] != MARKER:
        raise InvalidCurationRequest("Unsupported issue format")
    try:
        data = json.loads(lines[1])
    except (ValueError, TypeError) as exc:
        raise InvalidCurationRequest("Invalid JSON") from exc
    if not _keys(data, {"schema", "baseline_sha256", "changes"}) or data["schema"] != REQUEST_SCHEMA:
        raise InvalidCurationRequest("Unsupported curation request schema")
    baseline_sha256 = data["baseline_sha256"]
    if (not isinstance(baseline_sha256, str) or len(baseline_sha256) != 64
            or any(char not in "0123456789abcdef" for char in baseline_sha256)):
        raise InvalidCurationRequest("Invalid curation baseline")
    raw = data["changes"]
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_CHANGES:
        raise InvalidCurationRequest("Invalid change count")
    seen = set()
    result = []
    for change in raw:
        if not _keys(change, {"id", "field", "from", "to"}):
            raise InvalidCurationRequest("Invalid curation operation")
        identifier, field = change["id"], change["field"]
        if (not isinstance(identifier, str) or not identifier.startswith("igi-") or
                len(identifier) > 90 or not all(char in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in identifier)
                or field not in FIELDS or not isinstance(field, str) or
                type(change["from"]) is not bool or type(change["to"]) is not bool or
                change["from"] == change["to"] or (identifier, field) in seen):
            raise InvalidCurationRequest("Invalid curation value")
        seen.add((identifier, field))
        result.append(Change(identifier, field, change["from"], change["to"]))
    return baseline_sha256, tuple(result)


def validate_published(data: dict, valid_ids: set[str]) -> None:
    if not _keys(data, {"schema", "diamonds"}) or data["schema"] != CURATION_SCHEMA or not isinstance(data["diamonds"], dict):
        raise InvalidCurationRequest("Invalid stored curation document")
    for identifier, flags in data["diamonds"].items():
        if (identifier not in valid_ids or not isinstance(flags, dict) or not flags or
                any(field not in FIELDS or type(value) is not bool for field, value in flags.items())):
            raise InvalidCurationRequest("Invalid stored curation entry")


def apply_changes(data: dict, changes: tuple[Change, ...], valid_ids: set[str],
                  baseline_sha256: str | None = None) -> tuple[dict, bool]:
    validate_published(data, valid_ids)
    # All checks must pass before making even one change.
    for change in changes:
        if change.id not in valid_ids:
            raise InvalidCurationRequest("Diamond no longer exists in personal catalogue")
        current = data["diamonds"].get(change.id, {}).get(change.field, False)
        if current != change.before and current != change.after:
            raise CurationConflict("Saved status has changed; refresh before submitting again")
    if (baseline_sha256 is not None and curation_digest(data) != baseline_sha256):
        # Retries of an already applied request may have a changed baseline:
        # treat those as idempotent but never reapply a genuinely stale update.
        if all(data["diamonds"].get(change.id, {}).get(change.field, False) == change.after
               for change in changes):
            return json.loads(json.dumps(data)), False
        raise CurationConflict("Saved curation changed since this browser snapshot")
    revised = json.loads(json.dumps(data))
    for change in changes:
        flags = revised["diamonds"].setdefault(change.id, {})
        if change.after:
            flags[change.field] = True
        else:
            flags.pop(change.field, None)
        if not flags:
            del revised["diamonds"][change.id]
    return revised, revised != data


def _blob(api: GitHubAPI, sha: str):
    blob = api.get_json(f"{api.prefix}/git/blobs/{sha}")
    if blob.get("encoding") != "base64":
        raise InvalidCurationRequest("Unsupported stored blob encoding")
    try:
        # GitHub Git Blob API line-wraps Base64 content (typically at 76 chars).
        # Remove only transport line breaks, then keep strict alphabet checks.
        encoded = blob["content"]
        if not isinstance(encoded, str):
            raise InvalidCurationRequest("Invalid stored blob content")
        return json.loads(base64.b64decode("".join(encoded.splitlines()), validate=True))
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidCurationRequest("Invalid stored JSON") from exc


def save_changes(api: GitHubAPI, changes: tuple[Change, ...],
                 baseline_sha256: str | None = None) -> tuple[str, bool]:
    if api.repo != REPOSITORY:
        raise InvalidCurationRequest("Unexpected target repository")
    for attempt in range(3):
        head = api.get_json(f"{api.prefix}/git/ref/heads/master")["object"]["sha"]
        commit = api.get_json(f"{api.prefix}/git/commits/{head}")
        tree_sha = commit["tree"]["sha"]
        tree = api.get_json(f"{api.prefix}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise InvalidCurationRequest("Truncated Git tree")
        entries = {row["path"]: row["sha"] for row in tree["tree"] if row.get("type") == "blob"}
        if INDEX_PATH not in entries or CURATION_PATH not in entries:
            raise InvalidCurationRequest("Required catalogue files missing")
        catalogue = _blob(api, entries[INDEX_PATH])
        if (not isinstance(catalogue, dict) or catalogue.get("schema") != "sparkles-diamond-index/1" or
                not isinstance(catalogue.get("diamonds"), list)):
            raise InvalidCurationRequest("Invalid stored personal catalogue")
        ids = {row["id"] for row in catalogue["diamonds"]}
        if len(ids) != len(catalogue["diamonds"]):
            raise InvalidCurationRequest("Duplicate personal diamond ID")
        published = _blob(api, entries[CURATION_PATH])
        revised, changed = apply_changes(published, changes, ids, baseline_sha256)
        if not changed:
            return head, False
        updated_tree = api.post_json(f"{api.prefix}/git/trees", {
            "base_tree": tree_sha,
            "tree": [{"path": CURATION_PATH, "mode": "100644", "type": "blob",
                      "content": json.dumps(revised, indent=2, sort_keys=True, ensure_ascii=False) + "\n"}]
        })
        new_commit = api.post_json(f"{api.prefix}/git/commits", {
            "message": "Catalogue: save shortlist and archive changes",
            "tree": updated_tree["sha"], "parents": [head]
        })
        try:
            api.patch_json(f"{api.prefix}/git/refs/heads/master", {
                "sha": new_commit["sha"], "force": False
            })
        except GitHubError as exc:
            if exc.status not in {409, 422} or attempt == 2:
                raise
            continue
        return new_commit["sha"], True
    raise CurationConflict("Unable to commit after concurrent changes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        baseline, changes = parse_request(event)
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", ""))
        sha, changed = save_changes(api, changes, baseline)
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("commit_sha=" + sha + "\n")
            output.write("changed=" + ("true" if changed else "false") + "\n")
        print("Applied authorised curation request; changed=" + str(changed))
        return 0
    except (ValueError, KeyError, TypeError, OSError, GitHubError):
        # Never print raw issue bodies, author-controlled values or token-bearing errors.
        print("::error title=Diamond curation save rejected::Request rejected, conflicted, or GitHub publication failed; local draft is unaffected.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
