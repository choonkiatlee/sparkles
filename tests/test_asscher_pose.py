import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_pose, geometry


def _polygon_mask(points, size=280):
    image = Image.new("L", (size, size), 0)
    ImageDraw.Draw(image).polygon(
        [tuple(map(float, point)) for point in points],
        fill=255,
    )
    return np.asarray(image) > 0


def _asscher_mask(
    *,
    size=280,
    centre=(140.0, 140.0),
    half=72.0,
    cut=25.0,
    angle_deg=0.0,
):
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
    points += np.asarray(centre, float)
    return _polygon_mask(points, size=size)


class AsscherPoseTests(unittest.TestCase):
    def test_clean_square_on_frame_is_usable_and_auditable(self):
        mask = _asscher_mask(angle_deg=17.0)
        result = asscher_pose.assess_frame(mask, mask)

        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["score"], 0.9)
        self.assertEqual(result["reasons"], [])
        self.assertIn("projection_consistency", result["components"])
        self.assertIn("opposite_parallelism", result["components"])
        self.assertEqual(
            result["outline"]["orientation_period_deg"],
            90,
        )

    def test_projection_like_trapezoid_is_rejected_explicitly(self):
        mask = _polygon_mask(
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
        result = asscher_pose.assess_frame(mask, mask)

        self.assertEqual(result["status"], "rejected")
        self.assertIn(
            "severe_projection_parallelism",
            result["reasons"],
        )
        self.assertLess(
            result["components"]["projection_consistency"]["score"],
            0.4,
        )

    def test_clipped_frame_is_rejected_even_if_shape_is_otherwise_good(self):
        mask = _asscher_mask(
            size=180,
            centre=(68.0, 90.0),
            half=68.0,
            cut=23.0,
        )
        result = asscher_pose.assess_frame(mask, mask)

        self.assertEqual(result["status"], "rejected")
        self.assertIn(
            "outline_clipped_or_at_image_edge",
            result["reasons"],
        )

    def test_reduced_valid_support_is_visible(self):
        mask = _asscher_mask()
        valid = mask.copy()
        valid[:, :140] = False
        result = asscher_pose.assess_frame(mask, valid)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("insufficient_valid_support", result["reasons"])
        self.assertLess(
            result["components"]["valid_support"]["value"],
            0.65,
        )

    def test_canonicalise_frame_serializes_pose_transform(self):
        mask = _asscher_mask(angle_deg=-21.0)
        brightness = mask.astype(float)
        result = asscher_pose.canonicalise_frame(
            brightness,
            mask,
            mask,
            lowpass_sigma_px=0,
        )

        self.assertIsNotNone(result["brightness"])
        self.assertEqual(
            result["transform"]["pose_schema_version"],
            asscher_pose.SCHEMA,
        )
        self.assertEqual(result["transform"]["orientation_period_deg"], 90)
        self.assertTrue(result["transform"]["quarter_turn_ambiguous"])
        self.assertEqual(result["transform"]["rectification"], "none")

    def test_face_orientation_cues_distinguish_central_spokes_from_table_ring(self):
        mask = _asscher_mask()
        outline = geometry.fit_asscher_outline(mask)
        yy, xx = np.indices(mask.shape, dtype=float)
        cx, cy = outline["centre_xy"]
        dx = xx - cx
        dy = yy - cy
        radius = np.hypot(dx, dy)

        spokes = np.full(mask.shape, 0.5, dtype=float)
        diagonal_distance = np.minimum(
            np.abs(dy - dx),
            np.abs(dy + dx),
        ) / np.sqrt(2.0)
        spokes[(diagonal_distance < 1.5) & (radius < 65)] = 0.9

        table = np.full(mask.shape, 0.5, dtype=float)
        half = 26.0
        table_edge = (
            (
                (np.abs(np.abs(dx) - half) < 1.5)
                & (np.abs(dy) <= half)
            )
            | (
                (np.abs(np.abs(dy) - half) < 1.5)
                & (np.abs(dx) <= half)
            )
        )
        table[table_edge] = 0.9

        spoke_cues = asscher_pose.face_orientation_cues(
            spokes,
            mask,
            outline,
        )
        table_cues = asscher_pose.face_orientation_cues(
            table,
            mask,
            outline,
        )

        self.assertGreater(
            spoke_cues["central_radial_spoke_score"],
            table_cues["central_radial_spoke_score"],
        )
        self.assertGreater(
            spoke_cues["centre_gradient_ratio"],
            table_cues["centre_gradient_ratio"],
        )
        self.assertGreater(
            table_cues["central_ring_edge_score"],
            spoke_cues["central_ring_edge_score"],
        )

    def test_rank_puts_ok_then_review_then_rejected_then_failed(self):
        assessments = [
            {"status": "rejected", "score": 0.9},
            {"status": "ok", "score": 0.8},
            {"status": "review", "score": 0.95},
            {"status": "failed", "score": 1.0},
            {"status": "ok", "score": 0.9},
        ]
        self.assertEqual(
            asscher_pose.rank_assessments(assessments),
            [4, 1, 2, 0, 3],
        )


if __name__ == "__main__":
    unittest.main()
