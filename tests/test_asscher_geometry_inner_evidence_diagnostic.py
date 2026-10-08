"""Target-blind and estimator-invariant #124 diagnostics."""
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_geometry_inner_evidence_diagnostic as diagnostic


class InnerEvidenceDiagnosticsTests(unittest.TestCase):
    def test_candidate_ranking_uses_frozen_prominence_and_support_formula(self):
        candidates = [
            {"u": .48, "index": 76, "prominence": 2.0,
             "sector_support": .75, "sector_peaks": [None] * 8},
            {"u": .58, "index": 92, "prominence": 1.0,
             "sector_support": .875, "sector_peaks": [None] * 8},
            {"u": .70, "index": 111, "prominence": 10.0,
             "sector_support": 1.0, "sector_peaks": [None] * 8},
        ]
        ranked = diagnostic.candidate_rows({"candidates": candidates})
        self.assertEqual(len(ranked), 2)
        scale = 2.0
        self.assertAlmostEqual(
            ranked[0]["selection_score"],
            np.log1p(2.0 / scale) + 1.25 * .75,
        )
        self.assertTrue(all(.42 <= r["u"] <= .60 for r in ranked))

    def test_per_sector_peaks_remain_unassigned_image_contrast(self):
        u = np.linspace(0, 1, 160)
        profile = np.zeros(160)
        profile[np.argmin(abs(u - .48))] = 8
        profile[np.argmin(abs(u - .58))] = 6
        peaks = diagnostic._peaks(profile, u)
        self.assertEqual(len(peaks), 2)
        self.assertAlmostEqual(peaks[0]["u"], u[np.argmin(abs(u-.48))])
        self.assertAlmostEqual(peaks[1]["u"], u[np.argmin(abs(u-.58))])
        self.assertNotIn("semantic_id", peaks[0])

    def test_ray_discrepancy_is_zero_for_identical_masks(self):
        same = np.asarray([80., 90., 70.])
        self.assertEqual(diagnostic._rms_fraction(same, same), 0.)
        self.assertGreater(diagnostic._rms_fraction(
            same + np.asarray([8., 0., 0.]), same), 0)
        self.assertIsNone(diagnostic._rms_fraction(
            same, np.asarray([0., 90., 70.])))

    def test_inspection_uses_fixed_gauge_and_exposes_normalization(self):
        records = [
            {"source_index": i, "position": i,
             "canonical": {
                 "normalization": {
                     "transform_type": "similarity",
                     "rectification": "none",
                     "isotropic_scale": 1.0,
                     "source_centre_xy": [80, 80],
                 },
                 "registered_outline": {
                     "orientation_deg_mod_90": float(i),
                 },
             },
             "sequence_coordinate": {"gauge_quarter_turn": 0},
             "assessment": {"outline": {"aspect_ratio": 1.0}}}
            for i in [13, 16, 17, 18, 19]
        ]
        u = np.linspace(0, 1, 160)
        frame_evidence = np.zeros((8, 160), dtype=float)
        frame_evidence[:, 75] = 4.
        frame_evidence[:, 92] = 5.
        with patch.object(diagnostic.stability, "_load_gauged_arrays",
                          return_value=(None, np.ones((192, 192), bool), None)), \
             patch.object(diagnostic.stability.wireframe,
                          "extract_sector_evidence",
                          return_value=(u, frame_evidence)), \
             patch.object(diagnostic.steps, "_ray_geometry",
                          return_value=(u, np.ones(96)*80, None, None)), \
             patch.object(diagnostic, "template_summary",
                          side_effect=[
                              {"c3_selected_global_u": .58},
                              {"c3_selected_global_u": .48},
                          ]):
            output = diagnostic.inspect_evidence(records, "/unused")
        self.assertEqual(output["selected_source_indices"], [13, 16, 17, 18, 19])
        self.assertEqual(output["without_focus_frame"]["c3_selected_global_u"], .48)
        self.assertEqual(len(output["frames"]), 5)
        self.assertTrue(all(
            v["rectification"] == "none" for v in output["frames"]
        ))
        self.assertTrue(all(
            v["silhouette_ray_rms_fraction_of_median"] == 0
            for v in output["frames"]
        ))
        self.assertEqual(len(output["frames"][0]["c3_per_sector_top_peaks"]), 8)


if __name__ == "__main__":
    unittest.main()
