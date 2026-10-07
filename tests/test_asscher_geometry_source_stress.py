import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import asscher_geometry_source_stress as stress


class AsscherGeometrySourceStressTests(unittest.TestCase):
    def test_perturbation_matrix_is_frozen_and_complete(self):
        rows = stress.perturbation_matrix()
        self.assertEqual(len(rows), 7)
        self.assertEqual(
            {row["kind"] for row in rows},
            {
                "downsample_resample",
                "gaussian_blur",
                "brightness",
                "contrast",
                "jpeg_recompress",
            },
        )
        self.assertEqual(
            stress.REPRESENTATIVE_CERTIFICATES,
            ("IGI-LG756520111", "IGI-LG836619414"),
        )

    def test_non_jpeg_perturbations_preserve_dimensions(self):
        data = np.zeros((31, 47, 3), dtype=np.uint8)
        data[7:24, 10:37] = [160, 120, 80]
        image = Image.fromarray(data)
        for spec in stress.PERTURBATIONS:
            if spec["kind"] == "jpeg_recompress":
                continue
            result = stress.apply_perturbation(image, spec)
            self.assertEqual(result.size, image.size)
            self.assertEqual(result.mode, "RGB")

    def test_brightness_and_contrast_are_deterministic(self):
        data = np.arange(20 * 24 * 3, dtype=np.uint8).reshape(20, 24, 3)
        image = Image.fromarray(data)
        specs = [
            row for row in stress.PERTURBATIONS
            if row["kind"] in ("brightness", "contrast")
        ]
        for spec in specs:
            a = np.asarray(stress.apply_perturbation(image, spec))
            b = np.asarray(stress.apply_perturbation(image, spec))
            np.testing.assert_array_equal(a, b)

    def test_derived_manifest_updates_hashes_and_preserves_indices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "frames").mkdir(parents=True)
            frames = []
            for index in range(3):
                path = source / "frames" / f"frame-{index:03d}.jpg"
                Image.new(
                    "RGB", (24, 20), (80 + index * 20, 100, 120)
                ).save(path, quality=95)
                frames.append({
                    "source_index": index,
                    "path": f"frames/frame-{index:03d}.jpg",
                    "sha256": stress._sha256_file(path),
                    "bytes": path.stat().st_size,
                })
            manifest = {
                "schema_version": "diamond360-source/1",
                "certificate": "TEST",
                "source_pipeline": "fixture",
                "source_frame_count": 3,
                "sequence_complete": True,
                "frames": frames,
                "sequence_sampling": {
                    "kind": "uniform_cyclic_viewer_phase",
                    "period_frames": 3,
                    "nominal_cycle_deg": 360,
                    "physical_angle_calibrated": False,
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            destination = root / "derived"
            spec = next(
                row for row in stress.PERTURBATIONS
                if row["kind"] == "gaussian_blur"
            )
            derived_path, derived = stress.derive_perturbed_source(
                source, manifest_path, destination, spec
            )
            self.assertTrue(derived_path.is_file())
            self.assertEqual(
                [row["source_index"] for row in derived["frames"]],
                [0, 1, 2],
            )
            self.assertTrue(
                all(row["path"].endswith(".png") for row in derived["frames"])
            )
            self.assertTrue(
                all(
                    row["sha256"] != frames[index]["sha256"]
                    for index, row in enumerate(derived["frames"])
                )
            )
            self.assertTrue(
                derived["controlled_perturbation"][
                    "ordering_and_source_indices_preserved"
                ]
            )

    def test_jpeg_condition_remains_jpeg_and_is_hash_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "frames").mkdir(parents=True)
            path = source / "frames" / "frame-000.jpg"
            Image.new("RGB", (32, 28), (90, 130, 170)).save(
                path, quality=98
            )
            manifest = {
                "schema_version": "diamond360-source/1",
                "certificate": "TEST",
                "source_pipeline": "fixture",
                "source_frame_count": 1,
                "sequence_complete": True,
                "frames": [{
                    "source_index": 0,
                    "path": "frames/frame-000.jpg",
                    "sha256": stress._sha256_file(path),
                    "bytes": path.stat().st_size,
                }],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            spec = next(
                row for row in stress.PERTURBATIONS
                if row["kind"] == "jpeg_recompress"
            )
            _, derived = stress.derive_perturbed_source(
                source, manifest_path, root / "derived", spec
            )
            row = derived["frames"][0]
            derived_path = root / "derived" / row["path"]
            self.assertEqual(derived_path.suffix, ".jpg")
            self.assertEqual(row["sha256"], stress._sha256_file(derived_path))

    def test_support_delta_is_componentwise_not_a_composite_score(self):
        reference = {
            "status": "available",
            "boundary_support_fraction": {"C1_C2": 0.8},
            "boundary_median_residual_u": {"C1_C2": 0.01},
            "entity_ok_fraction": {"C1_N": 0.7},
            "entity_mean_confidence": {"C1_N": 0.6},
        }
        candidate = {
            "status": "available",
            "boundary_support_fraction": {"C1_C2": 0.6},
            "boundary_median_residual_u": {"C1_C2": 0.03},
            "entity_ok_fraction": {"C1_N": 0.5},
            "entity_mean_confidence": {"C1_N": 0.55},
        }
        result = stress._support_delta(reference, candidate)
        self.assertAlmostEqual(
            result["boundary_support_fraction_delta"]["C1_C2"], -0.2
        )
        self.assertAlmostEqual(
            result["boundary_median_residual_u_delta"]["C1_C2"], 0.02
        )
        self.assertNotIn("score", result)

    def test_poor_view_bins_cover_full_256_frame_half_cycle(self):
        covered = []
        for lo, hi in stress.POOR_VIEW_DISTANCE_BINS:
            covered.extend(range(lo, hi + 1))
        self.assertEqual(covered, list(range(129)))
        self.assertEqual(stress._bin_for_distance(0), "000-004")
        self.assertEqual(stress._bin_for_distance(128), "097-128")

    def test_distance_to_nearest_primary_is_cyclic(self):
        self.assertEqual(
            stress._distance_to_nearest_primary(255, [0, 10], 256), 1
        )
        self.assertEqual(
            stress._distance_to_nearest_primary(128, [0], 256), 128
        )


if __name__ == "__main__":
    unittest.main()
