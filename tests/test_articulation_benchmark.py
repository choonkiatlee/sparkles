import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from diamond360 import articulation_benchmark as ab


def _arrays():
    frames = []
    for spread in (0.02, 0.20, 0.40, 0.60):
        frame = np.full((6, 6), 0.5, float)
        frame[2, 2] = 0.5 - spread / 2
        frame[2, 3] = 0.5
        frame[3, 2] = 0.5
        frame[3, 3] = 0.5 + spread / 2
        frames.append(frame)
    brightness = np.stack(frames)
    valid = np.ones_like(brightness, bool)
    stone = np.ones_like(brightness, bool)
    inner = np.zeros_like(brightness, bool)
    inner[:, 2:4, 2:4] = True
    observed = np.ones(4, bool)
    return brightness, valid, inner, stone, observed


class ArticulationBenchmarkTests(unittest.TestCase):
    def test_exact_coarse_fixed_support_and_summaries(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = ab.measure_arrays(
            brightness, valid, inner, stone, observed, [10, 11, 12, 13]
        )
        self.assertEqual(result["representation"], "coarse")
        self.assertEqual(result["region"], "inner")
        self.assertEqual(result["support_mode"], "fixed")
        self.assertEqual(result["persistent_support_pixels"], 4)
        self.assertEqual(result["persistent_support_fraction"], 1.0)
        values = [row["raw_spread"] for row in result["frame_trace"]]
        self.assertEqual(values, sorted(values))
        self.assertEqual(
            result["summaries"]["raw_spread"]["validity"]["status"], "ok"
        )

    def test_upstream_review_is_not_upgraded(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = ab.measure_arrays(
            brightness,
            valid,
            inner,
            stone,
            observed,
            [0, 1, 2, 3],
            upstream={"status": "review", "reasons": ["segmentation_review"]},
        )
        self.assertEqual(
            result["summaries"]["raw_spread"]["validity"]["status"], "review"
        )
        self.assertIn(
            "segmentation_review",
            result["summaries"]["raw_spread"]["validity"]["reasons"],
        )

    def test_writer_round_trips_json_and_csv(self):
        brightness, valid, inner, stone, observed = _arrays()
        result = ab.measure_arrays(
            brightness, valid, inner, stone, observed, [0, 1, 2, 3]
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            ab.write_stone_outputs(result, out)
            payload = json.loads((out / "articulation.json").read_text())
            self.assertEqual(payload["schema_version"], ab.SCHEMA)
            self.assertTrue((out / "articulation.csv").exists())
            self.assertTrue((out / "summary.csv").exists())

    def test_benchmark_summary_links_profile_and_observations(self):
        results = {}
        for i, cert in enumerate(("A", "B", "C", "D")):
            brightness, valid, inner, stone, observed = _arrays()
            brightness = brightness * (1.0 + 0.05 * i)
            core = ab.measure_arrays(
                brightness, valid, inner, stone, observed, [248, 254, 0, 4]
            )
            wide = ab.measure_arrays(
                brightness * (1.0 + 0.01 * i),
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
                        "activity.activation.inner_relative_total_excursion": {
                            "value": i + 1
                        },
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
        summary = ab.build_benchmark_summary(
            results, profile=profile, observations=observations
        )
        self.assertEqual(summary["schema_version"], ab.SUMMARY_SCHEMA)
        self.assertIn(
            "activity.activation.inner_relative_total_excursion",
            summary["redundancy_diagnostics"]["retained_profile"],
        )
        self.assertEqual(len(summary["human_observation_checks"]), 1)
        self.assertEqual(
            summary["redundancy_diagnostics"]["adjacent_tier_status"],
            "pending_sibling_49",
        )


if __name__ == "__main__":
    unittest.main()
