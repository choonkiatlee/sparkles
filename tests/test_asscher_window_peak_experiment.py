"""Falsification tests for target-blind window-local step peak experiment."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_steps as steps
from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_geometry_window_peak_comparison as compare
from diamond360 import asscher_wireframe as wireframe


class WindowLocalPeakExperimentTests(unittest.TestCase):
    def test_semantic_window_prevents_stronger_outside_peak_suppressing_c3(self):
        u = np.linspace(0, 1, 160)
        def gaussian(centre, amplitude, sigma=.006):
            return amplitude * np.exp(-.5 * ((u-centre)/sigma)**2)
        # The outside peak is stronger but is not a valid C3 candidate.
        curve = (gaussian(.48, .10) + gaussian(.579, 1.) +
                 gaussian(.629, 1.04) + gaussian(.735, 1.2) +
                 gaussian(.87, 1.1))
        data = np.tile(curve, (5, 8, 1))
        original = steps.discover_template(data, u)
        explicit = steps.discover_template(
            data, u, peak_policy=steps.GLOBAL_PEAK_POLICY
        )
        alternative = steps.discover_template(
            data, u, peak_policy=steps.WINDOW_PEAK_POLICY
        )
        self.assertEqual(
            [round(c["u"], 8) for c in original["candidates"]],
            [round(c["u"], 8) for c in explicit["candidates"]],
        )
        valid = lambda result: [
            c["u"] for c in result["candidates"]
            if .565 < c["u"] < .59
        ]
        self.assertEqual(valid(original), [])
        self.assertEqual(len(valid(alternative)), 1)
        self.assertTrue(all(
            any(lo <= row["u"] <= hi for lo, hi in steps.BOUNDARY_WINDOWS)
            for row in alternative["candidates"]
        ))

    def test_no_cross_window_threshold_or_per_stone_override(self):
        config = steps.experimental_peak_policy_specification()
        self.assertEqual(config, validation.FROZEN_WINDOW_EXPERIMENT_POLICY)
        self.assertEqual(config["boundary_windows"],
                         [[.42,.60],[.64,.82],[.82,.92]])
        self.assertFalse(config["physical_facet_claim"])
        self.assertTrue(validation.assert_frozen_method(validation.WINDOW_METHOD))
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertEqual(
            validation.frozen_method_record(validation.OUTER_METHOD)[
                "wireframe_specification_sha256"
            ],
            validation.frozen_method_record(validation.WINDOW_METHOD)[
                "wireframe_specification_sha256"
            ],
        )
        self.assertNotEqual(
            validation.frozen_method_record(validation.OUTER_METHOD)[
                "method_revision"
            ],
            validation.frozen_method_record(validation.WINDOW_METHOD)[
                "method_revision"
            ],
        )

    def test_stability_method_switch_only_sets_inner_peak_policy(self):
        metadata = [
            {"source_index": i, "position": i} for i in (13,16,17,18)
        ]
        evidence = np.zeros((4, 8, 160))
        fixture = (evidence, np.linspace(0,1,160),
                   [np.ones((32,32),bool)]*4, [np.ones((32,32))]*4,
                   metadata)
        outer = {
            "vertices_topology_order": [[float(i), float(i)] for i in range(8)],
            "confidence": .96,
        }
        with patch.object(stability, "_load_evidence", return_value=fixture), \
             patch.object(stability.outer_octagon,"fit_consensus",
                          return_value=outer), \
             patch.object(wireframe, "fit_from_sector_evidence",
                          return_value={"scaffold":{}, "status":"ok"}) as fit:
            stability._fit_records(
                "/unused", metadata, "g", method=validation.WINDOW_METHOD
            )
        self.assertEqual(fit.call_args.kwargs["step_peak_policy"],
                         steps.WINDOW_PEAK_POLICY)
        self.assertEqual(fit.call_args.kwargs["outer_confidence"], .96)

    def test_comparison_rejects_swapped_controls_and_source_changes(self):
        fingerprint = validation.BENCHMARK_MANIFEST_CANONICAL_SHA256
        def record(method):
            return {"frozen_method": {"method_revision": method},
                    "benchmark_inputs": {"manifest_canonical_sha256":
                                         fingerprint}, "stones": []}
        old, new = record(validation.OUTER_METHOD), record(validation.WINDOW_METHOD)
        self.assertEqual(compare.compare("stability", old, new)["stones"], [])
        bad = copy.deepcopy(new)
        bad["benchmark_inputs"]["manifest_canonical_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "changed frozen"):
            compare.compare("stability", old, bad)
        with self.assertRaisesRegex(ValueError, "wrong peak"):
            compare.compare("stress", new, old)


if __name__ == "__main__":
    unittest.main()
