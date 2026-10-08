"""Policy and deterministic A/B tests for opt-in C3 multi-view ranker."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_steps as steps
from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


class C3FrameCoherenceExperimentTests(unittest.TestCase):
    def test_default_frozen_policy_is_not_replaced(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(validation.assert_frozen_method(validation.WINDOW_METHOD))
        self.assertTrue(validation.assert_frozen_method(validation.FRAME_RANK_METHOD))
        self.assertEqual(steps.experimental_frame_rank_specification(),
                         validation.FROZEN_C3_FRAME_RANK_EXPERIMENT_POLICY)
        self.assertEqual(
            validation.frozen_method_record(validation.OUTER_METHOD)[
                "wireframe_specification_sha256"],
            validation.frozen_method_record(validation.FRAME_RANK_METHOD)[
                "wireframe_specification_sha256"],
        )

    def test_per_frame_support_is_independent_of_contrast_amplitude(self):
        u = np.linspace(0, 1, 160)
        frame = np.zeros((5, 8, len(u)), float)
        for i in range(5):
            frame[i, :, np.argmin(abs(u-.58))] = 4.0
            if i in (0,1,2):
                frame[i, :, np.argmin(abs(u-.48))] = 8.0
        med = np.median(frame, axis=0)
        c48 = {"u": float(u[np.argmin(abs(u-.48))]),
               "prominence": 9.0, "sector_support": 1.0}
        c58 = {"u": float(u[np.argmin(abs(u-.58))]),
               "prominence": 2.0, "sector_support": 1.0}
        r48 = steps.candidate_frame_rank(c48, frame, med, u, (.42,.60), 5.0)
        r58 = steps.candidate_frame_rank(c58, frame, med, u, (.42,.60), 5.0)
        self.assertEqual(r48["frame_persistence_fraction"], .6)
        self.assertEqual(r58["frame_persistence_fraction"], 1.)
        self.assertGreater(r48["base_score"], r58["base_score"])
        self.assertEqual(len(r58["per_frame"]), 5)
        self.assertAlmostEqual(
            r58["rank_score"],
            r58["base_score"] + 1.25 -
            1.25*r58["angular_misalignment_fraction_of_window"]
        )
        self.assertIn("image-space contrast", r58["interpretation"])

    def test_invalid_rank_policy_and_mismatched_peak_policy_fail_closed(self):
        data = np.ones((4, 8, 160), float)
        u = np.linspace(0,1,160)
        with self.assertRaisesRegex(ValueError, "unknown C3"):
            steps.discover_template(data,u,rank_policy="unapproved")
        with self.assertRaisesRegex(ValueError, "needs window-local"):
            steps.discover_template(data,u,rank_policy=steps.FRAME_RANK_POLICY)

    def test_discover_template_retains_original_unmodified_outputs(self):
        u = np.linspace(0,1,160)
        profile = sum(
            amp*np.exp(-.5*((u-centre)/.008)**2)
            for centre,amp in ((.48,.3),(.58,1.),(.73,.8),(.87,.5)))
        data = np.broadcast_to(profile,(5,8,len(u))).copy()
        first = steps.discover_template(data,u)
        explicit = steps.discover_template(
            data,u,peak_policy=steps.GLOBAL_PEAK_POLICY,
            rank_policy=steps.LEGACY_RANK_POLICY)
        self.assertEqual(first["status"],explicit["status"])
        self.assertEqual(
            [p["u"] for p in first["candidates"]],
            [p["u"] for p in explicit["candidates"]])
        changed = steps.discover_template(
            data,u,peak_policy=steps.WINDOW_PEAK_POLICY,
            rank_policy=steps.FRAME_RANK_POLICY)
        self.assertIn("c3_ranking_audit",changed)
        self.assertTrue(changed["c3_ranking_audit"]["candidates"])

    def test_stability_method_dispatch_preserves_outer_scaffold(self):
        metadata=[{"source_index":i,"position":i} for i in (13,16,17,18)]
        matrix=(np.zeros((4,8,160)),np.linspace(0,1,160),
                [np.ones((32,32),bool)]*4,[np.ones((32,32))]*4,metadata)
        outer={"vertices_topology_order": [[float(i),float(i)] for i in range(8)],
               "confidence": .96}
        with patch.object(stability,"_load_evidence",return_value=matrix), \
             patch.object(stability.outer_octagon,"fit_consensus",
                          return_value=outer), \
             patch.object(wireframe,"fit_from_sector_evidence",
                          return_value={"status":"ok","scaffold":{}}) as fit:
            stability._fit_records("/unused",metadata,"g",
                                  method=validation.FRAME_RANK_METHOD)
        self.assertEqual(fit.call_args.kwargs["step_peak_policy"],
                         steps.WINDOW_PEAK_POLICY)
        self.assertEqual(fit.call_args.kwargs["step_rank_policy"],
                         steps.FRAME_RANK_POLICY)
        self.assertEqual(fit.call_args.kwargs["outer_confidence"], .96)


if __name__=="__main__":
    unittest.main()
