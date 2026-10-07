import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import geometry
from diamond360 import normalized_geometry as ng


def _asscher_mask(angle_deg=0.0, size=220):
    half, cut = 65.0, 22.0
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
    points += np.array([110.0, 110.0])
    image = Image.new("L", (size, size), 0)
    ImageDraw.Draw(image).polygon(
        [tuple(map(float, point)) for point in points],
        fill=255,
    )
    return np.asarray(image) > 0


class NormalizedGeometryTests(unittest.TestCase):
    def test_explicit_zero_pose_preserves_default_transfer(self):
        mask = np.zeros((120, 140), dtype=bool)
        mask[25:95, 35:105] = True
        yy, xx = np.indices(mask.shape)
        brightness = (xx + 2 * yy).astype(float)
        valid = mask.copy()

        default = ng.normalize_frame(
            brightness,
            mask,
            valid,
            lowpass_sigma_px=0,
        )
        explicit = ng.normalize_frame(
            brightness,
            mask,
            valid,
            lowpass_sigma_px=0,
            centre_xy=[69.5, 59.5],
            rotation_deg=0.0,
        )

        np.testing.assert_array_equal(
            default["brightness"],
            explicit["brightness"],
        )
        np.testing.assert_array_equal(
            default["mask"],
            explicit["mask"],
        )
        np.testing.assert_array_equal(
            default["valid_mask"],
            explicit["valid_mask"],
        )

    def test_similarity_transform_maps_declared_centre_to_canvas_centre(self):
        mask = _asscher_mask(angle_deg=18.0)
        outline = geometry.fit_asscher_outline(mask)
        brightness = mask.astype(float)
        result = ng.normalize_frame(
            brightness,
            mask,
            mask,
            lowpass_sigma_px=0,
            centre_xy=outline["centre_xy"],
            rotation_deg=outline["orientation_deg_mod_90"],
        )
        transform = result["transform"]
        forward = np.asarray(transform["source_to_canonical_xy"], float)
        inverse = np.asarray(transform["canonical_to_source_xy"], float)
        centre = np.array(outline["centre_xy"] + [1.0])
        canvas_centre = (result["mask"].shape[0] - 1) / 2.0

        np.testing.assert_allclose(
            forward @ centre,
            [canvas_centre, canvas_centre, 1.0],
            atol=1e-9,
        )
        np.testing.assert_allclose(
            inverse @ forward,
            np.eye(3),
            atol=1e-10,
        )
        gram = forward[:2, :2].T @ forward[:2, :2]
        np.testing.assert_allclose(
            gram,
            np.eye(2) * gram[0, 0],
            atol=1e-10,
        )
        self.assertEqual(
            transform["transform_type"],
            "similarity: translation + rotation + isotropic scale",
        )

    def test_rotated_asscher_canonicalises_to_cardinal_pose(self):
        mask = _asscher_mask(angle_deg=23.0)
        outline = geometry.fit_asscher_outline(mask)
        result = ng.normalize_frame(
            mask.astype(float),
            mask,
            mask,
            lowpass_sigma_px=0,
            centre_xy=outline["centre_xy"],
            rotation_deg=outline["orientation_deg_mod_90"],
        )
        canonical_outline = geometry.fit_asscher_outline(result["mask"])
        error = abs(
            (
                canonical_outline["orientation_deg_mod_90"]
                + 45.0
            )
            % 90.0
            - 45.0
        )
        self.assertLess(error, 0.8)


if __name__ == "__main__":
    unittest.main()
