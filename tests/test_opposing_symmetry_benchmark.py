import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import opposing_symmetry_benchmark as b
from diamond360 import regions


ROOT = Path(__file__).resolve().parents[1]
INDICES = [254, 255, 0, 1]


def build_synthetic(
    root: Path,
    scales=(1.0, 1.0, 1.0, 1.0),
    semantic_status="ok",
):
    processed = root / "processed"
    steps = root / "steps"
    for name in ("photometry", "regions", "diamond"):
        (processed / name).mkdir(parents=True, exist_ok=True)
    (steps / "regions").mkdir(parents=True, exist_ok=True)

    mask = np.ones((32, 32), bool)
    coarse = regions.build(mask, target_extent=24)
    traces = {
        "side_E": [0.00, 0.16, 0.30, 0.18],
        "side_W": [0.00, 0.14, 0.27, 0.16],
        "side_N": [0.00, 0.10, -0.08, 0.08],
        "side_S": [0.00, -0.08, 0.10, -0.06],
        "corner_NE": [0.00, 0.12, 0.20, 0.05],
        "corner_SW": [0.00, 0.11, 0.18, 0.04],
        "corner_NW": [0.00, 0.03, -0.05, 0.07],
        "corner_SE": [0.00, -0.02, 0.08, -0.03],
    }
    records = []
    step_frames = []
    for position, (source_index, scale) in enumerate(
        zip(INDICES, scales)
    ):
        brightness = np.ones(mask.shape, float) * 10.0
        for name, values in traces.items():
            brightness[coarse[name]] *= np.exp(
                values[position]
            )
        brightness *= float(scale)
        valid = np.ones(mask.shape, bool)
        np.savez_compressed(
            processed / "photometry" / f"{position:04d}.npz",
            encoded_brightness=brightness,
            valid_mask=valid,
        )
        Image.fromarray(
            mask.astype(np.uint8) * 255
        ).save(
            processed
            / "diamond"
            / f"{position:04d}-mask.png"
        )
        Image.new(
            "RGB",
            mask.shape[::-1],
            (100 + position * 15, 100, 100),
        ).save(
            processed
            / "diamond"
            / f"{position:04d}.png"
        )
        np.savez_compressed(
            processed / "regions" / f"{position:04d}.npz",
            **coarse,
        )
        semantic = {
            "centre": coarse["centre"],
            "inner_step": coarse["inner"],
            "middle_step": coarse["middle"],
            "outer_step": coarse["outer"],
        }
        np.savez_compressed(
            steps / "regions" / f"{position:04d}.npz",
            **semantic,
        )
        records.append({
            "position": position,
            "source_index": source_index,
            "sha256": f"{position + 1:064x}",
            "pixel_sha256": f"{position + 101:064x}",
            "segmentation": {
                "status": "ok",
                "reasons": [],
            },
            "registration": {
                "mask_path":
                    f"diamond/{position:04d}-mask.png",
                "rgb_path":
                    f"diamond/{position:04d}.png",
            },
            "photometry_path":
                f"photometry/{position:04d}.npz",
            "regions_path":
                f"regions/{position:04d}.npz",
        })
        step_frames.append({
            "source_index": source_index,
            "status": "ok",
            "region_path":
                f"regions/{position:04d}.npz",
            "boundary_support": [],
        })

    (processed / "sequence.json").write_text(
        json.dumps({
            "source_frame_count": 256,
            "brightness_definition":
                "synthetic encoded brightness",
            "frames": records,
        })
    )
    (steps / "steps.json").write_text(
        json.dumps({
            "template_status": semantic_status,
            "template_reason":
                "semantic_window_edge"
                if semantic_status == "review"
                else None,
            "boundaries": {},
            "frames": step_frames,
        })
    )
    return processed, steps


