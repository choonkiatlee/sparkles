"""Network-free checks of R03/R09 exact-browser Pixorac recovery audit."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.audit_r03_r09_loupe import CASES
from tools.audit_r03_r09_pixorac import (
    ENCODED_ROOTS, PIXORAC_HOST, observed_source, query_metadata,
    validate_full,
)


def _browser(name, *, root=None, status=200):
    original = CASES[name][1]
    root = ENCODED_ROOTS[name] if root is None else root
    return {"cases": [{
        "reference": CASES[name][0],
        "browser": [{
            "input_route": "landing",
            "page": {"path": "/" + original.split("/", 3)[-1]},
            "relevant_requests": [{
                "resource": {"host": PIXORAC_HOST, "path": "/" + root + "/0.webp"},
                "status": status, "mime_type": "image/webp",
            }],
        }],
    }]}


class R03R09PixoracTests(unittest.TestCase):
    def test_original_browser_must_have_loaded_exact_pinned_proxy(self):
        for name in CASES:
            self.assertEqual(
                observed_source(name, _browser(name)),
                "https://" + PIXORAC_HOST + "/" + ENCODED_ROOTS[name],
            )
        with self.assertRaises(ValueError):
            observed_source("R03", _browser("R03", root=ENCODED_ROOTS["R09"]))
        with self.assertRaises(ValueError):
            observed_source("R09", _browser("R09", status=404))
        with self.assertRaises(ValueError):
            observed_source("R03", _browser("R09"))

    def test_viewer_token_query_does_not_grant_certificate_status(self):
        name = "R03"
        root = "https://" + PIXORAC_HOST + "/" + ENCODED_ROOTS[name]
        response = {"data": {"certificate_by_cert_number": {
            "certNumber": "IGI-UNVERIFIED", "lab": "IGI",
            "v360": {"url": root, "frame_count": 256, "top_index": 123},
        }}}
        client = Mock()
        client.post.return_value = SimpleNamespace(
            status_code=200, content=json.dumps(response).encode()
        )
        item = query_metadata(client, name, root)
        self.assertEqual(item["status"], "proxy_match")
        self.assertEqual(item["top_index"], 123)
        self.assertFalse(item["identity_independently_verified"])
        sent = json.loads(client.post.call_args.kwargs["content"])
        self.assertEqual(sent["variables"]["cert"], "636493231")

        response["data"]["certificate_by_cert_number"]["v360"]["url"] = (
            "https://assets-images.pixorac.com/different-item"
        )
        client.post.return_value.content = json.dumps(response).encode()
        self.assertEqual(query_metadata(client, name, root)["status"], "not_confirmed_256_proxy")

    def test_complete_256_requires_distinct_same_size_frames(self):
        def frame(idx):
            return {"valid": True, "sha256": str(idx), "dimensions": [600, 600]}
        client = Mock()
        with patch("tools.audit_r03_r09_pixorac.request_one",
                   side_effect=lambda _c, _r, idx, _fmt: frame(idx)):
            valid = validate_full(client, "https://assets-images.pixorac.com/pin", "jpg", {})
            self.assertEqual(valid["status"], "complete_256_proxy_frames")
            self.assertEqual(valid["distinct_hashes"], 256)
        with patch("tools.audit_r03_r09_pixorac.request_one",
                   side_effect=lambda _c, _r, idx, _fmt:
                        {"valid": True, "sha256": "same", "dimensions": [600, 600]}):
            static = validate_full(client, "https://assets-images.pixorac.com/pin", "webp", {})
            self.assertEqual(static["status"], "inconsistent_or_effectively_static")
        with patch("tools.audit_r03_r09_pixorac.request_one",
                   side_effect=lambda _c, _r, idx, _fmt:
                        {"valid": idx != 17, "sha256": str(idx), "dimensions": [600, 600]}):
            missing = validate_full(client, "https://assets-images.pixorac.com/pin", "jpg", {})
            self.assertEqual(missing["status"], "incomplete")
            self.assertEqual(missing["first_missing_index"], 17)


if __name__ == "__main__":
    unittest.main()
