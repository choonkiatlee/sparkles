import unittest

from diamond360 import asscher_geometry_method_comparison as comparison


MANIFEST = "fixed-manifest"
OLD = {"wireframe_revision": comparison.OLD_REVISION}
NEW = {"wireframe_revision": comparison.NEW_REVISION}


def report(method, stones):
    return {"benchmark_inputs": {"manifest_canonical_sha256": MANIFEST},
            "frozen_method": method, "stones": stones}


class MethodComparisonTests(unittest.TestCase):
    def test_stability_pairs_stones_and_retains_missing_not_zero(self):
        old = report(OLD, [
            {"certificate": "B", "primary": {"status": "review"},
             "estimator_stability": {
                 "run_count": 7,
                 "max_boundary_displacement_tier_fraction": .99}},
            {"certificate": "A", "primary_result_status": "unavailable"},
        ])
        new = report(NEW, [
            {"certificate": "A", "primary_result_status": "unavailable"},
            {"certificate": "B", "primary": {"status": "ok"},
             "estimator_stability": {
                 "run_count": 5,
                 "max_boundary_displacement_tier_fraction": .30}}
        ])
        outcome = comparison.compare("stability", old, new)
        self.assertEqual([r["certificate"] for r in outcome["stones"]],
                         ["A", "B"])
        self.assertIsNone(
            outcome["stones"][0]["max_boundary_displacement_tier_delta"]
        )
        self.assertAlmostEqual(
            outcome["stones"][1]["max_boundary_displacement_tier_delta"], -.69
        )
        self.assertEqual(
            outcome["stones"][1]["leave_one_out_count_after"], 5
        )

    def test_stress_preserves_gauge_failure_and_condition_matching(self):
        def row(status, gauge):
            return {"certificate": "A", "conditions": [
                {"condition_id": "blur", "geometry_comparison": {
                    "status": status,
                    "max_boundary_displacement_tier_fraction": None
                }, "identity_detail": {"gauge_consistent": gauge}}
            ]}
        result = comparison.compare("stress", report(OLD, [row("review", True)]),
                                   report(NEW, [row("unavailable", False)]))
        condition = result["stones"][0]["conditions"][0]
        self.assertIsNone(condition["max_boundary_tier_delta"])
        self.assertFalse(condition["gauge_consistent_after"])
        self.assertEqual(condition["status_after"], "unavailable")

    def test_changed_manifest_and_method_fail_closed(self):
        before = report(OLD, [])
        after = report(NEW, [])
        self.assertEqual(comparison.compare("stability", before, after)["stones"], [])
        after["benchmark_inputs"]["manifest_canonical_sha256"] = "changed"
        with self.assertRaises(ValueError):
            comparison.compare("stability", before, after)
        after["benchmark_inputs"]["manifest_canonical_sha256"] = MANIFEST
        after["frozen_method"]["wireframe_revision"] = "unexpected"
        with self.assertRaises(ValueError):
            comparison.compare("stress", before, after)


if __name__ == "__main__":
    unittest.main()
