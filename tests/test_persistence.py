import unittest

import numpy as np

from diamond360 import persistence as p


def run(values, observed=None, support=None, mode="fixed", whole=None):
    brightness = np.asarray(values, float)[:, None, None]
    valid = (
        np.ones_like(brightness, bool)
        if support is None
        else np.asarray(support, bool)[:, None, None]
    )
    region = np.ones_like(brightness, bool)
    if observed is None:
        observed = [True] * len(values)
    if whole is None:
        whole = [10.0] * len(values)
    return p.persistence_trace(
        brightness, valid, region, whole, observed, mode, 0.65
    )


class PersistenceTests(unittest.TestCase):
    def test_static_dark_run_spans_window_and_is_endpoint_censored(self):
        result = run([5, 5, 5, 5])
        self.assertEqual(result["dark"]["q90_frames"], 4.0)
        self.assertEqual(result["dark"]["q90_window_fraction"], 1.0)
        self.assertEqual(result["non_dark"]["q90_frames"], 0.0)
        self.assertEqual(
            result["evidence"]["dark"]["left_boundary"], "window_endpoint"
        )
        self.assertEqual(
            result["evidence"]["dark"]["right_boundary"], "window_endpoint"
        )

    def test_alternation_has_unit_runs_and_does_not_join_end_to_start(self):
        result = run([5, 8, 5, 8, 5])
        self.assertEqual(result["dark"]["max_frames"], 1)
        self.assertEqual(result["non_dark"]["max_frames"], 1)

    def test_gap_breaks_and_censors_run(self):
        result = run(
            [5, 5, 5, 5, 8],
            observed=[True, True, False, True, True],
        )
        self.assertEqual(result["dark"]["max_frames"], 2)
        self.assertGreater(
            result["dark"]["censor_boundaries"]["right"]["gap"], 0
        )
        self.assertEqual(result["evidence"]["dark"]["right_boundary"], "gap")

    def test_dynamic_support_loss_breaks_and_reentry_starts_new_run(self):
        result = run(
            [5, 5, 5, 5, 5],
            support=[True, True, False, True, True],
            mode="dynamic",
        )
        self.assertEqual(result["dark"]["max_frames"], 2)
        self.assertGreater(
            result["dark"]["censor_boundaries"]["right"]["support_loss"], 0
        )
        self.assertAlmostEqual(result["dark"]["q90_window_fraction"], 0.4)

    def test_fixed_support_excludes_pixel_lost_mid_interval(self):
        result = run(
            [5, 5, 5],
            support=[True, False, True],
            mode="fixed",
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["persistent_support_pixels"], 0)

    def test_invalid_reference_breaks_run(self):
        result = run([5, 5, 5], whole=[10, None, 10])
        self.assertEqual(result["dark"]["max_frames"], 1)
        self.assertGreater(
            result["dark"]["censor_boundaries"]["right"]["invalid_reference"], 0
        )

    def test_threshold_boundary_is_non_dark(self):
        result = run([6.5, 6.49, 6.5])
        self.assertEqual(result["dark"]["max_frames"], 1)
        self.assertEqual(result["non_dark"]["max_frames"], 1)

    def test_normalization_uses_requested_window_not_dynamic_support(self):
        result = run(
            [5, 5, 5, 5, 5],
            support=[True, True, False, False, False],
            mode="dynamic",
        )
        self.assertEqual(result["dark"]["max_frames"], 2)
        self.assertEqual(result["dark"]["q90_window_fraction"], 0.4)

    def test_threshold_sweep_is_shared_neighborhood(self):
        brightness = np.array([6.2, 6.6])[:, None, None]
        valid = np.ones_like(brightness, bool)
        region = np.ones_like(brightness, bool)
        sweep = p.threshold_sweep(
            brightness,
            valid,
            region,
            [10, 10],
            [True, True],
            "fixed",
        )
        self.assertEqual(list(sweep), ["0.60", "0.65", "0.70"])
        self.assertEqual(sweep["0.65"]["dark"]["max_frames"], 1)


if __name__ == "__main__":
    unittest.main()
