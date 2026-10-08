"""Fail-closed dense optical region experiment with static RGB controls."""
import unittest

import numpy as np

from diamond360 import asscher_dense_optical_regions as regions
from diamond360 import asscher_geometry_validation as validation


class DenseOpticalRegionTests(unittest.TestCase):
    def test_no_physical_facet_labels_or_production_change(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(regions.POLICY["no_real_vs_virtual_facet_classifier"])
        self.assertTrue(regions.POLICY["no_estimator_change"])
        self.assertTrue(regions.POLICY["no_source_stress"])

    def test_smallest_circular_window_fills_missing_views(self):
        pairs,policy=regions.dense_pairs([250,2,4,5,19])
        self.assertEqual(pairs[0],(248,249))
        self.assertEqual(pairs[-1],(20,21))
        self.assertEqual(policy["pair_count"],29)
        self.assertTrue(policy["all_anchors_covered"])
        self.assertIn((255,0),pairs)
        for a,b in pairs:
            self.assertEqual((b-a)%256,1)
        self.assertEqual(len(set(pairs)),len(pairs))

    def test_deterministic_window_ignores_order_and_preserves_anchors(self):
        a,policy=regions.dense_pairs([16,13,18,19,17])
        b,_=regions.dense_pairs([19,17,13,16,18])
        self.assertEqual(a,b)
        self.assertEqual(a[0],(11,12))
        self.assertEqual(a[-1],(20,21))
        self.assertEqual(policy["pair_count"],10)

    def test_overwide_or_duplicate_window_abstains(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            regions.dense_pairs([1,1,2])
        with self.assertRaisesRegex(ValueError,"window cap"):
            regions.dense_pairs([0,62,125,188])

    def test_gain_invariant_relative_brightness_and_no_facet_ids(self):
        rng=np.random.default_rng(12)
        a=.25+.3*rng.random((144,144))
        mask=np.ones_like(a,bool)
        result=regions.region_appearance(a,1.5*a,mask,mask,mask,mask)
        self.assertEqual(result["status"],"observed")
        self.assertAlmostEqual(result["raw_luminance_ratio_b_over_a"],1.5,places=8)
        self.assertLess(result["median_gain_normalized_abs_change"],1e-9)
        self.assertLess(result["total_dark_switch_fraction"],1e-9)
        self.assertLess(result["total_bright_switch_fraction"],1e-9)
        for tile in result["bins"]:
            self.assertIsNone(tile["physical_facet_semantic_id"])

    def test_local_darkening_exposed_as_optical_not_physical(self):
        rng=np.random.default_rng(7)
        a=.3+.12*rng.random((192,192))
        b=a.copy()
        b[44:82,44:82]*=.20
        mask=np.ones_like(a,bool)
        r=regions.region_appearance(a,b,mask,mask,mask,mask)
        self.assertEqual(r["status"],"observed")
        self.assertGreater(r["total_dark_switch_fraction"],0)
        observed=[tile for tile in r["bins"] if tile["status"]=="observed"]
        self.assertTrue(any(tile["dark_occupancy_before_after"][1]>
                            tile["dark_occupancy_before_after"][0]
                            for tile in observed))
        self.assertEqual(r["physical_facet_correspondence"],"unavailable")
        self.assertFalse(r["can_claim_virtual_facets"])

    def test_gauge_mask_rejects_optical_changes_outside_stone(self):
        a=np.full((160,160),.4)
        b=a.copy()
        b[:28,:]=1.
        mask=np.zeros_like(a,bool)
        mask[35:125,35:125]=True
        r=regions.region_appearance(a,b,mask,mask,mask,mask)
        self.assertEqual(r["status"],"observed")
        self.assertAlmostEqual(r["median_gain_normalized_abs_change"],0.,places=8)
        self.assertEqual(r["total_dark_switch_fraction"],0.)

    def test_empty_overlap_and_unsupported_bins_are_not_zero_scores(self):
        a=np.full((144,144),.45)
        missing=np.zeros_like(a,bool)
        r=regions.region_appearance(a,a,missing,missing,missing,missing)
        self.assertEqual(r["status"],"unavailable")
        self.assertEqual(r["bins"],[])
        m=np.zeros_like(a,bool)
        m[27:117,27:117]=True
        good=regions.region_appearance(a,a,m,m,m,m,grid=12)
        self.assertEqual(good["status"],"observed")
        self.assertTrue(any(b["status"]=="unavailable" for b in good["bins"]))

    def test_reject_nonfinite_source_images(self):
        a=np.ones((144,144),float)*.5
        b=a.copy();b[70,70]=np.nan
        mask=np.ones_like(a,bool)
        with self.assertRaisesRegex(ValueError,"incompatible"):
            regions.region_appearance(a,b,mask,mask,mask,mask)


if __name__=="__main__":
    unittest.main()
