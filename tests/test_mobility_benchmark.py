import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from diamond360 import activation_benchmark as ab
from diamond360 import mobility_benchmark as mb


def _summary(values):
    data = sorted(values)
    return {
        "status": "ok",
        "finite_frames": len(values),
        "q10": data[0],
        "q50": data[len(data) // 2],
        "q90": data[-1],
        "bright_excursion": data[-1] - data[len(data) // 2],
        "dark_excursion": data[len(data) // 2] - data[0],
        "total_excursion": data[-1] - data[0],
        "mad_scale": 0.0,
    }


def _cell(raw, relative, validity=None):
    validity = validity or {"status": "ok", "reasons": []}
    return {
        "support_mode": "fixed",
        "raw_values": raw,
        "relative_values": relative,
        "persistent_support_pixels": 10,
        "persistent_support_fraction": 1.0,
        "per_frame_support_fraction": [1.0] * len(raw),
        "raw_summary": _summary(raw),
        "relative_summary": _summary(relative),
        "raw_validity": validity,
        "relative_validity": validity,
    }


def activation_fixture(rgb_paths=None):
    indices = [254, 255, 0, 1]
    whole_values = [10.0, 11.0, 9.0, 10.0]
    coarse = {
        name: {
            "fixed": _cell(
                [4.0, 5.0, 3.0, 4.0],
                [0.0, 0.2, -0.1, 0.1],
            )
        }
        for name in ("centre", "inner", "middle", "outer")
    }
    semantic = {
        name: {
            "fixed": _cell(
                [4.0, 4.5, 3.5, 4.0],
                [0.0, 0.1, -0.1, 0.0],
                {"status": "review", "reasons": ["semantic_window_edge"]},
            )
        }
        for name in ("centre", "inner_step", "middle_step", "outer_step")
    }
    return {
        "schema_version": ab.SCHEMA,
        "requested_indices": indices,
        "accepted_indices": indices,
        "excluded": [],
        "wrap_explicit": True,
        "brightness_definition": "encoded",
        "upstream_validity": {"status": "ok", "reasons": []},
        "whole_stone": {
            "values": whole_values,
            "persistent_support_pixels": 20,
            "per_frame_support_fraction": [1.0] * 4,
            "summary": _summary(whole_values),
            "validity": {"status": "ok", "reasons": []},
        },
        "representations": {
            "coarse": {"source_indices": indices, "regions": coarse},
            "semantic": {"source_indices": indices, "regions": semantic},
        },
        "frame_rgb_paths": rgb_paths or [],
    }


class MobilityBenchmarkTests(unittest.TestCase):
    def test_consumes_retained_activation_contract(self):
        result = mb.measure_from_activation(activation_fixture())
        self.assertEqual(result["upstream_activation_schema"], ab.SCHEMA)
        self.assertIn(
            "whole_stone/whole_stone/fixed/raw",
            result["traces"],
        )
        self.assertTrue(
            result["traces"]["coarse/centre/fixed/relative"]["primary"]
        )
        self.assertTrue(
            result["traces"]["coarse/inner/fixed/relative"]["primary"]
        )
        self.assertTrue(
            result["traces"]["coarse/middle/fixed/relative"]["primary"]
        )
        self.assertFalse(
            result["traces"]["coarse/outer/fixed/relative"]["primary"]
        )
        self.assertEqual(
            result["traces"][
                "semantic/centre/fixed/relative"
            ]["upstream_activation"]["disposition"],
            "REVISE",
        )

    def test_does_not_derive_dynamic_support_variants(self):
        fixture = activation_fixture()
        fixture["representations"]["coarse"]["regions"]["centre"][
            "dynamic"
        ] = _cell([1, 2, 3, 4], [0.0, 0.3, 0.2, 0.4])
        result = mb.measure_from_activation(fixture)
        self.assertFalse(
            any("/dynamic/" in trace_id for trace_id in result["traces"])
        )

    def test_wrap_pair_is_observed(self):
        result = mb.measure_from_activation(activation_fixture())
        trace = result["traces"]["coarse/centre/fixed/relative"]
        wrap = [
            pair
            for pair in trace["pair_trace"]
            if pair["left_source_index"] == 255
        ][0]
        self.assertEqual(wrap["right_source_index"], 0)
        self.assertEqual(wrap["status"], "ok")

    def test_writer_is_json_safe_and_emits_pair_panels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = root / "processed"
            processed.mkdir()
            paths = []
            for i in range(4):
                name = f"frame-{i}.png"
                Image.new(
                    "RGB",
                    (12, 12),
                    (40 + i * 20, 50, 60),
                ).save(processed / name)
                paths.append(name)
            result = mb.measure_from_activation(activation_fixture(paths))
            out = root / "out"
            mb.write_stone_outputs(result, out, processed)
            payload = json.loads((out / "mobility.json").read_text())
            self.assertEqual(payload["schema_version"], mb.SCHEMA)
            with (out / "mobility.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 4)
            panel = (
                out
                / result["traces"][
                    "coarse/centre/fixed/relative"
                ]["evidence_panel"]
            )
            self.assertTrue(panel.exists())

    def test_rejects_other_activation_schema(self):
        fixture = activation_fixture()
        fixture["schema_version"] = "other/1"
        with self.assertRaises(ValueError):
            mb.measure_from_activation(fixture)


if __name__ == "__main__":
    unittest.main()
