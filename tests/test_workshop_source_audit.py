"""Read-only Workshop exact-source diagnostic contract tests (#221)."""
from __future__ import annotations

import unittest

from diamond_retrieval.protocols import HttpResponse
from tests.test_diamond_retrieval_motion import (
    AUDITS, FakeHttpClient, _progressive_source_responses,
)
from tools.audit_workshop_references import SOURCES, audit


class WorkshopAuditTests(unittest.TestCase):
    def test_missing_bootstraps_report_missing_not_motion(self):
        for reference_id, viewer in SOURCES.items():
            client = FakeHttpClient({})
            rows = audit(client, reference_id, viewer)
            self.assertEqual([r["status"] for r in rows], [404, 404])
            self.assertTrue(all(r.get("valid_progressive_contract") is not True for r in rows))
            self.assertEqual(len(client.calls), 2)

    def test_403_halts_without_variant_enumeration(self):
        class Forbidden:
            def __init__(self):
                self.calls = []

            def get(self, url, *, timeout):
                self.calls.append(url)
                return HttpResponse(403, url, {"Content-Type": "text/plain"}, b"blocked")

        for reference_id, viewer in SOURCES.items():
            client = Forbidden()
            rows = audit(client, reference_id, viewer)
            self.assertEqual(rows[0]["status"], 403)
            self.assertEqual(len(client.calls), 1)

    def test_complete_known_workshop_bootstrap_is_detected_without_batches(self):
        reference_id, viewer = next(iter(SOURCES.items()))
        from diamond_retrieval.motion_sources import WorkshopRotationDownloader
        from diamond_retrieval.models import ROTATION, EvidenceReference
        reference = EvidenceReference(reference_id, ROTATION, viewer, viewer)
        root = WorkshopRotationDownloader(None)._source(reference)[1]
        responses = _progressive_source_responses(AUDITS[1], root, version=2)
        self.assertIn(root + "/0.json?version=", responses)
        client = FakeHttpClient(responses)
        rows = audit(client, reference_id, viewer)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], 200)
        self.assertTrue(rows[0]["valid_progressive_contract"])
        self.assertEqual(rows[0]["version"], "2")
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
