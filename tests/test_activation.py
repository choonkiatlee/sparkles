import math
import unittest

import numpy as np

from diamond360 import activation as a


class ActivationTests(unittest.TestCase):
    def test_excursion_summaries(self):
        result = a.summarise_activation([1, 2, 3, 4, 5])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["finite_frames"], 5)
        self.assertAlmostEqual(result["q10"], 1.4)
        self.assertAlmostEqual(result["q50"], 3.0)
        self.assertAlmostEqual(result["q90"], 4.6)
        self.assertAlmostEqual(result["bright_excursion"], 1.6)
        self.assertAlmostEqual(result["dark_excursion"], 1.6)
        self.assertAlmostEqual(result["total_excursion"], 3.2)
        self.assertAlmostEqual(
            result["total_excursion"],
            result["bright_excursion"] + result["dark_excursion"],
        )
        self.assertAlmostEqual(result["mad_scale"], 1.4826)

    def test_summary_requires_three_finite_observations(self):
        result = a.summarise_activation([1.0, None, float("nan"), 2.0])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["finite_frames"], 2)
        for key in ("q10", "q50", "q90", "bright_excursion", "dark_excursion", "total_excursion", "mad_scale"):
            self.assertIsNone(result[key])

    def test_fixed_and_dynamic_region_support_are_distinct(self):
        brightness = np.array([
            [[1.0, 10.0], [4.0, 4.0]],
            [[2.0, 20.0], [4.0, 4.0]],
            [[3.0, 30.0], [4.0, 4.0]],
        ])
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([
            [[1, 1], [0, 0]],
            [[1, 0], [0, 0]],
            [[1, 1], [0, 0]],
        ], dtype=bool)
        observed = np.array([True, True, True])
        whole = [1.0, 2.0, 3.0]

        fixed = a.regional_trace(brightness, valid, regions, whole, observed, "fixed")
        dynamic = a.regional_trace(brightness, valid, regions, whole, observed, "dynamic")

        self.assertEqual(fixed["raw_values"], [1.0, 2.0, 3.0])
        self.assertEqual(dynamic["raw_values"], [5.5, 2.0, 16.5])
        self.assertEqual(fixed["persistent_support_pixels"], 1)
        self.assertEqual(dynamic["persistent_support_pixels"], 1)

    def test_unobserved_frame_does_not_shrink_persistent_support(self):
        brightness = np.ones((3, 1, 2), float)
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([[[1, 1]], [[1, 0]], [[1, 1]]], dtype=bool)
        observed = np.array([True, False, True])
        result = a.regional_trace(brightness, valid, regions, [1.0, None, 1.0], observed, "fixed")
        self.assertEqual(result["persistent_support_pixels"], 2)
        self.assertEqual(result["raw_values"], [1.0, None, 1.0])

    def test_global_multiplicative_brightening_is_removed_from_relative_trace(self):
        base = np.array([[1.0, 2.0], [3.0, 4.0]])
        brightness = np.stack([base, 2 * base, 4 * base])
        valid = np.ones_like(brightness, dtype=bool)
        stone_masks = np.ones_like(brightness, dtype=bool)
        region_masks = np.broadcast_to(np.array([[1, 1], [0, 0]], bool), brightness.shape)
        observed = np.ones(3, dtype=bool)

        whole = a.whole_stone_trace(brightness, valid, stone_masks, observed)
        region = a.regional_trace(brightness, valid, region_masks, whole["values"], observed, "fixed")

        self.assertGreater(whole["summary"]["total_excursion"], 0)
        self.assertGreater(region["raw_summary"]["total_excursion"], 0)
        self.assertAlmostEqual(region["relative_summary"]["total_excursion"], 0.0, places=12)

    def test_local_band_brightening_moves_relative_trace(self):
        brightness = np.ones((3, 4, 4), float) * 10.0
        brightness[0, 0, 0] = 1.0
        brightness[1, 0, 0] = 2.0
        brightness[2, 0, 0] = 4.0
        valid = np.ones_like(brightness, dtype=bool)
        stone_masks = np.ones_like(brightness, dtype=bool)
        regions = np.zeros_like(brightness, dtype=bool)
        regions[:, 0, 0] = True
        observed = np.ones(3, dtype=bool)

        whole = a.whole_stone_trace(brightness, valid, stone_masks, observed)
        region = a.regional_trace(brightness, valid, regions, whole["values"], observed, "fixed")

        self.assertEqual(whole["values"], [10.0, 10.0, 10.0])
        self.assertGreater(region["relative_summary"]["total_excursion"], 0)

    def test_nonpositive_regional_median_makes_relative_summary_unavailable(self):
        brightness = np.zeros((3, 1, 1), float)
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        observed = np.ones(3, dtype=bool)
        result = a.regional_trace(brightness, valid, region, [1.0, 1.0, 1.0], observed, "fixed")
        self.assertEqual(result["relative_values"], [None, None, None])
        self.assertEqual(result["relative_summary"]["status"], "unavailable")
        self.assertNotIn(float("inf"), [v for v in result["relative_values"] if v is not None])

    def test_compose_validity_is_monotone_and_keeps_reasons(self):
        self.assertEqual(a.compose_validity([{"status": "ok"}]), {"status": "ok", "reasons": []})
        review = a.compose_validity([
            {"status": "ok"},
            {"status": "review", "reason": "segmentation_review"},
            {"status": "review", "reason": "segmentation_review"},
        ])
        self.assertEqual(review, {"status": "review", "reasons": ["segmentation_review"]})
        unavailable = a.compose_validity([
            {"status": "review", "reason": "upstream_review"},
            {"status": "unavailable", "reason": "no_support"},
        ])
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["reasons"], ["upstream_review", "no_support"])


if __name__ == "__main__":
    unittest.main()
