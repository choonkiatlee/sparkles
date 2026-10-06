import unittest

import numpy as np

from diamond360 import occupancy as o
from diamond360 import switching as s


class SwitchingTests(unittest.TestCase):
    def test_shared_state_definition_keeps_strict_boundary(self):
        state = o.relative_dark_state(np.array([6.49, 6.50, 6.51]), 10.0, 0.65)
        self.assertEqual(state.tolist(), [True, False, False])
        self.assertIsNone(o.relative_dark_state(np.array([1.0]), None, 0.65))

    def test_static_sequence_has_zero_switching(self):
        brightness = np.array([[[5.0, 8.0]], [[5.0, 8.0]], [[5.0, 8.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = s.switching_trace(brightness, valid, region, [10.0] * 3, [True] * 3, "fixed", 0.65)
        self.assertEqual(result["switched_pixel_pairs"], 0)
        self.assertEqual(result["eligible_pixel_pairs"], 4)
        self.assertEqual(result["regional_switch_rate"], 0.0)
        self.assertEqual(result["per_pixel_rate"]["q50"], 0.0)

    def test_normalized_rate_does_not_grow_with_window_length(self):
        for frame_count in (5, 17):
            brightness = np.array(
                [5.0 if i % 2 == 0 else 8.0 for i in range(frame_count)],
                dtype=float,
            )[:, None, None]
            valid = np.ones_like(brightness, dtype=bool)
            region = np.ones_like(brightness, dtype=bool)
            result = s.switching_trace(
                brightness, valid, region, [10.0] * frame_count, [True] * frame_count, "fixed", 0.65
            )
            self.assertEqual(result["switched_pixel_pairs"], frame_count - 1)
            self.assertEqual(result["eligible_pixel_pairs"], frame_count - 1)
            self.assertEqual(result["regional_switch_rate"], 1.0)
            self.assertEqual(result["per_pixel_rate"]["q50"], 1.0)

    def test_gap_breaks_adjacency(self):
        brightness = np.array([5.0, 8.0, 5.0, 8.0, 5.0])[:, None, None]
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = s.switching_trace(
            brightness, valid, region, [10.0] * 5,
            [True, True, False, True, True], "fixed", 0.65,
        )
        self.assertEqual([item["status"] for item in result["pair_trace"]], ["ok", "gap", "gap", "ok"])
        self.assertEqual(result["observed_adjacent_pairs"], 2)
        self.assertEqual(result["regional_switch_rate"], 1.0)

    def test_pair_local_excludes_pixels_entering_or_leaving_support(self):
        brightness = np.array([[[5.0, 8.0]], [[8.0, 5.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([[[1, 0]], [[1, 1]]], dtype=bool)
        result = s.switching_trace(
            brightness, valid, regions, [10.0, 10.0], [True, True], "pair_local", 0.65
        )
        self.assertEqual(result["eligible_pixel_pairs"], 1)
        self.assertEqual(result["switched_pixel_pairs"], 1)
        self.assertEqual(result["regional_switch_rate"], 1.0)

    def test_fixed_support_is_interval_intersection(self):
        brightness = np.array([[[5.0, 8.0]], [[8.0, 5.0]], [[5.0, 5.0]]])
        valid = np.ones_like(brightness, dtype=bool)
        regions = np.array([[[1, 1]], [[1, 1]], [[1, 0]]], dtype=bool)
        fixed = s.switching_trace(
            brightness, valid, regions, [10.0] * 3, [True] * 3, "fixed", 0.65
        )
        pair_local = s.switching_trace(
            brightness, valid, regions, [10.0] * 3, [True] * 3, "pair_local", 0.65
        )
        self.assertEqual(fixed["persistent_support_pixels"], 1)
        self.assertEqual(fixed["eligible_pixel_pairs"], 2)
        self.assertEqual(pair_local["eligible_pixel_pairs"], 3)

    def test_invalid_reference_breaks_adjacent_pairs(self):
        brightness = np.array([5.0, 8.0, 5.0])[:, None, None]
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        result = s.switching_trace(
            brightness, valid, region, [10.0, None, 10.0], [True] * 3, "fixed", 0.65
        )
        self.assertEqual(
            [item["status"] for item in result["pair_trace"]],
            ["invalid_reference", "invalid_reference"],
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["regional_switch_rate"])

    def test_threshold_sweep_uses_occupancy_neighborhood(self):
        brightness = np.array([[[6.2]], [[6.6]]])
        valid = np.ones_like(brightness, dtype=bool)
        region = np.ones_like(brightness, dtype=bool)
        sweep = s.threshold_sweep(
            brightness, valid, region, [10.0, 10.0], [True, True], "fixed"
        )
        self.assertEqual(list(sweep), ["0.60", "0.65", "0.70"])
        self.assertEqual(
            [sweep[key]["regional_switch_rate"] for key in sweep],
            [0.0, 1.0, 0.0],
        )

    def test_pair_evidence_selects_highest_and_lowest_nonzero(self):
        evidence = s.select_pair_evidence([
            {"left_position": 0, "right_position": 1, "switch_fraction": 0.2,
             "eligible_pixels": 10, "switched_pixels": 2},
            {"left_position": 1, "right_position": 2, "switch_fraction": 0.0,
             "eligible_pixels": 10, "switched_pixels": 0},
            {"left_position": 2, "right_position": 3, "switch_fraction": 0.8,
             "eligible_pixels": 10, "switched_pixels": 8},
        ])
        self.assertEqual(evidence["highest"]["pair_position"], 2)
        self.assertEqual(evidence["lowest_nonzero"]["pair_position"], 0)


if __name__ == "__main__":
    unittest.main()
