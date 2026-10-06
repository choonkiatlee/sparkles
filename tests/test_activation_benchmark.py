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

    def test_measure_stone_preserves_upstream_segmentation_reason_codes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed, steps = build_synthetic(root)
            sequence_path = processed / "sequence.json"
            sequence = json.loads(sequence_path.read_text())
            sequence["frames"][1]["segmentation"] = {"status": "review", "reasons": ["border_outliers", "low_contrast"]}
            sequence_path.write_text(json.dumps(sequence))
            result = b.measure_stone(processed, steps, [0, 1, 2], wrap=False)
            self.assertEqual(result["upstream_validity"]["status"], "review")
            self.assertIn("border_outliers", result["upstream_validity"]["reasons"])
            self.assertIn("low_contrast", result["upstream_validity"]["reasons"])

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


class CommittedActivationArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "docs" / "360" / "activation"
    CORE = [248, 249, 250, 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5, 6, 7, 8]
    WIDE = list(range(240, 256)) + list(range(0, 17))
    STONES = (
        "IGI-LG756580087",
        "IGI-LG756520111",
        "IGI-LG818659722",
        "IGI-LG836619414",
    )
    REPRESENTATIVE_PANELS = {
        "per-stone/IGI-LG756520111/core/evidence/coarse-centre-fixed-relative.png",
        "per-stone/IGI-LG756520111/core/evidence/semantic-centre-fixed-relative.png",
        "per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed-relative.png",
        "per-stone/IGI-LG818659722/core/evidence/semantic-inner_step-fixed-relative.png",
        "per-stone/IGI-LG836619414/core/evidence/semantic-middle_step-fixed-relative.png",
        "per-stone/IGI-LG836619414/core/evidence/semantic-middle_step-dynamic-relative.png",
        "per-stone/IGI-LG756580087/core/evidence/semantic-outer_step-fixed-relative.png",
        "per-stone/IGI-LG756580087/core/evidence/semantic-outer_step-dynamic-relative.png",
    }

    def test_committed_summary_pins_benchmark_scope(self):
        summary = json.loads((self.ROOT / "summary.json").read_text())
        self.assertEqual(summary["core_indices"], self.CORE)
        self.assertEqual(summary["wide_indices"], self.WIDE)
        self.assertEqual(summary["stones"], list(self.STONES))

    def test_committed_artifacts_are_curated(self):
        per_stone = self.ROOT / "per-stone"
        self.assertEqual(list(per_stone.rglob("activation.json")), [])
        self.assertEqual(list(per_stone.rglob("activation.csv")), [])
        panels = {
            path.relative_to(self.ROOT).as_posix()
            for path in per_stone.rglob("*.png")
        }
        self.assertEqual(panels, self.REPRESENTATIVE_PANELS)

    def test_committed_dispositions_cover_candidate_axes(self):
        payload = json.loads((self.ROOT / "dispositions.json").read_text())
        decisions = payload["decisions"]
        allowed = {"KEEP", "REVISE", "REJECT"}
        self.assertTrue(decisions)
        self.assertTrue(all(item["disposition"] in allowed and item["reason"] for item in decisions))

        keys = {
            (item["representation"], item["region"], item["support_mode"], item["trace_type"])
            for item in decisions
        }
        self.assertIn(("whole_stone", "whole_stone", "fixed", "raw"), keys)
        for representation, regions in (
            ("coarse", ("centre", "inner", "middle", "outer")),
            ("semantic", ("centre", "inner", "middle", "outer")),
        ):
            for region in regions:
                for support_mode in ("fixed", "dynamic"):
                    for trace_type in ("raw", "relative"):
                        self.assertIn((representation, region, support_mode, trace_type), keys)

        summaries = {item["candidate"]: item["disposition"] for item in payload["summary_candidates"]}
        self.assertEqual(summaries["Q10/Q50/Q90 directional excursions"], "KEEP")
        self.assertEqual(summaries["MAD_scale"], "REJECT")


if __name__ == "__main__":
    unittest.main()
