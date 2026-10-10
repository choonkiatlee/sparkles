"""Network-free contract tests for the exact R05 source diagnostic."""
import json
import unittest
from tools.filesonsky_r05_audit import describe_html, status_for_bootstrap, ROOTS, HOST


class FilesOnSkyAuditTests(unittest.TestCase):
    def test_only_fixed_same_origin_roots(self):
        self.assertEqual(HOST, "www.filesonsky.com")
        self.assertEqual(len(ROOTS), 2)
        self.assertTrue(all(root.startswith("https://" + HOST + "/") for root in ROOTS))
        self.assertTrue(all(root.endswith("/659844") for root in ROOTS))

    def test_html_diagnostics_strip_source_queries(self):
        page = (b'<html><script src="/v360/player.js?access=secret"></script>'
                b'<script>var x="imaged/659844/0.json"</script></html>')
        result = describe_html(page)
        self.assertTrue(result["mentions_imaged"])
        self.assertTrue(result["mentions_json"])
        self.assertEqual(result["scripts"][0]["host"], HOST)
        self.assertEqual(result["scripts"][0]["path_suffix"], "player.js")
        self.assertTrue(result["scripts"][0]["has_query"])
        self.assertNotIn("secret", json.dumps(result))

    def test_bad_bootstrap_is_never_treated_as_motion(self):
        for payload in (b"not json", b"{}", b'{"width":100,"height":100}',
                        b'{"width":100,"height":100,"scramble":"x","version":1}'):
            result = status_for_bootstrap(payload)
            self.assertEqual(result["wire"], "not-progressive-bootstrap")
            self.assertNotIn("dimensions", result)


if __name__ == "__main__":
    unittest.main()
