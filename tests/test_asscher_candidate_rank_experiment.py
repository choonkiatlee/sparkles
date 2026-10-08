"""Candidate ranking ablation: independent frames, unchanged frozen controls."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_steps as steps
from diamond360 import asscher_wireframe as wireframe
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_geometry_temporal_comparison as compare


class CandidateRankExperimentTests(unittest.TestCase):
    def test_frozen_policy_and_explicit_opt_in(self):
        self.assertEqual(steps.experimental_candidate_rank_specification(),
                         validation.FROZEN_TEMPORAL_EXPERIMENT_POLICY)
        for method in (validation.OUTER_METHOD, validation.WINDOW_METHOD,
                       validation.TEMPORAL_METHOD):
            self.assertTrue(validation.assert_frozen_method(method))
        original = validation.frozen_method_record(validation.OUTER_METHOD)
        new = validation.frozen_method_record(validation.TEMPORAL_METHOD)
        self.assertEqual(original["wireframe_specification_sha256"],
                         new["wireframe_specification_sha256"])
        self.assertNotEqual(original["method_revision"], new["method_revision"])
        self.assertFalse(new["candidate_rank_policy"]["physical_facet_claim"])

    @staticmethod
    def evidence():
        u = np.linspace(0,1,160)
        def gaussian(centre, amp):
            return amp*np.exp(-.5*((u-centre)/.006)**2)
        # Strong but intermittent inner peak versus weaker persistent one;
        # neither is assigned a physical-facet identity.
        a = np.array([
            gaussian(.470, 5.) + gaussian(.579, 2.2)
            if frame < 2 else gaussian(.579, 2.2)
            for frame in range(4)
        ])
        a = np.stack([np.tile(row, (8,1)) for row in a])
        a += gaussian(.731, 2.5)[None,None,:]
        a += gaussian(.874, 2.3)[None,None,:]
        return u,a

    def test_frame_persistence_beats_intermitttent_aggregate_intensity(self):
        u, data = self.evidence()
        legacy = steps.discover_template(
            data,u,peak_policy=steps.WINDOW_PEAK_POLICY
        )
        temporal = steps.discover_template(
            data,u,peak_policy=steps.WINDOW_PEAK_POLICY,
            candidate_rank_policy=steps.TEMPORAL_RANK_POLICY,
        )
        self.assertIn(legacy["status"],("ok","review"))
        self.assertIn(temporal["status"],("ok","review"))
        self.assertAlmostEqual(legacy["controls"][0]["global_u"],.47,delta=.013)
        self.assertAlmostEqual(temporal["controls"][0]["global_u"],.579,delta=.013)
        rows = temporal["ranking_evidence"]["centre_inner"]["candidates"]
        intermittent=min(rows,key=lambda r:abs(r["u"]-.470))
        stable=min(rows,key=lambda r:abs(r["u"]-.579))
        self.assertEqual(intermittent["frame_vote_count"],2)
        self.assertEqual(stable["frame_vote_count"],4)
        self.assertGreater(stable["supported_sector_frame_pairs"],
                           intermittent["supported_sector_frame_pairs"])
        self.assertGreater(intermittent["original_selection_score"],
                           stable["original_selection_score"])

    def test_candidate_votes_independent_of_permutation_and_heldout_views(self):
        u, data=self.evidence()
        candidate={"u":.579}
        a=steps.candidate_frame_persistence(data,u,candidate)
        b=steps.candidate_frame_persistence(data[::-1],u,candidate)
        self.assertEqual(a["frame_vote_count"],b["frame_vote_count"])
        self.assertEqual(a["supported_sector_frame_pairs"],
                         b["supported_sector_frame_pairs"])
        removed=steps.candidate_frame_persistence(data[:3],u,candidate)
        self.assertEqual(removed["frame_count"],3)
        self.assertEqual(removed["frame_vote_count"],3)

    def test_missing_support_does_not_fabricate_votes(self):
        u=np.linspace(0,1,160)
        data=np.zeros((4,8,160),float)
        d=steps.candidate_frame_persistence(data,u,{"u":.50})
        self.assertEqual(d["frame_vote_count"],0)
        self.assertEqual(d["supported_sector_frame_pairs"],0)
        self.assertIsNone(d["median_radial_offset_u"])

    def test_temporal_ranking_requires_window_local_candidates(self):
        u,a=self.evidence()
        with self.assertRaisesRegex(ValueError,"requires declared window-local"):
            steps.discover_template(
                a,u,candidate_rank_policy=steps.TEMPORAL_RANK_POLICY
            )

    def test_method_dispatch_preserves_v2_and_v3(self):
        evidence=np.ones((5,8,160),float)
        records=[{"source_index":i,"position":i} for i in range(5)]
        mocked=(evidence,np.linspace(0,1,160),
                [np.ones((40,40),bool)]*5,
                [np.ones((40,40))]*5,records)
        fit_data={
            "vertices_topology_order":[[float(i),float(i)] for i in range(8)],
            "confidence":0.96
        }
        with patch.object(stability,"_load_evidence",return_value=mocked), \
             patch.object(stability.outer_octagon,"fit_consensus",
                          return_value=fit_data), \
             patch.object(wireframe,"fit_from_sector_evidence",
                          return_value={"scaffold":{},"status":"ok"}) as fitting:
            for method,peak,rank in (
                (validation.OUTER_METHOD,steps.GLOBAL_PEAK_POLICY,
                 steps.LEGACY_RANK_POLICY),
                (validation.WINDOW_METHOD,steps.WINDOW_PEAK_POLICY,
                 steps.LEGACY_RANK_POLICY),
                (validation.TEMPORAL_METHOD,steps.WINDOW_PEAK_POLICY,
                 steps.TEMPORAL_RANK_POLICY),
            ):
                stability._fit_records("/no-files",records,"fixed-gauge",method=method)
                self.assertEqual(fitting.call_args.kwargs["step_peak_policy"],peak)
                self.assertEqual(fitting.call_args.kwargs["candidate_rank_policy"],rank)
                self.assertEqual(fitting.call_args.kwargs["outer_confidence"],.96)

    def test_paired_comparison_fail_closed(self):
        fingerprint=validation.BENCHMARK_MANIFEST_CANONICAL_SHA256
        def report(method):
            return {"frozen_method":{"method_revision":method},
                    "benchmark_inputs":{"manifest_canonical_sha256":fingerprint},
                    "stones":[{"certificate":f"cert{i}"} for i in range(4)]}
        old=report(validation.WINDOW_METHOD)
        new=report(validation.TEMPORAL_METHOD)
        with patch.object(compare.comparison,"compare_stability",return_value=[]):
            out=compare.compare(old,new,control_method=validation.WINDOW_METHOD)
            self.assertEqual(out["stones"],[])
        bad=copy.deepcopy(new)
        bad["benchmark_inputs"]["manifest_canonical_sha256"]="wrong"
        with self.assertRaisesRegex(ValueError,"non-frozen"):
            compare.compare(old,bad,control_method=validation.WINDOW_METHOD)
        bad=copy.deepcopy(new)
        bad["stones"].pop()
        with self.assertRaisesRegex(ValueError,"four-stone"):
            compare.compare(old,bad,control_method=validation.WINDOW_METHOD)


if __name__=="__main__":
    unittest.main()
