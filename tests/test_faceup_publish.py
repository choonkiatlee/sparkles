"""Approval is explicit and atomically published without source mutations."""
import hashlib
import unittest

from diamond_catalogue import InMemoryStorage
from diamond_catalogue.faceup_publish import plan_reviewed_thumbnail
from diamond_catalogue.github_catalogue import GitHubCatalogue
from diamond_catalogue.github_catalogue import publish_result
from diamond_catalogue.models import CatalogueError
from tests.test_diamond_catalogue import result
from tests.test_diamond_catalogue_publisher import FakeGitHub


class FaceUpPublishingTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeGitHub()
        publish_result(result(),self.api)
        self.doc=self.api.manifest("igi-lg800667394")
        self.frame=self.doc["evidence"][2]["frames"][0]
        self.payload=b"RIFFfake-validity-is-checked-by-thumbnail-generator"
        self.digest=hashlib.sha256(self.payload).hexdigest()
        self.source=self.frame["asset"]["sha256"]
        self.record={
            "schema":"sparkles-faceup-thumbnail-candidate/1",
            "diamond_id":self.doc["id"],
            "status":"unverified_pose_candidate",
            "review_status":"unverified",
            "source":{"evidence_kind":"rotation","sha256":self.source,
                      "frame_position":0,"source_index":self.frame["source_index"],
                      "stored_position":self.frame.get("stored_position")},
            "derivative":{"sha256":self.digest,"byte_count":len(self.payload),
                          "media_type":"image/webp","crop_source_bbox_xyxy":[5,5,190,190]},
            "algorithm":{"pose":"diamond360-asscher-pose/1"},
            "selection":{"status":"unverified_pose_candidate"},
        }

    def plan(self, **kwargs):
        return plan_reviewed_thumbnail(
            self.doc,self.record,self.payload,
            approved_image_sha=kwargs.get("image",self.digest),
            approved_source_sha=kwargs.get("source",self.source),
            reviewer=kwargs.get("reviewer","test-reviewer"),
        )

    def test_reject_wrong_media_source_or_missing_explicit_reviewer(self):
        with self.assertRaisesRegex(CatalogueError,"hash"):
            self.plan(image="0"*64)
        with self.assertRaisesRegex(CatalogueError,"hash"):
            self.plan(source="0"*64)
        with self.assertRaisesRegex(CatalogueError,"hash"):
            self.plan(reviewer="")
        self.record["source"]["evidence_kind"]="still"
        with self.assertRaises(CatalogueError):
            self.plan()
        self.record["source"]["evidence_kind"]="rotation"
        self.record["status"]="unverified_still_crop"
        with self.assertRaises(CatalogueError):
            self.plan()

    def test_release_style_storage_and_atomic_index_preserve_original_media(self):
        asset,metadata=self.plan()
        storage=InMemoryStorage(backend="r2")
        uploaded=storage.publish((asset,))[asset.asset_id]
        metadata["asset"]={
            "sha256":uploaded.sha256,"byte_count":uploaded.byte_count,
            "media_type":"image/webp",
            "storage":{"backend":uploaded.backend,"locator":uploaded.locator,"url":uploaded.url},
        }
        publisher=GitHubCatalogue(self.api)
        before=self.api.manifest(self.doc["id"])
        result=publisher.attach_verified_thumbnail(self.doc["id"],metadata)
        self.assertTrue(result.changed)
        after=self.api.manifest(self.doc["id"])
        self.assertEqual(after["evidence"],before["evidence"])
        self.assertEqual(after["derived_media"]["face_up_thumbnail"],metadata)
        self.assertEqual(self.api.index()["diamonds"][0]["face_up_thumbnail_url"],
                         metadata["asset"]["storage"]["url"])
        second=publisher.attach_verified_thumbnail(self.doc["id"],metadata)
        self.assertFalse(second.changed)
        revised=dict(metadata)
        revised["review"]=dict(revised["review"], reviewer="other")
        with self.assertRaisesRegex(CatalogueError,"replace already reviewed"):
            publisher.attach_verified_thumbnail(self.doc["id"],revised)

    def test_new_catalogue_diamonds_continue_to_build_index_after_thumbnail(self):
        asset,metadata=self.plan()
        storage=InMemoryStorage()
        uploaded=storage.publish((asset,))[asset.asset_id]
        metadata["asset"]={"sha256":uploaded.sha256,"byte_count":uploaded.byte_count,
            "media_type":"image/webp","storage":{"backend":uploaded.backend,
                "locator":uploaded.locator,"url":uploaded.url}}
        GitHubCatalogue(self.api).attach_verified_thumbnail(self.doc["id"],metadata)
        publish_result(result(report="LG800667395"),self.api)
        rows={x["id"]:x for x in self.api.index()["diamonds"]}
        self.assertIn("face_up_thumbnail_url",rows[self.doc["id"]])
        self.assertNotIn("face_up_thumbnail_url",rows["igi-lg800667395"])
