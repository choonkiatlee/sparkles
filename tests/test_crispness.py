import unittest

import numpy as np

from diamond360 import asscher_steps as steps
from diamond360 import crispness as c


class CrispnessKernelTests(unittest.TestCase):
    def setUp(self):
        self.u = np.linspace(0, 1, 160)
        self.angles = np.linspace(0, 2 * np.pi, 96, endpoint=False)
        self.control = {"sector_u": np.repeat(.50, 8)}

    def _edge(self, width=.008, missing=None, jitter=0.0):
        edge = np.zeros((96, 160), float)
        support = np.ones_like(edge, bool)
        for i, angle in enumerate(self.angles):
            target = .50 + jitter * np.sin(3 * angle)
            edge[i] = .02 + np.exp(
                -.5 * ((self.u - target) / width) ** 2
            )
        for lo, hi in missing or []:
            edge[lo:hi] = .02
        return edge, support

    def test_strength_continuity_and_position_are_separate_primitives(self):
        sharp, support = self._edge()
        blurred, _ = self._edge(width=.03)
        fragmented, _ = self._edge(missing=[(10, 40)])
        wavy, _ = self._edge(jitter=.03)
        sharp_r = c.measure_boundary_frame(
            sharp,
            support,
            self.u,
            self.angles,
            self.control,
            include_ray_evidence=False,
        )
        blur_r = c.measure_boundary_frame(
            blurred,
            support,
            self.u,
            self.angles,
            self.control,
            include_ray_evidence=False,
        )
        frag_r = c.measure_boundary_frame(
            fragmented,
            support,
            self.u,
            self.angles,
            self.control,
            include_ray_evidence=False,
        )
        wavy_r = c.measure_boundary_frame(
            wavy,
            support,
            self.u,
            self.angles,
            self.control,
            include_ray_evidence=False,
        )
        self.assertGreater(
            sharp_r["median_peak_z"],
            blur_r["median_peak_z"],
        )
        self.assertAlmostEqual(sharp_r["supported_fraction"], 1.0)
        self.assertGreater(frag_r["longest_gap_fraction"], .25)
        self.assertGreater(
            wavy_r["offset_mad_u"],
            sharp_r["offset_mad_u"] + .015,
        )

    def test_longest_gap_is_circular(self):
        supported = np.ones(12, bool)
        supported[[10, 11, 0, 1]] = False
        self.assertAlmostEqual(
            c.longest_circular_gap_fraction(supported),
            4 / 12,
        )
        self.assertEqual(
            c.longest_circular_gap_fraction(np.ones(8, bool)),
            0.0,
        )
        self.assertEqual(
            c.longest_circular_gap_fraction(np.zeros(8, bool)),
            1.0,
        )

    def test_crossfit_discovers_on_opposite_parity_only(self):
        sector = np.zeros((8, 8, len(self.u)), float)
        for frame in range(8):
            for s in range(8):
                sector[frame, s] = (
                    .01
                    + np.exp(-.5 * ((self.u - .50) / .008) ** 2)
                    + .8 * np.exp(-.5 * ((self.u - .73) / .008) ** 2)
                    + .7 * np.exp(-.5 * ((self.u - .87) / .008) ** 2)
                )
        templates = c.build_crossfit_templates(sector, self.u)
        self.assertEqual(len(templates), 2)
        self.assertEqual(
            templates[0]["holdout_positions"],
            [0, 2, 4, 6],
        )
        self.assertEqual(
            templates[0]["train_positions"],
            [1, 3, 5, 7],
        )
        self.assertEqual(
            templates[1]["holdout_positions"],
            [1, 3, 5, 7],
        )
        self.assertTrue(
            all(t["status"] in {"ok", "review"} for t in templates)
        )

    def test_ray_local_photometry_is_invariant_to_global_scale(self):
        size = 96
        y, x = np.indices((size, size))
        cy = cx = (size - 1) / 2
        radius = np.hypot(x - cx, y - cy)
        mask = radius <= 40
        u_image = radius / 40
        brightness = np.where(
            u_image < .50,
            1.0,
            np.where(
                u_image < .73,
                .65,
                np.where(u_image < .87, 1.15, .75),
            ),
        )
        valid = mask.copy()
        first = steps.polar_profiles(
            brightness,
            mask,
            valid,
            96,
            160,
        )
        second = steps.polar_profiles(
            brightness * 3.7,
            mask,
            valid,
            96,
            160,
        )
        e1 = steps.edge_evidence(
            first["profiles"],
            first["support"],
        )
        e2 = steps.edge_evidence(
            second["profiles"],
            second["support"],
        )
        self.assertTrue(
            np.allclose(e1, e2, equal_nan=True, atol=1e-10)
        )

    def test_pipeline_perturbations_preserve_shape_and_finiteness(self):
        image = np.linspace(.2, 1.0, 64 * 64).reshape(64, 64)
        for kind in c.PERTURBATIONS:
            transformed = c.apply_perturbation(image, kind)
            self.assertEqual(transformed.shape, image.shape)
            self.assertTrue(np.isfinite(transformed).all())
        with self.assertRaisesRegex(ValueError, "unknown perturbation"):
            c.apply_perturbation(image, "magic")


if __name__ == "__main__":
    unittest.main()
