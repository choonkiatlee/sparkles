"""The owner-triggered 360 batch selects only vetted, plausible candidates."""
import json
import tempfile
import unittest
from pathlib import Path

from diamond_catalogue.reference_batch import batch_targets


class ReferenceBatchTests(unittest.TestCase):
    def test_batch_tracks_current_eligible_refs_as_new_lessons_are_added(self):
        from diamond_catalogue.references import REFERENCE_DIR
        from diamond_retrieval.resolvers import Loupe360CertificateResolver
        selected = batch_targets()
        self.assertEqual(selected, tuple(sorted(set(selected))))
        records = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in REFERENCE_DIR.glob("*.json")
        }
        self.assertGreaterEqual(len(records), 23)
        self.assertTrue(set(selected) <= set(records))
        for ref_id, record in records.items():
            identity = record["identity"]
            full_report = identity["status"] in {"reported", "linked"} and bool(
                identity["lab"] and identity["report_number"]
            )
            supported_viewer = any(
                media["kind"] == "viewer"
                and Loupe360CertificateResolver._is_supported_rotation_url(media["url"])
                for media in record.get("media_sources", [])
            )
            complete_motion = any(
                evidence.get("kind") == "rotation"
                and evidence.get("status") == "success"
                and len(evidence.get("frames", [])) == 256
                for evidence in record.get("evidence", [])
            )
            self.assertEqual(ref_id in selected, (full_report or supported_viewer) and not complete_motion)

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
