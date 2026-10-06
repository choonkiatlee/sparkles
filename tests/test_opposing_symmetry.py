import unittest

from diamond360.opposing_symmetry import pair_trace, select_evidence


class OpposingSymmetryTests(unittest.TestCase):
    def test_exact_pair_summaries(self):
        result = pair_trace(
            [0.0, 1.0, 2.0, 1.0],
            [0.0, 1.0, 1.0, 2.0],
            [10, 11, 12, 13],
        )
        self.assertAlmostEqual(
            result["metrics"]["median_absolute_difference"]["value"], 0.5
        )
        sign = result["metrics"]["sign_agreement"]
        self.assertAlmostEqual(sign["value"], 0.5)
        self.assertEqual(sign["same_direction_pairs"], 1)
        self.assertEqual(sign["opposite_direction_pairs"], 1)
        self.assertEqual(sign["flat_pairs"], 1)
        self.assertAlmostEqual(result["median_signed_difference"], 0.0)

    def test_gaps_break_adjacency(self):
        result = pair_trace(
            [0.0, None, 1.0, 2.0],
            [0.0, None, 2.0, 3.0],
            [10, 11, 12, 13],
        )
        self.assertEqual(result["adjacent_trace"][0]["status"], "gap")
        self.assertEqual(result["adjacent_trace"][1]["status"], "gap")
        self.assertEqual(result["adjacent_trace"][2]["status"], "ok")

    def test_non_adjacent_source_steps_are_not_bridged(self):
        result = pair_trace([0, 1, 2], [0, 1, 2], [1, 3, 4])
        self.assertEqual(
            result["adjacent_trace"][0]["status"],
            "non_adjacent_source_steps",
        )
        self.assertEqual(result["adjacent_trace"][1]["status"], "ok")

    def test_explicit_wrap_is_observed(self):
        result = pair_trace(
            [0, 1, 2, 3],
            [0, 1, 2, 3],
            [254, 255, 0, 1],
            wrap=True,
        )
        self.assertEqual(result["adjacent_trace"][1]["status"], "ok")
        self.assertEqual(
            result["adjacent_trace"][1]["left_source_index"], 255
        )
        self.assertEqual(
            result["adjacent_trace"][1]["right_source_index"], 0
        )

    def test_zero_variance_correlation_is_unavailable_not_nan(self):
        result = pair_trace([1, 1, 1], [0, 1, 2], [1, 2, 3])
        correlation = result["metrics"]["correlation"]
        self.assertIsNone(correlation["value"])
        self.assertEqual(correlation["status"], "unavailable")
        self.assertEqual(
            correlation["reason"], "zero_variance_component_trace"
        )

    def test_flat_pairs_do_not_inflate_sign_agreement(self):
        result = pair_trace([0, 0, 1], [0, 1, 2], [1, 2, 3])
        sign = result["metrics"]["sign_agreement"]
        self.assertEqual(sign["flat_pairs"], 1)
        self.assertEqual(sign["directional_pairs"], 1)
        self.assertEqual(sign["value"], 1.0)

    def test_evidence_selection_is_deterministic(self):
        result = pair_trace(
            [0, 1, 2, 1, 4],
            [0, 1, 0, 1, 5],
            [1, 2, 3, 4, 5],
        )
        evidence = select_evidence(result)
        self.assertIsNotNone(evidence["strongest_coordinated"])
        self.assertIsNotNone(evidence["strongest_divergent"])
        self.assertIsNotNone(evidence["typical"])
        self.assertEqual(
            evidence["strongest_coordinated"]["right_source_index"], 5
        )
        self.assertEqual(
            evidence["strongest_divergent"]["right_source_index"], 3
        )


if __name__ == "__main__":
    unittest.main()
