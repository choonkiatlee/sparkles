import unittest
import numpy as np
from diamond360 import registration
from diamond360.geometry import measure

class RegistrationTests(unittest.TestCase):
    def test_translation_scale_inverse_and_fixed_centre(self):
        for x,y,width in [(20,15,40),(45,35,60)]:
            mask = np.zeros((130,160),bool);mask[y:y+width,x:x+width]=True
            rgb = np.full((130,160,3),200,dtype=np.uint8);rgb[mask]=60
            g = measure(mask)
            r = registration.canonicalise(rgb,mask,g,size=100,target_extent=70)
            centre = np.array(g['centroid_xy']+[1])
            np.testing.assert_allclose(r['camera_to_diamond']@centre,[49.5,49.5,1])
            np.testing.assert_allclose(r['diamond_to_camera']@r['camera_to_diamond'],np.eye(3),atol=1e-10)
            np.testing.assert_allclose(measure(r['mask'])['centroid_xy'],[49.5,49.5],atol=.6)
            self.assertEqual(r['rgb'][50,50,0],60)
            self.assertTrue(r['valid_mask'][50,50])
            self.assertEqual(r['rgb'].shape,(100,100,3))

    def test_temporal_brightness_preserved(self):
        mask=np.zeros((100,100),bool);mask[20:80,20:80]=True
        values=[]
        for b in [40,160]:
            rgb=np.full((100,100,3),b,dtype=np.uint8)
            r=registration.canonicalise(rgb,mask,measure(mask))
            values.append(r['rgb'][128,128,0])
        self.assertEqual(values,[40,160])

    def test_invalid_target_rejected(self):
        mask=np.ones((10,10),bool)
        with self.assertRaises(ValueError):
            registration.canonicalise(np.zeros((10,10,3),np.uint8),mask,measure(mask),size=32,target_extent=40)
