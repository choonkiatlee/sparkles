"""Frozen optical atlas sensitivity to registration/illumination is not grading."""
import unittest

import numpy as np

from diamond360 import asscher_optical_switch_confounds as confounds
from diamond360 import asscher_geometry_validation as validation


def scene():
    im=np.ones((160,160),float)*.5
    im[35:125,20:65]=.355  # near predeclared dark threshold
    im[35:125,95:140]=.645  # near predeclared bright threshold
    valid=np.ones_like(im,bool)
    return im,valid


class SwitchingConfoundTests(unittest.TestCase):
    def test_unchanged_frozen_geometry_and_no_facet_identity(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(confounds.POLICY["no_estimator_or_92_change"])
        self.assertTrue(confounds.POLICY["no_source_stress"])
        self.assertIsNone(confounds.POLICY["facet_semantic_ids"])

    def test_predeclared_perturbations_no_wrap_or_fabricated_support(self):
        im,valid=scene()
        for name in confounds.POLICY["controlled_scenarios"]:
            arr,mask,footprint=confounds.perturb_second(im,valid,valid,name)
            self.assertEqual(arr.shape,im.shape)
            self.assertEqual(footprint.shape,im.shape)
            self.assertEqual(mask.shape,im.shape)
            self.assertTrue(np.isfinite(arr).all())
            self.assertGreater(int(np.sum(mask)),20000-400)
        moved,mask,footprint=confounds.perturb_second(
            im,valid,valid,"x_plus_1px"
        )
        self.assertFalse(footprint[:,0].any())
        self.assertTrue(footprint[:,1:].all())
        self.assertTrue(np.allclose(moved[:,1:],im[:,:-1]))
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            confounds.perturb_second(im,valid,valid,"tuned_to_stone")

    def test_pure_gain_does_not_change_normalized_contrast(self):
        im,valid=scene()
        report=confounds.run_pair(im,im,valid,valid,valid,valid)
        self.assertEqual(report["status"],"observed")
        self.assertAlmostEqual(
            report["baseline"]["median_gain_normalized_abs_change"],0,
            places=10
        )
        gain=next(x for x in report["scenarios"]
                  if x["scenario"]=="global_gain_x1p20")
        self.assertEqual(gain["status"],"observed")
        for key in confounds.METRICS:
            self.assertLess(abs(gain["delta_from_unperturbed"][key]),1e-8)

    def test_spatial_light_gradient_is_appearance_not_a_facet(self):
        im,valid=scene()
        report=confounds.run_pair(im,im,valid,valid,valid,valid)
        grad=next(x for x in report["scenarios"]
                  if x["scenario"]=="smooth_horizontal_gradient_12pct")
        self.assertGreater(
            grad["metrics"]["total_dark_switch_fraction"],0)
        self.assertGreater(
            grad["metrics"]["total_bright_switch_fraction"],0)
        self.assertFalse(report["not_an_optical_quality_score"] is False)
        self.assertEqual(report["physical_facet_correspondence"],"unavailable")
        self.assertIsNone(report["facet_semantic_ids"])

    def test_one_pixel_registration_injects_optical_changes(self):
        im,valid=scene()
        report=confounds.run_pair(im,im,valid,valid,valid,valid)
        shifted=next(x for x in report["scenarios"]
                     if x["scenario"]=="x_plus_1px")
        self.assertEqual(shifted["status"],"observed")
        self.assertGreater(
            shifted["metrics"]["median_gain_normalized_abs_change"],0)
        self.assertLess(shifted["overlap_change_pixels"],0)
        self.assertEqual(report["baseline"]["median_gain_normalized_abs_change"],0.)

    def test_missing_intersection_abstains_not_zero(self):
        im,valid=scene()
        invalid=np.zeros_like(valid,bool)
        report=confounds.run_pair(im,im,valid,valid,valid,invalid)
        self.assertEqual(report["status"],"unavailable")
        self.assertIsNone(report["baseline"])
        self.assertEqual(report["scenarios"],[])


if __name__=="__main__":
    unittest.main()
