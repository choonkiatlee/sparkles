"""Network-free provenance and safety tests for R03/R09 source investigation."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from tools.audit_r03_r09_loupe import (
    CASES, ROOT, SUFFIXES, probe_http, validate_manifest,
    validate_route, wire_type,
)


class OpaqueLoupeAuditTests(unittest.TestCase):
    def test_both_reviewed_sources_are_unverified_opaque_viewers(self):
        self.assertEqual(set(CASES), {"R03", "R09"})
        for name, (reference_id, url) in CASES.items():
            with self.subTest(name=name):
                record = json.loads(
                    (ROOT / "data" / "references" / (reference_id + ".json")).read_text("utf-8")
                )
                self.assertEqual(validate_manifest(name, record), url)
                self.assertIsNone(record["identity"]["report_number"])

    def test_fail_closed_if_identity_source_or_evidence_changes(self):
        name = "R03"
        reference_id = CASES[name][0]
        record = json.loads(
            (ROOT / "data" / "references" / (reference_id + ".json")).read_text("utf-8")
        )
        for mutated in (
            {**record, "identity": {"status": "reported", "lab": "IGI", "report_number": "LG636493231"}},
            {**record, "media_sources": []},
            {**record, "id": "wrong-stone"},
            {**record, "evidence": [{"kind": "rotation"}]},
        ):
            with self.subTest(mutated=list(mutated)):
                with self.assertRaises(ValueError):
                    validate_manifest(name, mutated)

    def test_only_exact_pre_reviewed_routes(self):
        for name in CASES:
            for suffix in SUFFIXES:
                self.assertTrue(validate_route(name, suffix).startswith("https://loupe360.com/diamond/"))
        for name, suffix in (
            ("R03", "/video/900/900"), ("R03", "/../../../admin"),
            ("R09", "?report=1498922544"), ("R05", ""), ("R09", "//a"),
        ):
            with self.subTest(name=name, suffix=suffix):
                with self.assertRaises(ValueError):
                    validate_route(name, suffix)

    def test_html_200_is_not_recoverable_motion(self):
        self.assertEqual(wire_type(b"<!doctype html><html>fallback</html>"), "html_not_motion")
        self.assertEqual(wire_type(b"xxxxftypisom"), "mp4_candidate_unverified")
        self.assertEqual(wire_type(bytes.fromhex("ffd8ff") + b"x"), "jpeg_candidate_unverified")
        self.assertEqual(wire_type(b'{"frames":256}'), "other_not_verified")

    def test_http_probe_does_not_mark_html_as_rotation(self):
        client = Mock()
        client.get.return_value = SimpleNamespace(
            status_code=200, content=b"<html>app shell</html>",
            url=CASES["R03"][1],
        )
        out = probe_http(client, "R03", "")
        self.assertEqual(out["type"], "html_not_motion")
        self.assertEqual(out["http"], 200)
        self.assertEqual(out["redirected"], False)
        client.get.assert_called_once_with(CASES["R03"][1], timeout=12)


if __name__ == "__main__":
    unittest.main()
