"""Deterministic owner-only curation write, strict request and atomic Git mocks."""
from __future__ import annotations
import base64
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from diamond_catalogue.github_api import GitHubError
from tools.apply_diamond_curation_issue import (
    MARKER, REQUEST_SCHEMA, CURATION_SCHEMA, REPOSITORY,
    Change, CurationConflict, InvalidCurationRequest,
    parse_request, apply_changes, save_changes, curation_digest,
)

ONE = "igi-lg756520111"
TWO = "igi-lg816611062"


def event(changes=None, *, author="choonkiatlee", repo=REPOSITORY,
          title="Save diamond curation", action="opened", body=None):
    if changes is None:
        changes = [{"id": ONE, "field": "starred", "from": False, "to": True}]
    if body is None:
        body = MARKER + "\n" + json.dumps({
            "schema": REQUEST_SCHEMA, "baseline_sha256": curation_digest(published()), "changes": changes,
        }, separators=(",", ":")) + "\n"
    return {"action": action, "repository": {"full_name": repo},
            "issue": {"user": {"login": author}, "title": title, "body": body}}


def published(**flags):
    return {"schema": CURATION_SCHEMA, "diamonds": flags}


class FakeGit:
    """No GitHub network; models blob trees, parents and ref CAS."""
    repo = REPOSITORY
    prefix = "/repos/" + REPOSITORY

    def __init__(self):
        self.head = "head-1"
        self.base = {
            "data/catalog.json": {"schema": "sparkles-diamond-index/1",
                                  "diamonds": [{"id": ONE}, {"id": TWO}]},
            "data/diamond-curation.json": published(),
            "data/diamonds/" + ONE + ".json": {"immutable": "media"},
        }
        self.state = copy.deepcopy(self.base)
        self.commits = {}
        self.trees = {}
        self.changes = []
        self.race = False

    def get_json(self, path):
        if path.endswith("/git/ref/heads/master"):
            return {"object": {"sha": self.head}}
        if "/git/commits/" in path:
            # Existing/new commits have unique base trees.
            sha = path.split("/")[-1]
            return {"tree": {"sha": ("tree-base" if sha == "head-1" else "tree-merged")}}
        if "/git/trees/" in path:
            return {"tree": [{"path": name, "type": "blob", "sha": "blob-" + name}
                             for name in self.state], "truncated": False}
        if "/git/blobs/" in path:
            name = path.split("blob-", 1)[1]
            payload = json.dumps(self.state[name]).encode()
            # GitHub sends line-wrapped Base64 rather than a single unbroken line.
            return {"encoding": "base64", "content": base64.encodebytes(payload).decode()}
        raise AssertionError(path)

    def post_json(self, path, data):
        if path.endswith("/git/trees"):
            self.trees["tree-updated"] = copy.deepcopy(data)
            return {"sha": "tree-updated"}
        if path.endswith("/git/commits"):
            self.commits["commit-curation"] = copy.deepcopy(data)
            return {"sha": "commit-curation"}
        raise AssertionError(path)

    def patch_json(self, path, data):
        assert path.endswith("/git/refs/heads/master")
        assert data["force"] is False
        if self.race:
            self.race = False
            # Simulate another writer changing an *unrelated* file.
            self.state["unrelated.txt"] = {"created": True}
            self.head = "head-updated"
            raise GitHubError(422, "refs")
        assert self.commits["commit-curation"]["parents"] == [self.head]
        tree = self.trees["tree-updated"]
        assert len(tree["tree"]) == 1
        entry = tree["tree"][0]
        assert entry["path"] == "data/diamond-curation.json"
        self.state[entry["path"]] = json.loads(entry["content"])
        self.head = data["sha"]
        self.changes.append(entry["path"])


