"""Network-free tests for safe, attribution-abstaining paired Imgur browser metadata."""
from __future__ import annotations

import json
import unittest

from tools.audit_r13_r15_imgur_browser import (
    MEDIA_BLOCK_PATTERNS, classify_browser, safe_location,
    sanitise_labels, summarize_performance, _metadata_items, inspect_observed_album_json,
)
from tools.audit_r13_r15_imgur import ALBUMS, check_manifest


class BrowserAuditTests(unittest.TestCase):
    def test_pinned_albums_and_unverified_identity(self):
        self.assertEqual(tuple(ALBUMS), ("R14_R15", "R12_R13"))
        for group in ALBUMS:
            check_manifest(group)

    def test_media_requests_are_blocked_before_browser_navigation(self):
        self.assertIn("*://i.imgur.com/*", MEDIA_BLOCK_PATTERNS)
        self.assertTrue(any(".mp4" in pattern for pattern in MEDIA_BLOCK_PATTERNS))
        self.assertTrue(any(".webm" in pattern for pattern in MEDIA_BLOCK_PATTERNS))

    def test_url_token_and_unreviewed_media_path_not_disclosed(self):
        obj = safe_location("https://i.imgur.com/abcde12.mp4?token=sensitive")
        self.assertEqual(obj["provider"], "imgur")
        self.assertTrue(obj["looks_like_video"])
        self.assertTrue(obj["query_present"])
        self.assertNotIn("token", json.dumps(obj))
        self.assertNotIn("abcde12", json.dumps(obj))
        self.assertEqual(safe_location("http://localhost/video.mp4")["valid_https"], False)
        self.assertEqual(safe_location("https://i.imgur.com.evil.org/xx.mp4")["provider"], "other")

    def test_labels_cannot_imply_a_specific_stone_media(self):
        labels = sanitise_labels([
            {"role": "h1", "text": "Pair of 2.00ct Asschers"},
            {"role": "caption", "text": "Second stone"},
            {"role": "unreviewed_role", "text": "ignored"},
        ])
        self.assertEqual(len(labels), 2)
        obj = classify_browser({
            "title": "Asscher videos",
            "video_nodes": [{"source": "https://i.imgur.com/abcde12.mp4"}],
            "image_nodes": 1, "figure_nodes": 0,
            "labels": labels,
        }, [], current_url="https://imgur.com/a/mKh7jTv")
        self.assertEqual(obj["status"], "browser_dom_media_elements_observed")
        self.assertFalse(obj["clip_count_verified"])
        self.assertFalse(obj["media_original_bytes_downloaded"])
        self.assertEqual(obj["per_stone_clip_mapping"], "unknown")
        self.assertNotIn("abcde12.mp4", json.dumps(obj))

    def test_geo_block_no_false_no_media(self):
        obj = classify_browser({
            "title": "Imgur",
            "video_nodes": [], "image_nodes": 0, "figure_nodes": 0,
            "body_signals": {"geo_restriction": True},
        }, [], current_url="https://imgur.com/a/mKh7jTv")
        self.assertEqual(obj["status"], "region_or_access_restricted")
        self.assertEqual(obj["per_stone_clip_mapping"], "unknown")
        self.assertEqual(
            classify_browser({}, [], current_url="https://malicious.example/video.mp4")["status"],
            "redirected_outside_reviewed_album_host",
        )

    def test_network_metadata_no_raw_urls_or_media_bytes(self):
        events = [
            {"message": json.dumps({"message": {
                "method": "Network.requestWillBeSent",
                "params": {"requestId": "x", "type": "Media",
                           "request": {"url": "https://i.imgur.com/abcde12.mp4?secret=abc"}},
            }})},
            {"message": json.dumps({"message": {
                "method": "Network.loadingFailed",
                "params": {"requestId": "x"},
            }})},
            {"message": json.dumps({"message": {
                "method": "Network.responseReceived",
                "params": {"requestId": "missing",
                           "response": {"status": 200, "mimeType": "video/mp4"}},
            }})},
        ]
        out = summarize_performance(events)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["location"]["looks_like_video"])
        self.assertTrue(out[0]["request_failed_or_blocked"])
        self.assertNotIn("secret", json.dumps(out))
        self.assertNotIn("abcde12", json.dumps(out))


    def test_generic_imgur_homepage_is_not_album_media(self):
        page = {
            "title": "Imgur: The magic of the Internet",
            "image_nodes": 15, "figure_nodes": 0, "video_nodes": [],
            "labels": [{"role": "h3", "text": "NEWEST IN MOST VIRAL"}],
        }
        result = classify_browser(page, [], current_url="https://imgur.com/a/mKh7jTv",
                                  expected_url="https://imgur.com/a/mKh7jTv")
        self.assertEqual(result["status"], "generic_homepage_no_album_identity")
        self.assertTrue(result["exact_album_path_preserved"])
        self.assertEqual(
            classify_browser(page, [], current_url="https://imgur.com/",
                             expected_url="https://imgur.com/a/mKh7jTv")["status"],
            "browser_navigated_away_from_reviewed_album",
        )

    def test_only_small_observed_same_album_api_json(self):
        from unittest.mock import Mock
        token = "mKh7jTv"
        fake = Mock()
        fake.execute_cdp_cmd.return_value = {
            "body": json.dumps({"data": {"media": [
                {"id": "a12345", "type": "video/mp4", "width": 500, "height": 400,
                 "description": "First Asscher"},
                {"id": "b12345", "type": "video/mp4", "width": 600, "height": 500,
                 "description": "Second Asscher"},
            ]}}),
            "base64Encoded": False,
        }
        entry = lambda url, size="2000": {"message": json.dumps({"message": {
            "method": "Network.responseReceived",
            "params": {"requestId": url, "response": {
                "url": url, "status": 200, "mimeType": "application/vnd.imgur.v1+json",
                "headers": {"Content-Length": size},
            }},
        }})}
        events = [
            entry("https://api.imgur.com/post/v1/albums/other"),
            entry("https://api.imgur.com/post/v1/albums/" + token, "300000"),
            entry("https://api.imgur.com/post/v1/albums/" + token, "2000"),
        ]
        out = inspect_observed_album_json(fake, events, "https://imgur.com/a/" + token)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["media_item_hints"]), 2)
        self.assertNotIn("a12345", json.dumps(out))
        self.assertEqual(fake.execute_cdp_cmd.call_count, 1)
        self.assertEqual(_metadata_items({"title": "Not media"}), [])


if __name__ == "__main__":
    unittest.main()
