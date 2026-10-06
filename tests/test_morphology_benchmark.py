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
        brightness = np.ones((7, 7), float) * 10.0
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
            self.assertEqual(result["thresholds"], [1.20, 1.25, 1.30])
            self.assertEqual(result["baseline_threshold"], 1.25)
            self.assertEqual(result["connectivity"], 8)
            self.assertEqual(result["representation_policy"]["radial_partition_axis"], "omitted")
            for mode in ("fixed", "dynamic"):
                wrapper = result["supports"][mode]
                self.assertEqual(list(wrapper["thresholds"]), ["1.20", "1.25", "1.30"])
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
            frames = result["supports"]["fixed"]["thresholds"]["1.25"]["frames"]
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
                    processed, [0, 1, 2], thresholds=(1.10, 1.25, 1.40)
                )
            with self.assertRaises(ValueError):
                b.measure_stone(processed, [0, 1, 2], connectivity=4)


if __name__ == "__main__":
    unittest.main()
