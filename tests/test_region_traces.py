import unittest
import numpy as np
from diamond360 import region_traces as t

class TraceTests(unittest.TestCase):
    def test_same_occupancy_different_runs(self):
        a=t.state_summary([False,True,False,True,False,True])
        b=t.state_summary([False,False,False,True,True,True])
        self.assertEqual(a['dark_occupancy'],b['dark_occupancy'])
        self.assertEqual(a['transitions'],5);self.assertEqual(b['transitions'],1)
        self.assertEqual(a['longest_dark_run_frames'],1);self.assertEqual(b['longest_dark_run_frames'],3)
    def test_gap_breaks_runs_and_transitions(self):
        r=t.state_summary([True,True,None,False,False])
        self.assertEqual(r['transitions'],0);self.assertEqual(r['longest_dark_run_frames'],2)
        self.assertEqual(r['observed_frames'],4)
        self.assertIsNone(t.state_summary([None])['dark_occupancy'])
    def test_contiguous_wrap_and_sparse_refusal(self):
        t.validate_interval([254,255,0,1],256,True)
        for indices,wrapped in [([254,0,1],True),([255,0],False),([0,1,0],True),([1,0],False)]:
            with self.assertRaises(ValueError):t.validate_interval(indices,256,wrapped)
    def test_common_support_prevents_outline_changes_and_missing_is_not_dark(self):
        brightness=np.array([[[0.,.8]],[[1.,.8]]])
        masks=np.array([[[False,True]],[[True,True]]])
        regions={'centre':np.ones((1,2),bool),'empty':np.zeros((1,2),bool)}
        r=t.measure_regions(brightness,masks,regions)
        self.assertEqual(r['centre']['median_brightness'],[.8,.8])
        self.assertEqual(r['centre']['activation_amplitude_p90_p10'],0)
        self.assertEqual(r['centre']['relative_dark_pixel_fraction'],[0.,0.])
        self.assertIsNone(r['empty']['states']['dark_occupancy'])
    def test_unknown_frames_break_instead_of_interpolating(self):
        b=np.array([[[.1,.8]],[[.1,.8]],[[.1,.8]]]);v=np.ones_like(b,bool)
        r=t.measure_regions(b,v,{'centre':np.array([[True,False]])},observed=[True,False,True])['centre']
        self.assertEqual(r['median_brightness'],[.1,None,.1])
        self.assertEqual(r['states']['longest_dark_run_frames'],1)
        self.assertEqual(r['states']['transitions'],0)

class PixelTraceTests(unittest.TestCase):
    def test_pixels_distinguish_dark_blocks_from_switching_despite_same_bright_region_median(self):
        # Three bright pixels keep the regional median bright; the fourth alternates.
        b=np.array([[[.1,.8,.8,.8]],[[.8,.8,.8,.8]],[[.1,.8,.8,.8]],[[.8,.8,.8,.8]]])
        r=t.measure_regions(b,np.ones_like(b,bool),{'centre':np.ones((1,4),bool)})['centre']
        self.assertEqual(r['states']['transitions'],0)
        self.assertEqual(r['pixel_states']['fraction_with_transitions'],.25)
        self.assertEqual(r['pixel_states']['max_transitions'],3)
        self.assertEqual(r['pixel_states']['longest_dark_run_max_frames'],1)
        b[1,0,0]=.1;b[2,0,0]=.8
        r=t.measure_regions(b,np.ones_like(b,bool),{'centre':np.ones((1,4),bool)})['centre']
        self.assertEqual(r['pixel_states']['max_transitions'],1)
        self.assertEqual(r['pixel_states']['longest_dark_run_max_frames'],2)
