"""Network-free reference contract and expert-seed regression tests (#195)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from diamond_catalogue.models import CatalogueError
from diamond_catalogue.references import (
    INDEX_PATH, REFERENCE_DIR, build_index, build_repository_index,
    index_row, validate_reference,
)
from diamond_catalogue.serialization import json_document


def minimal_reference():
    return {
        "schema": "sparkles-reference/1",
        "id": "thread-r01",
        "label": "A teaching diamond",
        "identity": {"status": "unverified", "lab": None, "report_number": None},
        "linked_diamond_id": None,
        "diamond_metadata": {"shape": "Asscher"},
        "commentary": "Reviewer A found it lively; reviewer B disagreed.",
        "source_links": [{"kind": "discussion", "url": "https://www.pricescope.com/community/threads/example/"}],
        "media_sources": [],
        "topics": ["liveliness"],
        "evidence": [],
    }


class ReferenceContractTests(unittest.TestCase):
    def test_minimal_unidentified_reference_is_valid_and_basket_ready(self):
        record = minimal_reference()
        self.assertEqual(validate_reference(record), record)
        row = index_row(record)
        self.assertEqual(row["selection_id"], "ref-thread-r01")
        self.assertEqual(row["manifest_path"], "data/references/thread-r01.json")
        self.assertFalse(row["has_motion"])
        self.assertIsNone(row["thumbnail_url"])
        self.assertEqual(row["commentary_excerpt"], record["commentary"])

    def test_igi_only_is_reported_not_assumed_verified(self):
        record = minimal_reference()
        record["identity"] = {"status": "reported", "lab": "IGI", "report_number": "LG123456789"}
        self.assertEqual(index_row(record)["report_number"], "LG123456789")
        self.assertIsNone(index_row(record)["linked_diamond_id"])

    def test_viewer_only_needs_no_certificate_or_locally_recovered_motion(self):
        record = minimal_reference()
        record["media_sources"] = [{
            "kind": "viewer", "provider": "loupe360",
            "url": "https://loupe360.com/diamond/1498922544",
            "status": "linked_unverified",
        }]
        self.assertEqual(index_row(record)["has_motion"], False)
        self.assertIsNone(record["identity"]["report_number"])

    def test_rejects_mistyped_schema_and_basket_collision(self):
        record = minimal_reference()
        record["id"] = "ref-thread-r01"
        with self.assertRaises(CatalogueError):
            validate_reference(record)
        record = minimal_reference()
        with self.assertRaises(CatalogueError):
            build_index([record], certified_ids=["ref-thread-r01"])
        record["schema"] = "sparkles-diamond-catalogue/1"
        with self.assertRaises(CatalogueError):
            validate_reference(record)

    def test_invalid_or_duplicate_sources_cannot_pass(self):
        record = minimal_reference()
        for url in ("http://pricescope.com/post", "https://127.0.0.1/post",
                    "https://example.com@127.0.0.1/post", "https://localhost/post",
                    "https://example.com/a b"):
            candidate = copy.deepcopy(record)
            candidate["source_links"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(CatalogueError):
                validate_reference(candidate)
        record["source_links"].append(copy.deepcopy(record["source_links"][0]))
        with self.assertRaises(CatalogueError):
            validate_reference(record)

    def test_identity_mismatch_cannot_create_fictitious_certified_link(self):
        record = minimal_reference()
        record["identity"] = {"status": "linked", "lab": "IGI", "report_number": "LG123456789"}
        record["linked_diamond_id"] = "igi-lg999999999"
        with self.assertRaises(CatalogueError):
            validate_reference(record)
        record["linked_diamond_id"] = "igi-lg123456789"
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(CatalogueError):
                validate_reference(record, diamond_dir=Path(folder))
            path = Path(folder) / "igi-lg123456789.json"
            path.write_text(json_document({
                "id": "igi-lg123456789",
                "identity": {"lab": "IGI", "report_number": "LG123456789"},
            }), encoding="utf-8")
            self.assertEqual(validate_reference(record, diamond_dir=Path(folder)), record)

    def test_rejects_duplicate_certificates_without_automatic_merging(self):
        first = minimal_reference()
        first["identity"] = {"status": "reported", "lab": "IGI", "report_number": "LG123456789"}
        second = copy.deepcopy(first)
        second["id"] = "thread-r02"
        with self.assertRaises(CatalogueError):
            build_index([first, second])

    def test_seed_inventory_preserves_distinct_stones_and_six_remote_viewers(self):
        paths = sorted(REFERENCE_DIR.glob("*.json"))
        self.assertGreaterEqual(len(paths), 11)
        records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in paths}
        for stem, record in records.items():
            self.assertEqual(validate_reference(record, expected_id=stem), record)
            self.assertTrue(record["commentary"].strip())
            self.assertIsInstance(record["evidence"], list)  # Enrichment may add original stills/motion.
            self.assertIn(record["identity"]["status"], ("unverified", "reported", "linked"))
            self.assertTrue(record["source_links"])
        self.assertGreaterEqual(sum(len(r["media_sources"]) for r in records.values()), 6)
        self.assertTrue(all(f"ps285166-r{i:02d}" in records for i in range(1, 12)))
        self.assertNotEqual(records["ps285166-r05"]["identity"]["report_number"],
                            records["ps285166-r10"]["identity"]["report_number"])
        self.assertIsNone(records["ps285166-r03"]["identity"]["report_number"])
        self.assertIsNone(records["ps285166-r09"]["identity"]["report_number"])
        self.assertEqual(records["ps285166-r07"]["media_sources"][0]["provider"], "v360.diamonds")
        self.assertIn("GROUP", records["ps285166-r06"]["commentary"])

    def test_index_is_deterministic_checked_in_and_uses_safe_paths(self):
        regenerated = build_repository_index()
        self.assertGreaterEqual(len(regenerated["references"]), 11)
        self.assertEqual(INDEX_PATH.read_text(encoding="utf-8"), json_document(regenerated))
        ids = [row["id"] for row in regenerated["references"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(row["selection_id"] for row in regenerated["references"])), len(regenerated["references"]))
        self.assertTrue(all(row["manifest_path"] == f"data/references/{row['id']}.json"
                            for row in regenerated["references"]))


if __name__ == "__main__":
    unittest.main()
