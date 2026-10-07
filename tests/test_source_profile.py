import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import source_profile as sp


def _metadata(size=4, diameter_px=180):
    area = int(np.pi * (diameter_px / 2.0) ** 2)
    return {
        "schema_version": "1.0",
        "ordering": "explicit_manifest",
        "frames": [
            {
                "position": i,
                "source_index": i,
                "status": "valid",
                "geometry": {
                    "area_px": area,
                    "width_px": diameter_px,
                    "height_px": diameter_px,
                },
            }
            for i in range(size)
        ],
        "source_manifest": {
            "schema_version": "diamond360-source/1",
            "source_pipeline": "synthetic",
            "source_frame_count": size,
            "sequence_complete": True,
            "dimensions": [256, 256],
            "ordering": "test order",
            "sequence_sampling": {
                "kind": "uniform_cyclic_viewer_phase",
                "period_frames": size,
                "nominal_cycle_deg": 360.0,
                "physical_angle_calibrated": False,
            },
        },
    }


def _pose(size=4):
    return {
        "schema_version": "diamond360-asscher-pose-sequence/1",
        "face_selection": {"status": "resolved"},
        "sequence_gauge": {
            "phase": {
                "status": "available",
                "period_deg": 360.0,
                "physical_camera_angle_calibrated": False,
            }
        },
        "frames": [
            {
                "assessment": {"status": "ok"},
                "face_role": "likely_crown_lobe",
                "canonical": {
                    "normalization": {
                        "valid_fraction_of_mask": 0.99,
                    }
                },
            }
            for _ in range(size)
        ],
    }


def _diagnostics():
    return {
        "compression_processing": {
            "status": "ok",
            "reasons": [],
        },
        "photometric": {
            "status": "ok",
            "reasons": [],
            "background_reference": {
                "status": "ok",
                "reasons": [],
            },
            "stone_channel_clipping_fraction": {
                "max": 0.0,
            },
            "colour_calibrated": False,
            "radiometric_calibrated": False,
            "whole_stone_exposure_drift": "unsupported_inference",
        },
    }


class SourceProfileContractTests(unittest.TestCase):
    def test_builder_separates_facts_diagnostics_and_policy(self):
        profile = sp.build_profile(
            _metadata(),
            pose=_pose(),
            certificate_dimensions_mm=[6.4, 6.4],
            image_diagnostics=_diagnostics(),
        )
        self.assertEqual(profile["schema_version"], sp.SCHEMA)
        self.assertEqual(profile["source"]["source_pipeline"], "synthetic")
        self.assertEqual(profile["sequence"]["ordering"]["status"], "ok")
        self.assertEqual(profile["pose_coverage"]["status"], "ok")
        self.assertEqual(profile["physical_scale"]["status"], "ok")
        self.assertNotIn("measurement_capabilities", profile)

    def test_missing_pose_fails_closed_for_angular_measurement(self):
        profile = sp.build_profile(
            _metadata(),
            image_diagnostics=_diagnostics(),
        )
        result = sp.assess_measurement(profile, "angular_persistence")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("pose_sequence_phase_not_supplied", result["reasons"])

    def test_absolute_cross_source_luminance_is_review_without_calibration(self):
        left = sp.build_profile(
            _metadata(),
            pose=_pose(),
            image_diagnostics=_diagnostics(),
        )
        right_meta = _metadata()
        right_meta["source_manifest"]["source_pipeline"] = "other-vendor"
        right = sp.build_profile(
            right_meta,
            pose=_pose(),
            image_diagnostics=_diagnostics(),
        )
        result = sp.can_compare(
            left,
            right,
            "absolute_luminance_amplitude",
        )
        self.assertEqual(result["status"], "review")
        self.assertIn(
            "cross_source_radiometric_calibration_missing",
            result["reasons"],
        )

    def test_spatial_common_transfer_requires_review_when_upsampling(self):
        profile = sp.build_profile(
            _metadata(diameter_px=120),
            pose=_pose(),
            image_diagnostics=_diagnostics(),
        )
        result = sp.assess_measurement(
            profile,
            "spatial_optical_morphology",
        )
        self.assertEqual(result["status"], "review")
        self.assertIn(
            "common_transfer_requires_upsampling",
            result["reasons"],
        )

    def test_angular_comparison_keeps_viewer_phase_caveat(self):
        left = sp.build_profile(
            _metadata(),
            pose=_pose(),
            image_diagnostics=_diagnostics(),
        )
        right = sp.build_profile(
            _metadata(),
            pose=_pose(),
            image_diagnostics=_diagnostics(),
        )
        result = sp.can_compare(left, right, "angular_persistence")
        self.assertEqual(result["status"], "ok")
        self.assertIn(
            "viewer_sequence_phase_not_physical_angle",
            result["reasons"],
        )


