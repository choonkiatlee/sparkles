import unittest

import numpy as np

from diamond360 import spatial_articulation as sa


def _sector_frame(values, shape=(41, 41)):
    support = np.ones(shape, bool)
    labels, _ = sa.angular_sector_labels(support, len(values))
    frame = np.ones(shape, float)
    for index, value in enumerate(values):
        frame[labels == index] = value
    return frame, support


class SpatialArticulationTests(unittest.TestCase):
    def test_spatial_participation_distinguishes_concentrated_from_distributed_contrast(self):
        concentrated, support = _sector_frame(
            [0.2, 0.2, 0.5, 0.5, 0.8, 0.8, 0.5, 0.5]
        )
        distributed, _ = _sector_frame(
            [0.2, 0.8, 0.2, 0.8, 0.2, 0.8, 0.2, 0.8]
        )
        first = sa.frame_spatial_participation(concentrated, support)
        second = sa.frame_spatial_participation(distributed, support)

        self.assertAlmostEqual(first["cell_log_spread"], second["cell_log_spread"])
        self.assertGreater(second["contrast_participation"], first["contrast_participation"])
        self.assertGreater(second["distributed_contrast"], first["distributed_contrast"])
        self.assertGreater(
            second["adjacent_log_contrast_median"],
            first["adjacent_log_contrast_median"],
        )

    def test_spatial_metrics_are_scale_invariant(self):
        frame, support = _sector_frame(
            [0.2, 0.8, 0.3, 0.7, 0.4, 0.6, 0.3, 0.7]
        )
        first = sa.frame_spatial_participation(frame, support)
        second = sa.frame_spatial_participation(frame * 2.5, support)
        for key in sa.SPATIAL_MEASURES:
            self.assertAlmostEqual(first[key], second[key])

    def test_coverage_distinguishes_area_with_same_global_range(self):
        narrow = np.array([0.2] * 20 + [0.5] * 60 + [0.8] * 20, float)
        broad = np.array([0.2] * 40 + [0.5] * 20 + [0.8] * 40, float)

        narrow_global = np.quantile(narrow, 0.9) - np.quantile(narrow, 0.1)
        broad_global = np.quantile(broad, 0.9) - np.quantile(broad, 0.1)
        self.assertAlmostEqual(narrow_global, broad_global)

        first = sa.frame_contrast_coverage(narrow, 1.15)
        second = sa.frame_contrast_coverage(broad, 1.15)
        self.assertAlmostEqual(first["balanced_coverage"], 0.2)
        self.assertAlmostEqual(second["balanced_coverage"], 0.4)
        self.assertGreater(second["balanced_coverage"], first["balanced_coverage"])

    def test_coverage_is_scale_invariant(self):
        values = np.array([0.2] * 30 + [0.5] * 40 + [0.8] * 30, float)
        first = sa.frame_contrast_coverage(values, 1.15)
        second = sa.frame_contrast_coverage(values * 3.0, 1.15)
        for key in (
            "dark_fraction",
            "bright_fraction",
            "extreme_coverage",
            "balanced_coverage",
            "coverage_balance",
        ):
            self.assertAlmostEqual(first[key], second[key])

    def test_coverage_tightens_monotonically_with_threshold(self):
        values = np.linspace(0.2, 0.8, 1001)
        loose = sa.frame_contrast_coverage(values, 1.10)
        primary = sa.frame_contrast_coverage(values, 1.15)
        strict = sa.frame_contrast_coverage(values, 1.20)
        self.assertGreaterEqual(loose["balanced_coverage"], primary["balanced_coverage"])
        self.assertGreaterEqual(primary["balanced_coverage"], strict["balanced_coverage"])

    def test_trace_preserves_gaps_and_summarises_both_candidates(self):
        frame, support = _sector_frame(
            [0.2, 0.8, 0.3, 0.7, 0.4, 0.6, 0.3, 0.7]
        )
        trace = sa.articulation_trace(
            [frame, None, frame * 1.1, frame * 0.9],
            support,
            [10, 11, 12, 13],
            whole_medians=[0.5, None, 0.55, 0.45],
        )
        self.assertEqual(trace["frame_trace"][1]["status"], "gap")
        self.assertEqual(trace["summaries"][sa.SPATIAL_PRIMARY]["status"], "ok")
        self.assertEqual(trace["summaries"][sa.COVERAGE_PRIMARY]["status"], "ok")

    def test_primary_candidates_are_not_just_global_spread(self):
        concentrated, support = _sector_frame(
            [0.2, 0.2, 0.5, 0.5, 0.8, 0.8, 0.5, 0.5]
        )
        distributed, _ = _sector_frame(
            [0.2, 0.8, 0.2, 0.8, 0.2, 0.8, 0.2, 0.8]
        )
        first = sa.measure_frame(concentrated, support)
        second = sa.measure_frame(distributed, support)
        self.assertAlmostEqual(first["global_raw_spread"], second["global_raw_spread"])
        self.assertGreater(second[sa.SPATIAL_PRIMARY], first[sa.SPATIAL_PRIMARY])

    def test_evidence_selects_extremes_and_matched_brightness_pair(self):
        frames = []
        support = np.ones((41, 41), bool)
        for values in (
            [0.45, 0.55] * 4,
            [0.2, 0.8] * 4,
            [0.35, 0.65] * 4,
            [0.3, 0.7] * 4,
        ):
            frame, _ = _sector_frame(values)
            frames.append(frame)
        trace = sa.articulation_trace(
            frames,
            support,
            [0, 1, 2, 3],
            whole_medians=[0.80, 0.81, 0.805, 1.20],
        )
        evidence = sa.select_evidence(trace["frame_trace"], sa.SPATIAL_PRIMARY)
        self.assertIsNotNone(evidence["lowest"])
        self.assertIsNotNone(evidence["highest"])
        self.assertTrue(evidence["matched_brightness_pair"]["brightness_matched"])


if __name__ == "__main__":
    unittest.main()
