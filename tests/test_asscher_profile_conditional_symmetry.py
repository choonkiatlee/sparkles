"""Head-on conditional symmetry never masquerades as observed lower facets."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import numpy as np

from diamond360 import asscher_profile_auto_exterior as auto
from diamond360 import asscher_profile_auto_changepoints as joint
from diamond360 import asscher_profile_endpoint_candidates as endpoint
from diamond360 import asscher_profile_conditional_symmetry as symmetric
from diamond360 import asscher_profile_feasibility as feasibility

SOURCE = (Path(__file__).resolve().parents[1] /
          "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG")


class ConditionalSymmetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arr = np.asarray(Image.open(SOURCE).convert("RGB"))
        cls.contour = auto.analyse_array(cls.arr)
        cls.contour["source_sha256"] = feasibility.ORIGINAL_PROFILE_SHA256
        cls.joint = joint.analyse(cls.contour)
        cls.ends = endpoint.analyse(cls.arr, cls.contour, cls.joint)

    def pose(self):
        p = symmetric.pose_template()
        p.update({
            "status": "reviewed_head_on",
            "head_on_pose_confirmed": True,
            "stone_mirror_symmetry_assumed": True,
            "review_basis": "Independently reviewed source profile view and declared a modeled mirror symmetry assumption, not a measurement.",
            "reviewed_by": "test_human_review_provenance",
        })
        return p

    def test_unreviewed_is_only_counterfactual_not_measured(self):
        r = symmetric.analyse(self.contour, self.joint, self.ends)
        self.assertEqual(r["status"], "preview_only_not_adopted")
        self.assertEqual(r["top_shape_interpretation"],
                         "point_like_projected_apex_not_physical_culet_or_confirmed_table")
        self.assertEqual(r["pose_review"]["status"], "not_confirmed")
        self.assertEqual(r["physical_facet_angles"], "all_unavailable")
        mirror = r["right_terminal_symmetry_hypothesis"]
        self.assertEqual(mirror["status"], "counterfactual_mirror_preview_not_applied")
        self.assertEqual(mirror["provenance"],
                         "MODEL_INFERRED_from_left_NOT_observed_right")
        self.assertIsNone(mirror["physical_angle_deg"])
        self.assertIsNone(mirror["semantic_facet_id"])
        self.assertEqual(mirror["right_independent_observation"], "unavailable")

    def test_explicit_head_on_and_stone_symmetry_can_activate_only_conditional_inference(self):
        review = self.pose()
        r = symmetric.analyse(self.contour, self.joint, self.ends, review)
        diagnostic = r["image_only_symmetry_diagnostic"]
        self.assertGreaterEqual(diagnostic["paired_crown_rows"], 30)
        expected = (
            "conditional_symmetry_model_inferred"
            if diagnostic["status"] == "image_only_compatible_not_pose_proof"
            else "counterfactual_mirror_preview_not_applied"
        )
        self.assertEqual(r["right_terminal_symmetry_hypothesis"]["status"], expected)
        self.assertEqual(r["independent_terminal_candidates"]["right"],
                         self.ends["last_pavilion_changepoint_candidates"]["right"])
        self.assertEqual(r["physical_facet_angles"], "all_unavailable")
        if expected == "conditional_symmetry_model_inferred":
            axis = diagnostic["axis_x_px"]
            left = self.ends["last_pavilion_changepoint_candidates"]["left"]["xy_px"]
            right = r["right_terminal_symmetry_hypothesis"]["xy_px"]
            self.assertAlmostEqual(right[0], 2*axis-left[0], places=2)
            self.assertAlmostEqual(right[1], left[1])

    def test_head_on_not_enough_without_symmetry_assumption(self):
        review = self.pose()
        review["stone_mirror_symmetry_assumed"] = False
        result = symmetric.analyse(self.contour, self.joint, self.ends, review)
        self.assertEqual(result["pose_review"]["status"], "not_confirmed")
        self.assertEqual(result["status"], "preview_only_not_adopted")

    def test_mirrored_right_must_not_overwrite_independent_observation(self):
        ends = deepcopy(self.ends)
        ends["last_pavilion_changepoint_candidates"]["right"] = {
            "status": "candidate_only",
            "xy_px": [314.0, 271],
            "reason": "hypothetical independent observed right external change",
        }
        result = symmetric.analyse(self.contour, self.joint, ends, self.pose())
        self.assertEqual(result["right_terminal_symmetry_hypothesis"]["status"],
                         "counterfactual_mirror_preview_not_applied")
        self.assertIn("already_has_independent", result["right_terminal_symmetry_hypothesis"]["reason"])
        self.assertEqual(result["independent_terminal_candidates"]["right"]["xy_px"],
                         [314.0, 271])

    def test_inconsistent_mirror_outline_blocks_acceptance_even_with_pose_flag(self):
        contour = deepcopy(self.contour)
        for row in contour["paths"]["right_crown"]["points"]:
            if row["support"] == "edge_supported_candidate" and row["xy_px"]:
                row["xy_px"][0] += 40
        result = symmetric.analyse(contour, self.joint, self.ends, self.pose())
        self.assertEqual(result["image_only_symmetry_diagnostic"]["status"],
                         "image_only_inconsistent")
        self.assertEqual(result["status"], "preview_only_not_adopted")
        self.assertIn("gate_not_met", result["right_terminal_symmetry_hypothesis"]["reason"])

    def test_missing_left_candidate_does_not_force_any_break(self):
        ends = deepcopy(self.ends)
        ends["last_pavilion_changepoint_candidates"]["left"] = {"status": "unavailable"}
        result = symmetric.analyse(self.contour, self.joint, ends, self.pose())
        self.assertEqual(result["right_terminal_symmetry_hypothesis"]["status"],
                         "unavailable")

    def test_reject_expert_target_and_forged_pose(self):
        pose = self.pose()
        pose["target_angles_used"] = True
        with self.assertRaisesRegex(ValueError, "target"):
            symmetric.analyse(self.contour, self.joint, self.ends, pose)
        pose = self.pose()
        pose["review_basis"] = "yes"
        with self.assertRaisesRegex(ValueError, "independent"):
            symmetric.analyse(self.contour, self.joint, self.ends, pose)
        pose = self.pose()
        pose["unknown_angle_target_field"] = 40
        with self.assertRaisesRegex(ValueError, "exact schema"):
            symmetric.analyse(self.contour, self.joint, self.ends, pose)
        contour = deepcopy(self.contour)
        contour["policy_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "method"):
            symmetric.analyse(contour, self.joint, self.ends)

    def test_source_locked_artifact_with_explicit_unreviewed_template(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            auto.write_qc(SOURCE, root, feasibility.ORIGINAL_PROFILE_SHA256)
            joint.write_report(SOURCE, root / "auto-exterior.json", root)
            endpoint.write_report(SOURCE, root / "auto-exterior.json",
                                  root / "joint-changepoints.json", root)
            report = symmetric.write_report(
                SOURCE, root / "auto-exterior.json",
                root / "joint-changepoints.json",
                root / "endpoint-candidates.json", root,
            )
            self.assertEqual(report["status"], "preview_only_not_adopted")
            self.assertTrue((root / "conditional-symmetry-preview.png").is_file())
            self.assertEqual(json.loads((root / "conditional-symmetry.json").read_text()), report)
            self.assertEqual(json.loads((root / "pose-review-template.json").read_text()),
                             symmetric.pose_template())


if __name__ == "__main__":
    unittest.main()
