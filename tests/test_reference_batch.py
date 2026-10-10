"""The owner-triggered 360 batch selects only vetted, plausible candidates."""
import json
import tempfile
import unittest
from pathlib import Path

from diamond_catalogue.reference_batch import batch_targets


class ReferenceBatchTests(unittest.TestCase):
    def test_current_reviewed_inventory_only_selects_full_reports(self):
        self.assertEqual(batch_targets(), (
            "ps285166-r02", "ps285166-r04", "ps285166-r05",
            "ps285166-r06", "ps285166-r08", "ps285166-r10",
            "ps285166-r11",
        ))

    def test_unsupported_opaque_loupe_or_v360_viewer_not_dispatched(self):
        from diamond_catalogue.references import SCHEMA
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def record(ref_id, viewer):
                return {
                    "schema": SCHEMA, "id": ref_id, "label": ref_id,
                    "identity": {"status": "unverified", "lab": None, "report_number": None},
                    "diamond_metadata": {}, "commentary": "Example teaching case.",
                    "source_links": [{"kind": "discussion", "url": "https://pricescope.com/example"}],
                    "media_sources": [{
                        "kind": "viewer", "provider": "curator",
                        "status": "linked_unverified", "url": viewer,
                    }],
                    "topics": [], "evidence": [],
                }
            candidates = (
                ("supported", "https://vision.diajewel360.com/Vision360.html?d=EXACT-42"),
                ("loupe-numeric", "https://loupe360.com/diamond/636493231"),
                ("opaque", "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b"),
            )
            for ref_id, viewer in candidates:
                (root / f"{ref_id}.json").write_text(json.dumps(record(ref_id, viewer)))
            self.assertEqual(batch_targets(root), ("supported",))


if __name__ == "__main__":
    unittest.main()