class OpposingSymmetryBenchmarkTests(unittest.TestCase):
    def test_emits_declared_pairs_and_localisation_surfaces(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            result = b.measure_stone(
                processed, steps, INDICES, wrap=True
            )
            self.assertEqual(
                result["schema_version"], b.SCHEMA
            )
            self.assertEqual(
                set(result["surfaces"]),
                {
                    "coarse_whole",
                    "coarse_inner",
                    "coarse_middle",
                    "semantic_inner_step",
                    "semantic_middle_step",
                },
            )
            pairs = (
                result["surfaces"]["coarse_whole"]
                ["support_modes"]["fixed"]["pairs"]
            )
            self.assertEqual(
                set(pairs),
                {
                    "side_E_W",
                    "side_N_S",
                    "corner_NE_SW",
                    "corner_NW_SE",
                },
            )
            self.assertEqual(
                pairs["side_E_W"]["validity"]["status"],
                "ok",
            )
            self.assertGreater(
                pairs["side_E_W"]["metrics"][
                    "correlation"
                ]["value"],
                0.9,
            )
            self.assertLess(
                pairs["side_N_S"]["metrics"][
                    "sign_agreement"
                ]["value"],
                0.5,
            )

    def test_global_frame_scaling_does_not_change_metrics(self):
        with (
            tempfile.TemporaryDirectory() as td1,
            tempfile.TemporaryDirectory() as td2,
        ):
            p1, s1 = build_synthetic(Path(td1))
            p2, s2 = build_synthetic(
                Path(td2),
                scales=(0.6, 1.8, 0.9, 1.4),
            )
            one = b.measure_stone(
                p1, s1, INDICES, wrap=True
            )
            two = b.measure_stone(
                p2, s2, INDICES, wrap=True
            )
            for pair_id in (
                "side_E_W",
                "side_N_S",
                "corner_NE_SW",
                "corner_NW_SE",
            ):
                left = (
                    one["surfaces"]["coarse_whole"]
                    ["support_modes"]["fixed"]["pairs"]
                    [pair_id]
                )
                right = (
                    two["surfaces"]["coarse_whole"]
                    ["support_modes"]["fixed"]["pairs"]
                    [pair_id]
                )
                for metric in (
                    "correlation",
                    "median_absolute_difference",
                    "sign_agreement",
                ):
                    self.assertAlmostEqual(
                        left["metrics"][metric]["value"],
                        right["metrics"][metric]["value"],
                    )

    def test_semantic_review_does_not_contaminate_coarse(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(
                Path(td),
                semantic_status="review",
            )
            result = b.measure_stone(
                processed, steps, INDICES, wrap=True
            )
            coarse = (
                result["surfaces"]["coarse_inner"]
                ["support_modes"]["fixed"]["pairs"]
                ["side_E_W"]
            )
            semantic = (
                result["surfaces"]["semantic_inner_step"]
                ["support_modes"]["fixed"]["pairs"]
                ["side_E_W"]
            )
            self.assertEqual(
                coarse["validity"]["status"], "ok"
            )
            self.assertEqual(
                semantic["validity"]["status"], "review"
            )
            self.assertIn(
                "semantic_window_edge",
                semantic["validity"]["reasons"],
            )

    def test_writer_is_json_safe_and_emits_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed, steps = build_synthetic(root)
            result = b.measure_stone(
                processed, steps, INDICES, wrap=True
            )
            out = root / "out"
            b.write_stone_outputs(
                result,
                out,
                processed,
                steps,
            )
            payload = json.loads(
                (out / "opposing-symmetry.json").read_text()
            )
            self.assertEqual(
                payload["schema_version"], b.SCHEMA
            )
            with (
                out / "opposing-symmetry.csv"
            ).open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 5 * 2 * 4)
            panel = (
                out
                / result["surfaces"]["coarse_whole"]
                ["support_modes"]["fixed"]["pairs"]
                ["side_E_W"]["evidence_panel"]
            )
            self.assertTrue(panel.exists())
            self.assertGreater(panel.stat().st_size, 0)


class CommittedOpposingSymmetryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "docs" / "360" / "opposing-symmetry"
        self.summary = json.loads(
            (self.root / "summary.json").read_text()
        )
        self.dispositions = json.loads(
            (self.root / "dispositions.json").read_text()
        )

    def test_committed_benchmark_covers_completion_gate(self):
        self.assertEqual(
            self.summary["schema_version"],
            "diamond360-opposing-region-symmetry-benchmark/1",
        )
        self.assertEqual(len(self.summary["rows"]), 304)
        self.assertEqual(len(self.summary["run_status"]), 8)

        baseline = [
            row for row in self.summary["rows"]
            if row["window"] == "core"
            and row["surface_id"] == "coarse_whole"
            and row["support_mode"] == "fixed"
        ]
        self.assertEqual(len(baseline), 16)
        self.assertEqual(
            {row["pair_id"] for row in baseline},
            {
                "side_E_W",
                "side_N_S",
                "corner_NE_SW",
                "corner_NW_SE",
            },
        )
        self.assertTrue(
            all(row["paired_frames"] == 17 for row in baseline)
        )

        north_south = {
            row["certificate"]: row["correlation"]
            for row in baseline
            if row["pair_id"] == "side_N_S"
        }
        self.assertGreater(
            north_south["IGI-LG818659722"], 0.9
        )
        self.assertLess(
            north_south["IGI-LG756520111"], -0.9
        )

        run_status = {
            (item["certificate"], item["window"]): item
            for item in self.summary["run_status"]
        }
        unavailable = run_status[
            ("IGI-LG756580087", "wide")
        ]
        self.assertEqual(
            unavailable["semantic_qc"]["template_status"],
            "unavailable",
        )
        self.assertEqual(
            unavailable["semantic_qc"]["template_reason"],
            "no_supported_middle_outer_edge",
        )
        self.assertEqual(
            set(unavailable["surface_ids"]),
            {"coarse_whole", "coarse_inner", "coarse_middle"},
        )

        decisions = {
            item["candidate"]: item["disposition"]
            for item in self.dispositions["summary_families"]
        }
        self.assertEqual(
            decisions["pair_trace_correlation"], "KEEP"
        )
        self.assertEqual(
            decisions["median_absolute_pair_difference"], "REVISE"
        )
        self.assertEqual(
            decisions["adjacent_sign_agreement"], "REJECT"
        )
        self.assertEqual(
            {item["disposition"]
             for item in self.dispositions["pair_correlation"]},
            {"KEEP"},
        )

    def test_committed_evidence_inventory_resolves_to_small_real_files(self):
        evidence = json.loads(
            (self.root / "evidence.json").read_text()
        )
        self.assertGreaterEqual(len(evidence), 4)
        self.assertLessEqual(len(evidence), 7)
        labels = {item["label"] for item in evidence}
        self.assertIn("highest_core_correlation", labels)
        self.assertIn("lowest_core_correlation", labels)
        for item in evidence:
            path = self.root / item["committed_path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.suffix.lower(), ".png")
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
