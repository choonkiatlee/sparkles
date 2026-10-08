"""Target-blind upper pavilion tip and lower crown endpoint proposals."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_profile_endpoint_candidates as endpoint
from diamond360 import asscher_profile_auto_exterior as exterior
from diamond360 import asscher_profile_auto_changepoints as joint
from diamond360 import asscher_profile_feasibility as feasibility

SOURCE = (
    Path(__file__).resolve().parents[1] /
    "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = np.asarray(Image.open(SOURCE).convert("RGB"))
        cls.profile = exterior.analyse_array(cls.source)
        cls.profile["source_sha256"] = feasibility.ORIGINAL_PROFILE_SHA256
        cls.joint = joint.analyse(cls.profile)

    def test_detects_point_like_pavilion_tip_without_certifying_polished_culet(self):
        result = endpoint.analyse(self.source, self.profile, self.joint)
        cap = result["top_pavilion_tip_candidate"]
        self.assertEqual(cap["status"], "candidate_only")
        self.assertGreaterEqual(cap["observed_width_px"], 5)
        self.assertLessEqual(cap["observed_width_px"], 20)
        self.assertLess(cap["top_source_y_px"], 60)
        self.assertEqual(cap["physical_table_identity"], "not_established")
        self.assertTrue(all(
            p[1] <= cap["top_source_y_px"] + 1 for p in cap["source_xy_px"]
        ))

    def test_late_crown_break_may_be_missing_on_shadow_side(self):
        result = endpoint.analyse(self.source, self.profile, self.joint)
        self.assertEqual(result["physical_facet_angle_status"], "all_unavailable")
        self.assertEqual(set(result["last_crown_changepoint_candidates"]), {"left","right"})
        left = result["last_pavilion_changepoint_candidates"]["left"]
        right = result["last_pavilion_changepoint_candidates"]["right"]
        # The two sides are independent: no mirrored break may be invented.
        self.assertIn(left["status"], {"candidate_only", "ambiguous", "unavailable"})
        self.assertIn(right["status"], {"candidate_only", "ambiguous", "unavailable"})
        for side in ("left","right"):
            p = result["lower_crown_contours"][side]["points"]
            self.assertTrue(all(
                row["status"] in ("candidate_only", "weak_or_shadow_contaminated")
                for row in p
            ))

    def test_bright_interior_band_cannot_displace_outer_endpoint_proposals(self):
        altered = self.source.copy()
        # Strong central optical lines *inside* the outline and far from
        # outside edge; source edge evidence must not change.
        altered[125:132, 165:245] = [255, 255, 255]
        a = endpoint.analyse(self.source, self.profile, self.joint)
        b = endpoint.analyse(altered, self.profile, self.joint)
        self.assertEqual(a["top_cap_candidate"], b["top_cap_candidate"])
        self.assertEqual(a["terminal_contours"], b["terminal_contours"])
        self.assertEqual(a["last_pavilion_changepoint_candidates"], b["last_pavilion_changepoint_candidates"])

    def test_flat_blank_source_has_no_top_pavilion_tip(self):
        fake = np.full((319,410,3), 205, dtype=np.uint8)
        cap = endpoint._top_cap(endpoint._signals(fake))
        self.assertEqual(cap["status"], "unavailable")

    def test_wrong_source_or_wrong_method_revision_fails_closed(self):
        wrong = deepcopy(self.profile)
        wrong["policy_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "frozen"):
            endpoint.analyse(self.source, wrong, self.joint)
        wrong = deepcopy(self.profile)
        wrong["comparison_targets_loaded"] = True
        with self.assertRaisesRegex(ValueError, "Sergey"):
            endpoint.analyse(self.source, wrong, self.joint)
        wrong_joint = deepcopy(self.joint)
        wrong_joint["source_sha256"] = "other"
        with self.assertRaisesRegex(ValueError, "incorrect source"):
            endpoint.analyse(self.source, self.profile, wrong_joint)

    def test_original_source_produces_reproducible_json_and_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contour = exterior.write_qc(SOURCE, root, feasibility.ORIGINAL_PROFILE_SHA256)
            j = joint.write_report(SOURCE, root/"auto-exterior.json", root)
            endpoint_result = endpoint.write_report(
                SOURCE, root/"auto-exterior.json", root/"joint-changepoints.json", root
            )
            self.assertEqual(endpoint_result, endpoint.analyse(self.source, contour, j))
            self.assertEqual(json.loads((root/"endpoint-candidates.json").read_text()), endpoint_result)
            self.assertTrue((root/"endpoint-review-overlay.png").is_file())
            self.assertFalse(endpoint_result["comparison_targets_loaded"])


if __name__=="__main__":
    unittest.main()
