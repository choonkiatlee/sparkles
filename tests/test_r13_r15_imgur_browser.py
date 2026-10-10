"""No-network contract tests for exact Imgur browser metadata audit."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tools.audit_r13_r15_imgur_browser import (
    BLOCKED_MEDIA_PATTERNS, _label_signals, _url_details,
    media_url_details, summarize_dom, summarize_network,
    disposition, inspect_pair,
)


def event(method, params):
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class BrowserAuditTests(unittest.TestCase):
    def test_media_block_policy_covers_media_and_still_image_urls(self):
        for suffix in (".mp4", ".webm", ".gif", ".jpg", ".png", ".webp", ".m3u8"):
            self.assertTrue(any(suffix in p for p in BLOCKED_MEDIA_PATTERNS), suffix)

    def test_first_party_video_only_no_secret_or_spoofed_domain(self):
        valid = media_url_details("https://i.imgur.com/Abc1234.mp4?token=secret")
        self.assertEqual(valid["host"], "i.imgur.com")
        self.assertTrue(valid["query_present"])
        self.assertNotIn("token", str(valid))
        self.assertNotIn("Abc1234", str(valid))
        for url in (
            "http://i.imgur.com/abc1234.mp4",
            "https://i.imgur.com.evil.example/a.mp4",
            "https://127.0.0.1/a.mp4",
            "https://evil.example/a.mp4",
            "https://i.imgur.com/a.jpg",
            "file:///tmp/a.mp4",
        ):
            with self.subTest(url=url):
                self.assertIsNone(media_url_details(url))

    def test_dom_hints_do_not_prove_clip_count_or_attribution(self):
        dom = summarize_dom({
            "ready_state": "complete", "video_elements": [
                {"src": "https://i.imgur.com/abc1234.mp4", "poster": "https://i.imgur.com/pic.jpg",
                 "video_width": 0, "video_height": 0, "title": "first", "duration_known": False}],
            "item_nodes_detected": 2, "item_labels": [
                {"label": "first stone", "heading": "2.00 ct", "video_count": 1},
                {"label": "second stone", "heading": "2.00 ct", "video_count": 0}],
        })
        self.assertEqual(dom["video_nodes"], 1)
        self.assertTrue(dom["item_signals"][0]["first"])
        self.assertTrue(dom["item_signals"][1]["second"])
        self.assertEqual(disposition("R14_R15", dom, {})["per_stone_attribution"], "unknown")
        self.assertFalse(disposition("R14_R15", dom, {})["original_clip_count_verified"])
        self.assertNotIn("abc1234", str(dom))

    def test_network_only_media_metadata_reports_blocked_but_not_downloaded(self):
        rows = [
            event("Network.requestWillBeSent", {"requestId": "r1", "request": {
                "url": "https://i.imgur.com/abc1234.mp4?secret=abc"},
                "type": "Media"}),
            event("Network.loadingFailed", {"requestId": "r1", "errorText": "net::ERR_BLOCKED_BY_CLIENT"}),
            event("Network.requestWillBeSent", {"requestId": "r2",
                "request": {"url": "https://i.imgur.com/img1234.jpg"}, "type": "Image"}),
            event("Network.requestWillBeSent", {"requestId": "r3",
                "request": {"url": "https://imgur.com/album-code.js"}, "type": "Script"}),
        ]
        x = summarize_network(rows)
        self.assertEqual(x["media_requests_seen"], 2)
        self.assertEqual(x["blocked_by_browser"], 1)
        self.assertEqual(x["video_requests_seen"], 1)
        self.assertNotIn("secret", str(x))
        self.assertNotIn("abc1234", str(x))

    def test_unverified_identity_for_single_video_and_region_block(self):
        x = disposition("R12_R13", {"video_nodes": 1}, {"video_requests_seen": 1})
        self.assertEqual(x["status"], "video_hint_observed_not_attributed")
        self.assertEqual(x["per_stone_attribution"], "unknown")
        self.assertFalse(x["playable_motion_verified"])
        y = disposition("R14_R15", {"region_block_message": True}, {})
        self.assertEqual(y["status"], "region_or_access_blocked")

    def test_site_navigation_pinned_and_media_block_before_page_load(self):
        class Driver:
            current_url = "https://imgur.com/a/mKh7jTv"
            def __init__(self):
                self.calls = []
            def execute_cdp_cmd(self, name, args):
                self.calls.append(("cdp", name))
            def get(self, url):
                self.calls.append(("get", url))
            def execute_script(self, _code):
                return {"ready_state": "complete", "body_block_message": False,
                        "video_elements": [], "item_labels": []}
            def get_log(self, category):
                self.calls.append(("get_log", category))
                return []
        driver = Driver()
        with patch("tools.audit_r13_r15_imgur_browser.time.sleep"):
            result = inspect_pair("R14_R15", driver)
        self.assertEqual(driver.calls[:3], [
            ("cdp", "Network.enable"), ("cdp", "Network.setBlockedURLs"),
            ("get", "https://imgur.com/a/mKh7jTv"),
        ])
        self.assertTrue(result["final_album_page"])
        self.assertFalse(result["media_downloaded"])
        self.assertEqual(result["decision"]["per_stone_attribution"], "unknown")

    def test_redirect_away_is_not_trusted_media(self):
        class RedirectDriver:
            current_url = "https://evil.example/other"
            def execute_cdp_cmd(self, *_args): pass
            def get(self, *_args): pass
            def get_log(self, *_args): return []
        with patch("tools.audit_r13_r15_imgur_browser.time.sleep"):
            out = inspect_pair("R14_R15", RedirectDriver())
        self.assertEqual(out["status"], "navigation_outside_exact_album")
        self.assertEqual(out["decision"]["status"], "no_trusted_page")


if __name__ == "__main__":
    unittest.main()
