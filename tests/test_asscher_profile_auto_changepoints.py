"""Regression for silhouette-wide versus run-fragment changepoint fitting."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from diamond360 import asscher_profile_auto_exterior as auto
from diamond360 import asscher_profile_auto_changepoints as change
from diamond360 import asscher_profile_feasibility as feasibility


ORIGINAL = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


def synthetic_auto(three_crown_stretches=3, internal_noise=False):
    """Synthetic image-only outside paths, with a short shared widest band."""
    points = {"left_crown": [], "right_crown": [],
              "left_pavilion": [], "right_pavilion": []}
    if three_crown_stretches == 1:
        anchors = [(60, 205), (200, 40)]
    elif three_crown_stretches == 2:
        anchors = [(60, 205), (130, 150), (200, 40)]
    else:
        anchors = [(60, 205), (100, 183), (150, 133), (200, 40)]
    def left_x(y):
        if y >= 200 and y <= 221:
            return 40.0
        if y > 221:
            return 40 + 1.12 * (y - 221)
        for (y0, x0), (y1, x1) in zip(anchors, anchors[1:]):
            if y <= y1:
                return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
        return 40.0
    for phase, ys in (("crown", range(60, 213)), ("pavilion", range(212, 277))):
        for y in ys:
            # Small holes must not split the model into independent fragments.
            if y in (89, 90, 91, 143, 144):
                status, valid = "weak_or_ambiguous", False
            else:
                status, valid = "edge_supported_candidate", True
            jitter = 0.05 * np.sin(0.43*y)
            left = int(round(left_x(y) + jitter))
            for side, xpos in (("left", left), ("right", 410-left)):
                points[f"{side}_{phase}"].append({
                    "xy_px": [xpos, y] if valid else None,
                    "support": status,
                })
    return {
        "schema_version": auto.SCHEMA,
        "policy_sha256": feasibility.canonical_sha256(auto.POLICY),
        "source_dimensions_xy_px": [410, 319],
        "comparison_targets_loaded": False,
        "source_sha256": "synthetic-not-original",
        "paths": {name: {
            "points": rows,
            "source_provenance": "synthetic_outer_contour",
        } for name, rows in points.items()},
        # Appearance may vary, but the fitting algorithm must not inspect it.
        "unread_internal_appearance_note": "bright_many_stripes" if internal_noise else "quiet",
    }


class JointAutoChangepointsTests(unittest.TestCase):
    def test_widest_region_is_a_band_and_not_automatically_a_girdle(self):
        result = change.analyse(synthetic_auto())
        band = result["widest_band_candidate"]
        self.assertEqual(band["status"], "candidate_only")
        self.assertIn("not_verified_girdle", band["kind"])
        self.assertLessEqual(band["y_first_px"], 204)
        self.assertGreaterEqual(band["y_last_px"], 217)
        self.assertEqual(result["physical_facet_angles"], "all_unavailable")

    def test_joint_support_recovers_one_two_three_visible_stretches(self):
        for k in (1, 2, 3):
            with self.subTest(k=k):
                result = change.analyse(synthetic_auto(k))
                self.assertEqual(result["regions"]["left_crown"]["selected_segment_count"], k)
                self.assertEqual(result["regions"]["right_crown"]["selected_segment_count"], k)
                self.assertEqual(len(result["regions"]["left_crown"]["candidate_breakpoints"]), k-1)
                self.assertLess(result["regions"]["left_crown"]["unsupported_rows_between_observations"], 8)

    def test_virtual_appearance_is_not_a_fitting_input(self):
        a = change.analyse(synthetic_auto(3, internal_noise=False))
        b = change.analyse(synthetic_auto(3, internal_noise=True))
        self.assertEqual(a, b)
        self.assertFalse(a["comparison_targets_loaded"])

    def test_model_changes_are_not_mistaken_for_physical_facets(self):
        result = change.analyse(synthetic_auto(3))
        for row in result["regions"].values():
            self.assertIn(row["status"], {"review", "unavailable"})
            if row["status"] == "review":
                self.assertEqual(row["physical_facet_correspondence"], "not_established")
                for cut in row["candidate_breakpoints"]:
                    self.assertEqual(cut["status"], "candidate_only")
                    self.assertIn(cut["stability"], {"stable_to_penalty_variants", "model_dependent"})
                    self.assertIn("not_polished_facet", cut["meaning"])

    def test_missing_one_side_fails_girdle_closed(self):
        record = synthetic_auto()
        record["paths"]["right_crown"]["points"] = []
        record["paths"]["right_pavilion"]["points"] = []
        result = change.analyse(record)
        self.assertEqual(result["widest_band_candidate"]["status"], "unavailable")
        self.assertTrue(all(r["status"] == "unavailable" for r in result["regions"].values()))

    def test_only_background_first_v2_without_target_data_is_accepted(self):
        record = synthetic_auto()
        record["schema_version"] = "diamond360-asscher-auto-exterior/1"
        with self.assertRaisesRegex(ValueError, "auto-exterior/2"):
            change.analyse(record)
        record = synthetic_auto()
        record["comparison_targets_loaded"] = True
        with self.assertRaisesRegex(ValueError, "expert angle targets"):
            change.analyse(record)
        record = synthetic_auto()
        record["policy_sha256"] = "modified"
        with self.assertRaisesRegex(ValueError, "method revision"):
            change.analyse(record)

    def test_original_source_produces_no_certified_facets_and_reproducible_qc(self):
        self.assertTrue(ORIGINAL.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = auto.write_qc(ORIGINAL, tmp, feasibility.ORIGINAL_PROFILE_SHA256)
            result = change.analyse(source)
            self.assertEqual(result["widest_band_candidate"]["status"], "candidate_only")
            self.assertEqual(result["physical_facet_angles"], "all_unavailable")
            self.assertIn(result["regions"]["left_crown"]["selected_segment_count"], (1, 2, 3))
            self.assertIn(result["regions"]["right_crown"]["selected_segment_count"], (1, 2, 3))
            output = change.write_report(ORIGINAL, tmp / "auto-exterior.json", tmp / "derived")
            self.assertEqual(output, result)
            self.assertTrue((tmp / "derived" / "joint-changepoints-overlay.png").is_file())


if __name__ == "__main__":
    unittest.main()
