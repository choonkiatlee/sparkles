"""Pavilion-only outer-boundary modeling; symmetry can never become a fake observation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from diamond360 import asscher_profile_auto_exterior as exterior
from diamond360 import asscher_profile_auto_changepoints as joint
from diamond360 import asscher_profile_endpoint_candidates as terminal
from diamond360 import asscher_profile_pavilion_fit as pavilion
from diamond360 import asscher_profile_conditional_symmetry as symmetry
from diamond360 import asscher_profile_feasibility as feasibility

SOURCE=(Path(__file__).resolve().parents[1] /
        "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG")


class PavilionFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arr=np.asarray(Image.open(SOURCE).convert("RGB"))
        cls.contour=exterior.analyse_array(arr)
        cls.contour["source_sha256"]=feasibility.ORIGINAL_PROFILE_SHA256
        cls.joint=joint.analyse(cls.contour)
        cls.terminal=terminal.analyse(arr,cls.contour,cls.joint)

    def head_on(self):
        return {
            "schema_version":symmetry.POSE_SCHEMA,
            "source_sha256":feasibility.ORIGINAL_PROFILE_SHA256,
            "status":"reviewed_head_on",
            "head_on_pose_confirmed":True,
            "stone_mirror_symmetry_assumed":True,
            "review_basis":"Reviewed original photograph separately from numeric targets and assumed approximately mirror-symmetric stone for model sensitivity.",
            "reviewed_by":"synthetic-test-reviewer",
            "target_angles_used":False,
        }

    def test_independent_left_right_are_not_replaced_by_shared_fit(self):
        result=pavilion.analyse(self.contour,self.joint,self.terminal)
        self.assertEqual(result["status"],"review")
        for side in ("left","right"):
            model=result["independent_pavilion_models"][side]
            self.assertEqual(model["status"],"review")
            self.assertIn(model["selected_segment_count"],(1,2,3))
            self.assertTrue(model["source_observed_points"])
            self.assertEqual(model["physical_facet_correspondence"],"not_established")
            self.assertIsNone(model["orthogonal_physical_angle_deg"])
            self.assertTrue(all(p["physical_facet_id"] is None
                                for p in model["source_observed_points"]))
        self.assertLess(
            result["shadow_unresolved_region"]["last_supported_right_y_px"],
            result["shadow_unresolved_region"]["last_supported_left_y_px"]
        )
        self.assertIsNone(result["shadow_unresolved_region"]["tip_or_culet_xy_px"])
        self.assertEqual(result["physical_facet_angles"],"all_unavailable")

    def test_default_mirror_is_only_counterfactual_and_shows_missing_right(self):
        result=pavilion.analyse(self.contour,self.joint,self.terminal)
        shared=result["shared_symmetry_model"]
        self.assertEqual(shared["status"],"counterfactual_not_adopted")
        self.assertEqual(shared["fit"]["status"],"counterfactual_model_preview")
        self.assertGreater(len(shared["inferred_right_points_only_where_no_right_source_support"]),2)
        self.assertTrue(all(p["provenance"]=="MODEL_ONLY_NOT_PIXEL_OBSERVED"
                            for p in shared["inferred_right_points_only_where_no_right_source_support"]))
        self.assertEqual(result["pose_assessment"]["status"],"not_confirmed")
        self.assertEqual(result["comparison_targets_loaded"],False)
        self.assertGreaterEqual(result["pavilion_paired_alignment"]["paired_rows"],25)

    def test_pose_and_stone_assumption_are_both_needed_to_adopt(self):
        review=self.head_on()
        with_pose=pavilion.analyse(self.contour,self.joint,self.terminal,review)
        without_pose=pavilion.analyse(self.contour,self.joint,self.terminal)
        if (with_pose["pavilion_paired_alignment"]["status"]=="compatible_2d_only"
            and with_pose["image_only_crown_alignment"]["status"]=="image_only_compatible_not_pose_proof"):
            self.assertEqual(with_pose["shared_symmetry_model"]["status"],
                             "conditional_symmetry_model_inferred")
        else:
            self.assertEqual(with_pose["shared_symmetry_model"]["status"],
                             "counterfactual_not_adopted")
        self.assertEqual(
            with_pose["independent_pavilion_models"],
            without_pose["independent_pavilion_models"])
        self.assertEqual(
            with_pose["observed_terminal_changepoints"],
            without_pose["observed_terminal_changepoints"])
        self.assertEqual(with_pose["physical_facet_angles"],"all_unavailable")
        review["stone_mirror_symmetry_assumed"]=False
        without_stone=pavilion.analyse(self.contour,self.joint,self.terminal,review)
        self.assertEqual(without_stone["shared_symmetry_model"]["status"],
                         "counterfactual_not_adopted")

    def test_asymmetric_right_contour_rejects_symmetry_but_retains_observed_data(self):
        contour=deepcopy(self.contour)
        for path in (contour["paths"]["right_pavilion"],):
            for p in path["points"]:
                if p["support"]=="edge_supported_candidate" and p["xy_px"]:
                    p["xy_px"][0] += 27
        result=pavilion.analyse(contour,self.joint,self.terminal,self.head_on())
        self.assertEqual(result["pavilion_paired_alignment"]["status"],"inconsistent_2d")
        self.assertEqual(result["shared_symmetry_model"]["status"],
                         "counterfactual_not_adopted")
        self.assertTrue(result["independent_pavilion_models"]["right"]["source_observed_points"])

    def test_independent_right_terminal_is_never_overwritten(self):
        ends=deepcopy(self.terminal)
        ends["last_pavilion_changepoint_candidates"]["right"]={
            "status":"candidate_only","xy_px":[310,273],
            "reason":"independently_source_observed_hypothetical_right_candidate"}
        result=pavilion.analyse(self.contour,self.joint,ends,self.head_on())
        self.assertEqual(result["shared_symmetry_model"]["status"],
                         "counterfactual_not_adopted")
        self.assertIn("independent_right",result["shared_symmetry_model"]["reason"])
        self.assertEqual(result["observed_terminal_changepoints"]["right"]["xy_px"],
                         [310,273])

    def test_unrelated_internal_brightness_data_cannot_change_pavilion_fit(self):
        source=pavilion.analyse(self.contour,self.joint,self.terminal)
        altered=deepcopy(self.contour)
        altered["optical_virtual_facets"]={"strong_internal_stripes":True}
        other=pavilion.analyse(altered,self.joint,self.terminal)
        self.assertEqual(source,other)

    def test_missing_supported_right_rows_remain_inferred_not_observed(self):
        result=pavilion.analyse(self.contour,self.joint,self.terminal)
        right_ys={p["xy_px"][1] for p in
                  result["independent_pavilion_models"]["right"]["source_observed_points"]}
        inferred=result["shared_symmetry_model"]["inferred_right_points_only_where_no_right_source_support"]
        self.assertTrue(inferred)
        self.assertTrue(all(p["xy_px"][1] not in right_ys for p in inferred))
        self.assertLessEqual(max(p["xy_px"][1] for p in inferred),
                             result["shadow_unresolved_region"]["last_supported_left_y_px"])

    def test_rejects_stale_method_source_hash_and_target_inputs(self):
        cases=[
            ("contour",lambda c,j,t:c.update(policy_sha256="changed"),"v2"),
            ("joint",lambda c,j,t:j.update(source_sha256="other"),"source"),
            ("terminal",lambda c,j,t:t.update(comparison_targets_loaded=True),"target"),
        ]
        for name,mutate,reason in cases:
            with self.subTest(name=name):
                c,j,t=(deepcopy(self.contour),deepcopy(self.joint),deepcopy(self.terminal))
                mutate(c,j,t)
                with self.assertRaisesRegex(ValueError,reason):
                    pavilion.analyse(c,j,t)

    def test_reproducible_pavilion_only_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            exterior.write_qc(SOURCE,root,feasibility.ORIGINAL_PROFILE_SHA256)
            joint.write_report(SOURCE,root/"auto-exterior.json",root)
            terminal.write_report(SOURCE,root/"auto-exterior.json",
                                  root/"joint-changepoints.json",root)
            record=pavilion.write_report(SOURCE,root/"auto-exterior.json",
                                         root/"joint-changepoints.json",
                                         root/"endpoint-candidates.json",root)
            self.assertEqual(record,pavilion.analyse(self.contour,self.joint,self.terminal))
            self.assertTrue((root/"pavilion-only-overlay.png").is_file())
            self.assertEqual(json.loads((root/"pavilion-fit.json").read_text()),record)


if __name__=="__main__":
    unittest.main()
