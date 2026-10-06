import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from diamond360 import spatial_articulation as sa
from diamond360 import spatial_articulation_benchmark as sb


def _frame(values, shape=(41, 41)):
    support = np.ones(shape, bool)
    labels, _ = sa.angular_sector_labels(support, len(values))
    frame = np.ones(shape, float)
    for index, value in enumerate(values):
        frame[labels == index] = value
    return frame


def _arrays():
    patterns = [
        [0.45, 0.55] * 4,
        [0.35, 0.65] * 4,
        [0.25, 0.75] * 4,
        [0.20, 0.80] * 4,
    ]
    brightness = np.stack([_frame(values) for values in patterns])
    valid = np.ones_like(brightness, bool)
    stone = np.ones_like(brightness, bool)
    inner = np.ones_like(brightness, bool)
    observed = np.ones(len(brightness), bool)
    return brightness, valid, inner, stone, observed


class SpatialArticulationBenchmarkTests(unittest.TestCase):
    def test_exact_coarse_fixed_support_and_candidates(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = sb.measure_arrays(
            brightness, valid, inner, stone, observed, [10, 11, 12, 13]
        )
        self.assertEqual(result["support_mode"], "fixed")
        self.assertEqual(result["sector_count"], 8)
        self.assertEqual(result["persistent_support_fraction"], 1.0)
        self.assertEqual(
            result["summaries"][sa.SPATIAL_PRIMARY]["validity"]["status"], "ok"
        )
        self.assertEqual(
            result["summaries"][sa.COVERAGE_PRIMARY]["validity"]["status"], "ok"
        )

    def test_upstream_review_is_not_upgraded(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = sb.measure_arrays(
            brightness,
            valid,
            inner,
            stone,
            observed,
            [0, 1, 2, 3],
            upstream={"status": "review", "reasons": ["segmentation_review"]},
        )
        self.assertEqual(
            result["summaries"][sa.SPATIAL_PRIMARY]["validity"]["status"], "review"
        )
        self.assertIn(
            "segmentation_review",
            result["summaries"][sa.SPATIAL_PRIMARY]["validity"]["reasons"],
        )

    def test_writer_round_trips(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = sb.measure_arrays(
            brightness, valid, inner, stone, observed, [0, 1, 2, 3]
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            sb.write_stone_outputs(result, out)
            payload = json.loads((out / "spatial-articulation.json").read_text())
            self.assertEqual(payload["schema_version"], sb.SCHEMA)
            self.assertTrue((out / "spatial-articulation.csv").exists())
            self.assertTrue((out / "summary.csv").exists())

    def test_summary_compares_both_candidates_to_existing_profile(self):
        results = {}
        for i, cert in enumerate(("A", "B", "C", "D")):
            brightness, valid, inner, stone, observed = _arrays()
            core = sb.measure_arrays(
                brightness * (1 + 0.02 * i),
                valid,
                inner,
                stone,
                observed,
                [248, 254, 0, 4],
            )
            wide = sb.measure_arrays(
                brightness[::-1] * (1 + 0.02 * i),
                valid,
                inner,
                stone,
                observed,
                [248, 254, 0, 4],
            )
            results[cert] = {"core": core, "wide": wide}
        profile = {
            "stones": [
                {
                    "certificate": cert,
                    "measurements": {
                        "activity.activation.inner_relative_total_excursion": {"value": i + 1},
                        "dark_state.occupancy.inner_mean": {"value": 4 - i},
                        "activity.mobility.inner_median": {"value": i + 0.5},
                    },
                }
                for i, cert in enumerate(("A", "B", "C", "D"))
            ]
        }
        observations = {
            "observations": [
                {
                    "id": "LG756520111-pale-inner-panels",
                    "certificate": "A",
                    "concept": "quiet_or_pale_inner_region",
                    "role": "check",
                    "summary": "fixture",
                    "source_frames": [248, 0],
                }
            ]
        }
        summary = sb.build_benchmark_summary(
            results, profile=profile, observations=observations
        )
        self.assertEqual(summary["issue"], 59)
        self.assertFalse("human" in summary["validation_target"].lower() and "not human" not in summary["validation_target"].lower())
        self.assertIn(
            "#51_global_raw_spread",
            summary["redundancy_diagnostics"]["spatial_participation"],
        )
        self.assertIn(
            "dark_state.occupancy.inner_mean",
            summary["redundancy_diagnostics"]["contrast_coverage"],
        )
        self.assertEqual(len(summary["evaluation_observation_checks"]), 1)


if __name__ == "__main__":
    unittest.main()
