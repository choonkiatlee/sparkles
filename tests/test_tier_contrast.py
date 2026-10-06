import math
import unittest

import numpy as np

from diamond360 import tier_contrast as tc


class TierContrastTests(unittest.TestCase):
    def test_exact_signed_and_absolute_contrast(self):
        result = tc.contrast_trace(
            [0.2, -0.1, 0.0],
            [0.0, 0.2, 0.0],
            [0, 1, 2],
        )
        self.assertEqual(
            [row["signed_log_contrast"] for row in result["frame_trace"]],
            [0.2, -0.30000000000000004, 0.0],
        )
        self.assertEqual(
            [row["separation"] for row in result["frame_trace"]],
            [0.2, 0.30000000000000004, 0.0],
        )

    def test_swapping_bands_preserves_separation_and_flips_sign(self):
        left = tc.contrast_trace(
            [0.1, 0.4, -0.2],
            [0.3, 0.0, -0.1],
            [0, 1, 2],
        )
        right = tc.contrast_trace(
            [0.3, 0.0, -0.1],
            [0.1, 0.4, -0.2],
            [0, 1, 2],
        )
        self.assertEqual(left["separation_values"], right["separation_values"])
        for a, b in zip(left["frame_trace"], right["frame_trace"]):
            self.assertAlmostEqual(
                a["signed_log_contrast"],
                -b["signed_log_contrast"],
            )

    def test_equal_bands_have_zero_separation(self):
        result = tc.contrast_trace(
            [0.1, 0.2, 0.3],
            [0.1, 0.2, 0.3],
            [0, 1, 2],
        )
        self.assertEqual(result["separation_values"], [0.0, 0.0, 0.0])
        self.assertEqual(result["summary"]["q50"], 0.0)

    def test_global_multiplicative_change_is_removed_by_log_relative_input(self):
        first = [
            math.log(4) - math.log(8),
            math.log(8) - math.log(16),
            math.log(16) - math.log(32),
        ]
        second = [
            math.log(2) - math.log(8),
            math.log(4) - math.log(16),
            math.log(8) - math.log(32),
        ]
        result = tc.contrast_trace(first, second, [0, 1, 2])
        expected = abs(math.log(2.0))
        for value in result["separation_values"]:
            self.assertAlmostEqual(value, expected)

    def test_gap_is_preserved_without_interpolation(self):
        result = tc.contrast_trace(
            [0.0, None, 0.2],
            [0.1, 0.2, None],
            [0, 1, 2],
        )
        self.assertEqual(
            [row["status"] for row in result["frame_trace"]],
            ["ok", "gap", "gap"],
        )
        self.assertEqual(result["summary"]["status"], "unavailable")

    def test_brightness_contrast_recovers_log_ratio_and_sign(self):
        result = tc.brightness_contrast_trace(
            [4.0, 2.0, 8.0],
            [2.0, 4.0, 8.0],
            [0, 1, 2],
        )
        expected = math.log(2.0)
        self.assertAlmostEqual(result["frame_trace"][0]["signed_log_contrast"], expected)
        self.assertAlmostEqual(result["frame_trace"][1]["signed_log_contrast"], -expected)
        self.assertEqual(result["frame_trace"][2]["separation"], 0.0)

    def test_brightness_contrast_is_invariant_to_common_scale(self):
        first = tc.brightness_contrast_trace(
            [4.0, 8.0, 12.0], [2.0, 4.0, 6.0], [0, 1, 2]
        )
        second = tc.brightness_contrast_trace(
            [40.0, 80.0, 120.0], [20.0, 40.0, 60.0], [0, 1, 2]
        )
        for left, right in zip(first["separation_values"], second["separation_values"]):
            self.assertAlmostEqual(left, right)

    def test_brightness_contrast_preserves_nonpositive_values_as_gaps(self):
        result = tc.brightness_contrast_trace(
            [1.0, 0.0, None], [2.0, 2.0, 2.0], [0, 1, 2]
        )
        self.assertEqual(
            [row["status"] for row in result["frame_trace"]],
            ["ok", "gap", "gap"],
        )
        self.assertIsNone(result["frame_trace"][1]["inside_brightness"])
    def test_robust_fractional_spread_is_scale_invariant(self):
        first = tc.robust_fractional_spread([1, 2, 2, 3, 100])
        second = tc.robust_fractional_spread([10, 20, 20, 30, 1000])
        self.assertAlmostEqual(first, second)

    def test_standardized_separation_penalizes_noisy_bands(self):
        simple = tc.contrast_trace(
            [0.0, 0.0, 0.0],
            [0.2, 0.2, 0.2],
            [0, 1, 2],
        )
        clean = tc.standardized_trace(
            simple["frame_trace"],
            [0.05] * 3,
            [0.05] * 3,
        )
        noisy = tc.standardized_trace(
            simple["frame_trace"],
            [0.20] * 3,
            [0.20] * 3,
        )
        self.assertGreater(clean["summary"]["q50"], noisy["summary"]["q50"])

    def test_zero_spread_scale_is_unsupported_not_epsilon_adjusted(self):
        simple = tc.contrast_trace(
            [0.0, 0.0, 0.0],
            [0.2, 0.2, 0.2],
            [0, 1, 2],
        )
        result = tc.standardized_trace(
            simple["frame_trace"],
            [0.0] * 3,
            [0.0] * 3,
        )
        self.assertEqual(
            [row["status"] for row in result["frame_trace"]],
            ["zero_spread_scale"] * 3,
        )
        self.assertEqual(result["summary"]["status"], "unavailable")

    def test_evidence_uses_simple_extremes_and_rank_disagreement(self):
        simple = tc.contrast_trace(
            [0.0, 0.0, 0.0, 0.0],
            [0.1, 0.2, 0.3, 0.4],
            [10, 11, 12, 13],
        )
        scaled = tc.standardized_trace(
            simple["frame_trace"],
            [0.01, 0.1, 0.3, 1.0],
            [0.01, 0.1, 0.3, 1.0],
        )
        evidence = tc.select_evidence(
            simple["frame_trace"],
            scaled["frame_trace"],
        )
        self.assertEqual(evidence["weakest"]["source_index"], 10)
        self.assertEqual(evidence["strongest"]["source_index"], 13)
        self.assertIsNotNone(
            evidence["strongest_formulation_disagreement"]
        )
        self.assertGreaterEqual(
            evidence["strongest_formulation_disagreement"]["rank_disagreement"],
            0.0,
        )

    def test_sectorized_contrast_recovers_local_separation_hidden_by_global_median(self):
        # Whole-band medians can be identical while matched directions differ.
        # Sector A swaps dark/bright with sector B, so pooling would cancel.
        left = {
            "side_E": [1.0, 1.0, 1.0],
            "side_W": [4.0, 4.0, 4.0],
        }
        right = {
            "side_E": [4.0, 4.0, 4.0],
            "side_W": [1.0, 1.0, 1.0],
        }
        result = tc.sectorized_contrast_trace(left, right, [0, 1, 2])
        expected = abs(math.log(4.0))
        self.assertAlmostEqual(result["median_summary"]["q50"], expected)
        self.assertAlmostEqual(result["q75_summary"]["q50"], expected)
        self.assertEqual(
            result["frame_trace"][0]["finite_sectors"],
            2,
        )
        self.assertIn(
            result["frame_trace"][0]["strongest_sector"],
            {"side_E", "side_W"},
        )

    def test_sectorized_contrast_preserves_directional_traces(self):
        left = {"a": [1.0, 2.0, None], "b": [2.0, 2.0, 2.0]}
        right = {"a": [2.0, 1.0, 1.0], "b": [2.0, 4.0, 1.0]}
        result = tc.sectorized_contrast_trace(left, right, [10, 11, 12])
        self.assertEqual(set(result["per_sector"]), {"a", "b"})
        self.assertEqual(result["frame_trace"][2]["finite_sectors"], 1)
        self.assertEqual(
            set(result["frame_trace"][0]["sector_signed_log_contrasts"]),
            {"a", "b"},
        )
        evidence = tc.select_sectorized_evidence(result["frame_trace"])
        self.assertIsNotNone(evidence["strongest"])

    def test_multiscale_sector_consensus_medians_scale_without_collapsing_sectors(self):
        low = tc.sectorized_contrast_trace(
            {"a": [2.0, 2.0, 2.0], "b": [4.0, 4.0, 4.0]},
            {"a": [1.0, 1.0, 1.0], "b": [1.0, 1.0, 1.0]},
            [0, 1, 2],
        )
        high = tc.sectorized_contrast_trace(
            {"a": [4.0, 4.0, 4.0], "b": [8.0, 8.0, 8.0]},
            {"a": [1.0, 1.0, 1.0], "b": [1.0, 1.0, 1.0]},
            [0, 1, 2],
        )
        result = tc.multiscale_sector_consensus({"0.25": low, "0.55": high})
        row = result["frame_trace"][0]
        self.assertEqual(set(row["sector_separations"]), {"a", "b"})
        self.assertAlmostEqual(
            row["sector_separations"]["a"],
            (math.log(2.0) + math.log(4.0)) / 2,
        )
        self.assertGreater(row["sector_scale_spread"]["a"], 0)
        self.assertEqual(result["scale_labels"], ["0.25", "0.55"])

    def test_strongest_rank_disagreement_uses_aligned_frame_ranks(self):
        left = [
            {"position": 0, "source_index": 10, "median_separation": .1},
            {"position": 1, "source_index": 11, "median_separation": .2},
            {"position": 2, "source_index": 12, "median_separation": .3},
        ]
        right = [
            {"position": 0, "source_index": 10, "median_separation": .3},
            {"position": 1, "source_index": 11, "median_separation": .2},
            {"position": 2, "source_index": 12, "median_separation": .1},
        ]
        event = tc.strongest_rank_disagreement(
            left, "median_separation", right, "median_separation"
        )
        self.assertIn(event["source_index"], {10, 12})
        self.assertEqual(event["rank_disagreement"], 1.0)

    def test_rank_disagreement_rejects_misaligned_sources(self):
        left = [{"source_index": 1, "x": 1.0}, {"source_index": 2, "x": 2.0}]
        right = [{"source_index": 1, "x": 1.0}, {"source_index": 3, "x": 2.0}]
        with self.assertRaises(ValueError):
            tc.strongest_rank_disagreement(left, "x", right, "x")

    def test_sector_coverage_preserves_weak_direction_floor_and_dispersion(self):
        separations = {
            name: value
            for name, value in zip(
                "abcdefgh",
                [.01, .02, .03, .04, .30, .40, .50, .60],
            )
        }
        left = {
            name: [math.exp(value)] * 3
            for name, value in separations.items()
        }
        right = {name: [1.0] * 3 for name in separations}
        result = tc.sectorized_contrast_trace(left, right, [0, 1, 2])
        row = result["frame_trace"][0]
        self.assertLess(row["q25_separation"], row["median_separation"])
        self.assertGreater(row["iqr_separation"], 0)
        self.assertIsNotNone(result["q25_summary"]["q50"])
        self.assertIsNotNone(result["mad_summary"]["q50"])

    def test_joint_weakest_link_catches_complementary_boundary_collapse(self):
        sectors = list("abcdefgh")
        first_values = [.8, .8, .8, .8, .1, .1, .1, .1]
        second_values = [.1, .1, .1, .1, .8, .8, .8, .8]

        def row(position, source_index, values, signed):
            return {
                "position": position,
                "source_index": source_index,
                "sector_separations": dict(zip(sectors, values)),
                "sector_signed_log_contrasts": dict(zip(sectors, signed)),
                "sector_scale_spread": {sector: .02 for sector in sectors},
            }

        first = [
            row(i, i, first_values, [.8] * 8)
            for i in range(3)
        ]
        second = [
            row(i, i, second_values, [.1] * 8)
            for i in range(3)
        ]
        joint = tc.joint_nested_tier_readability(first, second)
        self.assertAlmostEqual(joint["median_summary"]["q50"], .1)
        self.assertGreater(
            float(np.median(first_values)),
            joint["median_summary"]["q50"],
        )
        self.assertGreater(
            float(np.median(second_values)),
            joint["median_summary"]["q50"],
        )
        self.assertEqual(
            joint["frame_trace"][0]["finite_sectors"],
            8,
        )
        self.assertAlmostEqual(
            joint["scale_spread_summary"]["q50"], .02
        )
        self.assertAlmostEqual(
            joint["frame_trace"][0]["pairwise_median_weakest"], .45
        )
        self.assertAlmostEqual(
            joint["frame_trace"][0]["joint_median_penalty"], .35
        )
        self.assertEqual(
            joint["evidence"]["strongest_joint_median_penalty"]["source_index"],
            0,
        )

    def test_joint_signed_ordering_keeps_all_exact_states(self):
        sectors = list("abcde")
        base = {
            "position": 0,
            "source_index": 10,
            "sector_separations": {sector: .2 for sector in sectors},
            "sector_scale_spread": {sector: .01 for sector in sectors},
        }
        first = [{
            **base,
            "sector_signed_log_contrasts": dict(
                zip(sectors, [1.0, -1.0, 1.0, -1.0, 0.0])
            ),
        }]
        second = [{
            **base,
            "sector_signed_log_contrasts": dict(
                zip(sectors, [1.0, -1.0, -1.0, 1.0, 1.0])
            ),
        }]
        result = tc.joint_nested_tier_readability(first, second)
        ordering = result["frame_trace"][0]["sector_ordering"]
        self.assertEqual(ordering["a"], "monotonic_light_to_dark_outward")
        self.assertEqual(ordering["b"], "monotonic_dark_to_light_outward")
        self.assertEqual(ordering["c"], "inner_local_minimum")
        self.assertEqual(ordering["d"], "inner_local_maximum")
        self.assertEqual(ordering["e"], "tied")
        self.assertEqual(result["ordering_observations"], 5)

    def test_joint_nested_readability_rejects_misaligned_frames(self):
        first = [{
            "source_index": 1,
            "sector_separations": {"a": .1},
            "sector_signed_log_contrasts": {"a": .1},
        }]
        second = [{
            "source_index": 2,
            "sector_separations": {"a": .1},
            "sector_signed_log_contrasts": {"a": .1},
        }]
        with self.assertRaises(ValueError):
            tc.joint_nested_tier_readability(first, second)

    def test_validity_is_monotone(self):
        result = tc.compose_validity(
            [{"status": "review", "reasons": ["upstream_review"]}],
            {
                "status": "unavailable",
                "reasons": ["insufficient_finite_frames"],
            },
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reasons"],
            ["upstream_review", "insufficient_finite_frames"],
        )


if __name__ == "__main__":
    unittest.main()
