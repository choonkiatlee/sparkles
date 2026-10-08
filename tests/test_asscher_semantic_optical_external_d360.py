"""External Karl D360 falsification: preserve source provenance and abstentions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diamond360 import asscher_semantic_optical_external_d360 as ext
from diamond360 import asscher_geometry_validation as validation

MANIFEST=Path(__file__).resolve().parents[1]/"docs/360/external-benchmark/pricescope/benchmark-manifest.json"

class ExternalD360Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads(MANIFEST.read_text())

    def test_both_holdout_sources_original_256_complete(self):
        self.assertEqual(ext.SAMPLES,("asscher-eval-crispest","asscher-eval-glittery"))
        for sid in ext.SAMPLES:
            with self.subTest(sample=sid):
                seq=ext._sample_from_manifest(self.manifest,sid)
                self.assertEqual(seq["frame_count"],256)
                self.assertEqual(len(seq["manifest_sha256"]),64)
                self.assertIn("d360/",seq["manifest_path"])
                self.assertIn(seq["frame_index_field"],("index","source_index"))

    def test_ordered_geometry_is_not_tuned_to_expert_labels(self):
        self.assertTrue(ext.POLICY["no_quality_scoring"])
        self.assertEqual(ext.POLICY["geometry_method"],validation.OUTER_METHOD)
        self.assertFalse(ext.POLICY["within_stone_per_frame_refit"])
        self.assertEqual(ext.POLICY["source_expert_labels"],
                         "never_loaded_or_used_in_generator")
        self.assertIn(255,ext.SOURCE_INDICES)
        self.assertIn(0,ext.SOURCE_INDICES)
        self.assertTrue(ext.SOURCE_INDICES.index(255)<ext.SOURCE_INDICES.index(0))
        self.assertEqual(len(ext.SOURCE_INDICES),len(set(ext.SOURCE_INDICES)))

    def test_expert_labels_do_not_affect_source_selection(self):
        for sid in ext.SAMPLES:
            modified=copy.deepcopy(self.manifest)
            row=next(x for x in modified["samples"] if x["sample_id"]==sid)
            orig=ext._sample_from_manifest(modified,sid)
            row.pop("observations",None)
            row["expert_observation"]="deliberately misleading target"
            self.assertEqual(orig,ext._sample_from_manifest(modified,sid))

    def test_unsupported_sources_and_missing_media_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"precommitted"):
            ext.run_external("synthetic-best",{},None,None)
        bad=copy.deepcopy(self.manifest)
        row=next(x for x in bad["samples"] if x["sample_id"]==ext.SAMPLES[0])
        row["media"]["sequence"]["frame_count"]=99
        with self.assertRaisesRegex(ValueError,"verified uncalibrated 256"):
            ext._sample_from_manifest(bad,ext.SAMPLES[0])

    def test_unavailable_no_quality_or_physical_facet_claim(self):
        o=ext._status("asscher-eval-crispest","no_stable_pose",
                      {"archive_hash":"test"})
        self.assertEqual(o["status"],"unavailable")
        self.assertIsNone(o["scaffold"])
        self.assertEqual(o["traces"],[])
        self.assertEqual(o["successful_image_support_rows"],0)
        self.assertIsNone(o["physical_angle_comparison"])
        self.assertIsNone(o["quality_score"])

    def test_unresolved_face_cannot_be_called_a_polished_crown(self):
        self.assertEqual(ext._face_role({"face_selection":{"status":"unresolved"}}),
                         "unresolved_not_verified_crown")
        self.assertEqual(ext._face_role({"face_selection":{"status":"resolved"}}),
                         "likely_crown_from_73_not_physical_facet_proof")

    def test_fitter_is_called_only_once_before_transfer(self):
        import inspect
        body=inspect.getsource(ext.run_external)
        self.assertEqual(body.count("stability._primary_fit("),1)
        self.assertIn("stability.transfer_fixed_ruler_frame(",body)
        self.assertIn("handoff.sample_fixed_frame(",body)
        self.assertIn("sensitivity.sample_frame_sensitivity(",body)
        self.assertNotIn("expert_observations",body)
        self.assertNotIn("Karl",body)
        self.assertNotIn("P3 leakage",body)


if __name__=="__main__":
    unittest.main()
