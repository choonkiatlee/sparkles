"""Network-free guardrails for the read-only paired Imgur album audit."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.audit_r13_r15_imgur import (
    ALBUMS, analyze_html, audit_one, candidates_from_html,
    check_manifest, validate_album, validate_media,
)


class SourceAuditTests(unittest.TestCase):
    def test_exact_curated_pairs(self):
        for name, (url, refs) in ALBUMS.items():
            self.assertEqual(validate_album(url), url)
            self.assertEqual(len(refs), 2)
            check_manifest(name)
        with self.assertRaises(ValueError):
            validate_album("https://imgur.com/a/guess")

    def test_public_candidate_host_and_direct_suffix_only(self):
        self.assertEqual(
            validate_media("https://i.imgur.com/abcde12.mp4"),
            "https://i.imgur.com/abcde12.mp4",
        )
        for url in (
            "http://i.imgur.com/abcde12.mp4",
            "https://attacker.test/abcde12.mp4",
            "https://i.imgur.com/abcde12.mp4?token=a",
            "https://i.imgur.com/abcde12.jpg",
            "https://127.0.0.1/abcde12.mp4",
            "https://i.imgur.com.evil.test/abcde12.mp4",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_media(url)

    def test_embedded_hints_without_claiming_clip_identity(self):
        html = (
            '<!doctype html><html><meta property="og:video" '
            'content="https://i.imgur.com/abcde12.mp4">'
            '<video src="https://i.imgur.com/xyza987.webm"></video></html>'
        )
        self.assertEqual(len(candidates_from_html(html)), 2)
        result = analyze_html(200, {"Content-Type": "text/html"}, html.encode())
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["attribution"], "unverified")
        self.assertFalse(result["clip_count_verified"])
        self.assertNotIn("https://i.imgur.com", str(result))

    def test_html_200_is_not_a_video_and_no_hints_is_not_no_media(self):
        h = b"<!doctype html><html>content unavailable in your region</html>"
        result = analyze_html(200, {"Content-Type": "text/html"}, h)
        self.assertEqual(result["status"], "public_album_html_no_media_hints")
        self.assertFalse(result["clip_count_verified"])
        self.assertEqual(
            analyze_html(200, {"Content-Type": "video/mp4"}, b"abc")["status"],
            "not_album_html",
        )
        self.assertEqual(
            analyze_html(403, {"Content-Type": "text/html"}, b"")["status"],
            "http_denied_or_unavailable",
        )
        self.assertEqual(
            analyze_html(302, {"Location": "https://other.test"}, b"")["status"],
            "redirect_blocked",
        )

    def test_album_no_video_download_and_no_stone_assignment(self):
        with patch(
            "tools.audit_r13_r15_imgur._request",
            return_value=(
                200, {"Content-Type": "text/html"},
                b'<!doctype html><html><source src="https://i.imgur.com/abcde12.mp4"></html>',
            ),
        ) as call:
            outcome = audit_one("R14_R15")
            self.assertEqual([c.args[1] for c in call.call_args_list], ["GET", "HEAD"])
            self.assertEqual(outcome["per_stone_clip_mapping"], "unknown")
            self.assertFalse(outcome["media_downloaded"])
            self.assertEqual(outcome["candidate_count"], 1)

    def test_failed_transport_abstains(self):
        with patch("tools.audit_r13_r15_imgur._request", side_effect=OSError("offline")):
            outcome = audit_one("R12_R13")
        self.assertEqual(outcome["status"], "bounded_transport_error")
        self.assertEqual(outcome["original_clip_count"], "unknown")


if __name__ == "__main__":
    unittest.main()
