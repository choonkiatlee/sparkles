"""#91 PR C comparison is separate from untouched image-only source fitting."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_profile_external_comparison as external
from diamond360 import asscher_profile_auto_exterior as exterior
from diamond360 import asscher_profile_auto_changepoints as changepoints
from diamond360 import asscher_profile_endpoint_candidates as endpoints
from diamond360 import asscher_profile_pavilion_refinement as pavilion
from diamond360 import asscher_profile_feasibility as source

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
REFERENCE = ROOT / "docs/360/geometry-ground-truth/diagem-2008-asscher/ground-truth.json"


class ProfilePostFreezeComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate target-blind frozen geometry. Do not import/read reference
        # until ALL geometry outputs have passed the frozen byte hash check.
        cls.working = tempfile.TemporaryDirectory()
        out = Path(cls.working.name)
        exterior.write_qc(IMAGE, out, source.ORIGINAL_PROFILE_SHA256)
        changepoints.write_report(IMAGE, out / "auto-exterior.json", out)
        endpoints.write_report(IMAGE, out / "auto-exterior.json",
                               out / "joint-changepoints.json", out)
        pavilion.write_report(IMAGE, out / "auto-exterior.json",
                              out / "joint-changepoints.json",
                              out / "endpoint-candidates.json", out)
        cls.frozen = (out / "pavilion-refinement.json").read_bytes()
        cls.frozen_path = out / "pavilion-refinement.json"

    @classmethod
    def tearDownClass(cls):
        cls.working.cleanup()

    def test_exact_original_ci_artifact_is_reproducible_before_opening_targets(self):
        self.assertEqual(
            hashlib.sha256(self.frozen).hexdigest(),
            external.FROZEN_PROFILE_SHA256,
            "The frozen independent #118 image report must NOT drift.")
        g = external.validate_frozen_profile_bytes(self.frozen)
        self.assertEqual(set(g), {"left","right"})
        self.assertEqual(g["left"]["model_selected_projected_stretches"], 3)
        self.assertEqual(g["right"]["model_selected_projected_stretches"], 3)
        self.assertEqual([v["xy_px"][1] for v in g["left"]["breakpoints"]],[79,131])
        self.assertEqual([v["xy_px"][1] for v in g["right"]["breakpoints"]],[79,117])
        self.assertEqual(g["left"]["physical_facet_correspondence"],"not_established")

    def test_all_eight_expert_photo_estimates_preserved_without_fake_residual(self):
        external.validate_frozen_profile_bytes(self.frozen)
        targets=json.loads(REFERENCE.read_text(encoding="utf-8"))
        o=external.compare(self.frozen, targets)
        self.assertEqual(o["status"],"inconclusive_physical_facet_correspondence")
        self.assertEqual(o["numeric_deltas_available"],0)
        self.assertEqual(o["physical_facet_angles_claimed"],0)
        self.assertTrue(o["independent_angle_reference_opened_only_after_frozen_verification"])
        self.assertEqual(o["semantic_facet_comparison"]["right"]["P1"]["target_photo_estimate_deg"],50)
        self.assertEqual(o["semantic_facet_comparison"]["left"]["C1"]["target_photo_estimate_deg"],46)
        for side in ("left","right"):
            for name,row in o["semantic_facet_comparison"][side].items():
                self.assertEqual(row["reference_uncertainty_deg"],1)
                self.assertEqual(row["reference_evidence_class"],"photo_estimate_not_physical_ground_truth")
                self.assertIsNone(row["sparkles_image_derived_facet_angle_deg"])
                self.assertIsNone(row["residual_deg"])
                self.assertEqual(row["status"],"not_comparable_unverified_physical_facet_correspondence")
        self.assertEqual(o["negative_view_status"],"unverified_rejected_original_source_not_included")

    def test_any_modified_unfrozen_report_fails_closed(self):
        bad=json.loads(self.frozen)
        variants=[
            ("source_orientation","pointed_lower_pavilion"),
            ("comparison_targets_loaded",True),
            ("physical_facet_angles","physical_angles_claimed"),
            ("source_sha256","not-the-original"),
        ]
        for field,value in variants:
            with self.subTest(field=field):
                altered=deepcopy(bad)
                altered[field]=value
                data=(json.dumps(altered,sort_keys=True,indent=2)+"\n").encode()
                with self.assertRaisesRegex(ValueError,"frozen #118"):
                    external.validate_frozen_profile_bytes(data)
        with self.assertRaisesRegex(ValueError,"frozen #118"):
            external.validate_frozen_profile_bytes(self.frozen+b" ")

    def test_unfrozen_profile_rejected_before_expert_reference_file_read(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            corrupted=folder/"wrong-frozen.json"
            corrupted.write_bytes(self.frozen+b" ")
            not_present=folder/"missing-reference.json"
            with self.assertRaisesRegex(ValueError,"frozen #118"):
                external.write_comparison(corrupted,not_present,folder/"out.json")
            self.assertFalse((folder/"out.json").exists())

    def test_wrong_source_or_reference_not_implicitly_substituted(self):
        target=json.loads(REFERENCE.read_text(encoding="utf-8"))
        other=deepcopy(target)
        other["independent_photo_estimate"]["evidence_class"]="manual_reported"
        with self.assertRaisesRegex(ValueError,"photo-estimate provenance"):
            external.compare(self.frozen, other)
        other=deepcopy(target)
        other["independent_photo_estimate"]["right_side_deg"]["P2"]="42"
        with self.assertRaisesRegex(ValueError,"invalid independent"):
            external.compare(self.frozen,other)

    def test_cli_file_output_is_reproducible_without_any_facet_angle(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"comparison.json"
            result=external.write_comparison(self.frozen_path,REFERENCE,out)
            self.assertEqual(result,json.loads(out.read_text()))
            self.assertEqual(result["frozen_source_profile_sha256"],external.FROZEN_PROFILE_SHA256)
            self.assertEqual(result["requested_slots"],8)
            self.assertEqual(result["numeric_deltas_available"],0)


if __name__=="__main__":
    unittest.main()
