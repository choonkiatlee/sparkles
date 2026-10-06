import math
import unittest

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
