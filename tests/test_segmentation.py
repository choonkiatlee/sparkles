import unittest
import numpy as np
from PIL import Image, ImageDraw
from diamond360 import segmentation


def polygon_image():
    image = Image.new('RGB', (160, 140), (190, 193, 199))
    ImageDraw.Draw(image).polygon([(50,30),(110,30),(125,45),(125,95),
                                  (110,110),(50,110),(35,95),(35,45)], fill=(70,75,80))
    rgb = np.asarray(image).copy()
    return rgb, np.any(rgb != [190,193,199], axis=2)


class SegmentationTests(unittest.TestCase):
    def test_polygon_silhouette_and_pale_interior(self):
        rgb, truth = polygon_image()
        rgb = rgb.copy(); rgb[50:90,60:100] = [190,193,199]
        result = segmentation.segment(rgb)
        self.assertEqual(result['status'], 'ok')
        mask = result['mask']
        self.assertGreater((mask & truth).sum()/(mask | truth).sum(), .90)
        self.assertTrue(mask[65,80])
        self.assertGreater(len(result['vertices_xy']), 4)

    def test_flat_frame_fails_visibly(self):
        r = segmentation.segment(np.full((100,100,3),180,dtype=np.uint8))
        self.assertEqual(r['status'], 'failed')
        self.assertFalse(r['mask'].any())

    def test_clipped_object_is_not_accepted(self):
        rgb, _ = polygon_image(); rgb[30:110,:55] = [50,50,50]
        r = segmentation.segment(rgb)
        self.assertNotEqual(r['status'], 'ok')

    def test_complex_background_is_not_accepted(self):
        rng = np.random.default_rng(3)
        r = segmentation.segment(rng.integers(0,255,(100,100,3),dtype=np.uint8))
        self.assertEqual(r['status'], 'failed')

if __name__ == '__main__':
    unittest.main()
