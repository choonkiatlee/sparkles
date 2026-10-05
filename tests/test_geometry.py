import unittest
import numpy as np
from diamond360 import geometry

class GeometryTests(unittest.TestCase):
    def test_centroid_dimensions_axes(self):
        mask = np.zeros((100,140),bool); mask[20:60,30:110] = True
        g = geometry.measure(mask)
        self.assertEqual(g['centroid_xy'], [69.5,39.5])
        self.assertEqual((g['width_px'],g['height_px']), (80,40))
        self.assertAlmostEqual(g['orientation_deg'], 0)
        self.assertFalse(g['orientation_ambiguous'])
        self.assertGreater(g['eigenvalue_ratio'], 3.9)

    def test_square_orientation_is_ambiguous(self):
        mask = np.zeros((80,80),bool); mask[20:60,20:60] = True
        g = geometry.measure(mask)
        self.assertTrue(g['orientation_ambiguous'])
        self.assertIsNone(g['orientation_deg'])

    def test_empty_mask_rejected(self):
        with self.assertRaisesRegex(ValueError,'empty'):
            geometry.measure(np.zeros((10,10),bool))
