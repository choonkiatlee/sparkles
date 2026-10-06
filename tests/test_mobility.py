import math
import unittest

from diamond360 import mobility as m


class MobilityTraceTests(unittest.TestCase):
    def test_constant_trace_is_zero(self):
        result = m.mobility_trace([2, 2, 2], [0, 1, 2])
        self.assertEqual(
            [pair["mobility"] for pair in result["pair_trace"]],
            [0.0, 0.0],
        )
        self.assertEqual(result["summary"]["median"], 0.0)
        self.assertEqual(result["summary"]["observed_adjacent_pairs"], 2)

    def test_same_excursion_can_have_different_mobility(self):
        smooth = m.mobility_trace([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
        alternating = m.mobility_trace([0, 4, 0, 4, 0], [0, 1, 2, 3, 4])
        self.assertEqual(max([0, 1, 2, 3, 4]) - min([0, 1, 2, 3, 4]), 4)
        self.assertEqual(max([0, 4, 0, 4, 0]) - min([0, 4, 0, 4, 0]), 4)
        self.assertEqual(smooth["summary"]["median"], 1.0)
        self.assertEqual(alternating["summary"]["median"], 4.0)

    def test_gap_breaks_adjacency_without_interpolation(self):
        result = m.mobility_trace([0, None, 2], [0, 1, 2])
        self.assertEqual(result["summary"]["observed_adjacent_pairs"], 0)
        self.assertEqual(
            [pair["status"] for pair in result["pair_trace"]],
            ["gap", "gap"],
        )
        self.assertIsNone(result["summary"]["median"])

    def test_non_adjacent_source_steps_are_not_formed(self):
        result = m.mobility_trace([0, 2], [0, 2])
        self.assertEqual(
            result["pair_trace"][0]["status"],
            "non_adjacent_source_steps",
        )
        self.assertEqual(result["summary"]["observed_adjacent_pairs"], 0)

    def test_explicit_wrap_allows_last_to_zero(self):
        blocked = m.mobility_trace([1, 4], [255, 0], wrap=False)
        wrapped = m.mobility_trace([1, 4], [255, 0], wrap=True)
        self.assertEqual(blocked["summary"]["observed_adjacent_pairs"], 0)
        self.assertEqual(wrapped["pair_trace"][0]["mobility"], 3.0)

    def test_nonfinite_value_is_a_gap(self):
        result = m.mobility_trace([0, math.inf, 1], [0, 1, 2])
        self.assertEqual(
            [pair["status"] for pair in result["pair_trace"]],
            ["gap", "gap"],
        )

    def test_evidence_selects_typical_largest_and_lowest_nonzero(self):
        trace = m.mobility_trace([0, 1, 1, 5, 3], [0, 1, 2, 3, 4])
        evidence = m.select_pair_evidence(trace["pair_trace"])
        self.assertEqual(evidence["largest"]["mobility"], 4.0)
        self.assertEqual(evidence["lowest_nonzero"]["mobility"], 1.0)
        self.assertEqual(evidence["median"]["mobility"], 1.0)
        self.assertIsNotNone(evidence["q90"])

    def test_validity_inherits_review(self):
        trace = m.mobility_trace([0, 1], [0, 1])
        validity = m.mobility_validity(
            {"status": "review", "reasons": ["segmentation_review"]},
            trace["summary"],
        )
        self.assertEqual(validity["status"], "review")
        self.assertEqual(validity["reasons"], ["segmentation_review"])

    def test_unavailable_adds_local_reason(self):
        trace = m.mobility_trace([0, None], [0, 1])
        validity = m.mobility_validity(
            {"status": "ok", "reasons": []},
            trace["summary"],
        )
        self.assertEqual(validity["status"], "unavailable")
        self.assertIn("no_observed_adjacent_pairs", validity["reasons"])


if __name__ == "__main__":
    unittest.main()
