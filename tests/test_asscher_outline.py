import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import geometry


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


def _angle_error_mod_90(actual, expected):
    return abs((actual - expected + 45.0) % 90.0 - 45.0)


class AsscherOutlineTests(unittest.TestCase):
    def test_recovers_cut_corner_pose_modulo_fourfold_symmetry(self):
        mask = _asscher_mask(
            centre=(137.0, 146.0),
            angle_deg=17.0,
        )
        result = geometry.fit_asscher_outline(mask)

        self.assertEqual(
            result["schema_version"],
            geometry.ASSCHER_OUTLINE_SCHEMA,
        )
        self.assertLess(
            _angle_error_mod_90(
                result["orientation_deg_mod_90"],
                17.0,
            ),
            0.75,
        )
        np.testing.assert_allclose(
            result["centre_xy"],
            [137.0, 146.0],
            atol=1.0,
        )
        self.assertAlmostEqual(result["aspect_ratio"], 1.0, delta=0.02)
        self.assertEqual(result["orientation_period_deg"], 90)
        self.assertTrue(result["quarter_turn_ambiguous"])
        self.assertEqual(len(result["vertices_xy"]), 8)
        self.assertEqual(len(result["side_lines"]), 8)

    def test_translation_scale_and_quarter_turn_preserve_normalised_shape(self):
        first = geometry.fit_asscher_outline(
            _asscher_mask(
                centre=(120.0, 130.0),
                half=55.0,
                cut=19.0,
                angle_deg=11.0,
            )
        )
        second = geometry.fit_asscher_outline(
            _asscher_mask(
                centre=(155.0, 145.0),
                half=82.0,
                cut=28.5,
                angle_deg=101.0,
            )
        )

        self.assertLess(
            _angle_error_mod_90(
                first["orientation_deg_mod_90"],
                second["orientation_deg_mod_90"],
            ),
            0.75,
        )
        first_ratio = (
            first["width_px"] / first["effective_diameter_px"]
        )
        second_ratio = (
            second["width_px"] / second["effective_diameter_px"]
        )
        self.assertAlmostEqual(first_ratio, second_ratio, delta=0.02)

    def test_projection_like_trapezoid_is_not_hidden_by_outline_model(self):
        good = geometry.fit_asscher_outline(
            _asscher_mask(angle_deg=0.0)
        )
        trapezoid = _polygon_mask(
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
        bad = geometry.fit_asscher_outline(trapezoid)

        parallel = [
            value
            for value in bad["parallelism_error_deg"].values()
            if value is not None
        ]
        self.assertGreater(max(parallel), 5.0)
        self.assertGreater(
            bad["normalized_q90_boundary_residual"],
            good["normalized_q90_boundary_residual"] * 3.0,
        )

    def test_rejects_degenerate_mask(self):
        with self.assertRaisesRegex(ValueError, "non-trivial"):
            geometry.fit_asscher_outline(
                np.zeros((40, 40), dtype=bool)
            )


if __name__ == "__main__":
    unittest.main()
