import unittest
import numpy as np
from diamond360 import diagnostics

class DiagnosticTests(unittest.TestCase):
    def test_activity_dark_fraction_and_missing_support(self):
        a=np.full((8,8),.8);b=a.copy();a[3,3]=.1;b[3,3]=.5
        m=np.ones((8,8),bool);n=m.copy();n[0,0]=False
        r=diagnostics.summarise([(a,m),(b,n)])
        self.assertAlmostEqual(r['mean'][3,3],.3)
        self.assertAlmostEqual(r['std'][3,3],.2)
        self.assertEqual(r['relative_dark_fraction'][3,3],1)
        self.assertTrue(np.isnan(r['std'][0,0]))
        self.assertEqual(r['support_count'][0,0],1)
        self.assertEqual(r['support_fraction'][0,0],.5)
        self.assertEqual(r['std'][1,1],0)

    def test_all_invalid_is_not_dark_or_bright(self):
        m=np.zeros((5,5),bool)
        r=diagnostics.summarise([(np.zeros((5,5)),m),(np.zeros((5,5)),m)])
        self.assertTrue(np.isnan(r['mean']).all())
        self.assertTrue(np.isnan(r['relative_dark_fraction']).all())

    def test_empty_and_mixed_dimensions_rejected(self):
        with self.assertRaises(ValueError):diagnostics.summarise([])
        with self.assertRaises(ValueError):
            diagnostics.summarise([(np.zeros((5,5)),np.ones((5,5),bool)),
                                   (np.zeros((6,5)),np.ones((6,5),bool))])
