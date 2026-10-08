"""Owner-only issue ingestion event contract."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.parse_diamond_ingest_issue import (
    REQUEST_MARKER, url_from_issue_event, validate_listing_url,
)

REPO = "choonkiatlee/sparkles"
QD = "https://www.qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=133/CE7EED747"
DIYONA = "https://diyona.com/pages/diamond-detail?sku=B934F4533"


def issue(url=QD, *, actor="choonkiatlee", body=None, title="Ingest diamond", action="opened"):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "issue": {
            "user": {"login": actor},
            "title": title,
            "body": body if body is not None else f"{REQUEST_MARKER}\nDiamond URL: {url}\n",
        },
    }


class DiamondIssueRequestTests(unittest.TestCase):
    def test_genuine_owner_event_dispatches_exact_pasted_listing(self):
        for url in (QD, DIYONA, QD.replace("133/", "133%2F")):
            with self.subTest(url=url):
                self.assertEqual(url_from_issue_event(issue(url)), url)

    def test_only_issue_creator_identity_authorizes(self):
        for actor in ("attacker", "someone_else", "Choonkiatlee", ""):
            with self.subTest(actor=actor):
                with self.assertRaises(ValueError):
                    url_from_issue_event(issue(actor=actor))

    def test_other_issues_and_extra_content_are_not_ingestion_requests(self):
        bad = [
            issue(title="Please ingest diamond"),
            issue(action="edited"),
            issue(body=f"{REQUEST_MARKER}\nDiamond URL: {QD}\n\nMalicious: true"),
            issue(body=f"Diamond URL: {QD}"),
            issue(body=f"{REQUEST_MARKER}\nDiamond URL: {QD}\nDiamond URL: {DIYONA}"),
            issue(body=f"{REQUEST_MARKER}\nDiamond URL: {QD}\nGH_OUTPUT=x"),
        ]
        changed_repo = issue()
        changed_repo["repository"]["full_name"] = "someone/sparkles"
        bad.append(changed_repo)
        changed_pr = issue()
        changed_pr["issue"]["pull_request"] = {"url": "https://example.com/"}
        bad.append(changed_pr)
        for event in bad:
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    url_from_issue_event(event)

    def test_url_validator_rejects_nonretailer_and_noncanonical_urls(self):
        bad = [
            "http://diyona.com/pages/diamond-detail?sku=A",
            "https://diyona.com/pages/diamond-detail?sku=../a",
            "https://diyona.com/pages/diamond-detail",
            "https://qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=133",
            QD + "&extra=1", QD + "\nmalicious=true",
            QD.replace("www.qualitydiamonds.co.uk", "www.qualitydiamonds.co.uk.attacker.com"),
            "https://localhost/pages/diamond-detail?sku=ABC",
            "javascript:alert(1)",
            QD.replace("https://", "https://user:secret@"),
            QD + "#fragment",
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_listing_url(value)

    def test_command_writes_single_safe_workflow_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "event.json"
            destination = Path(directory) / "output.txt"
            source.write_text(json.dumps(issue()), encoding="utf-8")
            subprocess.run([
                sys.executable, "tools/parse_diamond_ingest_issue.py",
                "--event", str(source), "--github-output", str(destination),
            ], check=True)
            self.assertEqual(destination.read_text(encoding="utf-8"), f"diamond_url={QD}\n")


if __name__ == "__main__":
    unittest.main()
