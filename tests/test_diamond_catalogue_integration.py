"""#104 compatibility: actual retrieval pipeline -> stable publication plan.

Uses the archive-backed full 256-frame retailer fixtures, never live HTTP.
"""
import hashlib
import unittest

from diamond_catalogue import (
    InMemoryStorage, build_index, finalize_manifest, merge_manifest, plan_publication,
)
from diamond_retrieval import default_config, retrieve_diamond
from diamond_retrieval.models import CERTIFICATE, EvidenceStatus, ResultStatus
from tests.test_diamond_retrieval_retailers import (
    DIYONA_URL, QD_URL, RetailerEndToEndTests,
)


class CatalogueMotionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = RetailerEndToEndTests()

    def _check_real_rotation(self, url, client):
        result = retrieve_diamond(url, config=default_config(client))
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(len(result.rotations), 1)
        frames = result.rotations[0].frames
        self.assertEqual(len(frames), 256)
        self.assertEqual([frame.source_index for frame in frames], list(range(256)))
        plan = plan_publication(result)
        # The progressive 256-frame reconstruction is synthetic JSON, not an original source
        # media asset. Publish original JPEG frames, PDF and optional still instead.
        assets = {asset.asset_id: asset for asset in plan.assets}
        self.assertEqual(plan.diamond_id.split("-")[0], "igi")
        self.assertGreaterEqual(len(plan.assets), 257)
        self.assertTrue(all(asset.desired_name.startswith("asset-") for asset in plan.assets))
        backend = InMemoryStorage()
        manifest = finalize_manifest(plan, backend.publish(plan.assets))
        self.assertEqual(manifest["id"], plan.diamond_id)
        self.assertEqual(manifest["schema"], "sparkles-diamond-catalogue/1")
        rotation = next(item for item in manifest["evidence"] if item["kind"] == "rotation")
        self.assertEqual(len(rotation["frames"]), 256)
        self.assertIsNone(rotation["payload_asset"])
        self.assertFalse(rotation["metadata"]["physical_angle_calibrated"])
        self.assertTrue(rotation["metadata"]["sequence_complete"])
        self.assertEqual(rotation["metadata"]["frame_count"], 256)
        for original, published in zip(frames, rotation["frames"]):
            self.assertEqual(original.source_index, published["source_index"])
            self.assertEqual(original.stored_position, published["stored_position"])
            self.assertEqual(original.source_batch, published["source_batch"])
            self.assertEqual(list(original.dimensions), published["dimensions"])
            ref = published["asset"]
            self.assertEqual(original.sha256, ref["sha256"])
            self.assertEqual(len(original.payload), ref["byte_count"])
            self.assertEqual(assets[ref["sha256"]].payload, original.payload)
            self.assertEqual(hashlib.sha256(original.payload).hexdigest(), ref["sha256"])
        index = build_index([merge_manifest(None, manifest)])
        self.assertTrue(index["diamonds"][0]["has_motion"])
        self.assertIsNotNone(index["diamonds"][0]["thumbnail_url"])
        return result, manifest

    def test_quality_diamonds_256_core360_frames_to_catalogue(self):
        self._check_real_rotation(QD_URL, self.fixtures.qd_http())

    def test_diyona_256_diajewel_frames_to_catalogue(self):
        self._check_real_rotation(DIYONA_URL, self.fixtures.diyona_http())

    def test_igi_403_preserves_certificate_link_without_fabricating_pdf(self):
        http = self.fixtures.qd_http(pdf_status=403)
        result = retrieve_diamond(QD_URL, config=default_config(http))
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertFalse(result.certificates)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertTrue(result.certificate_link)
        self.assertTrue(any(a.kind == CERTIFICATE and a.status == EvidenceStatus.DOWNLOAD_FAILED
                            for a in result.attempts))
        plan = plan_publication(result)
        manifest = finalize_manifest(plan, InMemoryStorage().publish(plan.assets))
        latest = manifest["retrievals"][0]
        self.assertEqual(latest["status"], "partial")
        self.assertEqual(latest["certificate_link"], result.certificate_link)
        self.assertFalse(any(e["kind"] == "certificate" for e in manifest["evidence"]))
        self.assertTrue(any(a["locator"] for a in latest["attempts"] if a["kind"] == "certificate"))
        self.assertTrue(any("failed" in str(a["status"]) for a in latest["attempts"]
                            if a["kind"] == "certificate"))
        self.assertTrue(build_index([manifest])["diamonds"][0]["has_motion"])


if __name__ == "__main__":
    unittest.main()
