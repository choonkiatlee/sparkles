import json
import tempfile
import unittest
from pathlib import Path

from diamond360 import activation_benchmark as ab
from diamond360 import tier_contrast_benchmark as tb


def _cell(values, validity=None):
    return {
        "relative_values": values,
        "relative_validity": validity or {"status": "ok", "reasons": []},
        "persistent_support_fraction": 1.0,
    }


def activation_fixture():
    indices = [254, 255, 0, 1]
    cells = {
        "centre": [0.0, 0.1, 0.2, 0.3],
        "inner": [0.1, 0.1, 0.3, 0.0],
        "middle": [0.4, 0.2, 0.1, 0.1],
    }
    return {
        "schema_version": ab.SCHEMA,
        "requested_indices": indices,
        "accepted_indices": indices,
        "excluded": [],
        "wrap_explicit": True,
        "representations": {
            "coarse": {
                "regions": {
                    name: {"fixed": _cell(values)}
                    for name, values in cells.items()
                }
            }
        },
        "frame_rgb_paths": [],
    }


class TierContrastBenchmarkTests(unittest.TestCase):
    def test_consumes_only_retained_coarse_fixed_pairs(self):
        result = tb.measure_from_activation(activation_fixture())
        self.assertEqual(
            set(result["pairs"]),
            {"centre__inner", "inner__middle"},
        )
        pair = result["pairs"]["centre__inner"]
        self.assertEqual(pair["representation"], "coarse")
        self.assertEqual(pair["support_mode"], "fixed")
        self.assertTrue(pair["primary"])

    def test_simple_candidate_works_without_pixel_spread(self):
        result = tb.measure_from_activation(activation_fixture())
        pair = result["pairs"]["centre__inner"]
        self.assertEqual(pair["simple"]["validity"]["status"], "ok")
        self.assertEqual(
            pair["standardized"]["validity"]["status"],
            "unavailable",
        )
        self.assertIn(
            "standardized_spread_unavailable",
            pair["standardized"]["validity"]["reasons"],
        )

    def test_standardized_challenger_is_optional_and_aligned(self):
        spreads = {
            "centre": [0.1, 0.1, 0.1, 0.1],
            "inner": [0.2, 0.2, 0.2, 0.2],
            "middle": [0.3, 0.3, 0.3, 0.3],
        }
        result = tb.measure_from_activation(
            activation_fixture(),
            spreads,
        )
        pair = result["pairs"]["inner__middle"]
        self.assertEqual(
            pair["standardized"]["validity"]["status"],
            "ok",
        )
        self.assertEqual(
            len(pair["standardized"]["frame_trace"]),
            4,
        )
        self.assertIsNotNone(
            pair["evidence"]["strongest_formulation_disagreement"]
        )

    def test_upstream_review_propagates_without_upgrade(self):
        fixture = activation_fixture()
        fixture["representations"]["coarse"]["regions"]["inner"]["fixed"][
            "relative_validity"
        ] = {
            "status": "review",
            "reasons": ["segmentation_review"],
        }
        result = tb.measure_from_activation(fixture)
        for pair_id in ("centre__inner", "inner__middle"):
            self.assertEqual(
                result["pairs"][pair_id]["simple"]["validity"]["status"],
                "review",
            )
            self.assertIn(
                "segmentation_review",
                result["pairs"][pair_id]["simple"]["validity"]["reasons"],
            )

    def test_writer_is_json_safe(self):
        result = tb.measure_from_activation(activation_fixture())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            tb.write_stone_outputs(result, out)
            payload = json.loads(
                (out / "tier-contrast.json").read_text()
            )
            self.assertEqual(payload["schema_version"], tb.SCHEMA)
            self.assertTrue((out / "tier-contrast.csv").exists())


    def test_committed_region_trace_reconstruction_matches_log_ratio(self):
        trace = {
            "schema_version": tb.REGION_TRACE_SCHEMA,
            "requested_indices": [0, 1, 2],
            "accepted_indices": [0, 1, 2],
            "excluded": [],
            "wrap_explicit": False,
            "regions": {
                "centre": {"median_brightness": [4.0, 8.0, 16.0]},
                "inner": {"median_brightness": [2.0, 4.0, 8.0]},
                "middle": {"median_brightness": [1.0, 8.0, 4.0]},
            },
        }
        result = tb.measure_primary_from_region_trace(trace)
        centre_inner = result["pairs"]["centre__inner"]["simple"]
        self.assertTrue(
            all(abs(value - 0.6931471805599453) < 1e-12
                for value in centre_inner["separation_values"])
        )
        self.assertEqual(
            result["reconstruction_source_schema"],
            tb.REGION_TRACE_SCHEMA,
        )

    def test_rejects_wrong_activation_schema(self):
        fixture = activation_fixture()
        fixture["schema_version"] = "other/1"
        with self.assertRaises(ValueError):
            tb.measure_from_activation(fixture)


class CommittedTierContrastArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_primary_summary_reconstructs_from_committed_region_traces(self):
        summary_path = self.ROOT / "docs" / "360" / "tier-contrast" / "summary.json"
        summary = json.loads(summary_path.read_text())
        self.assertEqual(
            summary["schema_version"],
            "diamond360-tier-contrast-primary-benchmark/1",
        )
        self.assertEqual(summary["provisional_disposition"], "REVISE")
        self.assertEqual(len(summary["rows"]), 16)

        for row in summary["rows"]:
            trace_path = self.ROOT / row["source_trace"]
            trace = json.loads(trace_path.read_text())
            rebuilt = tb.measure_primary_from_region_trace(trace)
            simple = rebuilt["pairs"][row["pair"]]["simple"]
            self.assertAlmostEqual(simple["summary"]["q10"], row["q10"])
            self.assertAlmostEqual(simple["summary"]["q50"], row["q50"])
            self.assertAlmostEqual(simple["summary"]["q90"], row["q90"])
            evidence = rebuilt["pairs"][row["pair"]]["evidence"]
            self.assertIn(row["status"], {"ok", "review", "unavailable"})
            self.assertIsInstance(row["reasons"], list)
            self.assertEqual(
                evidence["weakest"]["source_index"],
                row["weakest"]["source_index"],
            )
            self.assertEqual(
                evidence["strongest"]["source_index"],
                row["strongest"]["source_index"],
            )

    def test_summary_preserves_window_sensitivity_warning(self):
        summary = json.loads(
            (self.ROOT / "docs" / "360" / "tier-contrast" / "summary.json").read_text()
        )
        sensitivity = summary["core_wide_sensitivity"]
        self.assertEqual(
            sensitivity["centre__inner"]["q10"]["core_wide_rank_spearman"],
            0.0,
        )
        self.assertEqual(
            sensitivity["inner__middle"]["q50"]["core_wide_rank_spearman"],
            0.0,
        )
        self.assertEqual(
            sensitivity["centre__inner"]["q90"]["core_wide_rank_spearman"],
            0.8,
        )
        self.assertEqual(
            sensitivity["inner__middle"]["q90"]["core_wide_rank_spearman"],
            0.8,
        )


if __name__ == "__main__":
    unittest.main()
