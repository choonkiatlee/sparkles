import unittest

import numpy as np

from diamond360 import diagonal_arms as da
from diamond360 import normalized_geometry as ng
from diamond360 import normalized_tier_edges as te


class NormalizedGeometryTests(unittest.TestCase):
    def _scene(self, size, radius):
        y, x = np.indices((size, size))
        c = (size - 1) / 2
        rr = np.hypot(x-c, y-c)
        mask = rr <= radius
        u = rr / radius
        brightness = np.where(
            u < .55, .55, 1.0
        )
        return brightness, mask, mask.copy()

    def test_equivalent_sizes_map_to_common_transfer(self):
        a = ng.normalize_frame(
            *self._scene(160, 56),
            target_diameter=120,
        )
        b = ng.normalize_frame(
            *self._scene(240, 84),
            target_diameter=120,
        )
        support = (
            a["valid_mask"] & b["valid_mask"]
        )
        self.assertGreater(
            support.mean(), .45
        )
        self.assertLess(
            float(
                np.mean(
                    np.abs(
                        a["brightness"][support]
                        - b["brightness"][support]
                    )
                )
            ),
            .025,
        )
        self.assertAlmostEqual(
            ng.effective_diameter(a["mask"]),
            ng.effective_diameter(b["mask"]),
            delta=2.0,
        )


class TierEdgeTests(unittest.TestCase):
    def setUp(self):
        self.u = np.linspace(0, 1, 240)
        self.angles = np.linspace(
            0, 2*np.pi, 96, endpoint=False
        )
        self.support = np.ones(
            (96, len(self.u)), bool
        )

    def _profiles(
        self,
        width=.01,
        missing=None,
        wobble=0.0,
    ):
        rows = []
        missing = set(missing or [])
        for i, angle in enumerate(
            self.angles
        ):
            if i in missing:
                rows.append(
                    np.ones_like(self.u)*.8
                )
            else:
                centre = (
                    .51
                    + wobble*np.sin(3*angle)
                )
                rows.append(
                    .65
                    + .35
                    / (
                        1
                        + np.exp(
                            -(
                                self.u-centre
                            )
                            / width
                        )
                    )
                )
        return np.asarray(rows)

    def test_transition_width_tracks_blur(self):
        sharp = te.measure_boundary_frame(
            self._profiles(.004),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        blur = te.measure_boundary_frame(
            self._profiles(.025),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        self.assertLess(
            sharp[
                "median_transition_width_u"
            ],
            blur[
                "median_transition_width_u"
            ],
        )

    def test_fragmentation_and_missing_sector_are_distinct(self):
        contiguous = list(range(12, 36))
        fragmented = list(range(0, 96, 4))
        a = te.measure_boundary_frame(
            self._profiles(
                .008, contiguous
            ),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        b = te.measure_boundary_frame(
            self._profiles(
                .008, fragmented
            ),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        self.assertGreater(
            a[
                "longest_low_confidence_gap_fraction"
            ],
            b[
                "longest_low_confidence_gap_fraction"
            ],
        )
        self.assertLess(
            a[
                "low_confidence_component_count"
            ],
            b[
                "low_confidence_component_count"
            ],
        )

    def test_position_residual_detects_non_asscher_wobble(self):
        straight = te.measure_boundary_frame(
            self._profiles(.008),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        wavy = te.measure_boundary_frame(
            self._profiles(
                .008, wobble=.025
            ),
            self.support,
            self.u,
            self.angles,
            (.42, .60),
            include_rays=False,
        )
        self.assertGreater(
            wavy[
                "position_residual_mad_u"
            ],
            straight[
                "position_residual_mad_u"
            ] + .01,
        )


class DiagonalArmTests(unittest.TestCase):
    def _scene(
        self,
        curve=0.0,
        missing=False,
    ):
        size = 321
        y, x = np.indices(
            (size, size), dtype=float
        )
        c = (size - 1)/2
        dx, dy = x-c, y-c
        radius = 128.0
        rr = np.hypot(dx, dy)
        mask = rr <= radius
        image = np.ones(
            (size, size), float
        )*.2
        for k, angle in enumerate(
            da.ARM_ANGLES
        ):
            ca, sa = (
                np.cos(angle),
                np.sin(angle),
            )
            t = dx*ca + dy*sa
            perp = (
                dx*(-sa) + dy*ca
            )
            centre = (
                curve
                * (t/radius)**2
                * radius
                if k == 0
                else 0.0
            )
            gate = (
                (t > .12*radius)
                & (t < .90*radius)
            )
            if missing and k == 0:
                gate &= ~(
                    (t > .42*radius)
                    & (t < .62*radius)
                )
            image += (
                .7
                * np.exp(
                    -.5
                    * (
                        (
                            perp-centre
                        )/2.4
                    )**2
                )
                * gate
            )
        image[~mask] = 0
        return image, mask, mask.copy()

    def test_missing_segment_increases_arm_gap(self):
        full = da.measure_frame(
            *self._scene(),
            include_trace=False,
        )
        broken = da.measure_frame(
            *self._scene(missing=True),
            include_trace=False,
        )
        self.assertGreater(
            broken["arms"]["SE"][
                "longest_low_confidence_gap_fraction"
            ],
            full["arms"]["SE"][
                "longest_low_confidence_gap_fraction"
            ],
        )

    def test_curvature_reduces_straightness(self):
        straight = da.measure_frame(
            *self._scene(),
            include_trace=False,
        )
        curved = da.measure_frame(
            *self._scene(curve=.10),
            include_trace=False,
        )
        self.assertGreater(
            curved["arms"]["SE"][
                "trajectory_straightness_mad_radius"
            ],
            straight["arms"]["SE"][
                "trajectory_straightness_mad_radius"
            ] + .003,
        )


if __name__ == "__main__":
    unittest.main()
