"""Upper pointed pavilion must never be confused with lower crown."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from diamond360 import asscher_profile_auto_exterior as exterior
from diamond360 import asscher_profile_auto_changepoints as joint
from diamond360 import asscher_profile_endpoint_candidates as endpoint
from diamond360 import asscher_profile_conditional_symmetry as symmetry
from diamond360 import asscher_profile_pavilion_refinement as pavilion
from diamond360 import asscher_profile_feasibility as feasibility

PHOTO = (Path(__file__).resolve().parents[1] /
         "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG")


def shape(slopes, left=True):
    out = []
    y, x = 64, (203 if left else 207)
    sign = -1 if left else 1
    for slope in slopes:
        for _ in range(20):
            out.append({
                "xy_px": [round(x, 3), y],
                "weight": 1.0,
                "provenance": "synthetic_supported_pavilion_envelope",
            })
            x += sign * slope * 2
            y += 2
    return out


class PavilionOrientationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rgb = np.asarray(Image.open(PHOTO).convert("RGB"))
        cls.contour = exterior.analyse_array(cls.rgb)
        cls.contour["source_sha256"] = feasibility.ORIGINAL_PROFILE_SHA256
        cls.joint = joint.analyse(cls.contour)
        cls.ends = endpoint.analyse(cls.rgb, cls.contour, cls.joint)

    def pose(self):
        review = symmetry.pose_template()
        review.update({
            "status": "reviewed_head_on", "head_on_pose_confirmed": True,
            "stone_mirror_symmetry_assumed": True,
            "review_basis": (
                "Independent profile camera-pose evidence reviewed without expert angle "
                "targets; approximately bilateral pavilion geometry explicitly assumed."
            ),
            "reviewed_by": "synthetic_pose_review",
        })
        return review

    def test_source_orientation_is_upper_pavilion_lower_crown(self):
        self.assertEqual(self.contour["policy"]["source_orientation"],
                         "pointed_upper_pavilion_broad_lower_crown")
        upper = self.contour["paths"]["left_pavilion"]["points"]
        lower = self.contour["paths"]["left_crown"]["points"]
        self.assertLess(max(p["xy_px"][1] for p in upper if p["xy_px"]),
                        max(p["xy_px"][1] for p in lower if p["xy_px"]))
        self.assertEqual(self.joint["source_orientation"],
                         "pointed_upper_pavilion_broad_lower_crown")
        self.assertEqual(
            self.ends["top_pavilion_tip_candidate"]["status"], "candidate_only"
        )
        self.assertIn("culet_region",
                      self.ends["top_pavilion_tip_candidate"]["kind"])
        self.assertEqual(set(self.ends["last_crown_changepoint_candidates"]),
                         {"left","right"})

    def test_real_pavilion_has_only_upper_source_pixels(self):
        r = pavilion.analyse(self.contour, self.joint, self.ends)
        band = r["widest_width_band_candidate"]
        self.assertEqual(r["source_orientation"],pavilion.POLICY["source_orientation"])
        self.assertEqual(r["physical_facet_angles"],"all_unavailable")
        self.assertLess(band["y_first_px"],band["y_last_px"])
        self.assertIn(r["independent_pavilion"]["left"]["status"],{"review","unavailable"})
        self.assertIn(r["independent_pavilion"]["right"]["status"],{"review","unavailable"})
        for side in ("left","right"):
            pts=r["observed_supported_points"][side]
            self.assertGreater(len(pts),40)
            self.assertTrue(all(item["xy_px"][1] < band["y_first_px"] for item in pts))
            self.assertTrue(all(item["provenance"]==
                "automated_background_first_exterior_source" for item in pts))
        # Regression: previously mistaken crown bend at y=273 must never
        # reappear in any named physical pavilion breakpoint.
        self.assertTrue(all(
            mark["xy_px"][1] < band["y_first_px"]
            for fit in r["independent_pavilion"].values()
            for mark in fit.get("breakpoints",[])
        ))

    def test_one_two_three_apparent_upper_pavilion_slopes_are_optional(self):
        for slopes in ([0.3],[0.2,1.1],[0.2,1.3,0.25]):
            with self.subTest(slopes=slopes):
                fitted = pavilion._select(shape(slopes))
                self.assertEqual(fitted["status"],"review")
                self.assertEqual(fitted["selected_segment_count"],len(slopes))
                self.assertEqual(len(fitted["breakpoints"]),len(slopes)-1)

    def test_pose_unreviewed_never_adopts_mirror(self):
        r = pavilion.analyse(self.contour,self.joint,self.ends)
        self.assertEqual(r["pose_review"]["status"],"not_confirmed")
        self.assertEqual(r["conditional_pavilion_model"]["status"],
                         "not_adopted_pose_unconfirmed_or_inconsistent")
        self.assertGreater(len(r["conditional_pavilion_model"]
                              ["mirrored_right_pavilion_preview"]),40)
        self.assertTrue(all(
            row["provenance"]=="MODEL_ONLY_mirrored_left_pavilion_not_observed_right"
            for row in r["conditional_pavilion_model"]["mirrored_right_pavilion_preview"]
        ))
        self.assertIsNone(r["conditional_pavilion_model"]["common_model"])

    def test_symmetry_requires_independent_head_on_review_and_assumption(self):
        a = pavilion.analyse(self.contour,self.joint,self.ends)
        b = pavilion.analyse(self.contour,self.joint,self.ends,self.pose())
        self.assertEqual(a["independent_pavilion"],b["independent_pavilion"])
        self.assertEqual(a["observed_supported_points"],b["observed_supported_points"])
        if b["symmetry_diagnostic"]["status"]=="image_only_compatible_not_pose_proof":
            self.assertEqual(b["conditional_pavilion_model"]["status"],
                             "conditional_symmetry_model_inferred")
            self.assertFalse(b["conditional_pavilion_model"]["common_model"]
                             ["right_side_observations_replaced"])
        else:
            self.assertNotEqual(b["conditional_pavilion_model"]["status"],
                                "conditional_symmetry_model_inferred")
        no_sym=self.pose()
        no_sym["stone_mirror_symmetry_assumed"]=False
        c=pavilion.analyse(self.contour,self.joint,self.ends,no_sym)
        self.assertNotEqual(c["conditional_pavilion_model"]["status"],
                            "conditional_symmetry_model_inferred")

    def test_asymmetry_and_wrong_orientation_do_not_force_fits(self):
        altered=deepcopy(self.contour)
        for row in altered["paths"]["right_pavilion"]["points"]:
            if row["xy_px"] and row["support"]=="edge_supported_candidate":
                row["xy_px"][0]+=39
        r=pavilion.analyse(altered,self.joint,self.ends,self.pose())
        self.assertEqual(r["symmetry_diagnostic"]["status"],"image_only_inconsistent")
        self.assertNotEqual(r["conditional_pavilion_model"]["status"],
                            "conditional_symmetry_model_inferred")
        invalid=deepcopy(self.contour)
        invalid["policy"]["source_orientation"]="pointed_lower_pavilion"
        with self.assertRaisesRegex(ValueError,"orientation"):
            pavilion.analyse(invalid,self.joint,self.ends)

    def test_target_leak_and_missing_girdle_fail_closed(self):
        invalid=deepcopy(self.contour)
        invalid["comparison_targets_loaded"]=True
        with self.assertRaisesRegex(ValueError,"expert angle"):
            pavilion.analyse(invalid,self.joint,self.ends)
        bad=deepcopy(self.joint)
        bad["widest_band_candidate"]={"status":"unavailable"}
        result=pavilion.analyse(self.contour,bad,self.ends)
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["physical_facet_angles"],"all_unavailable")

    def test_original_photo_artifact_and_source_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            exterior.write_qc(PHOTO,root,feasibility.ORIGINAL_PROFILE_SHA256)
            joint.write_report(PHOTO,root/"auto-exterior.json",root)
            endpoint.write_report(PHOTO,root/"auto-exterior.json",
                                  root/"joint-changepoints.json",root)
            result=pavilion.write_report(PHOTO,root/"auto-exterior.json",
                root/"joint-changepoints.json",root/"endpoint-candidates.json",root)
            self.assertEqual(result,json.loads((root/"pavilion-refinement.json").read_text()))
            self.assertTrue((root/"pavilion-observed-vs-symmetry.png").is_file())
            self.assertTrue(all(
                p["xy_px"][1]<result["widest_width_band_candidate"]["y_first_px"]
                for side in result["observed_supported_points"].values() for p in side
            ))


if __name__=="__main__":
    unittest.main()
