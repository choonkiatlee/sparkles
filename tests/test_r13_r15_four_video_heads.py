"""Network-free guards for exact-album four-clip HEAD-only source investigation."""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from tools.audit_r13_r15_four_video_heads import (
    MAX_HEAD, _head, check_video_head, observed_album_json,
    observed_mp4_requests, ordered_media_items, summarize_album_items,
    validate_observed_mp4,
)
from tools.audit_r13_r15_imgur import ALBUMS, check_manifest


def event(method, params):
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class ImgurVideoHeadsTests(unittest.TestCase):
    def test_pinned_source_manifest_guards(self):
        self.assertEqual(tuple(ALBUMS), ("R14_R15", "R12_R13"))
        for group in ALBUMS:
            check_manifest(group)
        self.assertEqual(MAX_HEAD, 4)

    def test_only_exact_observed_public_no_query_video_url(self):
        url = "https://i.imgur.com/Abc1234.mp4"
        self.assertEqual(validate_observed_mp4(url, "Abc1234"), url)
        for sample, ident in (
            ("https://i.imgur.com/Abc1234.mp4", "Other99"),
            ("https://evil.example/Abc1234.mp4", "Abc1234"),
            ("https://i.imgur.com.evil.example/Abc1234.mp4", "Abc1234"),
            ("http://i.imgur.com/Abc1234.mp4", "Abc1234"),
            ("https://i.imgur.com/Abc1234.mp4?auth=s", "Abc1234"),
            ("https://i.imgur.com/a/Abc1234.mp4", "Abc1234"),
            ("https://i.imgur.com/Abc1234.jpg", "Abc1234"),
            ("https://i.imgur.com/Abc1234.mp4#part", "Abc1234"),
            ("https://i.imgur.com:8443/Abc1234.mp4", "Abc1234"),
        ):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                validate_observed_mp4(sample, ident)

    def test_json_order_with_unlabeled_video_is_not_stone_identity(self):
        tree = {"data": {"images": [
            {"id": "ThumbAA", "type": "image/jpeg", "width": 640, "height": 430},
            {"id": "VideoAA", "type": "video/mp4", "width": 530, "height": 530},
            {"id": "ThumbBB", "type": "image/jpeg", "width": 640, "height": 430},
            {"id": "VideoBB", "type": "video/mp4", "width": 530, "height": 530},
        ]}}
        items = ordered_media_items(tree)
        self.assertEqual([m["original_id"] for m in items],
                         ["ThumbAA", "VideoAA", "ThumbBB", "VideoBB"])
        out, used = summarize_album_items(items, {}, remaining=MAX_HEAD)
        self.assertEqual(used, 0)
        self.assertEqual([x["album_item_position"] for x in out], [0, 1, 2, 3])
        self.assertTrue(all(x["per_stone_identity"] == "unknown" for x in out))
        self.assertNotIn("VideoAA", json.dumps(out))

    def test_observed_requests_only_not_guessed(self):
        es = [
            event("Network.requestWillBeSent", {
                "requestId": "a", "request": {"url": "https://i.imgur.com/VideoAA.mp4"}, "type": "Media"}),
            event("Network.requestWillBeSent", {
                "requestId": "b", "request": {"url": "https://evil.example/VideoBB.mp4"}, "type": "Media"}),
            event("Network.requestWillBeSent", {
                "requestId": "c", "request": {"url": "https://i.imgur.com/VideoCC.mp4?token=bad"}, "type": "Media"}),
        ]
        observed = observed_mp4_requests(es)
        self.assertEqual(observed, {"VideoAA": "https://i.imgur.com/VideoAA.mp4"})
        item = [{"original_id":"VideoAA", "album_item_position":0,
                 "media_type":"video/mp4", "width":530, "height":530, "source_caption":None},
                {"original_id":"VideoBB", "album_item_position":1,
                 "media_type":"video/mp4", "width":530, "height":530, "source_caption":None}]
        fake = Mock(return_value={"status": "accessible_mp4_metadata"})
        report, used = summarize_album_items(item, observed, remaining=1, check=fake)
        self.assertEqual(used, 1)
        fake.assert_called_once_with("https://i.imgur.com/VideoAA.mp4", "VideoAA")
        self.assertEqual(report[1]["head"]["status"], "no_exact_observed_matching_media_request")

    def test_only_observed_exact_album_json_is_inspected(self):
        body = json.dumps({"data":{"images":[{"id":"VideoAA","type":"video/mp4",
                                              "width":530,"height":530}]}})
        browser = Mock()
        browser.execute_cdp_cmd.return_value = {"body":body,"base64Encoded":False}
        good = event("Network.responseReceived", {"requestId":"x", "response":{
            "url":"https://api.imgur.com/post/v1/albums/mKh7jTv",
            "status":200, "mimeType":"application/vnd.imgur.v1+json",
            "headers":{"Content-Length":len(body)},
        }})
        spoofed = event("Network.responseReceived", {"requestId":"z", "response":{
            "url":"https://evil.example/post/v1/albums/mKh7jTv",
            "status":200,"mimeType":"application/json",
            "headers":{"Content-Length":len(body)},
        }})
        self.assertEqual(
            observed_album_json(browser, [spoofed,good], "https://imgur.com/a/mKh7jTv")[0]["original_id"],
            "VideoAA",
        )
        browser.execute_cdp_cmd.assert_called_once_with(
            "Network.getResponseBody",{"requestId":"x"})
        browser.reset_mock()
        huge = event("Network.responseReceived", {"requestId":"z", "response":{
            "url":"https://api.imgur.com/post/v1/albums/mKh7jTv",
            "status":200, "mimeType":"application/json",
            "headers":{"Content-Length":"151000"},
        }})
        self.assertEqual(observed_album_json(browser,[huge],"https://imgur.com/a/mKh7jTv"),[])
        browser.execute_cdp_cmd.assert_not_called()

    def test_head_uses_no_get_or_redirects(self):
        opener = Mock()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.status = 200
        response.headers.items.return_value = [("Content-Type", "video/mp4"),
                                               ("Content-Length", "912673")]
        opener.open.return_value = response
        status, headers = _head("https://i.imgur.com/VideoAA.mp4",opener=opener)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "video/mp4")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "HEAD")
        response.read.assert_not_called()

    def test_html_200_and_405_cannot_be_validated_video(self):
        with patch("tools.audit_r13_r15_four_video_heads._head",
                   return_value=(200, {"Content-Type":"text/html","Content-Length":"15000"})):
            outcome = check_video_head("https://i.imgur.com/VideoAA.mp4", "VideoAA")
            self.assertEqual(outcome["status"],"unverified_or_unavailable")
        with patch("tools.audit_r13_r15_four_video_heads._head",
                   return_value=(405, {"Content-Type":"video/mp4","Content-Length":"912673"})):
            outcome = check_video_head("https://i.imgur.com/VideoAA.mp4", "VideoAA")
            self.assertEqual(outcome["status"],"unverified_or_unavailable")
        with patch("tools.audit_r13_r15_four_video_heads._head",
                   return_value=(200, {"Content-Type":"video/mp4","Content-Length":"999999999"})):
            outcome = check_video_head("https://i.imgur.com/VideoAA.mp4", "VideoAA")
            self.assertEqual(outcome["status"],"unverified_or_unavailable")


if __name__ == "__main__":
    unittest.main()
