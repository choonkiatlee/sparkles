import unittest

import numpy as np

from diamond360 import articulation as ar


class ArticulationTests(unittest.TestCase):
    def test_flat_region_has_zero_spread(self):
        result = ar.frame_articulation([0.5] * 101, whole_median=0.5, whole_spread=0.2)
        self.assertEqual(result["raw_spread"], 0.0)
        self.assertEqual(result["relative_to_whole_median"], 0.0)
        self.assertEqual(result["log_spread"], 0.0)

    def test_same_median_different_structure_is_separated(self):
        flat = ar.frame_articulation([0.5] * 101, whole_median=0.5)
        structured = ar.frame_articulation(
            np.linspace(0.2, 0.8, 101),
            whole_median=0.5,
        )
        self.assertAlmostEqual(flat["pixel_q50"], structured["pixel_q50"])
        self.assertGreater(structured["raw_spread"], flat["raw_spread"])
        self.assertGreater(structured["log_spread"], flat["log_spread"])

    def test_scale_normalizations_survive_uniform_brightness_change(self):
        values = np.linspace(0.2, 0.8, 101)
        first = ar.frame_articulation(values, whole_median=0.5, whole_spread=0.6)
        second = ar.frame_articulation(values * 2, whole_median=1.0, whole_spread=1.2)
        self.assertAlmostEqual(second["raw_spread"], 2 * first["raw_spread"])
        self.assertAlmostEqual(
            first["relative_to_whole_median"],
            second["relative_to_whole_median"],
        )
        self.assertAlmostEqual(first["log_spread"], second["log_spread"])
        self.assertAlmostEqual(
            first["relative_to_whole_contrast"],
            second["relative_to_whole_contrast"],
        )

    def test_trace_preserves_gaps_without_interpolation(self):
        result = ar.articulation_trace(
            [[0.1, 0.5, 0.9], None, [0.2, 0.5, 0.8]],
            [10, 11, 12],
            whole_medians=[0.5, None, 0.5],
        )
        self.assertEqual(
            [row["status"] for row in result["frame_trace"]],
            ["ok", "gap", "ok"],
        )
        self.assertEqual(result["summaries"]["raw_spread"]["status"], "unavailable")

    def test_matched_brightness_pair_maximizes_articulation_within_fixed_tolerance(self):
        trace = ar.articulation_trace(
            [
                [0.45, 0.50, 0.55],
                [0.10, 0.50, 0.90],
                [0.48, 0.50, 0.52],
                [0.20, 0.50, 0.80],
            ],
            [0, 1, 2, 3],
            whole_medians=[0.80, 0.81, 0.805, 1.20],
        )
        pair = ar.matched_brightness_pair(trace["frame_trace"])
        self.assertEqual(
            {pair["first"]["source_index"], pair["second"]["source_index"]},
            {1, 2},
        )
        self.assertGreater(pair["articulation_gap"], 0.6)
        self.assertLess(pair["whole_log_brightness_gap"], 0.02)
        self.assertTrue(pair["brightness_matched"])
        self.assertEqual(pair["matched_candidate_count"], 3)

    def test_matched_brightness_pair_marks_closest_pair_fallback(self):
        trace = ar.articulation_trace(
            [
                [0.45, 0.50, 0.55],
                [0.10, 0.50, 0.90],
                [0.20, 0.50, 0.80],
            ],
            [0, 1, 2],
            whole_medians=[0.80, 1.00, 1.40],
        )
        pair = ar.matched_brightness_pair(trace["frame_trace"])
        self.assertEqual(
            {pair["first"]["source_index"], pair["second"]["source_index"]},
            {0, 1},
        )
        self.assertFalse(pair["brightness_matched"])
        self.assertEqual(pair["matched_candidate_count"], 0)

    def test_evidence_uses_low_median_high_and_matched_pair(self):
        trace = ar.articulation_trace(
            [
                [0.49, 0.50, 0.51],
                [0.30, 0.50, 0.70],
                [0.10, 0.50, 0.90],
            ],
            [20, 21, 22],
            whole_medians=[0.80, 0.81, 0.82],
        )
        evidence = ar.select_evidence(trace["frame_trace"])
        self.assertEqual(evidence["lowest"]["source_index"], 20)
        self.assertEqual(evidence["highest"]["source_index"], 22)
        self.assertIsNotNone(evidence["median"])
        self.assertIsNotNone(evidence["matched_brightness_pair"])

    def test_rank_agreement_reports_scale_invariant_challengers(self):
        frames = [
            np.linspace(0.4, 0.6, 51),
            np.linspace(0.3, 0.7, 51),
            np.linspace(0.2, 0.8, 51),
            np.linspace(0.1, 0.9, 51),
        ]
        trace = ar.articulation_trace(
            frames,
            [0, 1, 2, 3],
            whole_medians=[0.5] * 4,
            whole_spreads=[0.5] * 4,
        )
        agreement = ar.rank_agreement(trace["frame_trace"])
        self.assertAlmostEqual(
            agreement["relative_to_whole_median"]["spearman_vs_baseline"],
            1.0,
        )
        self.assertAlmostEqual(
            agreement["relative_to_whole_contrast"]["spearman_vs_baseline"],
            1.0,
        )

    def test_invalid_reference_does_not_contaminate_raw_measurement(self):
        result = ar.frame_articulation(
            [0.2, 0.5, 0.8],
            whole_median=0.0,
            whole_spread=0.0,
        )
        self.assertIsNotNone(result["raw_spread"])
        self.assertIsNone(result["relative_to_whole_median"])
        self.assertIsNone(result["relative_to_whole_contrast"])


if __name__ == "__main__":
    unittest.main()
