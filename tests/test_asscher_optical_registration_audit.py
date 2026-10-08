"""Check archived #178 optical overlap audit without physical facet promotion."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
import json

from diamond360 import asscher_optical_registration_audit as qc
from diamond360 import asscher_optical_neighbor_motion as motion
from diamond360 import asscher_geometry_validation as validation


def fixture(overlap=.93,change=.18,face="uncertain",src=10):
    patches=[]
    for row in range(4):
        for col in range(4):
            measured=(row*4+col)<9
            patches.append({
                "grid":[row,col],
                "status":"measured" if measured else "ambiguous",
                "apparent_shift_gauge_px":{"dx":1,"dy":-1} if measured else None,
                "physical_facet_semantic_id":None,
            })
    return {
        "source_indices":[src,src+1],
        "positions":[src,src+1],
        "face_identity":face,
        "status":"observed",
        "physical_facet_semantic_ids":None,
        "physical_facet_correspondence":"unavailable",
        "mask_intersection_over_union":overlap,
        "median_gain_normalized_abs_change":change,
        "p90_gain_normalized_abs_change":change*1.5,
        "raw_median_luminance_ratio_b_over_a":1.05,
        "patches":patches,
        "measured_optical_shift_tile_count":9,
        "ambiguous_tile_count":7,
        "unavailable_tile_count":0,
    }


def stone():
    rows=[fixture(.93,.18,src=10),fixture(.94,.15,src=11),
          fixture(.965,.12,src=12),fixture(.985,.055,src=13),
          fixture(.992,.040,src=14)]
    return {
        "schema_version":motion.SCHEMA,
        "certificate":"SYNTHETIC",
        "production_estimator_changed":False,
        "physical_facet_identity":"not_established",
        "face_identity":{"status":"uncertain"},
        "frozen_anchor_source_indices":[10,12,14],
        "measured_pair_count":5,
        "pairs":rows,
    }


class OpticalRegistrationConfoundTests(unittest.TestCase):
    def test_source_remains_optical_and_no_model_changes(self):
        self.assertEqual(qc.POLICY["source_schema"],motion.SCHEMA)
        self.assertTrue(qc.POLICY["no_facet_geometry_or_quality_inference"])
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))

    def test_both_axes_and_camera_motion_ambiguity_reported_separately(self):
        output=qc.analyze_pair(fixture())
        self.assertEqual(output["overlap_class"],"low")
        self.assertEqual(output["local_match_class"],"intermediate")
        self.assertAlmostEqual(output["matched_tile_fraction"],9/16)
        self.assertEqual(output["modal_apparent_shift_gauge_pixels"],
                         {"dx":1,"dy":-1})
        self.assertEqual(output["exact_modal_shift_fraction_of_measured_tiles"],1.)
        self.assertEqual(output["facet_identity"],"unavailable")
        self.assertEqual(output["physical_interior_geometry"],"unavailable")

    def test_predeclared_threshold_boundaries(self):
        self.assertEqual(qc.analyze_pair(fixture(overlap=.95))["overlap_class"],
                         "intermediate")
        self.assertEqual(qc.analyze_pair(fixture(overlap=.98))["overlap_class"],
                         "high")

    def test_archive_bins_are_within_stone_no_global_quality_score(self):
        report=qc.summarize_stone(stone())
        self.assertEqual(report["overlap_bins"]["low"]["pair_count"],2)
        self.assertEqual(report["overlap_bins"]["intermediate"]["pair_count"],1)
        self.assertEqual(report["overlap_bins"]["high"]["pair_count"],2)
        self.assertTrue(report["low_vs_high_overlap_contrast"]["available"])
        self.assertGreater(
            report["low_vs_high_overlap_contrast"][
                "low_minus_high_overlap_bin_median_change"],0.)
        self.assertIsNotNone(
            report["within_stone_spearman_overlap_vs_appearance_change"])
        self.assertTrue(report["no_camera_registration_correction_performed"])
        self.assertTrue(report["no_quality_score"])

    def test_no_comparison_claim_when_no_low_overlap_bin(self):
        data=stone()
        for pair in data["pairs"]:
            pair["mask_intersection_over_union"]=.99
        result=qc.summarize_stone(data)
        self.assertFalse(result["low_vs_high_overlap_contrast"]["available"])
        self.assertEqual(result["overlap_bins"]["low"]["pair_count"],0)

    def test_ambiguous_tiles_may_not_fake_measured_motion(self):
        x=fixture()
        x["patches"][11]["apparent_shift_gauge_px"]={"dx":0,"dy":0}
        with self.assertRaisesRegex(ValueError,"uncertain tile"):
            qc.analyze_pair(x)

    def test_no_physical_facet_promotion_even_in_good_overlap(self):
        for mutation in ("pair","tile","correspondence"):
            pair=fixture(overlap=.999)
            if mutation=="pair":
                pair["physical_facet_semantic_ids"]=["C3_TABLE"]
            elif mutation=="tile":
                pair["patches"][0]["physical_facet_semantic_id"]="C3_TABLE"
            else:
                pair["physical_facet_correspondence"]="verified"
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                qc.analyze_pair(pair)

    def test_invalid_source_provenance_or_unsupported_pair_fails_closed(self):
        data=stone()
        data["pairs"][0]["positions"]=[10,14]
        with self.assertRaisesRegex(ValueError,"nonadjacent"):
            qc.summarize_stone(data)
        data=stone()
        data["production_estimator_changed"]=True
        with self.assertRaisesRegex(ValueError,"production"):
            qc.summarize_stone(data)
        data=stone()
        data["pairs"][0]["patches"][1]["grid"]=[0,0]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            qc.summarize_stone(data)

    def test_unavailable_pair_kept_as_absent_not_zero_change(self):
        data=stone()
        row=data["pairs"][0]
        row.clear()
        row.update({
            "source_indices":[10,11],"positions":[10,11],
            "face_identity":"uncertain","status":"unavailable",
            "reason":"pose_or_gauge_or_RGB_unavailable",
            "physical_facet_semantic_ids":None,
        })
        data["measured_pair_count"]=4
        result=qc.summarize_stone(data)
        self.assertEqual(result["pair_count"],5)
        self.assertEqual(result["measured_pair_count"],4)
        self.assertEqual(result["pairs"][0]["status"],"unavailable")
        self.assertNotIn("median_gain_normalized_abs_change",result["pairs"][0])


if __name__=="__main__":
    unittest.main()