class SourceImageDiagnosticTests(unittest.TestCase):
    def _processed(self, root, backgrounds, stone_levels):
        root = Path(root)
        (root / "camera").mkdir()
        (root / "masks").mkdir()
        records = []
        yy, xx = np.indices((96, 96))
        mask = (xx - 48) ** 2 + (yy - 48) ** 2 <= 28 ** 2
        for index, (background, stone) in enumerate(
            zip(backgrounds, stone_levels)
        ):
            rgb = np.full((96, 96, 3), background, np.uint8)
            pattern = (
                stone
                + 28 * (((xx + yy + index) // 4) % 2)
            ).clip(0, 255)
            rgb[mask] = np.repeat(pattern[:, :, None], 3, axis=2)[mask]
            camera = root / "camera" / f"{index:04d}.jpg"
            Image.fromarray(rgb).save(camera, quality=92)
            mask_path = root / "masks" / f"{index:04d}.png"
            Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
            records.append(
                {
                    "position": index,
                    "source_index": index,
                    "status": "valid",
                    "camera_original_path": f"camera/{index:04d}.jpg",
                    "segmentation": {
                        "mask_path": f"masks/{index:04d}.png"
                    },
                    "geometry": {
                        "area_px": int(mask.sum()),
                        "width_px": 57,
                        "height_px": 57,
                    },
                }
            )
        metadata = _metadata(size=len(records), diameter_px=57)
        metadata["frames"] = records
        (root / "sequence.json").write_text(json.dumps(metadata))
        return mask

    def test_stone_brightness_change_is_not_called_exposure_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            self._processed(
                directory,
                backgrounds=[220, 220, 220, 220],
                stone_levels=[40, 90, 140, 180],
            )
            diagnostics = sp.analyse_image_diagnostics(directory)
            photometric = diagnostics["photometric"]
            self.assertEqual(
                photometric["whole_stone_exposure_drift"],
                "unsupported_inference",
            )
            self.assertEqual(
                photometric["background_reference"]["status"],
                "ok",
            )

    def test_background_change_is_source_global_review_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            self._processed(
                directory,
                backgrounds=[180, 185, 220, 180],
                stone_levels=[80, 80, 80, 80],
            )
            diagnostics = sp.analyse_image_diagnostics(directory)
            reference = diagnostics["photometric"]["background_reference"]
            self.assertEqual(reference["status"], "review")
            self.assertTrue(
                any("background" in reason for reason in reference["reasons"])
            )

    def test_controlled_perturbations_cover_issue_81_source_family(self):
        yy, xx = np.indices((96, 96))
        base = np.full((96, 96, 3), 180, np.uint8)
        pattern = 70 + 120 * (((xx + yy) // 3) % 2)
        mask = (xx - 48) ** 2 + (yy - 48) ** 2 <= 30 ** 2
        base[mask] = np.repeat(pattern[:, :, None], 3, axis=2)[mask]

        outputs = {
            kind: sp.apply_diagnostic_perturbation(base, kind)
            for kind in (
                "downsample",
                "blur",
                "sharpen",
                "exposure",
                "contrast",
                "jpeg",
                "white_balance",
            )
        }
        for output in outputs.values():
            self.assertEqual(output.shape, base.shape)
            self.assertEqual(output.dtype, np.uint8)

        base_gray = (
            base.astype(float) / 255.0
            @ np.array([0.2126, 0.7152, 0.0722])
        )
        blur_gray = (
            outputs["blur"].astype(float) / 255.0
            @ np.array([0.2126, 0.7152, 0.0722])
        )
        self.assertLess(
            sp._acutance_proxy(blur_gray, mask),
            sp._acutance_proxy(base_gray, mask),
        )
        self.assertGreater(
            outputs["exposure"][0, 0].mean(),
            base[0, 0].mean(),
        )
        self.assertNotEqual(
            outputs["white_balance"][0, 0, 0],
            outputs["white_balance"][0, 0, 2],
        )


if __name__ == "__main__":
    unittest.main()
