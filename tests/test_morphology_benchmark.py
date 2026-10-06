import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import morphology_benchmark as b


def build_synthetic(root: Path):
    processed = root / "processed"
    for name in ("photometry", "diamond"):
        (processed / name).mkdir(parents=True, exist_ok=True)

    records = []
    for pos in range(3):
        y, x = np.indices((7, 7))
        brightness = 10.0 + ((x + y) % 3 - 1).astype(float)
        if pos == 0:
            brightness[2:5, 2:5] = 14.0
        elif pos == 1:
            brightness[1, 1:4] = 14.0
            brightness[3, 1:4] = 14.0
            brightness[5, 1:4] = 14.0
        else:
            brightness[2:5, 2:5] = 12.7
            brightness[3, 3] = 14.0

        valid = np.ones((7, 7), bool)
        stone = np.ones((7, 7), bool)
        if pos == 2:
            stone[-1, -1] = False

        np.savez_compressed(
            processed / "photometry" / f"{pos:04d}.npz",
            encoded_brightness=brightness.astype(np.float32),
            valid_mask=valid,
        )
        Image.fromarray(stone.astype(np.uint8) * 255).save(
            processed / "diamond" / f"{pos:04d}-mask.png"
        )
        rgb = np.repeat(
            np.clip(brightness[..., None] * 18, 0, 255).astype(np.uint8),
            3,
            axis=2,
        )
        Image.fromarray(rgb).save(processed / "diamond" / f"{pos:04d}.png")
        records.append({
            "position": pos,
            "source_index": pos,
            "sha256": f"{pos + 1:064x}",
            "photometry_path": f"photometry/{pos:04d}.npz",
            "segmentation": {"status": "ok", "reasons": []},
            "registration": {
                "mask_path": f"diamond/{pos:04d}-mask.png",
                "rgb_path": f"diamond/{pos:04d}.png",
            },
        })

    (processed / "sequence.json").write_text(json.dumps({
        "source_frame_count": 3,
        "brightness_definition": "synthetic encoded brightness",
        "frames": records,
    }))
    return processed


class MorphologyBenchmarkTests(unittest.TestCase):
    def test_measure_stone_emits_fixed_threshold_sweep_and_support_axis(self):
        with tempfile.TemporaryDirectory() as td:
            processed = build_synthetic(Path(td))
            result = b.measure_stone(processed, [0, 1, 2])
            self.assertEqual(result["schema_version"], b.SCHEMA)
            self.assertEqual(result["thresholds"], [0.90, 1.00, 1.10])
            self.assertEqual(result["baseline_threshold"], 1.00)
            self.assertEqual(result["connectivity"], 8)
            self.assertEqual(result["representation_policy"]["radial_partition_axis"], "omitted")
            for mode in ("fixed", "dynamic"):
                wrapper = result["supports"][mode]
                self.assertEqual(list(wrapper["thresholds"]), ["0.90", "1.00", "1.10"])
                for cell in wrapper["thresholds"].values():
                    self.assertEqual(len(cell["frames"]), 3)
                    self.assertIn("validity", cell)
                    self.assertEqual(
                        [frame["source_index"] for frame in cell["frames"]],
                        [0, 1, 2],
                    )

    def test_same_area_frames_are_separated_by_morphology(self):
        with tempfile.TemporaryDirectory() as td:
            processed = build_synthetic(Path(td))
            result = b.measure_stone(processed, [0, 1, 2])
            frames = result["supports"]["fixed"]["thresholds"]["1.00"]["frames"]
            self.assertEqual(frames[0]["active_pixels"], frames[1]["active_pixels"])
            self.assertEqual(frames[0]["largest_component_fraction"], 1.0)
            self.assertAlmostEqual(frames[1]["largest_component_fraction"], 1 / 3)
            pair = result["supports"]["fixed"]["baseline_evidence"]["matched_active_area_pair"]
            self.assertEqual({pair["left"]["source_index"], pair["right"]["source_index"]}, {0, 1})

    def test_support_sensitivity_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            processed = build_synthetic(Path(td))
            result = b.measure_stone(processed, [0, 1, 2])
            disagreement = result["support_disagreement"]
            self.assertIn("strongest", disagreement)
            self.assertIn("control", disagreement)

    def test_writer_is_json_safe_and_creates_one_compact_panel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = build_synthetic(root)
            result = b.measure_stone(processed, [0, 1, 2])
            out = root / "out"
            b.write_stone_outputs(result, out, processed)
            encoded = (out / "morphology.json").read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)
            self.assertTrue((out / "morphology.csv").exists())
            panel = out / "evidence" / "diagnostic.png"
            self.assertTrue(panel.exists())
            self.assertGreater(panel.stat().st_size, 500)

    def test_noncanonical_thresholds_and_connectivity_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            processed = build_synthetic(Path(td))
            with self.assertRaises(ValueError):
                b.measure_stone(
                    processed, [0, 1, 2], thresholds=(0.80, 1.00, 1.20)
                )
            with self.assertRaises(ValueError):
                b.measure_stone(processed, [0, 1, 2], connectivity=4)


class CommittedMorphologyArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "docs" / "360" / "morphology"
    CORE = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
    WIDE = list(range(240,256)) + list(range(0,17))

    def test_summary_pins_final_protocol_and_four_stones(self):
        summary = json.loads((self.ROOT / "summary.json").read_text())
        self.assertEqual(summary["core_indices"], self.CORE)
        self.assertEqual(summary["wide_indices"], self.WIDE)
        self.assertEqual(summary["thresholds"], [0.9, 1.0, 1.1])
        self.assertEqual(summary["baseline_threshold"], 1.0)
        self.assertEqual(summary["connectivity"], 8)
        self.assertEqual(len(summary["stones"]), 4)
        analysis = summary["analysis"]["median_largest_component_fraction"]
        self.assertAlmostEqual(analysis["core_to_wide_spearman"], 1.0)
        self.assertAlmostEqual(analysis["threshold_rank_spearman_0.90_vs_1.00"], 1.0)
        self.assertAlmostEqual(analysis["threshold_rank_spearman_1.10_vs_1.00"], 1.0)
        self.assertAlmostEqual(analysis["fixed_vs_dynamic_core_spearman"], 1.0)

    def test_dispositions_keep_one_primary_morphology_scalar(self):
        payload = json.loads((self.ROOT / "dispositions.json").read_text())
        decisions = {item["candidate"]: item["disposition"] for item in payload["decisions"]}
        self.assertEqual(decisions["robust bright active field G_t + k*S_t"], "KEEP")
        self.assertEqual(decisions["fixed-support median largest-component fraction"], "KEEP")
        self.assertEqual(decisions["effective component count"], "REJECT")
        self.assertEqual(decisions["raw component count"], "REJECT")
        self.assertEqual(decisions["spatial entropy"], "REJECT")

    def test_compact_evidence_is_one_panel_per_stone(self):
        panels = sorted(path.name for path in (self.ROOT / "evidence").glob("*.png"))
        self.assertEqual(
            panels,
            [
                "IGI-LG756520111-core.png",
                "IGI-LG756580087-core.png",
                "IGI-LG818659722-core.png",
                "IGI-LG836619414-core.png",
            ],
        )
        self.assertTrue(all((self.ROOT / "evidence" / name).stat().st_size > 1000 for name in panels))


if __name__ == "__main__":
    unittest.main()
