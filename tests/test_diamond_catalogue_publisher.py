"""Offline publication smoke tests for GitHub Releases and atomic Git updates."""
import base64
import copy
import hashlib
import json
import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from diamond_catalogue import CatalogueError, plan_publication
from diamond_catalogue.github_api import GitHubError
from diamond_catalogue.github_catalogue import publish_plan, publish_result
from diamond_retrieval.models import IdentityComparison, IdentityOutcome, ResultStatus
from tests.test_diamond_catalogue import result
from tests.test_diamond_retrieval_retailers import (
    QD_URL, RetailerEndToEndTests,
)
from diamond_retrieval import default_config, retrieve_diamond


class FakeGitHub:
    """Minimal stateful model of the REST Release/Tree/Commit/Refs protocol."""
    prefix = "/repos/test/sparkles"

    def __init__(self):
        self.releases = {}
        self.releases_by_id = {}
        self.assets = {}  # asset-id -> asset metadata
        self.asset_bytes = {}
        self.next_id = 0
        self.uploads = 0
        self.downloads = 0
        self.fail_upload_number = None
        self.omit_digests = False
        self.stale_once = False
        self.truncated = False
        self.head = "c0"
        self.commit_trees = {"c0": "t0"}
        self.commit_parents = {}
        self.trees = {"t0": {}}
        self.blobs = {}
        self.commits_created = 0

    def get_json(self, path):
        if "/releases/tags/" in path:
            tag = path.split("/releases/tags/", 1)[1]
            if tag not in self.releases:
                raise GitHubError(404, "GET release")
            return self.releases[tag]
        if "/releases/" in path and "/assets?" in path:
            rid = int(path.split("/releases/", 1)[1].split("/", 1)[0])
            tag = self.releases_by_id[rid]
            page = int(parse_qs(urlsplit(path).query)["page"][0])
            arr = sorted(
                (a for a in self.assets.values() if a["release_tag"] == tag),
                key=lambda a: a["id"]
            )
            return [copy.deepcopy(a) for a in arr[(page-1)*100:page*100]]
        if path == self.prefix + "/git/ref/heads/master":
            return {"object": {"sha": self.head}}
        if "/git/commits/" in path:
            commit = path.rsplit("/", 1)[-1]
            return {"tree": {"sha": self.commit_trees[commit]}}
        if "/git/trees/" in path:
            tid = path.split("/git/trees/", 1)[1].split("?", 1)[0]
            records = self.trees[tid]
            return {
                "truncated": self.truncated,
                "tree": [{"path": path, "type": "blob", "sha": blob_id}
                         for path, blob_id in sorted(records.items())],
            }
        if "/git/blobs/" in path:
            bid = path.rsplit("/", 1)[-1]
            return {"encoding": "base64", "content": base64.b64encode(
                self.blobs[bid].encode("utf-8")
            ).decode("ascii")}
        raise AssertionError("Unrecognized fake GET: " + path)

    def post_json(self, path, data):
        if path == self.prefix + "/releases":
            tag = data["tag_name"]
            if tag in self.releases:
                raise GitHubError(422, "release already exists")
            self.next_id += 1
            rid = self.next_id
            release = {
                "id": rid, "tag_name": tag,
                "upload_url": f"https://uploads.github.com{self.prefix}/releases/{rid}/assets{{?name,label}}",
            }
            self.releases[tag] = release
            self.releases_by_id[rid] = tag
            return release
        if path == self.prefix + "/git/trees":
            if any(e["path"] not in ("data/catalog.json",) and
                   not e["path"].startswith("data/diamonds/") for e in data["tree"]):
                raise AssertionError("Binary or unsafe file committed in catalogue")
            self.next_id += 1
            tid = f"t{self.next_id}"
            tree = self.trees[data["base_tree"]].copy()
            for entry in data["tree"]:
                self.next_id += 1
                bid = f"b{self.next_id}"
                self.blobs[bid] = entry["content"]
                tree[entry["path"]] = bid
            self.trees[tid] = tree
            return {"sha": tid}
        if path == self.prefix + "/git/commits":
            self.commits_created += 1
            cid = f"c{self.next_id}-{self.commits_created}"
            self.commit_trees[cid] = data["tree"]
            self.commit_parents[cid] = data["parents"][0]
            return {"sha": cid}
        raise AssertionError("Unrecognized fake POST: " + path)

    def patch_json(self, path, data):
        assert path == self.prefix + "/git/refs/heads/master"
        assert data["force"] is False
        if self.stale_once:
            self.stale_once = False
            self.head = "c-external"
            self.commit_trees["c-external"] = self.commit_trees[self.head] if False else self.commit_trees["c0"]
            raise GitHubError(422, "non-fast-forward")
        if self.commit_parents[data["sha"]] != self.head:
            raise GitHubError(422, "non-fast-forward")
        self.head = data["sha"]
        return {"object": {"sha": self.head}}

    def post_bytes(self, url, payload, media_type):
        self.uploads += 1
        if self.uploads == self.fail_upload_number:
            raise GitHubError(503, "asset upload")
        parsed = urlsplit(url)
        assert parsed.hostname == "uploads.github.com"
        rid = int(parsed.path.split("/releases/", 1)[1].split("/", 1)[0])
        tag = self.releases_by_id[rid]
        name = parse_qs(parsed.query)["name"][0]
        self.next_id += 1
        aid = self.next_id
        info = {
            "id": aid, "name": name, "release_tag": tag, "state": "uploaded",
            "size": len(payload),
            "digest": None if self.omit_digests else "sha256:" + hashlib.sha256(payload).hexdigest(),
            "browser_download_url": f"https://github.com/test/sparkles/releases/download/{tag}/{name}",
        }
        self.assets[aid] = info
        self.asset_bytes[aid] = payload
        return copy.deepcopy(info)

    def get_bytes(self, path):
        self.downloads += 1
        aid = int(path.rsplit("/", 1)[-1])
        return self.asset_bytes[aid]

    def manifest(self, diamond_id):
        path = "data/diamonds/" + diamond_id + ".json"
        blob_id = self.trees[self.commit_trees[self.head]][path]
        return json.loads(self.blobs[blob_id])

    def index(self):
        blob_id = self.trees[self.commit_trees[self.head]]["data/catalog.json"]
        return json.loads(self.blobs[blob_id])

    @property
    def committed_paths(self):
        return sorted(self.trees[self.commit_trees[self.head]])


