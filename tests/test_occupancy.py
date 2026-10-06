import unittest

import numpy as np

from diamond360 import occupancy as o


class OccupancyTests(unittest.TestCase):
    def test_exact_numerator_denominator_and_fraction(self):
        brightness = np.array([[[1.0, 4.0], [7.0, 9.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = o.occupancy_trace(brightness, valid, region, [10.0], [True], "dynamic", 0.65)
        self.assertEqual(result["dark_pixel_counts"], [2])
        self.assertEqual(result["supported_pixel_counts"], [4])
        self.assertEqual(result["values"], [0.5])

    def test_threshold_boundary_is_strictly_less_than(self):
        brightness = np.array([[[6.49, 6.50, 6.51]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = o.occupancy_trace(brightness, valid, region, [10.0], [True], "dynamic", 0.65)
        self.assertEqual(result["dark_pixel_counts"], [1])
        self.assertAlmostEqual(result["values"][0], 1 / 3)

    def test_fixed_and_dynamic_differ_when_membership_changes(self):
        brightness = np.array([[[1.0, 9.0]], [[1.0, 9.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([[[1, 1]], [[1, 0]]], dtype=bool)
        observed = np.array([True, True])
        fixed = o.occupancy_trace(brightness, valid, regions, [10.0, 10.0], observed, "fixed", 0.65)
        dynamic = o.occupancy_trace(brightness, valid, regions, [10.0, 10.0], observed, "dynamic", 0.65)
        self.assertEqual(fixed["values"], [1.0, 1.0])
        self.assertEqual(dynamic["values"], [0.5, 1.0])

    def test_unobserved_frame_does_not_enter_persistent_intersection(self):
        brightness = np.ones((3, 1, 2), float)
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([[[1, 1]], [[1, 0]], [[1, 1]]], dtype=bool)
        observed = np.array([True, False, True])
        result = o.occupancy_trace(brightness, valid, regions, [2.0, None, 2.0], observed, "fixed", 0.65)
        self.assertEqual(result["persistent_support_pixels"], 2)
        self.assertEqual(result["supported_pixel_counts"], [2, None, 2])
        self.assertEqual(result["values"], [1.0, None, 1.0])

    def test_no_support_is_unavailable_not_nan(self):
        brightness = np.ones((2, 1, 1), float)
        valid = np.ones_like(brightness, dtype=bool)
        region = np.zeros_like(brightness, dtype=bool)
        result = o.occupancy_trace(brightness, valid, region, [1.0, 1.0], [True, True], "fixed", 0.65)
        self.assertEqual(result["values"], [None, None])
        self.assertEqual(result["summary"]["status"], "unavailable")
        self.assertEqual(result["supported_pixel_counts"], [0, 0])

    def test_invalid_whole_stone_reference_is_unavailable(self):
        brightness = np.ones((4, 1, 1), float)
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = o.occupancy_trace(
            brightness, valid, region,
            [None, 0.0, float("nan"), float("inf")],
            [True, True, True, True], "fixed", 0.65,
        )
        self.assertEqual(result["values"], [None, None, None, None])
        self.assertEqual(result["dark_pixel_counts"], [None, None, None, None])
        self.assertEqual(result["supported_pixel_counts"], [1, 1, 1, 1])

    def test_global_multiplicative_scaling_leaves_occupancy_unchanged(self):
        base = np.array([[[1.0, 4.0, 7.0, 9.0]]])
        valid = np.ones_like(base, dtype=bool)
        region = np.ones_like(base, dtype=bool)
        first = o.occupancy_trace(base, valid, region, [10.0], [True], "fixed", 0.65)
        second = o.occupancy_trace(base * 4, valid, region, [40.0], [True], "fixed", 0.65)
        self.assertEqual(first["values"], second["values"])

    def test_local_darkening_increases_occupancy(self):
        brightness = np.array([[[7.0, 7.0]], [[5.0, 7.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = o.occupancy_trace(brightness, valid, region, [10.0, 10.0], [True, True], "fixed", 0.65)
        self.assertEqual(result["values"], [0.0, 0.5])

    def test_summary_mean_median_and_quantiles_are_finite_and_json_safe(self):
        summary = o.summarise_occupancy([0.0, 0.25, None, 0.5, 1.0])
        self.assertEqual(summary["finite_frames"], 4)
        self.assertAlmostEqual(summary["mean"], 0.4375)
        self.assertAlmostEqual(summary["median"], 0.375)
        for key in ("q10", "q50", "q90"):
            self.assertTrue(np.isfinite(summary[key]))

    def test_predeclared_threshold_sweep(self):
        brightness = np.array([[[6.2, 6.6]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        sweep = o.threshold_sweep(brightness, valid, region, [10.0], [True], "fixed")
        self.assertEqual(list(sweep), ["0.60", "0.65", "0.70"])
        self.assertEqual([sweep[key]["values"][0] for key in sweep], [0.0, 0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
