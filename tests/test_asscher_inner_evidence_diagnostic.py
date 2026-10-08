"""Unit checks for the frozen #124 diagnostic, not a new geometry estimator."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from diamond360 import asscher_inner_evidence_diagnostic as diag


class InnerEvidenceDiagnosticTests(unittest.TestCase):
    def test_two_mode_peak_probes_are_source_and_sector_specific(self):
        u = np.linspace(0, 1, 160)
        frame = np.zeros((2, 8, len(u)))
        for sector in range(8):
            frame[0, sector] = (1.8 * np.exp(-((u-.48)/.012)**2)
                                + .4 * np.exp(-((u-.58)/.012)**2))
            frame[1, sector] = (.3 * np.exp(-((u-.48)/.012)**2)
                                + 2 * np.exp(-((u-.58)/.012)**2))
        rows = diag._frame_evidence(frame, u, [16,17], .58, .48)
        self.assertEqual(rows[0]["omit_mode_stronger_sector_count"], 8)
        self.assertEqual(rows[1]["full_mode_stronger_sector_count"], 8)
        self.assertEqual(rows[0]["source_index"], 16)
        self.assertEqual(len(rows[0]["sectors"]), 8)
        self.assertIsNotNone(rows[0]["sectors"][0]["full_mode"]["peak_u"])

    def test_unavailable_local_peaks_remain_missing(self):
        u = np.linspace(0,1,160)
        row = diag._local_energy(np.full(len(u),np.nan), u, .5)
        self.assertIsNone(row["peak_u"])
        self.assertIsNone(row["peak_evidence"])

    def test_registration_is_similarity_only_without_projective_claim(self):
        record = {
            "canonical": {
                "registered_to_canonical_xy": [
                    [0, -2, 10], [2, 0, 12], [0, 0, 1]
                ],
                "registered_outline": {
                    "orientation_deg_mod_90": 13.5,
                    "aspect_ratio": 1.07
                },
                "normalization": {"rectification": "none"}
            }
        }
        row = diag._similarity_diagnostics(record)
        self.assertAlmostEqual(row["linear_anisotropy_fraction"], 0)
        self.assertEqual(row["normalization_rectification"], "none")
        self.assertAlmostEqual(row["registered_orientation_mod90_deg"], 13.5)

    def test_shape_residual_is_reported_without_relabeling_facets(self):
        mask = np.ones((64,64), bool)
        frames = [{"source_index": 16,"canonical":{}}]
        outer = {"vertices_topology_order": [[0,0]]*8}
        with patch.object(diag.octagon, "_normalized_fitted_vertices",
                          return_value=(
                              np.ones((8,2)), {
                                  "aspect_ratio": 1.02,
                                  "normalized_q90_boundary_residual": 0.01
                              }
                          )), patch.object(
                              diag, "_similarity_diagnostics",
                              return_value={"normalization_rectification": "none"}
                          ):
            rows = diag._per_frame_outer_geometry([mask],frames,outer)
        self.assertAlmostEqual(rows[0]["median_octagon_rms_u"], 2**.5)
        self.assertEqual(rows[0]["source_index"], 16)

    def test_heatmap_keeps_competing_modes_as_descriptive_evidence(self):
        u = np.linspace(0, 1, 160)
        data = np.tile(np.sin(u*40)[None,None,:]**2, (5,8,1))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"modes.png"
            name = diag.write_evidence_qc(
                data,u,[16,13,18,19,17],.579,.478,path
            )
            self.assertEqual(name,"modes.png")
            img = Image.open(path)
            self.assertGreater(img.width,600)
            self.assertGreater(img.height,400)

    def test_report_keeps_audit_flags_and_all_five_leaveouts(self):
        u = np.linspace(0,1,160)
        data = np.zeros((5,8,160))
        indices = [16,13,18,19,17]
        fake_full = {
            "full_outer_full_inner": {
                "outer_evidence": {"vertices_topology_order":[[0,0]]*8}
            }
        }
        fake_summary = {
            "full_selected_source_indices": indices,
            "cases": {"full_outer_full_inner": {}}
        }
        def tmpl(_data,_u):
            return {
                "status": "ok", "c3_selected_u":
                    .579 if len(_data)==5 else .478,
                "persistent_edge_candidates": []
            }
        with patch.object(diag.ablation, "analyse_pose",
                          return_value=(fake_summary,fake_full,
                             [{"source_index":v} for v in indices])), \
             patch.object(diag.stability, "_load_evidence",
                          return_value=(data,u,[None]*5,None,None)), \
             patch.object(diag, "_per_frame_outer_geometry",
                          return_value=[]), \
             patch.object(diag, "_template_report",
                          side_effect=tmpl), \
             patch.object(diag.validation, "assert_frozen_method"):
            report, _ = diag.inspect_pose("/unused")
        self.assertEqual(set(report["leave_one_out_templates"]),
                         set(str(v) for v in indices))
        self.assertAlmostEqual(report["c3_modes"]["delta_without_minus_full_u"],
                               -.101)
        self.assertFalse(report["frozen_115_reference_checked"])
        self.assertIn("no square-on projective rectification",
                      report["normalization_contract"])
        self.assertIn("do not identify physical",report["interpretation_limits"])


if __name__ == "__main__":
    unittest.main()
