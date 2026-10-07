import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_pose_sequence, geometry


def _polygon_mask(points, size=280):
    image = Image.new("L", (size, size), 0)
    ImageDraw.Draw(image).polygon(
        [tuple(map(float, point)) for point in points],
        fill=255,
    )
    return np.asarray(image) > 0


def _asscher_mask(angle_deg):
    half, cut = 72.0, 25.0
    points = np.array(
        [
            [-half + cut, -half],
            [half - cut, -half],
            [half, -half + cut],
            [half, half - cut],
            [half - cut, half],
            [-half + cut, half],
            [-half, half - cut],
            [-half, -half + cut],
        ],
        dtype=float,
    )
    points = geometry._rotate_points(points, angle_deg)
    points += np.array([140.0, 140.0])
    return _polygon_mask(points)


def _write_processed_frame(root, position, source_index, mask):
    stem = f"{position:04d}"
    for folder in ["camera", "masks", "diamond", "photometry"]:
        (root / folder).mkdir(exist_ok=True)

    rgb = np.full((*mask.shape, 3), 195, dtype=np.uint8)
    rgb[mask] = [70, 75, 80]
    Image.fromarray(rgb).save(root / "camera" / f"{stem}.png")
    Image.fromarray(mask.astype(np.uint8) * 255).save(
        root / "masks" / f"{stem}.png"
    )
    Image.fromarray(mask.astype(np.uint8) * 255).save(
        root / "diamond" / f"{stem}-mask.png"
    )
    Image.fromarray(mask.astype(np.uint8) * 255).save(
        root / "diamond" / f"{stem}-valid.png"
    )

    brightness = np.full(mask.shape, 0.75, dtype=float)
    brightness[mask] = 0.3
    np.savez_compressed(
        root / "photometry" / f"{stem}.npz",
        encoded_brightness=brightness,
        valid_mask=mask,
    )
    return {
        "status": "valid",
        "source_index": source_index,
        "position": position,
        "name": f"frame{source_index}.png",
        "camera_original_path": f"camera/{stem}.png",
        "segmentation": {
            "status": "ok",
            "mask_path": f"masks/{stem}.png",
        },
        "registration": {
            "mask_path": f"diamond/{stem}-mask.png",
            "valid_mask_path": f"diamond/{stem}-valid.png",
            "camera_to_diamond": np.eye(3).tolist(),
        },
        "photometry_path": f"photometry/{stem}.npz",
    }


