import unittest

from diamond360 import coordination as c


class CoordinationTests(unittest.TestCase):
    def test_perfect_positive_level_coordination(self):
        result = c.level_correlation([0, 1, 2, 3], [10, 12, 14, 16])
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["pearson_r"], 1.0)

    def test_perfect_alternation_is_negative(self):
        result = c.level_correlation([0, 1, 2, 3], [6, 4, 2, 0])
        self.assertAlmostEqual(result["pearson_r"], -1.0)

    def test_level_correlation_is_offset_invariant(self):
        a = c.level_correlation([0, 1, 4, 2], [2, 3, 8, 1])
        b = c.level_correlation([10, 11, 14, 12], [22, 23, 28, 21])
        self.assertAlmostEqual(a["pearson_r"], b["pearson_r"])

    def test_constant_trace_is_explicitly_unavailable(self):
        result = c.level_correlation([1, 1, 1], [1, 2, 3])
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("constant_component_trace", result["reasons"])

    def test_change_coordination_counts_same_opposite_and_tie(self):
        result = c.adjacent_change_coordination(
            [0, 1, 0, 0, 2], [0, 2, 3, 3, 1], [0, 1, 2, 3, 4]
        )
        summary = result["summary"]
        self.assertEqual(summary["same_direction_pairs"], 1)
        self.assertEqual(summary["opposite_direction_pairs"], 2)
        self.assertEqual(summary["tie_pairs"], 1)
        self.assertAlmostEqual(summary["same_direction_fraction"], 1 / 3)

    def test_gap_breaks_adjacent_event(self):
        result = c.adjacent_change_coordination([0, None, 2], [0, 1, 2], [0, 1, 2])
        self.assertEqual([x["status"] for x in result["event_trace"]], ["gap", "gap"])
        self.assertEqual(result["summary"]["status"], "unavailable")

    def test_explicit_wrap_allows_255_to_zero(self):
        blocked = c.adjacent_change_coordination([0, 1], [0, 1], [255, 0], wrap=False)
        wrapped = c.adjacent_change_coordination([0, 1], [0, 1], [255, 0], wrap=True)
        self.assertEqual(blocked["event_trace"][0]["status"], "non_adjacent_source_steps")
        self.assertEqual(wrapped["event_trace"][0]["relationship"], "same")

    def test_evidence_prefers_events_where_both_bands_move(self):
        result = c.adjacent_change_coordination(
            [0, 10, 11, 1, 3], [0, 0.1, 5.1, 8.1, 6.1], [0, 1, 2, 3, 4]
        )
        evidence = c.select_event_evidence(result["event_trace"])
        self.assertEqual(evidence["strongest_coordinated"]["right_source_index"], 2)
        self.assertEqual(evidence["strongest_divergent"]["right_source_index"], 3)

    def test_validity_is_monotone(self):
        validity = c.compose_validity(
            [{"status": "review", "reasons": ["outer_support"]}, {"status": "ok", "reasons": []}],
            {"status": "ok", "reasons": []},
        )
        self.assertEqual(validity["status"], "review")
        self.assertEqual(validity["reasons"], ["outer_support"])


if __name__ == "__main__":
    unittest.main()