class CurationIssueTests(unittest.TestCase):
    def test_workflow_uses_importable_repo_module_in_clean_runner(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/diamond-curation-issue-request.yml").read_text(encoding="utf-8")
        expected = "python -m tools.apply_diamond_curation_issue --event"
        self.assertIn(expected, workflow)
        self.assertNotIn("python tools/apply_diamond_curation_issue.py", workflow)
        # Running through -m makes the checkout root importable even without
        # 'pip install -e .' on the GitHub Actions runner.
        result = subprocess.run(
            [sys.executable, "-m", "tools.apply_diamond_curation_issue", "--help"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--github-output", result.stdout)

    def test_accept_exact_owner_request_and_independent_transitions(self):
        changes = [
            {"id": ONE, "field": "starred", "from": False, "to": True},
            {"id": TWO, "field": "archived", "from": False, "to": True},
        ]
        baseline, parsed = parse_request(event(changes))
        self.assertEqual(baseline, curation_digest(published()))
        self.assertEqual(parsed, (Change(ONE, "starred", False, True),
                                  Change(TWO, "archived", False, True)))

    def test_reject_other_actors_repos_titles_actions_and_prs(self):
        cases = [
            event(author="attacker"), event(author="Choonkiatlee"),
            event(repo="attacker/sparkles"), event(title="Ingest diamond"),
            event(action="edited"), event(action="closed"),
        ]
        pull = event()
        pull["issue"]["pull_request"] = {"url": "https://example.org"}
        cases.append(pull)
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(InvalidCurationRequest):
                    parse_request(case)

    def test_reject_invalid_injected_json_and_duplicate_transitions(self):
        valid = {"id": ONE, "field": "archived", "from": False, "to": True}
        malformed = [
            [], [valid, valid],
            [{"id": "ref-r07", "field": "starred", "from": False, "to": True}],
            [{"id": "../../etc/passwd", "field": "starred", "from": False, "to": True}],
            [{"id": ONE, "field": "price", "from": False, "to": True}],
            [{"id": ONE, "field": "starred", "from": 0, "to": True}],
            [{"id": ONE, "field": "starred", "from": False, "to": False}],
            [{**valid, "script": "echo injected"}],
            [valid for _ in range(21)],
        ]
        for changes in malformed:
            with self.subTest(changes=changes):
                with self.assertRaises(InvalidCurationRequest):
                    parse_request(event(changes))
        for body in (
            MARKER + "\n{}\n", MARKER + "\n{}\nextra",
            "Hi\n" + json.dumps(valid),
            MARKER + "\n" + json.dumps({"schema": REQUEST_SCHEMA, "baseline_sha256": curation_digest(published()),
                                           "changes": [valid], "extra": True}),
            "x" * 5000,
        ):
            with self.subTest(body=body[:30]):
                with self.assertRaises(InvalidCurationRequest):
                    parse_request(event(body=body))


    def test_stale_snapshot_rejected_even_if_boolean_old_value_is_repeated(self):
        original = published()
        baseline = curation_digest(original)
        new = published(**{TWO: {"starred": True}})
        with self.assertRaises(CurationConflict):
            apply_changes(new, (Change(ONE, "archived", False, True),), {ONE, TWO}, baseline)
        applied, changed = apply_changes(
            new, (Change(TWO, "starred", False, True),), {ONE, TWO}, baseline
        )
        self.assertFalse(changed)
        self.assertEqual(applied, new)

    def test_invalid_baseline_never_dispatches(self):
        wrong = event()
        wrong["issue"]["body"] = wrong["issue"]["body"].replace(
            curation_digest(published()), "f" * 63 + "z")
        with self.assertRaises(InvalidCurationRequest):
            parse_request(wrong)

    def test_unknown_id_causes_no_partial_update(self):
        data = published()
        changes = (Change(ONE, "starred", False, True),
                   Change("igi-nonexistent", "archived", False, True))
        with self.assertRaises(InvalidCurationRequest):
            apply_changes(data, changes, {ONE, TWO})
        self.assertEqual(data, published())

    def test_real_github_blob_line_wrapping_is_present_in_fixture(self):
        api = FakeGit()
        blob = api.get_json(api.prefix + "/git/blobs/blob-data/catalog.json")
        self.assertIn("\n", blob["content"])
        self.assertGreater(len(blob["content"]), 77)
        # Tests below exercise save_changes end-to-end against wrapped blobs.

    def test_commit_updates_only_curation_and_is_idempotent(self):
        api = FakeGit()
        source = copy.deepcopy(api.state["data/diamonds/" + ONE + ".json"])
        changes = (Change(ONE, "starred", False, True),
                   Change(ONE, "archived", False, True),
                   Change(TWO, "starred", False, True))
        sha, changed = save_changes(api, changes)
        self.assertTrue(changed)
        self.assertEqual(sha, "commit-curation")
        self.assertEqual(api.changes, ["data/diamond-curation.json"])
        self.assertEqual(api.state["data/diamond-curation.json"]["diamonds"],
                         {ONE: {"starred": True, "archived": True},
                          TWO: {"starred": True}})
        self.assertEqual(api.state["data/diamonds/" + ONE + ".json"], source)
        self.assertEqual(api.state["data/catalog.json"], api.base["data/catalog.json"])
        sha2, changed2 = save_changes(api, changes)
        self.assertFalse(changed2)
        self.assertEqual(sha2, sha)
        self.assertEqual(len(api.changes), 1)

    def test_sparse_restore_preserves_star_and_other_diamonds(self):
        data = published(**{ONE: {"starred": True, "archived": True},
                            TWO: {"starred": True}})
        revised, changed = apply_changes(data, (Change(ONE, "archived", True, False),),
                                         {ONE, TWO})
        self.assertTrue(changed)
        self.assertEqual(revised["diamonds"], {ONE: {"starred": True}, TWO: {"starred": True}})
        self.assertTrue(data["diamonds"][ONE]["archived"])

    def test_ref_conflict_retries_without_overwriting_unrelated_commits(self):
        api = FakeGit()
        api.race = True
        save_changes(api, (Change(ONE, "starred", False, True),))
        self.assertIn("unrelated.txt", api.state)
        self.assertEqual(api.state["data/diamond-curation.json"]["diamonds"][ONE]["starred"], True)
        self.assertEqual(api.changes, ["data/diamond-curation.json"])


if __name__ == "__main__":
    unittest.main()
