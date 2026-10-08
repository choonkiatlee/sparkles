"""Isolated diagnostic tests: no estimator thresholds are changed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_geometry_frame_ablation as ablation


class Frame16AblationTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"source_index": i, "position": i}
            for i in (16, 13, 18, 19, 17)
        ]
        self.reference = {
            "status": "ok",
            "scaffold": {"placeholder": True},
            "selected_frames": self.records,
            "semantic_gauge_id": "g",
            "outer_evidence": {
                "tag": "full",
                "vertices_topology_order": [[0.0, 0.0]] * 8,
            },
        }

    def _run(self):
        calls = []

        def evidence(_pose, selected):
            n = len(selected)
            return (np.zeros((n, 8, 16)), np.arange(16),
                    [np.ones((12, 12), bool) for _ in selected],
                    [], [{"source_index": row["source_index"]}
                         for row in selected])

        def fit_inner(data, grid, metadata, outer, gauge):
            calls.append((len(data), outer["tag"], gauge))
            return {
                "status": "review", "scaffold": {"placeholder": True},
                "selected_frames": metadata,
                "outer_evidence": {
                    "vertices_topology_order": [[0.0, 0.0]] * 8
                },
                "tag": f"{len(data)}-{outer['tag']}",
            }

        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "asscher-pose.json").write_text("{}")
            with patch.object(ablation.validation, "assert_frozen_method"), \
                 patch.object(ablation.stability, "_primary_fit",
                              return_value=(self.reference, self.records, [], [])), \
                 patch.object(ablation.stability, "_load_evidence",
                              side_effect=evidence), \
                 patch.object(ablation, "_outer",
                              return_value={
                                  "tag": "without",
                                  "vertices_topology_order": [[0, 0]] * 8
                              }), \
                 patch.object(ablation, "_inner", side_effect=fit_inner), \
                 patch.object(ablation, "_comparison",
                              side_effect=lambda ref, candidate: {
                                  "tag": candidate.get("tag", "full")
                              }):
                result, _, selected = ablation.analyse_pose(temp)
        return result, selected, calls

    def test_counterfactuals_separately_hold_outer_and_inner_evidence(self):
        result, selected, calls = self._run()
        self.assertEqual([r["source_index"] for r in selected],
                         [16, 13, 18, 19, 17])
        self.assertEqual(result["without_selected_source_indices"],
                         [13, 18, 19, 17])
        cases = result["cases"]
        self.assertEqual(cases["full_outer_full_inner"]["tag"], "full")
        self.assertEqual(cases["full_outer_without_inner"]["tag"], "4-full")
        self.assertEqual(cases["without_outer_full_inner"]["tag"], "5-without")
        self.assertEqual(cases["without_outer_without_inner"]["tag"],
                         "4-without")
        self.assertCountEqual(calls, [
            (4, "full", "g"), (5, "without", "g"),
            (4, "without", "g"),
        ])
        self.assertTrue(result["factor_design"]["no_reselection"])

    def test_missing_source_index_is_rejected_not_replaced(self):
        self.records[0]["source_index"] = 12
        with self.assertRaisesRegex(ValueError, "not uniquely"):
            self._run()

    def test_comparison_preserves_unavailable_cases(self):
        reference = {"status": "ok", "scaffold": None}
        candidate = {"status": "unavailable", "scaffold": None}
        row = ablation._comparison(reference, candidate)
        self.assertEqual(row["validation_status"], "unavailable")
        self.assertEqual(row["boundary_displacement"], {})
        self.assertIsNone(row["outer_vertex_max_delta_from_full_u"])

    def test_frozen_reference_guard_catches_changed_inner_boundary(self):
        observed = {"cases": {
            "full_outer_full_inner": {
                "selected_source_indices": [16, 13, 18, 19, 17],
                "status": "ok",
                "boundaries": {name: {"global_u": 0.5}
                               for name in ("C1_C2", "C2_C3", "C3_TABLE")},
            },
            "without_outer_without_inner": {
                "selected_source_indices": [13, 18, 19, 17],
                "status": "review",
                "boundaries": {name: {"global_u": 0.4}
                               for name in ("C1_C2", "C2_C3", "C3_TABLE")},
            },
        }}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "per-stone" / ablation.CERTIFICATE
            (root / "stability").mkdir(parents=True)
            for name, filename in [
                ("full_outer_full_inner", "primary-wireframe.json"),
                ("without_outer_without_inner",
                 "stability/leave-out-0016-wireframe.json"),
            ]:
                row = observed["cases"][name]
                payload = {
                    "status": row["status"],
                    "selected_frames": [
                        {"source_index": n}
                        for n in row["selected_source_indices"]
                    ],
                    "boundary_evidence": row["boundaries"],
                }
                (root / filename).write_text(json.dumps(payload))
            ablation._confirm_frozen_reference(observed, temp)
            observed["cases"]["without_outer_without_inner"][
                "boundaries"]["C3_TABLE"]["global_u"] = 0.55
            with self.assertRaisesRegex(RuntimeError, "C3_TABLE"):
                ablation._confirm_frozen_reference(observed, temp)


if __name__ == "__main__":
    unittest.main()
