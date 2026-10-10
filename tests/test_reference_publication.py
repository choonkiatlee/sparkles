"""Offline reference enrichment/publishing contracts (#197)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from diamond_catalogue import CatalogueError
from diamond_catalogue.github_catalogue import publish_result
from diamond_catalogue.reference_publish import (
    GitHubReferenceCatalogue, plan_reference_media, publish_reference,
)
from diamond_catalogue.references import build_index, validate_reference
from diamond_catalogue.serialization import json_document
from diamond_retrieval import (
    IdentityComparison, IdentityOutcome, ResultStatus,
    retrieve_reference_media,
)
from tests.test_diamond_catalogue import result
from tests.test_diamond_catalogue_publisher import FakeGitHub
from tests.test_diamond_retrieval_motion import (
    AUDITS, FakeHttpClient, _progressive_source_responses,
)


class ReferenceFakeGitHub(FakeGitHub):
    """Same Releases/Git/refs fake as certified publisher, with reference paths."""

    def post_json(self, path, data):
        if path == self.prefix + "/git/trees":
            allowed = {"data/catalog.json", "data/reference-index.json"}
            for entry in data["tree"]:
                name = entry["path"]
                if (name not in allowed and
                    not name.startswith(("data/diamonds/", "data/references/"))):
                    raise AssertionError("Unsafe reference Git tree path")
            self.next_id += 1
            tid = f"t{self.next_id}"
            tree = self.trees[data["base_tree"]].copy()
            for item in data["tree"]:
                self.next_id += 1
                bid = f"b{self.next_id}"
                self.blobs[bid] = item["content"]
                tree[item["path"]] = bid
            self.trees[tid] = tree
            return {"sha": tid}
        return super().post_json(path, data)

    def seed(self, references):
        assert self.head == "c0"
        for item in references:
            path = f"data/references/{item['id']}.json"
            blob_id = "seed-" + item["id"]
            self.blobs[blob_id] = json_document(item)
            self.trees["t0"][path] = blob_id
        self.blobs["seed-index"] = json_document(build_index(references))
        self.trees["t0"]["data/reference-index.json"] = "seed-index"

    def reference(self, name):
        path = f"data/references/{name}.json"
        key = self.trees[self.commit_trees[self.head]][path]
        return json.loads(self.blobs[key])

    def reference_index(self):
        key = self.trees[self.commit_trees[self.head]]["data/reference-index.json"]
        return json.loads(self.blobs[key])


def ref(name="fixture-r01", media=None):
    return {
        "schema": "sparkles-reference/1", "id": name,
        "label": "Expert teaching example",
        "identity": {"status": "unverified", "lab": None, "report_number": None},
        "linked_diamond_id": None,
        "diamond_metadata": {"shape": "Asscher"},
        "commentary": "Buyer and Karl_K disagreed on how lively the centre looked.",
        "source_links": [{
            "kind": "discussion",
            "url": "https://www.pricescope.com/community/threads/example.12345/",
        }],
        "media_sources": media or [], "topics": ["liveliness"],
        "evidence": [],
    }


def still_result(*, partial=False):
    original = result(
        evidence=False, status=ResultStatus.PARTIAL if partial else ResultStatus.COMPLETE,
    )
    if partial:
        return original
    still = result().evidence[1]
    return replace(original, evidence=(still,))


class ReferencePublicationTests(unittest.TestCase):
    def test_metadata_mode_is_a_no_network_idempotent_noop(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        def forbidden(*args, **kwargs):
            raise AssertionError("metadata-only tried to retrieve media")
        a = publish_reference("fixture-r01", mode="metadata", api=api, retrieve=forbidden)
        self.assertFalse(a.changed)
        self.assertEqual(api.uploads, 0)
        self.assertEqual(api.commits_created, 0)
        self.assertEqual(api.reference_index()["references"][0]["selection_id"],
                         "ref-fixture-r01")

    def test_source_media_uploads_verified_original_and_atomic_manifest_index(self):
        api = ReferenceFakeGitHub()
        item = ref(media=[{
            "kind": "still", "provider": "curator", "status": "linked_unverified",
            "url": "https://media.example.test/asscher.jpg",
        }])
        api.seed([item])
        calls = []
        def retrieve(reference_id, **kwargs):
            calls.append((reference_id, kwargs))
            return still_result()
        receipt = publish_reference("fixture-r01", mode="media", api=api, retrieve=retrieve)
        self.assertTrue(receipt.changed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], item["id"])
        self.assertEqual(calls[0][1]["media_sources"], item["media_sources"])
        self.assertFalse(calls[0][1]["include_igi_pdf"])
        self.assertEqual(receipt.asset_count, 1)
        self.assertEqual(api.uploads, 1)
        self.assertIn("sparkles-reference-fixture-r01", api.releases)
        saved = api.reference("fixture-r01")
        self.assertEqual(saved["commentary"], item["commentary"])
        self.assertEqual(saved["source_links"], item["source_links"])
        self.assertEqual(saved["media_sources"], item["media_sources"])
        self.assertEqual(len(saved["evidence"]), 1)
        asset = saved["evidence"][0]["payload_asset"]
        self.assertIn("/releases/download/sparkles-reference-fixture-r01/", asset["storage"]["url"])
        self.assertEqual(api.reference_index()["references"][0]["thumbnail_url"],
                         asset["storage"]["url"])
        self.assertIn("data/reference-index.json", api.committed_paths)
        self.assertEqual(api.commits_created, 1)
        self.assertEqual(len(api.asset_bytes), 1)
        self.assertFalse(any("jpeg actual original still" in document for document in api.blobs.values()))

    def test_repeated_media_enrichment_is_noop_with_no_duplicate_release_asset(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        retrieve = lambda *args, **kwargs: still_result()
        first = publish_reference("fixture-r01", mode="media", api=api, retrieve=retrieve)
        second = publish_reference("fixture-r01", mode="media", api=api, retrieve=retrieve)
        self.assertFalse(second.changed)
        self.assertEqual(first.commit_sha, second.commit_sha)
        self.assertEqual(api.commits_created, 1)
        self.assertEqual(api.uploads, 1)

    def test_failure_only_updates_attempts_without_removing_old_good_media(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        publish_reference("fixture-r01", mode="media", api=api,
                          retrieve=lambda *args, **kwargs: still_result())
        receipt = publish_reference("fixture-r01", mode="all", api=api,
                                    retrieve=lambda *args, **kwargs: still_result(partial=True))
        self.assertTrue(receipt.changed)
        saved = api.reference("fixture-r01")
        self.assertEqual(len(saved["evidence"]), 1)
        self.assertEqual(saved["enrichment_attempts"][0]["status"], "missing")
        self.assertEqual(api.reference_index()["references"][0]["has_motion"], False)
        self.assertEqual(api.uploads, 1)

    def test_different_identity_blocks_all_mutations(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        bad = replace(still_result(), identity_comparisons=(
            IdentityComparison("report_number", IdentityOutcome.CONFLICT, ("A", "B")),
        ))
        with self.assertRaises(CatalogueError):
            publish_reference("fixture-r01", mode="media", api=api,
                              retrieve=lambda *args, **kwargs: bad)
        self.assertEqual(api.commits_created, 0)
        self.assertEqual(api.uploads, 0)
        self.assertFalse(api.releases)

    def test_report_lookup_mismatch_blocks_unrelated_source_publication(self):
        from diamond_retrieval import ROTATION, EvidenceAttempt, EvidenceStatus
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        a = EvidenceAttempt("r:lookup", ROTATION, "test", EvidenceStatus.RESOLUTION_FAILED,
                            message="Loupe360 lab mismatch: expected IGI, returned GIA")
        payload = replace(still_result(), attempts=(a,))
        with self.assertRaisesRegex(CatalogueError, "Conflicting reference"):
            publish_reference("fixture-r01", mode="media", api=api,
                              retrieve=lambda *args, **kwargs: payload)
        self.assertEqual(api.uploads, 0)

    def test_stale_curated_sources_fail_before_manifest_changes(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        def concurrent_change(*args, **kwargs):
            name = "data/references/fixture-r01.json"
            current = api.reference("fixture-r01")
            current["commentary"] = "Independent updated expert interpretation."
            api.blobs["changed"] = json_document(current)
            api.trees["t0"][name] = "changed"
            return still_result()
        with self.assertRaisesRegex(CatalogueError, "Curated reference changed"):
            publish_reference("fixture-r01", mode="media", api=api,
                              retrieve=concurrent_change)
        self.assertEqual(api.commits_created, 0)
        self.assertEqual(api.reference("fixture-r01")["commentary"],
                         "Independent updated expert interpretation.")

    def test_unsupported_sources_preserve_original_links(self):
        from diamond_retrieval import retrieve_reference_media, HttpResponse
        from tests.test_reference_media_lookup import FakeHttp
        url = "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b"
        item = ref(media=[{
            "kind": "viewer", "provider": "v360.diamonds",
            "url": url, "status": "linked_unverified",
        }])
        api = ReferenceFakeGitHub()
        api.seed([item])
        retrieved = lambda ref_id, **kwargs: retrieve_reference_media(
            ref_id, http_client=FakeHttp(), **kwargs
        )
        publish_reference("fixture-r01", mode="media", api=api, retrieve=retrieved)
        saved = api.reference("fixture-r01")
        self.assertEqual(saved["media_sources"], item["media_sources"])
        self.assertEqual(saved["enrichment_attempts"][0]["status"], "unsupported")
        self.assertEqual(saved["evidence"], [])
        self.assertEqual(api.uploads, 0)

    def test_unaccepted_id_cannot_trigger_any_download_or_release(self):
        api = ReferenceFakeGitHub()
        api.seed([ref()])
        for name in ("other", "../fixture-r01", "ref-fixture-r01"):
            with self.subTest(name=name), self.assertRaises(CatalogueError):
                publish_reference(name, mode="media", api=api,
                                  retrieve=lambda *args, **kwargs: self.fail("unexpected retrieval"))
        self.assertEqual(api.uploads, 0)

    def test_verified_certified_link_reuses_saved_media_without_release(self):
        api = ReferenceFakeGitHub()
        still_only = replace(result(), evidence=(result().evidence[1],))
        publish_result(still_only, api)
        linked = ref()
        linked["identity"] = {
            "status": "linked", "lab": "IGI", "report_number": "LG800667394",
        }
        linked["linked_diamond_id"] = "igi-lg800667394"
        cert = api.manifest("igi-lg800667394")
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "igi-lg800667394.json").write_text(json_document(cert))
            with patch("diamond_catalogue.references.DIAMOND_DIR", Path(temp)):
                # Seed the reference into the existing certified master tree.
                path = "data/references/fixture-r01.json"
                api.blobs["linked-ref"] = json_document(linked)
                api.trees[api.commit_trees[api.head]][path] = "linked-ref"
                api.blobs["reference-index"] = json_document(build_index([linked]))
                api.trees[api.commit_trees[api.head]]["data/reference-index.json"] = "reference-index"
                before = api.uploads
                publish_reference("fixture-r01", mode="media", api=api,
                    retrieve=lambda *args, **kwargs: self.fail("should reuse certified"))
                saved = api.reference("fixture-r01")
                self.assertEqual(saved["evidence"], cert["evidence"])
                self.assertEqual(api.uploads, before)
                self.assertFalse(any(k.startswith("sparkles-reference-") for k in api.releases))

    def test_real_256_frame_direct_viewer_to_release_and_static_index(self):
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-NEW123"
        root = "https://vision.diajewel360.com/imaged/VL-NEW123"
        item = ref(media=[{
            "kind": "viewer", "provider": "diajewel", "url": viewer,
            "status": "linked_unverified",
        }])
        api = ReferenceFakeGitHub()
        api.seed([item])
        responses = _progressive_source_responses(AUDITS[0], root, version=1)
        http = FakeHttpClient(responses)
        receipt = publish_reference("fixture-r01", mode="media", api=api,
            retrieve=lambda reference_id, **kwargs: retrieve_reference_media(
                reference_id, http_client=http, **kwargs))
        self.assertTrue(receipt.changed)
        saved = api.reference("fixture-r01")
        rotation = saved["evidence"][0]
        self.assertEqual(rotation["kind"], "rotation")
        self.assertEqual(rotation["status"], "success")
        self.assertEqual(len(rotation["frames"]), 256)
        self.assertEqual(sorted(f["source_index"] for f in rotation["frames"]), list(range(256)))
        self.assertEqual(api.reference_index()["references"][0]["has_motion"], True)
        self.assertEqual(receipt.asset_count, 256)
        self.assertEqual(api.uploads, 256)
        self.assertEqual(receipt.reference_count, 1)
        self.assertTrue(validate_reference(saved))
        self.assertEqual(api.commits_created, 1)


if __name__ == "__main__":
    unittest.main()
