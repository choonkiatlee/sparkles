import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import switching_benchmark as b


def build_synthetic(root: Path, semantic_status="ok"):
    processed = root / "processed"
    steps = root / "steps"
    for name in ("photometry", "regions", "diamond"):
        (processed / name).mkdir(parents=True, exist_ok=True)
    (steps / "regions").mkdir(parents=True)

    records = []
    semantic_frames = []
    for pos in range(3):
        brightness = np.ones((4, 4), float) * 10.0
        brightness[0, 0] = (5.0, 8.0, 5.0)[pos]
        brightness[0, 1] = (8.0, 5.0, 8.0)[pos]
        valid = np.ones((4, 4), bool)
        stone = np.ones((4, 4), bool)
        centre = np.zeros((4, 4), bool); centre[0, :2] = True
        inner = np.zeros((4, 4), bool); inner[0, 2:] = True
        middle = np.zeros((4, 4), bool); middle[1:3, :] = True
        outer = stone & ~(centre | inner | middle)
        np.savez_compressed(processed / "photometry" / f"{pos:04d}.npz",
                            encoded_brightness=brightness.astype(np.float32), valid_mask=valid)
        np.savez_compressed(processed / "regions" / f"{pos:04d}.npz",
                            centre=centre, inner=inner, middle=middle, outer=outer)
        np.savez_compressed(steps / "regions" / f"{pos:04d}.npz",
                            centre=centre, inner_step=inner, middle_step=middle, outer_step=outer)
        Image.fromarray(stone.astype(np.uint8) * 255).save(processed / "diamond" / f"{pos:04d}-mask.png")
        rgb = np.repeat(np.clip(brightness[..., None] * 20, 0, 255).astype(np.uint8), 3, axis=2)
        Image.fromarray(rgb).save(processed / "diamond" / f"{pos:04d}.png")
        records.append({
            "position": pos, "source_index": pos, "sha256": f"{pos+1:064x}",
            "photometry_path": f"photometry/{pos:04d}.npz",
            "regions_path": f"regions/{pos:04d}.npz",
            "segmentation": {"status": "ok", "reasons": []},
            "registration": {"mask_path": f"diamond/{pos:04d}-mask.png", "rgb_path": f"diamond/{pos:04d}.png"},
        })
        semantic_frames.append({
            "source_index": pos, "position": pos, "status": semantic_status,
            "region_path": f"regions/{pos:04d}.npz", "boundary_support": [],
        })
    (processed / "sequence.json").write_text(json.dumps({
        "source_frame_count": 3,
        "brightness_definition": "synthetic encoded brightness",
        "frames": records,
    }))
    (steps / "steps.json").write_text(json.dumps({
        "template_status": semantic_status,
        "template_reason": "synthetic_semantic_review" if semantic_status == "review" else None,
        "frames": semantic_frames,
    }))
    return processed, steps


class SwitchingBenchmarkTests(unittest.TestCase):
    def test_measure_stone_emits_two_by_two_and_exact_thresholds(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            result = b.measure_stone(processed, steps, [0, 1, 2])
            self.assertEqual(result["schema_version"], "diamond360-bright-dark-switching/1")
            self.assertEqual(result["thresholds"], [0.60, 0.65, 0.70])
            self.assertEqual(result["baseline_threshold"], 0.65)
            for representation, bands in (("coarse", ("centre", "inner", "middle", "outer")),
                                          ("semantic", ("centre", "inner_step", "middle_step", "outer_step"))):
                self.assertEqual(result["representations"][representation]["source_indices"], [0, 1, 2])
                for region in bands:
                    for mode in ("fixed", "pair_local"):
                        wrapper = result["representations"][representation]["regions"][region][mode]
                        self.assertEqual(list(wrapper["thresholds"]), ["0.60", "0.65", "0.70"])
                        for cell in wrapper["thresholds"].values():
                            self.assertEqual(len(cell["pair_trace"]), 2)
                            self.assertIn("validity", cell)
                            self.assertEqual(cell["pair_trace"][0]["left_source_index"], 0)
                            self.assertEqual(cell["pair_trace"][0]["right_source_index"], 1)

    def test_primary_scalar_reconstructs_from_pair_counts(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            result = b.measure_stone(processed, steps, [0, 1, 2])
            cell = result["representations"]["coarse"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
            self.assertEqual(cell["switched_pixel_pairs"], 4)
            self.assertEqual(cell["eligible_pixel_pairs"], 4)
            self.assertEqual(cell["regional_switch_rate"], 1.0)
            self.assertEqual(cell["per_pixel_rate"]["q50"], 1.0)

    def test_semantic_review_does_not_contaminate_coarse(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td), semantic_status="review")
            result = b.measure_stone(processed, steps, [0, 1, 2])
            coarse = result["representations"]["coarse"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
            semantic = result["representations"]["semantic"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
            self.assertEqual(coarse["validity"]["status"], "ok")
            self.assertEqual(semantic["validity"]["status"], "review")
            self.assertIn("synthetic_semantic_review", semantic["validity"]["reasons"])

    def test_writer_is_json_safe_and_creates_pair_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed, steps = build_synthetic(root)
            result = b.measure_stone(processed, steps, [0, 1, 2])
            out = root / "out"
            b.write_stone_outputs(result, out, processed, steps)
            encoded = (out / "switching.json").read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)
            self.assertTrue((out / "switching.csv").exists())
            panels = list((out / "evidence").glob("*.png"))
            self.assertEqual(len(panels), 16)

    def test_noncanonical_thresholds_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            with self.assertRaises(ValueError):
                b.measure_stone(processed, steps, [0, 1, 2], thresholds=(0.55, 0.65, 0.75))


if __name__ == "__main__":
    unittest.main()
