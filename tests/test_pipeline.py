import tempfile
import unittest
from pathlib import Path
import hashlib
import numpy as np
from PIL import Image,ImageDraw
from diamond360.pipeline import run

class PipelineTests(unittest.TestCase):
    def make_frames(self, source):
        source.mkdir()
        for i,level in [(0,60),(2,140)]:
            im=Image.new('RGB',(140,140),(200,200,200))
            ImageDraw.Draw(im).polygon([(45,30),(95,30),(110,45),(110,95),(95,110),(45,110),(30,95),(30,45)],fill=(level,level,level))
            im.save(source/f'frame-{i}.png')

    def test_end_to_end_preserves_sources_and_emits_supported_maps(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input';self.make_frames(source);out=root/'output'
            r=run(source,out,diagnostic_indices=[0,2])
            self.assertEqual(r['diagnostics']['status'],'complete')
            self.assertEqual(len(r['diagnostics']['accepted_indices']),2)
            for f in r['frames']:
                self.assertEqual(hashlib.sha256((out/f['camera_original_path']).read_bytes()).hexdigest(),f['sha256'])
                self.assertTrue((out/f['regions_path']).is_file())
            a=np.load(out/'temporal-diamond.npz')
            self.assertGreater(a['std'][128,128],.1)

    def test_output_reuse_refused_and_missing_selection_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input';self.make_frames(source);out=root/'output'
            run(source,out)
            with self.assertRaisesRegex(ValueError,'empty'):
                run(source,out)
            fresh=root/'fresh'
            with self.assertRaises(ValueError):run(source,fresh,diagnostic_indices=[999])
            self.assertFalse(fresh.exists())

    def test_flat_frames_have_visible_exclusions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input';source.mkdir()
            for i in [0,1]:Image.new('RGB',(80,80),'grey').save(source/f'frame-{i}.png')
            r=run(source,root/'output',diagnostic_indices=[0,1])
            self.assertEqual(r['diagnostics']['status'],'insufficient_accepted_frames')
            self.assertEqual(len(r['diagnostics']['excluded']),2)
