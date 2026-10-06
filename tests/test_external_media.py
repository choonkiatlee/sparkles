import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from diamond360.external_media import adapt_still, build_source


class ExternalMediaTests(unittest.TestCase):
    def test_build_source_preserves_order_and_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = root / "inputs"
            inputs.mkdir()
            paths = []
            for i, value in enumerate((20, 80, 140)):
                path = inputs / f"frame-{i}.png"
                Image.new("RGB", (40, 32), (value, value, value)).save(path)
                paths.append(path)
            out = root / "source"
            result = build_source(
                paths,
                out,
                provenance={"sample_id": "fixture", "evidence_type": "test"},
            )
            self.assertEqual(result["schema_version"], "diamond360-source/1")
            self.assertTrue(result["sequence_complete"])
            self.assertEqual(result["source_frame_count"], 3)
            self.assertEqual(
                [row["source_index"] for row in result["frames"]],
                [0, 1, 2],
            )
            for row in result["frames"]:
                raw = (out / row["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["sha256"])
            saved = json.loads((out / "source-manifest.json").read_text())
            self.assertEqual(saved, result)

    def test_adapt_still_is_explicit_one_frame_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "still.jpg"
            Image.new("RGB", (48, 48), "white").save(source)
            result = adapt_still(
                source,
                root / "adapted",
                provenance={"sample_id": "still"},
            )
            self.assertEqual(result["source_frame_count"], 1)
            self.assertEqual(len(result["frames"]), 1)
            self.assertEqual(result["source_media"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
