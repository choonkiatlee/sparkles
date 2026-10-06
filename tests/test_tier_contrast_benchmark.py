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

    def test_rejects_wrong_activation_schema(self):
        fixture = activation_fixture()
        fixture["schema_version"] = "other/1"
        with self.assertRaises(ValueError):
            tb.measure_from_activation(fixture)


if __name__ == "__main__":
    unittest.main()
