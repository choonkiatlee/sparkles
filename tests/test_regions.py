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

    def test_non_square_canvas_rejected(self):
        with self.assertRaises(ValueError):regions.build(np.ones((80,100),bool))
