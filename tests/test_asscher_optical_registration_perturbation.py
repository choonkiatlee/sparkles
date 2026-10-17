"""Predeclared registration/footprint perturbation has no facet inference."""
import unittest

import numpy as np
from scipy import ndimage as ndi

from diamond360 import asscher_optical_registration_perturbation as perturb
from diamond360 import asscher_geometry_validation as validation


class OpticalPerturbationTests(unittest.TestCase):
    def test_policy_is_fixed_without_physical_labels(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertEqual(len(perturb.SHIFTS),9)
        self.assertEqual(perturb.EXTRA_EROSIONS,(0,2))
        self.assertTrue(perturb.POLICY["no_physical_facet_labels"])
        self.assertTrue(perturb.POLICY["no_production_change"])
        self.assertTrue(perturb.POLICY["no_source_stress"])

    def test_shift_has_no_wraparound_and_moves_mask_with_rgb(self):
        a=np.zeros((8,9))
        a[1,1]=8
        b=perturb.translate_no_wrap(a,2,-1)
        self.assertEqual(b[3,0],8)
        self.assertEqual(b.sum(),8)
        no=perturb.translate_no_wrap(a,-3,0)
        self.assertEqual(no.sum(),0)
        self.assertEqual(perturb.translate_no_wrap(a,100,0).sum(),0)

    def test_gain_only_change_has_zero_switch_even_under_erosion(self):
        a=np.ones((160,160),float)*.36
        mask=np.zeros_like(a,bool)
        mask[14:146,14:146]=True
        result=perturb.perturbation_grid(
            a,a*1.6,mask,mask,mask,mask)
        self.assertEqual(result["status"],"evaluated")
        self.assertEqual(result["trial_count"],18)
        self.assertEqual(result["supported_trial_count"],18)
        for row in result["trials"]:
            self.assertEqual(row["status"],"observed")
            self.assertIsNone(row["physical_facet_semantic_ids"])
            self.assertEqual(row["physical_facet_correspondence"],"unavailable")
            self.assertAlmostEqual(row["median_gain_normalized_abs_change"],0.,places=9)
            self.assertAlmostEqual(row["total_dark_switch_fraction"],0.,places=9)
            self.assertAlmostEqual(row["total_bright_switch_fraction"],0.,places=9)

    def test_known_optical_texture_is_sensitive_to_1px_mapping_error(self):
        rng=np.random.default_rng(90)
        raw=ndi.gaussian_filter(rng.random((160,160)),.7)
        mask=np.zeros((160,160),bool)
        mask[12:148,12:148]=True
        result=perturb.perturbation_grid(raw,raw,mask,mask,mask,mask)
        self.assertEqual(result["status"],"evaluated")
        base=result["baseline"]
        self.assertLess(base["median_gain_normalized_abs_change"],1e-12)
        self.assertGreater(result["sensitivity"][
            "median_gain_normalized_abs_change"]["maximum"],0.005)
        self.assertGreater(result["sensitivity"][
            "median_gain_normalized_abs_change"]["max_abs_delta_from_baseline"],0)
        self.assertEqual(result["baseline"]["shift_dy_dx"],[0,0])

    def test_mask_never_includes_off_stone_brightness(self):
        rng=np.random.default_rng(12)
        a=.2+.2*rng.random((160,160))
        b=a.copy()
        mask=np.zeros_like(a,bool)
        mask[40:120,40:120]=True
        b[:30,:]=1.
        out=perturb.perturbation_grid(a,b,mask,mask,mask,mask)
        unchanged=perturb.perturbation_grid(a,a,mask,mask,mask,mask)
        self.assertEqual(out["status"],"evaluated")
        self.assertEqual(out["supported_trial_count"],
                         unchanged["supported_trial_count"])
        for trial,reference in zip(out["trials"],unchanged["trials"]):
            self.assertEqual(trial["status"],reference["status"])
            if trial["status"]=="observed":
                for key in perturb.MEASURES:
                    self.assertAlmostEqual(trial[key],reference[key],places=12)
        self.assertAlmostEqual(
            out["baseline"]["median_gain_normalized_abs_change"],0.,places=12)

    def test_empty_overlap_fails_closed_with_explicit_missing_trials(self):
        a=np.ones((100,100),float)*.3
        mask=np.zeros_like(a,bool)
        result=perturb.perturbation_grid(a,a,mask,mask,mask,mask)
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["supported_trial_count"],0)
        self.assertIsNone(result["sensitivity"][
            "median_gain_normalized_abs_change"]["baseline"])
        self.assertTrue(all(row["status"]=="unavailable"
                            for row in result["trials"]))


if __name__=="__main__":
    unittest.main()
