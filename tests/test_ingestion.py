import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from diamond360 import ingestion


class IngestionTests(unittest.TestCase):
    def test_numeric_order_corrupt_duplicates_and_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            Image.new('RGB', (12, 10), (128, 64, 32)).save(p / 'frame-2.png')
            (p / 'frame-10.png').write_bytes((p / 'frame-2.png').read_bytes())
            (p / 'frame-3.jpg').write_bytes(b'broken')
            Image.new('RGB', (8, 10), 'white').save(p / 'frame-20.png')
            result = ingestion.ingest(p)
            self.assertEqual([r['name'] for r in result['frames']],
                             ['frame-2.png', 'frame-3.jpg', 'frame-10.png', 'frame-20.png'])
            self.assertEqual(result['valid_count'], 3)
            self.assertEqual(result['frames'][1]['status'], 'invalid')
            self.assertEqual(result['frames'][2]['duplicate_of'], 'frame-2.png')
            self.assertEqual(result['dimensions'], [[8, 10], [12, 10]])
            self.assertAlmostEqual(result['frames'][0]['brightness']['mean'],
                                   (128*.2126 + 64*.7152 + 32*.0722)/255, places=5)
            json.dumps(result, allow_nan=False)

    def test_manifest_preserves_wrapped_order_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for i in [0, 2, 254]:
                Image.new('RGB', (8, 8), (i, i, i)).save(p / f'frame-{i:03}.png')
            manifest = p / 'order.json'
            manifest.write_text(json.dumps({'reading_order': [254, 0, 2], 'source_frame_count': 256}))
            r = ingestion.ingest(p, manifest)
            self.assertEqual([f['source_index'] for f in r['frames']], [254, 0, 2])
            self.assertTrue(r['sparse'])
            manifest.write_text(json.dumps({'reading_order': [254, 0, 5]}))
            with self.assertRaisesRegex(ValueError, 'missing'):
                ingestion.ingest(p, manifest)

    def test_empty_directory_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'No image'):
                ingestion.ingest(Path(d))

    def test_manifest_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            Image.new('RGB', (8, 8)).save(p / 'frame-0.png')
            manifest = p / 'order.json'
            manifest.write_text(json.dumps({'frames': [{'index': 0, 'path': 'frame-0.png', 'sha256': 'bad'}]}))
            with self.assertRaisesRegex(ValueError, 'hash'):
                ingestion.ingest(p, manifest)

if __name__ == '__main__':
    unittest.main()
