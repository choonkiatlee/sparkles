import unittest
import numpy as np
from diamond360 import regions

class RegionTests(unittest.TestCase):
    def test_partitions_are_disjoint_and_cover_silhouette(self):
        y,x=np.indices((100,100));mask=(abs(x-49.5)<35)&(abs(y-49.5)<35)
        r=regions.build(mask,target_extent=70)
        for names in [['centre','inner','middle','outer'],
                      ['quadrant_NE','quadrant_SE','quadrant_SW','quadrant_NW'],
                      ['side_E','corner_SE','side_S','corner_SW','side_W','corner_NW','side_N','corner_NE']]:
            count=np.stack([r[n] for n in names]).sum(axis=0)
            np.testing.assert_array_equal(count,mask.astype(int))
        self.assertTrue(r['centre'][50,50])
        self.assertTrue(r['side_N'][20,50])
        self.assertTrue(r['corner_NE'][20,78])
        for m in r.values():self.assertFalse((m&~mask).any())

    def test_boundary_strip_masks_match_legacy_square_radius(self):
        mask = np.ones((101, 101), bool)
        strips = regions.boundary_strip_masks(
            mask, radius=.45, width=.05, guard=.02, target_extent=100
        )
        self.assertFalse(np.any(strips['inside'] & strips['outside']))
        self.assertGreater(strips['inside'].sum(), 0)
        self.assertGreater(strips['outside'].sum(), 0)
        y, x = np.indices(mask.shape)
        r = np.maximum(abs(x - 50), abs(y - 50)) / 50
        self.assertLess(float(np.max(r[strips['inside']])), .45 - .02 + .03)
        self.assertGreater(float(np.min(r[strips['outside']])), .45 + .02 - .03)

    def test_boundary_strip_masks_clip_to_sector(self):
        mask = np.ones((101, 101), bool)
        sector = np.zeros_like(mask)
        sector[:, 50:] = True
        strips = regions.boundary_strip_masks(
            mask, radius=.45, width=.05, sector_mask=sector, target_extent=100
        )
        self.assertTrue(np.all(~strips['inside'] | sector))
        self.assertTrue(np.all(~strips['outside'] | sector))
    def test_non_square_canvas_rejected(self):
        with self.assertRaises(ValueError):regions.build(np.ones((80,100),bool))
