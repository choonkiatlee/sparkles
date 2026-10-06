import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import crispness_benchmark as b


def build_synthetic(root: Path, frame_count=8):
    processed = root / "processed"
    for folder in ("photometry", "diamond", "camera"):
        (processed / folder).mkdir(parents=True, exist_ok=True)

    size = 128
    y, x = np.indices((size, size))
    cy = cx = (size - 1) / 2
    radius = 52.0
    rr = np.hypot(x - cx, y - cy)
    mask = rr <= radius
    uu = rr / radius
    records = []

    for pos in range(frame_count):
        scale = 1.0 + .03 * np.sin(pos)
        brightness = scale * np.where(
            uu < .50,
            1.00,
            np.where(
                uu < .73,
                .62,
                np.where(uu < .87, 1.18, .76),
            ),
        )
        brightness += .005 * np.sin(x * .17 + pos)
        valid = mask.copy()
        np.savez_compressed(
            processed / "photometry" / f"{pos:04d}.npz",
            encoded_brightness=brightness.astype(np.float32),
            valid_mask=valid,
        )

        rgb = np.repeat(
            np.clip(
                brightness[..., None] / 1.25 * 255,
                0,
                255,
            ).astype(np.uint8),
            3,
            axis=2,
        )
        rgb[~mask] = 245
        Image.fromarray(rgb).save(
            processed / "diamond" / f"{pos:04d}.png"
        )
        Image.fromarray(rgb).save(
            processed / "camera" / f"{pos:04d}.png"
        )
        Image.fromarray(
            mask.astype(np.uint8) * 255
        ).save(
            processed / "diamond" / f"{pos:04d}-mask.png"
        )

        records.append(
            {
                "position": pos,
                "source_index": pos,
                "sha256": f"{pos + 1:064x}",
                "photometry_path": (
                    f"photometry/{pos:04d}.npz"
                ),
                "camera_original_path": (
                    f"camera/{pos:04d}.png"
                ),
                "segmentation": {
                    "status": "ok",
                    "reasons": [],
                },
                "registration": {
                    "mask_path": (
                        f"diamond/{pos:04d}-mask.png"
                    ),
                    "rgb_path": f"diamond/{pos:04d}.png",
                },
            }
        )

    (processed / "sequence.json").write_text(
        json.dumps(
            {
                "source_frame_count": frame_count,
                "frames": records,
            }
        )
    )
    return processed


class CrispnessBenchmarkTests(unittest.TestCase):
    def test_measure_stone_crossfits_and_stress_tests_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            processed = build_synthetic(Path(td))
            result = b.measure_stone(
                processed,
                list(range(8)),
                wrap=False,
            )
            self.assertEqual(
                result["schema_version"],
                b.SCHEMA,
            )
            self.assertEqual(
                result["accepted_indices"],
                list(range(8)),
            )
            self.assertEqual(
                set(result["baseline"]["summary"]),
                set(b.c.BOUNDARIES),
            )
            self.assertEqual(
                set(result["pipeline_sensitivity"]),
                set(b.c.PERTURBATIONS),
            )
            for cell in result["baseline"]["summary"].values():
                self.assertEqual(cell["validity"]["status"], "ok")
                self.assertEqual(cell["requested_frame_count"], 8)
                self.assertEqual(cell["scored_frame_count"], 8)
            self.assertEqual(
                len(result["crossfit_templates"]),
                2,
            )
            self.assertIn(
                "edge_alignment",
                result["full_template_diagnostic"],
            )

    def test_write_outputs_is_json_safe_and_renders_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = build_synthetic(root)
            result = b.measure_stone(
                processed,
                list(range(8)),
                wrap=False,
            )
            clean = b.write_stone_outputs(
                result,
                root / "out",
            )
            payload = json.loads(
                (root / "out" / "crispness.json").read_text()
            )
            self.assertEqual(
                payload["schema_version"],
                b.SCHEMA,
            )
            self.assertNotIn("_render", payload)
            self.assertTrue(payload["evidence_files"])
            self.assertTrue(
                list(
                    (root / "out" / "evidence").glob("*.jpg")
                )
            )
            encoded = (
                root / "out" / "crispness.json"
            ).read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)
            self.assertNotIn("_render", clean)


if __name__ == "__main__":
    unittest.main()