class GitHubPublishingTests(unittest.TestCase):
    def test_complete_first_publication_and_binary_excluded_from_git(self):
        api = FakeGitHub()
        expected = plan_publication(result())
        receipt = publish_result(result(), api)
        self.assertTrue(receipt.changed)
        self.assertEqual(receipt.diamond_id, "igi-lg800667394")
        self.assertEqual(receipt.asset_count, len(expected.assets))
        self.assertEqual(receipt.catalogue_count, 1)
        self.assertEqual(len(api.releases), 1)
        self.assertEqual(len(api.assets), len(expected.assets))
        self.assertEqual(api.committed_paths,
                         ["data/catalog.json", "data/diamonds/igi-lg800667394.json"])
        manifest = api.manifest(receipt.diamond_id)
        self.assertEqual(api.index()["diamonds"][0]["id"], receipt.diamond_id)
        self.assertEqual(manifest["evidence"][2]["frames"][0]["source_index"], 253)
        self.assertTrue(all(v.startswith("asset-") for v in
                            (a["name"] for a in api.assets.values())))
        for asset in expected.assets:
            self.assertIn(asset.payload, api.asset_bytes.values())
        for doc in api.blobs.values():
            self.assertNotIn("frame-X", doc)

    def test_identical_republication_is_noop_and_no_reupload(self):
        api = FakeGitHub()
        one = publish_result(result(), api)
        total = api.uploads
        two = publish_result(result(), api)
        self.assertFalse(two.changed)
        self.assertEqual(one.commit_sha, two.commit_sha)
        self.assertEqual(api.uploads, total)
        self.assertEqual(len(api.index()["diamonds"]), 1)

    def test_cross_retailer_upsert_keeps_both_observations_without_reupload(self):
        api = FakeGitHub()
        publish_result(result(), api)
        uploads = api.uploads
        receipt = publish_result(
            result(url="https://diyona.com/pages/diamond-detail?sku=another", price="4100"),
            api,
        )
        self.assertTrue(receipt.changed)
        self.assertEqual(api.uploads, uploads)
        self.assertEqual(len(api.manifest(receipt.diamond_id)["listings"]), 2)
        self.assertEqual(len(api.index()["diamonds"]), 1)

    def test_new_diamond_rebuilds_index_from_all_manifests(self):
        api = FakeGitHub()
        publish_result(result(), api)
        publish_result(result(report="LG800667395"), api)
        self.assertEqual(len(api.index()["diamonds"]), 2)
        self.assertEqual([r["id"] for r in api.index()["diamonds"]],
                         ["igi-lg800667394", "igi-lg800667395"])

    def test_partial_result_is_published_honestly_and_preserves_earlier_media(self):
        api = FakeGitHub()
        publish_result(result(), api)
        receipt = publish_result(result(
            url="https://diyona.com/pages/diamond-detail?sku=partial",
            status=ResultStatus.PARTIAL, evidence=False, price=None), api)
        manifest = api.manifest(receipt.diamond_id)
        self.assertEqual(len(manifest["evidence"]), 3)
        self.assertEqual(len(manifest["retrievals"]), 2)
        self.assertEqual(api.index()["diamonds"][0]["retrieval_status"], "partial")
        self.assertTrue(api.index()["diamonds"][0]["has_motion"])

    def test_conflicting_identity_fails_before_release_created(self):
        api = FakeGitHub()
        r = result()
        bad = replace(r, identity_comparisons=(
            IdentityComparison("report_number", IdentityOutcome.CONFLICT, ("A", "B")),
        ))
        with self.assertRaises(CatalogueError):
            publish_result(bad, api)
        self.assertFalse(api.releases)
        self.assertEqual(api.head, "c0")

    def test_invalid_original_sha_fails_before_release_created(self):
        api = FakeGitHub()
        plan = plan_publication(result())
        tampered = replace(plan.assets[0], sha256="0" * 64)
        with self.assertRaises(CatalogueError):
            publish_plan(replace(plan, assets=(tampered,) + plan.assets[1:]), api)
        self.assertFalse(api.releases)
        self.assertEqual(api.head, "c0")

    def test_upload_failure_leaves_no_manifest_commit(self):
        api = FakeGitHub()
        api.fail_upload_number = 2
        with self.assertRaises(GitHubError):
            publish_result(result(), api)
        self.assertEqual(api.head, "c0")
        self.assertNotIn("data/catalog.json", api.committed_paths)
        self.assertEqual(len(api.assets), 1)  # safe orphan; next attempt recovers
        api.fail_upload_number = None
        receipt = publish_result(result(), api)
        self.assertTrue(receipt.changed)
        self.assertEqual(len(api.assets), len(plan_publication(result()).assets))

    def test_existing_asset_digest_mismatch_prevents_manifest_commit(self):
        api = FakeGitHub()
        publish_result(result(), api)
        prior_head = api.head
        aid = sorted(api.assets)[0]
        api.assets[aid]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(CatalogueError, "digest mismatch"):
            publish_result(result(report="LG800667394"), api)
        self.assertEqual(api.head, prior_head)

    def test_missing_digest_fallback_checks_actual_bytes(self):
        api = FakeGitHub()
        api.omit_digests = True
        publish_result(result(), api)
        self.assertGreaterEqual(api.downloads, 4)
        api.downloads = 0
        publish_result(result(), api)
        self.assertGreaterEqual(api.downloads, 4)

    def test_stale_git_head_is_retried_without_losing_catalogue(self):
        api = FakeGitHub()
        api.stale_once = True
        receipt = publish_result(result(), api)
        self.assertTrue(receipt.changed)
        self.assertEqual(api.commits_created, 2)
        self.assertEqual(api.index()["diamonds"][0]["id"], receipt.diamond_id)

    def test_release_asset_cap_is_fail_closed(self):
        api = FakeGitHub()
        with patch("diamond_catalogue.github_release.ASSET_LIMIT", 2):
            with self.assertRaisesRegex(CatalogueError, "1,000-asset limit"):
                publish_result(result(), api)
        self.assertEqual(api.head, "c0")
        self.assertEqual(api.uploads, 0)

    def test_truncated_source_tree_fails_closed_after_upload_without_git_commit(self):
        api = FakeGitHub()
        api.truncated = True
        with self.assertRaisesRegex(CatalogueError, "truncated Git tree"):
            publish_result(result(), api)
        self.assertEqual(api.head, "c0")
        self.assertFalse(api.committed_paths)

    def test_real_256_frame_retrieval_to_github_release_and_git_manifest(self):
        fixtures = RetailerEndToEndTests()
        retrieved = retrieve_diamond(QD_URL, config=default_config(fixtures.qd_http()))
        api = FakeGitHub()
        receipt = publish_result(retrieved, api)
        self.assertTrue(receipt.changed)
        self.assertEqual(len(retrieved.rotations[0].frames), 256)
        self.assertEqual(len(api.assets), 258)  # certificate, still, 256 original frames
        manifest = api.manifest(receipt.diamond_id)
        rotation = next(e for e in manifest["evidence"] if e["kind"] == "rotation")
        self.assertEqual(len(rotation["frames"]), 256)
        self.assertIsNone(rotation["payload_asset"])
        self.assertEqual([f["source_index"] for f in rotation["frames"]], list(range(256)))
        self.assertEqual(api.index()["diamonds"][0]["thumbnail_url"],
                         next(e["payload_asset"]["storage"]["url"] for e in manifest["evidence"]
                              if e["kind"] == "still"))

    def test_real_igi_403_partial_creates_valid_catalogue_with_no_pdf(self):
        fixtures = RetailerEndToEndTests()
        retrieved = retrieve_diamond(QD_URL, config=default_config(fixtures.qd_http(pdf_status=403)))
        api = FakeGitHub()
        receipt = publish_result(retrieved, api)
        manifest = api.manifest(receipt.diamond_id)
        self.assertEqual(receipt.status, "partial")
        self.assertEqual(manifest["retrievals"][0]["certificate_link"], retrieved.certificate_link)
        self.assertFalse(any(e["kind"] == "certificate" for e in manifest["evidence"]))
        self.assertTrue(any(e["kind"] == "rotation" for e in manifest["evidence"]))
        self.assertEqual(len(api.index()["diamonds"]), 1)


if __name__ == "__main__":
    unittest.main()