class AsscherPoseSequenceTests(unittest.TestCase):
    def test_persists_ranking_canonical_support_and_qc(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            processed = root / "processed"
            output = root / "pose"
            processed.mkdir()

            good0 = _asscher_mask(7.0)
            good1 = _asscher_mask(24.0)
            bad = _polygon_mask(
                np.array(
                    [
                        [85, 55],
                        [185, 55],
                        [215, 85],
                        [225, 185],
                        [190, 220],
                        [70, 220],
                        [35, 185],
                        [45, 85],
                    ],
                    dtype=float,
                )
            )
            frames = [
                _write_processed_frame(processed, 0, 10, good0),
                _write_processed_frame(processed, 1, 20, good1),
                _write_processed_frame(processed, 2, 30, bad),
            ]
            (processed / "sequence.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "frames": frames,
                    }
                )
            )

            result = asscher_pose_sequence.analyse_processed_sequence(
                processed,
                output,
            )

            self.assertEqual(
                result["schema_version"],
                asscher_pose_sequence.SEQUENCE_SCHEMA,
            )
            self.assertEqual(result["frame_count"], 3)
            self.assertEqual(result["usable_count"], 2)
            self.assertEqual(
                {
                    row["source_index"]
                    for row in result["ranking"][:2]
                },
                {10, 20},
            )
            self.assertTrue(
                all(
                    row["status"] == "ok"
                    for row in result["ranking"][:2]
                )
            )
            bad_record = next(
                record
                for record in result["frames"]
                if record["source_index"] == 30
            )
            self.assertEqual(
                bad_record["assessment"]["status"],
                "rejected",
            )
            self.assertIn(
                "severe_projection_parallelism",
                bad_record["assessment"]["reasons"],
            )

            for record in result["frames"]:
                self.assertIsNotNone(record["canonical"])
                self.assertTrue(
                    (output / record["canonical"]["path"]).is_file()
                )
                forward = np.asarray(
                    record["canonical"]["camera_to_canonical_xy"],
                    float,
                )
                inverse = np.asarray(
                    record["canonical"]["canonical_to_camera_xy"],
                    float,
                )
                np.testing.assert_allclose(
                    inverse @ forward,
                    np.eye(3),
                    atol=1e-10,
                )

            self.assertTrue((output / "asscher-pose.json").is_file())
            self.assertTrue((output / "asscher-pose-qc.jpg").is_file())

    def test_competing_face_on_lobes_use_table_boundary_to_resolve_crown(self):
        size = 64

        def distance(index, centre):
            delta = abs(index - centre)
            return min(delta, size - delta)

        records = []
        for position in range(size):
            d0 = distance(position, 0)
            d1 = distance(position, 32)
            score = max(
                0.45 + 0.42 * np.exp(-((d0 / 4.0) ** 2)),
                0.45 + 0.39 * np.exp(-((d1 / 4.0) ** 2)),
            )
            table = (
                0.82 - 0.01 * d0
                if d0 <= d1
                else 0.62 - 0.005 * d1
            )
            records.append(
                {
                    "position": position,
                    "source_index": position,
                    "assessment": {
                        "status": "review",
                        "score": float(score),
                        "face_orientation_cues": {
                            "table_boundary_continuity_score": float(table),
                        },
                    },
                }
            )

        selection = asscher_pose_sequence.resolve_face_lobes(
            records,
            sequence_complete=True,
        )
        self.assertEqual(selection["status"], "resolved")
        self.assertLess(
            asscher_pose_sequence._circular_distance(
                selection["likely_crown_peak_position"],
                0,
                size,
            ),
            4,
        )
        self.assertLess(
            asscher_pose_sequence._circular_distance(
                selection["likely_opposite_peak_position"],
                32,
                size,
            ),
            4,
        )

        asscher_pose_sequence._annotate_face_roles(records, selection)
        ranked = asscher_pose_sequence.rank_sequence_records(
            records,
            selection,
        )
        self.assertEqual(
            records[ranked[0]]["face_role"],
            "likely_crown_lobe",
        )
        opposite_indices = {
            index
            for index, record in enumerate(records)
            if record["face_role"] == "likely_opposite_lobe"
        }
        self.assertTrue(opposite_indices)
        self.assertGreater(
            min(ranked.index(index) for index in opposite_indices),
            0,
        )

    def test_face_resolution_does_not_override_clear_single_geometry_lobe(self):
        size = 64
        records = []
        for position in range(size):
            d0 = asscher_pose_sequence._circular_distance(
                position, 0, size
            )
            d1 = asscher_pose_sequence._circular_distance(
                position, 32, size
            )
            score = max(
                0.35 + 0.55 * np.exp(-((d0 / 4.0) ** 2)),
                0.35 + 0.20 * np.exp(-((d1 / 4.0) ** 2)),
            )
            records.append(
                {
                    "position": position,
                    "source_index": position,
                    "assessment": {
                        "status": "review",
                        "score": float(score),
                        "face_orientation_cues": {
                            "table_boundary_continuity_score": (
                                0.6 if d0 <= d1 else 0.9
                            ),
                        },
                    },
                }
            )

        selection = asscher_pose_sequence.resolve_face_lobes(
            records,
            sequence_complete=True,
        )
        self.assertEqual(selection["status"], "not_needed")
        self.assertEqual(
            selection["reason"],
            "one_geometric_lobe_clearly_better",
        )


if __name__ == "__main__":
    unittest.main()
