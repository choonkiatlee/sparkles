"""Regression tests for the separate #96 validation method revision."""
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_geometry_validation as validation


class OuterRevisionTests(TestCase):
    def test_primary_selects_full_outer_candidate_pool_before_fitting(self):
        candidates = [
            {"source_index": i, "position": i} for i in range(9)
        ]
        chosen = candidates[2:7]
        diagnostics = {"candidate_count": 9, "selected_count": 5}
        result = {"schema_version": "diamond360-asscher-wireframe-fit/1",
                  "scaffold": {"dummy": True}, "status": "ok"}
        with patch.object(stability.wireframe, "_gauge_id", return_value="g"), \
             patch.object(stability.wireframe, "_select_geometry_records",
                          return_value=candidates) as coarse, \
             patch.object(stability.outer_octagon, "select_records",
                          return_value=(chosen, diagnostics)) as select, \
             patch.object(stability, "_fit_records",
                          return_value=(result, [], [])) as fit:
            primary, selected, _, _ = stability._primary_fit(
                "/unused", {"sequence_gauge": {}},
                method=validation.OUTER_METHOD
            )
        coarse.assert_called_once()
        self.assertIsNone(coarse.call_args.kwargs["max_frames"])
        select.assert_called_once()
        self.assertEqual([v["source_index"] for v in selected], [2,3,4,5,6])
        self.assertIs(primary["outer_selection"], diagnostics)
        self.assertEqual(fit.call_args.kwargs["method"], validation.OUTER_METHOD)

    def test_outer_subset_fit_uses_octagon_consensus_not_legacy_outline(self):
        evidence = np.zeros((4, 8, 100))
        masks = [np.ones((16,16), bool) for _ in range(4)]
        metadata = [{"source_index": i, "position": i} for i in range(4)]
        fixture = (evidence, np.linspace(0,1,100), masks,
                   [np.zeros((16,16)) for _ in masks], metadata)
        octagon = {"vertices_topology_order": [[float(i),float(i)] for i in range(8)],
                   "confidence": .86}
        with patch.object(stability, "_load_evidence", return_value=fixture), \
             patch.object(stability.outer_octagon, "fit_consensus",
                          return_value=octagon) as outer, \
             patch.object(stability.wireframe, "_median_outer_vertices") as legacy, \
             patch.object(stability.wireframe, "fit_from_sector_evidence",
                          return_value={"status":"ok", "scaffold":{}}) as fit:
            result, _, _ = stability._fit_records(
                "/unused", metadata, "g", method=validation.OUTER_METHOD
            )
        outer.assert_called_once()
        legacy.assert_not_called()
        self.assertAlmostEqual(fit.call_args.kwargs["outer_confidence"], .86)
        self.assertEqual(result["outer_evidence"], octagon)

    def test_original_validation_snapshot_remains_addressable(self):
        v1 = validation.frozen_method_record(validation.LEGACY_METHOD)
        v2 = validation.frozen_method_record(validation.OUTER_METHOD)
        self.assertEqual(v1["wireframe_revision"],
                         "8bbbbf64754f2bcbb48ab435b731bdf95f7722bc")
        self.assertEqual(v2["wireframe_revision"],
                         "6334cc9d0c7e2c9a26854bfaeec7a8ebbb6fc668")
        self.assertNotEqual(v1["wireframe_specification_sha256"],
                            v2["wireframe_specification_sha256"])
        self.assertEqual(validation.canonical_sha256(
            validation.FROZEN_OUTER_WIREFRAME_SPECIFICATION
        ), validation.FROZEN_OUTER_WIREFRAME_SPEC_SHA256)
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        with self.assertRaises(RuntimeError):
            validation.assert_frozen_method(validation.LEGACY_METHOD)
