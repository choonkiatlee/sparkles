import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from diamond360.ingestion import ingest

class SourceContractTests(unittest.TestCase):
    def fixture(self, p):
        frames=[]
        for name,idx,value in [('a.jpg',255,100),('b.jpg',0,200)]:
            Image.new('RGB',(8,8),(value,)*3).save(p/name)
            frames.append(dict(path=name,source_index=idx,sha256=hashlib.sha256((p/name).read_bytes()).hexdigest()))
        m=dict(schema_version='diamond360-source/1',source_frame_count=256,sequence_complete=False,frames=frames)
        return m
    def test_order_and_indices_independent_of_filenames(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m=self.fixture(p);m['frames'].reverse();(p/'manifest.json').write_text(json.dumps(m))
            r=ingest(p,p/'manifest.json')
            self.assertEqual([f['source_index'] for f in r['frames']],[0,255])
            self.assertEqual(r['ordering'],'explicit_manifest')
    def test_hash_missing_unlisted_duplicate_and_false_completeness(self):
        for case in ['hash','missing','unlisted','duplicate','complete','escape']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                p=Path(d);m=self.fixture(p)
                if case=='hash':m['frames'][0]['sha256']='0'*64
                if case=='missing':m['frames'][0]['path']='missing.jpg'
                if case=='unlisted':Image.new('RGB',(8,8)).save(p/'c.jpg')
                if case=='duplicate':m['frames'][1]['source_index']=255
                if case=='complete':m['sequence_complete']=True
                if case=='escape':m['frames'][0]['path']='../a.jpg'
                (p/'manifest.json').write_text(json.dumps(m))
                with self.assertRaises(ValueError):ingest(p,p/'manifest.json')
