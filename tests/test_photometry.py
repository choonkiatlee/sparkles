import unittest
import numpy as np
from diamond360 import photometry

class PhotometryTests(unittest.TestCase):
    def test_srgb_transfer_and_masks(self):
        rgb=np.full((10,10,3),128,dtype=np.uint8);mask=np.ones((10,10),bool)
        p=photometry.represent(rgb,mask,mask)
        np.testing.assert_allclose(p['encoded_brightness'],128/255,atol=1e-6)
        np.testing.assert_allclose(p['linear_luminance'],.2158605,atol=1e-6)
        np.testing.assert_array_equal(p['mask'],mask)
        self.assertEqual(p['chroma_range'].max(),0)

    def test_fixed_gain_preserves_pulse_ratio_and_raw(self):
        mask=np.ones((10,10),bool); values=[]
        for level in [40,180]:
            p=photometry.represent(np.full((10,10,3),level,np.uint8),mask,mask,gain=1.05)
            values.append((p['linear_luminance'][0,0],p['gain_luminance'][0,0]))
        self.assertAlmostEqual(values[0][1]/values[0][0],1.05,places=5)
        self.assertAlmostEqual(values[1][1]/values[1][0],1.05,places=5)
        self.assertAlmostEqual(values[1][1]/values[0][1],values[1][0]/values[0][0],places=4)

    def test_gain_limits_and_nonfinite_rejected(self):
        a=np.zeros((3,3,3),np.uint8);m=np.ones((3,3),bool)
        for gain in [0,2,float('nan')]:
            with self.assertRaises(ValueError):photometry.represent(a,m,m,gain=gain)
