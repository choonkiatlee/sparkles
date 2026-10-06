import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from diamond360 import activation_benchmark as ab
from diamond360 import coordination_benchmark as cb


def _cell(values, validity=None):
    validity = validity or {"status": "ok", "reasons": []}
    return {
        "relative_values": values,
        "relative_validity": validity,
        "persistent_support_fraction": 1.0,
    }


def activation_fixture():
    indices = [254, 255, 0, 1]
    coarse = {
        band: {
            "fixed": _cell(values),
            "dynamic": _cell(values),
        }
        for band, values in {
            "centre": [0.0, 0.1, 0.2, 0.0],
            "inner": [0.0, 0.2, 0.4, 0.0],
            "middle": [0.1, 0.0, -0.1, 0.2],
            "outer": [0.2, 0.3, 0.2, 0.1],
        }.items()
    }
    semantic = {
        region: {
            "fixed": _cell(values, {"status": "review", "reasons": ["semantic_window_edge"]}),
            "dynamic": _cell(values, {"status": "review", "reasons": ["semantic_window_edge"]}),
        }
        for region, values in {
            "centre": [0.0, 0.1, 0.2, 0.0],
            "inner_step": [0.0, 0.2, 0.4, 0.0],
            "middle_step": [0.1, 0.0, -0.1, 0.2],
            "outer_step": [0.2, 0.3, 0.2, 0.1],
        }.items()
    }
    return {
        "schema_version": ab.SCHEMA,
        "requested_indices": indices,
        "accepted_indices": indices,
        "excluded": [],
        "wrap_explicit": True,
        "representations": {
            "coarse": {"regions": coarse},
            "semantic": {"regions": semantic},
        },
        "frame_rgb_paths": [],
    }


class CoordinationBenchmarkTests(unittest.TestCase):
    def test_consumes_activation_and_promotes_only_clean_adjacent_pairs(self):
        result = cb.measure_from_activation(activation_fixture())
        pairs = result["representations"]["coarse"]["fixed"]["pairs"]
        self.assertTrue(pairs["centre__inner"]["primary"])
        self.assertTrue(pairs["inner__middle"]["primary"])
        self.assertFalse(pairs["middle__outer"]["primary"])
        self.assertEqual(pairs["middle__outer"]["inherited_disposition"], "REVISE")
        self.assertFalse(pairs["centre__middle"]["adjacent"])

    def test_emits_symmetric_four_by_four_matrix(self):
        result = cb.measure_from_activation(activation_fixture())
        matrix = result["representations"]["coarse"]["fixed"]["level_correlation_matrix"]
        self.assertEqual(set(matrix), {"centre", "inner", "middle", "outer"})
        self.assertEqual(matrix["centre"]["inner"], matrix["inner"]["centre"])
        self.assertEqual(matrix["outer"]["outer"], 1.0)

    def test_dynamic_support_is_outer_qc_only(self):
        result = cb.measure_from_activation(activation_fixture())
        pairs = result["representations"]["coarse"]["outer_support_sensitivity"]["pairs"]
        self.assertEqual(set(pairs), {"middle__outer"})
        self.assertEqual(pairs["middle__outer"]["inherited_disposition"], "REJECT")

    def test_semantic_validity_remains_review(self):
        result = cb.measure_from_activation(activation_fixture())
        pair = result["representations"]["semantic"]["fixed"]["pairs"]["centre__inner"]
        self.assertEqual(pair["level_validity"]["status"], "review")
        self.assertIn("semantic_window_edge", pair["level_validity"]["reasons"])

    def test_writer_is_json_safe_and_can_emit_evidence_panels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = root / "processed"
            processed.mkdir()
            fixture = activation_fixture()
            paths = []
            for i in range(4):
                name = f"frame-{i}.png"
                Image.new("RGB", (24, 24), (40 + i * 20, 50, 60)).save(processed / name)
                paths.append(name)
            fixture["frame_rgb_paths"] = paths
            result = cb.measure_from_activation(fixture)
            out = root / "out"
            cb.write_stone_outputs(result, out, processed=processed)
            payload = json.loads((out / "coordination.json").read_text())
            self.assertEqual(payload["schema_version"], cb.SCHEMA)
            self.assertTrue((out / "coordination.csv").exists())
            self.assertTrue((out / "evidence" / "coarse-centre__inner.png").exists())

    def test_rejects_wrong_upstream_schema(self):
        fixture = activation_fixture()
        fixture["schema_version"] = "other/1"
        with self.assertRaises(ValueError):
            cb.measure_from_activation(fixture)


class CommittedCoordinationArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "docs" / "360" / "coordination"
    CORE = [248, 249, 250, 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5, 6, 7, 8]
    WIDE = list(range(240, 256)) + list(range(0, 17))

    def test_summary_pins_benchmark_scope(self):
        summary = json.loads((self.ROOT / "summary.json").read_text())
        self.assertEqual(summary["core_indices"], self.CORE)
        self.assertEqual(summary["wide_indices"], self.WIDE)
        self.assertEqual(summary["upstream_activation_schema"], ab.SCHEMA)
        self.assertEqual(len(summary["stones"]), 4)

    def test_dispositions_cover_retained_and_rejected_candidates(self):
        payload = json.loads((self.ROOT / "dispositions.json").read_text())
        decisions = {item["candidate"]: item["disposition"] for item in payload["decisions"]}
        self.assertEqual(
            decisions["coarse-fixed centre__inner Pearson level correlation"], "KEEP"
        )
        self.assertEqual(
            decisions["coarse-fixed inner__middle Pearson level correlation"], "KEEP"
        )
        self.assertEqual(
            decisions["coarse-fixed middle__outer Pearson level correlation"], "REVISE"
        )
        self.assertEqual(
            decisions["adjacent-change same-direction fraction"], "REJECT"
        )


if __name__ == "__main__":
    unittest.main()
