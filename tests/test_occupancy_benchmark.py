import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import occupancy_benchmark as b


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
        brightness[0, 0] = (7.0, 5.0, 3.0)[pos]
        brightness[0, 1] = (8.0, 7.0, 6.0)[pos]
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


class OccupancyBenchmarkTests(unittest.TestCase):
    def test_measure_stone_emits_two_by_two_and_exact_thresholds(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            result = b.measure_stone(processed, steps, [0, 1, 2])
            self.assertEqual(result["schema_version"], "diamond360-relative-dark-occupancy/1")
            self.assertEqual(result["thresholds"], [0.60, 0.65, 0.70])
            self.assertEqual(result["baseline_threshold"], 0.65)
            for representation, bands in (("coarse", ("centre", "inner", "middle", "outer")),
                                          ("semantic", ("centre", "inner_step", "middle_step", "outer_step"))):
                self.assertEqual(result["representations"][representation]["source_indices"], [0, 1, 2])
                for region in bands:
                    for mode in ("fixed", "dynamic"):
                        wrapper = result["representations"][representation]["regions"][region][mode]
                        self.assertEqual(list(wrapper["thresholds"]), ["0.60", "0.65", "0.70"])
                        for cell in wrapper["thresholds"].values():
                            self.assertEqual(len(cell["values"]), 3)
                            self.assertEqual(len(cell["dark_pixel_counts"]), 3)
                            self.assertEqual(len(cell["supported_pixel_counts"]), 3)
                            self.assertIn("validity", cell)

    def test_semantic_review_does_not_contaminate_coarse(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td), semantic_status="review")
            result = b.measure_stone(processed, steps, [0, 1, 2])
            coarse = result["representations"]["coarse"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
            semantic = result["representations"]["semantic"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
            self.assertEqual(coarse["validity"]["status"], "ok")
            self.assertEqual(semantic["validity"]["status"], "review")
            self.assertIn("synthetic_semantic_review", semantic["validity"]["reasons"])

    def test_writer_is_json_safe_and_creates_annotated_baseline_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed, steps = build_synthetic(root)
            result = b.measure_stone(processed, steps, [0, 1, 2])
            out = root / "out"
            b.write_stone_outputs(result, out, processed, steps)
            encoded = (out / "occupancy.json").read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)
            self.assertTrue((out / "occupancy.csv").exists())
            panels = list((out / "evidence").glob("*.png"))
            self.assertEqual(len(panels), 16)

    def test_noncanonical_thresholds_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            processed, steps = build_synthetic(Path(td))
            with self.assertRaises(ValueError):
                b.measure_stone(processed, steps, [0, 1, 2], thresholds=(0.55, 0.65, 0.75))


    def test_select_evidence_frames_breaks_moves_at_gaps(self):
        selected = b.select_evidence_frames([1.0, None, 3.0, 2.0, 5.0], [0, 1, 2, 3, 4])
        self.assertEqual(selected["q10"]["source_index"], 0)
        self.assertEqual(selected["q50"]["source_index"], 2)
        self.assertEqual(selected["q90"]["source_index"], 4)
        self.assertEqual(selected["largest_positive_move"]["source_index"], 4)
        self.assertAlmostEqual(selected["largest_positive_move"]["delta"], 3.0)
        self.assertEqual(selected["largest_negative_move"]["source_index"], 3)
        self.assertAlmostEqual(selected["largest_negative_move"]["delta"], -1.0)


class CommittedOccupancyArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "docs" / "360" / "occupancy"
    CORE = [248, 249, 250, 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5, 6, 7, 8]
    WIDE = list(range(240, 256)) + list(range(0, 17))
    STONES = (
        "IGI-LG756580087",
        "IGI-LG756520111",
        "IGI-LG818659722",
        "IGI-LG836619414",
    )

    def _occupancy(self, certificate, window):
        path = self.ROOT / "per-stone" / certificate / window / "occupancy.json"
        encoded = path.read_text()
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)
        return json.loads(encoded)

    def test_committed_windows_thresholds_and_ab_indices_are_exact(self):
        summary_text = (self.ROOT / "summary.json").read_text()
        self.assertNotIn("NaN", summary_text)
        self.assertNotIn("Infinity", summary_text)
        summary = json.loads(summary_text)
        self.assertEqual(summary["core_indices"], self.CORE)
        self.assertEqual(summary["wide_indices"], self.WIDE)
        self.assertEqual(summary["stones"], list(self.STONES))
        self.assertEqual(summary["thresholds"], [0.60, 0.65, 0.70])
        self.assertEqual(summary["baseline_threshold"], 0.65)
        self.assertEqual(len(summary["rows"]), 360)

        for certificate in self.STONES:
            for window, indices in (("core", self.CORE), ("wide", self.WIDE)):
                result = self._occupancy(certificate, window)
                self.assertEqual(result["requested_indices"], indices)
                self.assertEqual(result["accepted_indices"], indices)
                self.assertEqual(result["excluded"], [])
                self.assertEqual(result["thresholds"], [0.60, 0.65, 0.70])
                self.assertEqual(result["baseline_threshold"], 0.65)
                self.assertEqual(result["threshold_boundary"], "strict_less_than")
                self.assertEqual(result["representations"]["coarse"]["source_indices"], indices)
                self.assertEqual(result["representations"]["semantic"]["source_indices"], indices)

    def test_committed_traces_reconstruct_from_numerator_and_denominator(self):
        for certificate in self.STONES:
            for window in ("core", "wide"):
                result = self._occupancy(certificate, window)
                for representation in ("coarse", "semantic"):
                    for modes in result["representations"][representation].get("regions", {}).values():
                        self.assertEqual(set(modes), {"fixed", "dynamic"})
                        for wrapper in modes.values():
                            self.assertEqual(set(wrapper["thresholds"]), {"0.60", "0.65", "0.70"})
                            for cell in wrapper["thresholds"].values():
                                values = cell["values"]
                                dark = cell["dark_pixel_counts"]
                                support = cell["supported_pixel_counts"]
                                self.assertEqual(len(values), len(result["requested_indices"]))
                                self.assertEqual(len(dark), len(values))
                                self.assertEqual(len(support), len(values))
                                for value, numerator, denominator in zip(values, dark, support):
                                    if value is None:
                                        continue
                                    self.assertIsNotNone(numerator)
                                    self.assertIsNotNone(denominator)
                                    self.assertGreater(denominator, 0)
                                    self.assertAlmostEqual(value, numerator / denominator, places=12)

    def test_committed_validity_is_machine_readable_and_semantic_scoped(self):
        for certificate in self.STONES:
            for window in ("core", "wide"):
                result = self._occupancy(certificate, window)
                for representation in ("coarse", "semantic"):
                    rep = result["representations"][representation]
                    for modes in rep.get("regions", {}).values():
                        for wrapper in modes.values():
                            for cell in wrapper["thresholds"].values():
                                validity = cell["validity"]
                                self.assertIn(validity["status"], {"ok", "review", "unavailable"})
                                self.assertIsInstance(validity["reasons"], list)

        review = self._occupancy("IGI-LG818659722", "core")
        semantic = review["representations"]["semantic"]["regions"]["inner_step"]["fixed"]["thresholds"]["0.65"]
        coarse = review["representations"]["coarse"]["regions"]["inner"]["fixed"]["thresholds"]["0.65"]
        self.assertIn("semantic_window_edge", semantic["validity"]["reasons"])
        self.assertNotIn("semantic_window_edge", coarse["validity"]["reasons"])

        unavailable = self._occupancy("IGI-LG756580087", "wide")
        semantic_rep = unavailable["representations"]["semantic"]
        self.assertEqual(semantic_rep["validity"]["status"], "unavailable")
        self.assertIn("no_supported_middle_outer_edge", semantic_rep["validity"]["reasons"])
        self.assertEqual(semantic_rep["regions"], {})
        coarse_cell = unavailable["representations"]["coarse"]["regions"]["centre"]["fixed"]["thresholds"]["0.65"]
        self.assertEqual(coarse_cell["validity"]["status"], "ok")

    def test_committed_evidence_and_dispositions_cover_completion_gate(self):
        self.assertTrue((self.ROOT / "threshold-sensitivity.png").exists())
        self.assertGreater((self.ROOT / "threshold-sensitivity.png").stat().st_size, 1000)

        curated = {
            "per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed.png",
            "per-stone/IGI-LG836619414/wide/evidence/semantic-middle_step-fixed.png",
            "per-stone/IGI-LG836619414/wide/evidence/semantic-middle_step-dynamic.png",
            "per-stone/IGI-LG756580087/core/evidence/coarse-middle-dynamic.png",
            "per-stone/IGI-LG756580087/core/evidence/semantic-middle_step-dynamic.png",
        }
        for path in curated:
            self.assertTrue((self.ROOT / path).exists(), path)
        committed = {
            str(path.relative_to(self.ROOT))
            for path in (self.ROOT / "per-stone").glob("**/evidence/*.png")
        }
        self.assertEqual(committed, curated)

        payload = json.loads((self.ROOT / "dispositions.json").read_text())
        self.assertEqual(payload["redundancy_with_switching"], "pending_issue_28")
        self.assertIn("intentionally omitted from Git", payload["benchmark_evidence"]["note"])
        survivor = payload["surviving_state_definition"]
        self.assertEqual(survivor["representation"], "coarse")
        self.assertEqual(survivor["regions"], ["centre", "inner", "middle"])
        self.assertEqual(survivor["support_mode"], "fixed")
        self.assertEqual(survivor["primary_scalar"], "mean occupancy over the exact predeclared 17-frame core")

        decisions = payload["decisions"]
        self.assertEqual(len(decisions), 32)
        allowed = {"KEEP", "REVISE", "REJECT"}
        self.assertTrue(all(item["disposition"] in allowed and item["reason"] for item in decisions))
        keys = {
            (item["representation"], item["region"], item["support_mode"], item["summary_candidate"])
            for item in decisions
        }
        for representation in ("coarse", "semantic"):
            for region in ("centre", "inner", "middle", "outer"):
                for support_mode in ("fixed", "dynamic"):
                    for summary_candidate in ("mean", "median"):
                        self.assertIn(
                            (representation, region, support_mode, summary_candidate),
                            keys,
                        )


if __name__ == "__main__":
    unittest.main()
