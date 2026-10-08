"""Deterministic automatic overview-thumbnail publication and safe fallbacks."""
import hashlib
import unittest
from diamond_catalogue.faceup_publish import plan_generated_thumbnail, publish_generated_thumbnail
from diamond_catalogue.github_catalogue import GitHubCatalogue,publish_result
from diamond_catalogue.models import CatalogueError
from diamond_catalogue import InMemoryStorage
from tests.test_diamond_catalogue import result
from tests.test_diamond_catalogue_publisher import FakeGitHub


class AutomaticThumbnailPublishingTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeGitHub()
        publish_result(result(),self.api)
        self.manifest=self.api.manifest("igi-lg800667394")
        self.frame=next(e for e in self.manifest["evidence"] if e["kind"]=="rotation")["frames"][0]
        self.content=b"generated-test-icon"
        self.hash=hashlib.sha256(self.content).hexdigest()
        self.source=self.frame["asset"]["sha256"]
        self.record={
            "schema":"sparkles-faceup-thumbnail-candidate/1",
            "diamond_id":self.manifest["id"],
            "status":"unverified_pose_candidate",
            "source":{"evidence_kind":"rotation","sha256":self.source,
                      "frame_position":0,"source_index":self.frame["source_index"]},
            "derivative":{"sha256":self.hash,"byte_count":len(self.content),
                          "media_type":"image/webp","crop_source_bbox_xyxy":[5,5,190,190]},
            "algorithm":{"pose":"diamond360-asscher-pose/1"},
            "selection":{"selection_method":"outer_usable_face_unresolved"},
        }

    def test_automatic_plan_accepts_unverified_pose_without_reviewer(self):
        asset,metadata=plan_generated_thumbnail(self.manifest,self.record,self.content)
        self.assertEqual(asset.sha256,self.hash)
        self.assertFalse(metadata["generation"]["human_verified"])
        self.assertEqual(metadata["generation"]["pose_status"],"unverified")
        self.assertEqual(metadata["derivation"]["candidate_status"],"unverified_pose_candidate")

    def test_refuses_mismatched_source_or_derivative_bytes(self):
        self.record["source"]["sha256"]="0"*64
        with self.assertRaisesRegex(CatalogueError,"provenance"):
            plan_generated_thumbnail(self.manifest,self.record,self.content)
        self.record["source"]["sha256"]=self.source
        with self.assertRaisesRegex(CatalogueError,"payload"):
            plan_generated_thumbnail(self.manifest,self.record,self.content+b"changed")

    def test_attaches_generated_icon_to_index_preserving_large_original_evidence(self):
        asset,meta=plan_generated_thumbnail(self.manifest,self.record,self.content)
        stored=InMemoryStorage(backend="r2").publish((asset,))[asset.asset_id]
        meta["asset"]={"sha256":stored.sha256,"byte_count":stored.byte_count,
                       "media_type":asset.media_type,
                       "storage":{"backend":stored.backend,"locator":stored.locator,
                                  "url":stored.url}}
        catalogue=GitHubCatalogue(self.api)
        receipt=catalogue.attach_generated_thumbnail(self.manifest["id"],meta)
        self.assertTrue(receipt.changed)
        newest=self.api.manifest(self.manifest["id"])
        self.assertEqual(newest["evidence"],self.manifest["evidence"])
        self.assertEqual(self.api.index()["diamonds"][0]["overview_thumbnail_url"],stored.url)
        self.assertFalse(catalogue.attach_generated_thumbnail(self.manifest["id"],meta).changed)
        publish_result(result(report="LG800667395"),self.api)
        newest_rows={row["id"]:row for row in self.api.index()["diamonds"]}
        self.assertNotIn("overview_thumbnail_url",newest_rows["igi-lg800667395"])

    def test_missing_media_produces_no_publication(self):
        no_motion=dict(self.manifest,evidence=[])
        storage=InMemoryStorage()
        receipt=publish_generated_thumbnail(
            no_motion,fetch_bytes=lambda url:b"",storage=storage,
            catalogue=GitHubCatalogue(self.api))
        self.assertIsNone(receipt)
        self.assertFalse(storage.objects)
