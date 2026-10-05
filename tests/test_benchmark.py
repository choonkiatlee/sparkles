import csv
import json
import tempfile
import unittest
from pathlib import Path

from diamond360 import benchmark as b


REGION = {
    "common_support_fraction": 0.8,
    "mean_relative_dark_pixel_fraction": 0.12,
    "activation_amplitude_p90_p10": 0.05,
    "states": {
        "observed_frames": 5,
        "dark_occupancy": 0.4,
        "transitions": 2,
        "observed_adjacent_pairs": 4,
        "longest_dark_run_frames": 2,
        "longest_bright_run_frames": 2,
    },
    "pixel_states": {
        "fraction_with_transitions": 0.6,
        "transitions_median": 1.0,
        "transitions_p90": 3.0,
        "max_transitions": 4,
        "longest_dark_run_p90_frames": 2.0,
        "longest_dark_run_max_frames": 3,
        "longest_bright_run_p90_frames": 4.0,
    },
}


def trace(indices=(0, 1, 2, 3, 4)):
    return {
        "schema_version": "diamond360-region-traces/1",
        "requested_indices": list(indices),
        "accepted_indices": list(indices),
        "excluded": [],
        "regions": {name: dict(REGION) for name in b.REGIONS},
    }


class BenchmarkTests(unittest.TestCase):
    def test_cyclic_window_is_fixed_width_and_wraps(self):
        self.assertEqual(b.cyclic_window(0, 5, 8), [6, 7, 0, 1, 2])
        self.assertEqual(b.cyclic_window(7, 3, 8), [6, 7, 0])
        with self.assertRaises(ValueError):
            b.cyclic_window(0, 4, 8)

    def test_manifest_rejects_duplicate_certificates_and_partial_complete_claim(self):
        manifest = {
            "schema_version": "diamond360-benchmark/1",
            "core_window": 17,
            "wide_window": 33,
            "stones": [
                {"certificate": "A", "source_pipeline": "diajewel", "source_frame_count": 256,
                 "available_frame_count": 256, "source_status": "complete", "faceup_center": 0},
                {"certificate": "A", "source_pipeline": "workshop", "source_frame_count": 256,
                 "available_frame_count": 128, "source_status": "complete", "faceup_center": 0},
            ],
        }
        with self.assertRaises(ValueError):
            b.validate_manifest(manifest)

    def test_trace_summary_keeps_raw_and_normalized_temporal_metrics(self):
        rows = b.summarise_trace(trace(), "A", "diajewel", "core")
        centre = next(row for row in rows if row["region"] == "centre")
        self.assertEqual(centre["accepted_frames"], 5)
        self.assertEqual(centre["transition_count"], 2)
        self.assertEqual(centre["transition_rate"], 0.5)
        self.assertEqual(centre["longest_dark_run_fraction"], 0.4)
        self.assertEqual(centre["pixel_fraction_with_transitions"], 0.6)

    def test_sparse_trace_is_refused_for_temporal_summary(self):
        sparse = trace(indices=(0, 2, 4, 6, 8))
        with self.assertRaises(ValueError):
            b.summarise_trace(sparse, "A", "diajewel", "core")

    def test_collect_existing_writes_rows_and_unavailable_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "core.json").write_text(json.dumps(trace()))
            (root / "wide.json").write_text(json.dumps(trace()))
            manifest = {
                "schema_version": "diamond360-benchmark/1",
                "core_window": 5,
                "wide_window": 5,
                "stones": [
                    {"certificate": "A", "source_pipeline": "diajewel", "source_frame_count": 8,
                     "available_frame_count": 8, "source_status": "complete", "faceup_center": 2,
                     "trace_files": {"core": "core.json", "wide": "wide.json"}},
                    {"certificate": "B", "source_pipeline": "workshop", "source_frame_count": 8,
                     "available_frame_count": 8, "source_status": "complete", "faceup_center": 3},
                ],
            }
            mp = root / "benchmark.json"
            mp.write_text(json.dumps(manifest))
            result = b.collect_existing(mp)
            self.assertEqual(len(result["rows"]), 8)
            self.assertEqual(result["stones"][0]["status"], "measured")
            self.assertEqual(result["stones"][1]["status"], "source_available")

    def test_complete_source_requires_authoritative_source_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                b.source_contract(root, 256)
            (root / "source-manifest.json").write_text(json.dumps({
                "schema_version": "diamond360-source/1",
                "source_frame_count": 256,
                "sequence_complete": True,
                "frames": [],
            }))
            self.assertEqual(b.source_contract(root, 256), root / "source-manifest.json")
            with self.assertRaises(ValueError):
                b.source_contract(root, 128)

    def test_write_outputs_creates_machine_readable_summary_and_plots(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = {
                "schema_version": "diamond360-benchmark-summary/1",
                "stones": [{"certificate": "A", "status": "measured"}],
                "rows": b.summarise_trace(trace(), "A", "diajewel", "core")
                      + b.summarise_trace(trace(), "A", "diajewel", "wide"),
            }
            b.write_outputs(result, out)
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "summary.csv").exists())
            self.assertTrue((out / "metrics.png").exists())
            self.assertTrue((out / "sensitivity.png").exists())
            self.assertTrue((out / "redundancy.png").exists())
            with (out / "summary.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main()
