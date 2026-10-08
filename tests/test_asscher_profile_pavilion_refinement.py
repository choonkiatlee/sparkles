"""Pavilion prioritized fit: independent source evidence vs conditional symmetry."""
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


def synthetic_shape(slopes, side, y0=225, interval=3, count=18):
    x = 46.0 if side == "left" else 364.0
    sign = 1 if side == "left" else -1
    points = []
    y = y0
    for rate in slopes:
        for idx in range(count):
            points.append({
                "xy_px": [round(x, 3), y],
                "weight": 1.0,
                "provenance": "synthetic_true_exterior",
            })
            y += interval
            x += sign * rate * interval
    return points


class PavilionRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rgb = np.asarray(Image.open(PHOTO).convert("RGB"))
        cls.contour = exterior.analyse_array(cls.rgb)
        cls.contour["source_sha256"] = feasibility.ORIGINAL_PROFILE_SHA256
        cls.joint = joint.analyse(cls.contour)
        cls.terminal = endpoint.analyse(cls.rgb, cls.contour, cls.joint)

    def _review(self):
        r = symmetry.pose_template()
        r.update({
            "status": "reviewed_head_on",
            "head_on_pose_confirmed": True,
            "stone_mirror_symmetry_assumed": True,
            "review_basis": (
                "Independent pose evidence reviewed, plus a separately declared "
                "modeling assumption of approximately mirror-symmetric pavilion geometry."
            ),
            "reviewed_by": "test_review",
        })
        return r

    def test_synthetic_one_two_three_visible_stretches_no_forced_three_tiers(self):
        for slopes in ([1.0], [0.7, 2.1], [0.7, 2.3, 0.8]):
            with self.subTest(slopes=slopes):
                pts = synthetic_shape(slopes, "left", count=17)
                result = pavilion._select(pts)
                self.assertEqual(result["status"], "review")
                self.assertEqual(result["selected_segment_count"], len(slopes))
                self.assertEqual(len(result["breakpoints"]), len(slopes)-1)
                self.assertEqual(result["physical_facet_identity"], "not_established")

    def test_shadow_extension_weighed_less_and_gaps_retained(self):
        result = pavilion.analyse(self.contour, self.joint, self.terminal)
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["physical_facet_angles"], "all_unavailable")
        self.assertEqual(result["conditional_pavilion_model"]["status"],
                         "not_adopted_pose_unconfirmed")
        for side in ("left", "right"):
            pts = result["observed_supported_points"][side]
            self.assertTrue(any(row["provenance"]=="automatic_shadow_limited_endpoint_extension"
                                for row in pts))
            self.assertTrue(any(row["provenance"]=="automated_background_first_exterior_source"
                                for row in pts))
            self.assertEqual([r["xy_px"][1] for r in pts],
                             sorted(set(r["xy_px"][1] for r in pts)))
            self.assertTrue(all(
                r["weight"]==pavilion.POLICY["main_source_weight"]
                if r["provenance"]=="automated_background_first_exterior_source"
                else r["weight"]==pavilion.POLICY["independently_source_supported_endpoint_weight"]
                for r in pts
            ))

    def test_left_vs_right_independent_and_mirror_remains_preview_without_pose(self):
        record = pavilion.analyse(self.contour, self.joint, self.terminal)
        self.assertEqual(record["pose_review"]["status"], "not_confirmed")
        proposed = record["conditional_pavilion_model"]["right_terminal_candidate"]
        self.assertIsNotNone(proposed)
        self.assertEqual(proposed["status"], "counterfactual_mirror_preview_not_applied")
        self.assertEqual(proposed["provenance"], "MODEL_INFERRED_from_left_NOT_observed_right")
        self.assertEqual(record["independent_pavilion"]["left"]["status"], "review")
        self.assertEqual(record["independent_pavilion"]["right"]["status"], "review")
        self.assertEqual(record["conditional_pavilion_model"]["common_model"], None)

    def test_pose_review_and_model_symmetry_are_both_required(self):
        nope = self._review()
        nope["stone_mirror_symmetry_assumed"] = False
        a = pavilion.analyse(self.contour, self.joint, self.terminal, nope)
        self.assertEqual(a["conditional_pavilion_model"]["status"],
                         "not_adopted_pose_unconfirmed")
        b = pavilion.analyse(self.contour, self.joint, self.terminal, self._review())
        consistent = b["symmetry_diagnostic"]["status"] == "image_only_compatible_not_pose_proof"
        self.assertEqual(
            b["conditional_pavilion_model"]["status"],
            "conditional_symmetry_model_inferred" if consistent
            else "not_adopted_pose_unconfirmed",
        )
        if consistent:
            self.assertEqual(b["conditional_pavilion_model"]["common_model"]["status"],
                             "conditional_model_inferred_not_observed")
            self.assertFalse(
                b["conditional_pavilion_model"]["common_model"]["right_side_observations_replaced"]
            )
            self.assertEqual(
                b["conditional_pavilion_model"]["right_terminal_candidate"]["provenance"],
                "MODEL_INFERRED_from_left_NOT_observed_right",
            )
        self.assertEqual(a["observed_supported_points"], b["observed_supported_points"])
        self.assertEqual(a["independent_pavilion"], b["independent_pavilion"])

    def test_asymmetric_outline_blocks_conditional_model_without_overwriting_right(self):
        altered = deepcopy(self.contour)
        for row in altered["paths"]["right_crown"]["points"]:
            if row["xy_px"] and row["support"]=="edge_supported_candidate":
                row["xy_px"][0] += 39
        r = pavilion.analyse(altered, self.joint, self.terminal, self._review())
        self.assertEqual(r["symmetry_diagnostic"]["status"], "image_only_inconsistent")
        self.assertEqual(r["conditional_pavilion_model"]["status"],
                         "not_adopted_pose_unconfirmed")
        self.assertEqual(r["physical_facet_angles"], "all_unavailable")

    def test_missing_width_band_is_unavailable_not_a_guessed_girdle(self):
        changed = deepcopy(self.joint)
        changed["widest_band_candidate"] = {"status":"unavailable"}
        r = pavilion.analyse(self.contour, changed, self.terminal)
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["physical_facet_angles"], "all_unavailable")

    def test_expert_targets_or_unpinned_method_forbidden(self):
        changed = deepcopy(self.contour)
        changed["comparison_targets_loaded"] = True
        with self.assertRaisesRegex(ValueError, "expert angle"):
            pavilion.analyse(changed, self.joint, self.terminal)
        changed = deepcopy(self.terminal)
        changed["policy_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "revision"):
            pavilion.analyse(self.contour, self.joint, changed)

    def test_real_image_generates_reproducible_separate_and_conditional_preview(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            exterior.write_qc(PHOTO,directory,feasibility.ORIGINAL_PROFILE_SHA256)
            joint.write_report(PHOTO,directory/"auto-exterior.json",directory)
            endpoint.write_report(PHOTO,directory/"auto-exterior.json",
                                  directory/"joint-changepoints.json",directory)
            fitted = pavilion.write_report(
                PHOTO, directory/"auto-exterior.json",
                directory/"joint-changepoints.json",
                directory/"endpoint-candidates.json", directory,
            )
            self.assertTrue((directory/"pavilion-observed-vs-symmetry.png").is_file())
            self.assertEqual(
                fitted,
                json.loads((directory/"pavilion-refinement.json").read_text())
            )
            self.assertEqual(
                fitted["symmetry_diagnostic"]["axis_x_px"],
                205.0
            )
            self.assertEqual(fitted["physical_facet_angles"],"all_unavailable")


if __name__=="__main__":
    unittest.main()
