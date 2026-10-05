import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import activation_benchmark as b


def build_synthetic(root: Path):
    processed = root / "processed"
    steps = root / "steps"
    for name in ("photometry", "regions", "diamond"):
        (processed / name).mkdir(parents=True, exist_ok=True)
    (steps / "regions").mkdir(parents=True)

    records = []
    semantic_frames = []
    for pos in range(3):
        brightness = np.ones((4, 4), float) * (10 + pos)
        brightness[0, 0] = 2 ** pos
        valid = np.ones((4, 4), bool)
        stone = np.ones((4, 4), bool)
        centre = np.zeros((4, 4), bool); centre[0, 0] = True
        inner = np.zeros((4, 4), bool); inner[0, 1:3] = True
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
            "source_index": pos, "position": pos, "status": "ok",
            "region_path": f"regions/{pos:04d}.npz", "boundary_support": [],
        })
    (processed / "sequence.json").write_text(json.dumps({
        "source_frame_count": 3,
        "brightness_definition": "synthetic encoded brightness",
        "frames": records,
    }))
    (steps / "steps.json").write_text(json.dumps({
        "template_status": "ok", "template_reason": None, "frames": semantic_frames,
    }))
    return processed, steps


class ActivationBenchmarkTests(unittest.TestCase):
    def test_measure_stone_emits_full_two_by_two_on_same_indices(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            result = b.measure_stone(processed, steps, [0, 1, 2], wrap=False)
            self.assertEqual(result["schema_version"], "diamond360-activation/1")
            self.assertEqual(result["requested_indices"], [0, 1, 2])
            self.assertEqual(result["accepted_indices"], [0, 1, 2])
            for representation, bands in (("coarse", ("centre", "inner", "middle", "outer")),
                                          ("semantic", ("centre", "inner_step", "middle_step", "outer_step"))):
                self.assertEqual(result["representations"][representation]["source_indices"], [0, 1, 2])
                for region in bands:
                    self.assertEqual(set(result["representations"][representation]["regions"][region]), {"fixed", "dynamic"})
                    for mode in ("fixed", "dynamic"):
                        cell = result["representations"][representation]["regions"][region][mode]
                        self.assertEqual(len(cell["raw_values"]), 3)
                        self.assertEqual(len(cell["relative_values"]), 3)
                        self.assertIn("raw_validity", cell)
                        self.assertIn("relative_validity", cell)

    def test_select_evidence_frames_breaks_moves_at_gaps(self):
        selected = b.select_evidence_frames([1.0, None, 3.0, 2.0, 5.0], [0, 1, 2, 3, 4])
        self.assertEqual(selected["q10"]["source_index"], 0)
        self.assertEqual(selected["q50"]["source_index"], 2)
        self.assertEqual(selected["q90"]["source_index"], 4)
        self.assertEqual(selected["largest_positive_move"]["source_index"], 4)
        self.assertAlmostEqual(selected["largest_positive_move"]["delta"], 3.0)
        self.assertEqual(selected["largest_negative_move"]["source_index"], 3)
        self.assertAlmostEqual(selected["largest_negative_move"]["delta"], -1.0)

    def test_select_evidence_frames_ties_are_deterministic(self):
        selected = b.select_evidence_frames([1.0, 3.0, 2.0, 4.0], [10, 11, 12, 13])
        self.assertEqual(selected["q50"]["source_index"], 11)

    def test_write_stone_outputs_is_json_safe_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed, steps = build_synthetic(root)
            result = b.measure_stone(processed, steps, [0, 1, 2], wrap=False)
            out = root / "out"
            b.write_stone_outputs(result, out, processed)
            payload = json.loads((out / "activation.json").read_text())
            self.assertEqual(payload["schema_version"], "diamond360-activation/1")
            self.assertTrue((out / "activation.csv").exists())
            panels = list((out / "evidence").glob("*.png"))
            self.assertGreater(len(panels), 0)
            encoded = (out / "activation.json").read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)

    def test_committed_activation_benchmark_contract(self):
        root = Path("docs/360/activation")
        summary = json.loads((root / "summary.json").read_text())
        self.assertEqual(summary["schema_version"], "diamond360-activation-benchmark/1")
        self.assertEqual(summary["core_indices"], [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8])
        self.assertEqual(len(summary["stones"]), 4)
        for stone in summary["stones"]:
            cert = stone["certificate"]
            for window in ("core", "wide"):
                path = root / "per-stone" / cert / window / "activation.json"
                payload = json.loads(path.read_text())
                self.assertEqual(payload["schema_version"], "diamond360-activation/1")
                self.assertEqual(payload["representations"]["coarse"]["source_indices"], payload["requested_indices"])
                self.assertEqual(payload["representations"]["semantic"]["source_indices"], payload["requested_indices"])
                self.assertNotIn("NaN", path.read_text())
                self.assertNotIn("Infinity", path.read_text())
                for rep in payload["representations"].values():
                    for modes in rep.get("regions", {}).values():
                        for cell in modes.values():
                            self.assertIn("reasons", cell["raw_validity"])
                            self.assertIn("reasons", cell["relative_validity"])


if __name__ == "__main__":
    unittest.main()
