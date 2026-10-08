"""Frozen geometry, exposure and bounded sampling-zone negative-control tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from diamond360 import asscher_semantic_optical_handoff as handoff
from diamond360 import asscher_semantic_optical_sensitivity as sensitivity
from tests.test_asscher_semantic_optical_handoff import fixture


def patterned_raw():
    y,x=np.indices((96,96))
    return np.asarray(.20+.0023*x+.0016*y+.016*np.sin((x-25)/13),float)


class SensitivityTest(unittest.TestCase):
    def setup_data(self):
        scaffold,transfer,_,gauge,valid=fixture()
        return scaffold,transfer,patterned_raw(),gauge,valid

    def test_positive_affine_exposure_does_not_change_stone_percentile_support(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        before=sensitivity.sample_sensitivity_frame(
            scaffold,transfer,raw,gauge,valid)
        brighter=sensitivity.sample_sensitivity_frame(
            scaffold,transfer,raw*.81+.12,gauge,valid)
        self.assertEqual([r["semantic_id"] for r in before["entities"]],
                         [r["semantic_id"] for r in brighter["entities"]])
        self.assertEqual(before["reference_stone_pixels"],brighter["reference_stone_pixels"])
        self.assertNotEqual(before["stone_reference_median"],
                            brighter["stone_reference_median"])
        nonempty=0
        for x,y in zip(before["entities"],brighter["entities"]):
            self.assertEqual(x["geometry_support_status"],y["geometry_support_status"])
            for region in sensitivity.POLICY["support_variants"]:
                a=x["variants"][region];b=y["variants"][region]
                self.assertEqual(a["pixels"],b["pixels"])
                self.assertEqual(a["mean_stone_percentile"],b["mean_stone_percentile"])
                if a["mean_raw"] is not None:
                    nonempty+=1
                    self.assertNotAlmostEqual(a["mean_raw"],b["mean_raw"],places=4)
            if x["normalized_raw_mean_minus_stone_median_over_iqr"] is not None:
                self.assertAlmostEqual(
                    x["normalized_raw_mean_minus_stone_median_over_iqr"],
                    y["normalized_raw_mean_minus_stone_median_over_iqr"],
                    places=5)
        self.assertGreater(nonempty,20)

    def test_two_insets_and_one_outset_do_not_shift_fixed_geometry(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        original=deepcopy(scaffold)
        src=handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid)
        diag=sensitivity.sample_sensitivity_frame(scaffold,transfer,raw,gauge,valid,
                                                   baseline_report=src)
        self.assertEqual(scaffold,original)
        self.assertFalse(diag["scaffold_refitted"])
        self.assertEqual(len(src["entities"]),len(diag["entities"]))
        observed=[]
        for row in diag["entities"]:
            p=row["variants"]
            self.assertLessEqual(p["inset_2px"]["pixels"],p["inset_1px"]["pixels"])
            self.assertLessEqual(p["inset_1px"]["pixels"],p["baseline"]["pixels"])
            self.assertGreaterEqual(p["outset_1px"]["pixels"],p["baseline"]["pixels"])
            if p["baseline"]["pixels"]:
                observed.append(row)
                self.assertEqual(row["physical_facet_correspondence"],
                                 "not_established")
                self.assertIsNotNone(p["baseline"]["mean_stone_percentile"])
                self.assertGreaterEqual(p["baseline"]["mean_stone_percentile"],0)
                self.assertLessEqual(p["baseline"]["mean_stone_percentile"],1)
        self.assertGreater(len(observed),10)

    def test_unavailable_stays_unavailable_and_inner_C3_is_not_physical(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        key=next(s for s in transfer["entities"] if s.startswith("P1_"))
        transfer["entities"][key]["status"]="unavailable"
        transfer["entities"][key]["confidence"]=0
        c3=next(s for s in transfer["entities"] if s.startswith("C3_"))
        transfer["entities"][c3]["status"]="review"
        result=sensitivity.sample_sensitivity_frame(scaffold,transfer,raw,gauge,valid)
        rows={x["semantic_id"]:x for x in result["entities"]}
        self.assertEqual(rows[key]["geometry_support_status"],"unavailable")
        for metric in rows[key]["variants"].values():
            self.assertEqual(metric["pixels"],0)
            self.assertIsNone(metric["mean_raw"])
            self.assertIsNone(metric["mean_stone_percentile"])
        self.assertTrue(all(x is None for x in rows[key]["rank_delta_from_baseline"].values()))
        self.assertEqual(rows[c3]["inner_C3_table_identity"],"review_not_verified")
        self.assertEqual(rows[c3]["geometry_support_status"],"review")

    def test_uniform_brightness_has_midrank_half_not_fake_scintillation(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        raw[:]=0.5
        result=sensitivity.sample_sensitivity_frame(scaffold,transfer,raw,gauge,valid)
        self.assertEqual(result["stone_reference_iqr"],0)
        for row in result["entities"]:
            if row["variants"]["baseline"]["pixels"]:
                self.assertEqual(row["variants"]["baseline"]["mean_stone_percentile"],0.5)
                self.assertIsNone(row["normalized_raw_mean_minus_stone_median_over_iqr"])

    def test_summary_contains_trace_and_bounded_raster_perturbation_statistics(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        frames=[]
        raw_frames=[]
        for source,shift in [(255,0),(0,.085),(2,.055)]:
            t=deepcopy(transfer)
            t["source_index"]=source
            pixel=raw+shift
            original=handoff.sample_fixed_frame(scaffold,t,pixel,gauge,valid)
            original["source_index"]=source
            frames.append(original)
            raw_frames.append(sensitivity.sample_sensitivity_frame(
                scaffold,t,pixel,gauge,valid,baseline_report=original))
        baseline={
            "certificate":"IGI-SYNTHETIC-TEST-ONLY",
            "sampled_source_indices":[255,0,2],
            "frames":frames,
            "frozen_artifact_sha256":{"primary_wireframe_sha256":"pinned-test",
                                      "transfer_sha256":"pinned-test"},
            "scaffold_was_refitted":False,
            "archived_crown_face_selection":"unresolved_not_safe_to_call_crown",
        }
        report=sensitivity.summarize_sensitivity(baseline["certificate"],baseline,raw_frames)
        self.assertEqual(report["source_indices"],[255,0,2])
        self.assertEqual(len(report["stone_intensity_reference"]),3)
        self.assertEqual(set(report["entities"]),set(scaffold["entity_observations"]))
        self.assertFalse(report["physical_facet_angle_claim"])
        self.assertIsNone(report["outlier_threshold_or_quality_score"])
        c=next(k for k in report["entities"] if k.startswith("C1_"))
        self.assertGreater(report["entities"][c]["raw_mean_frame_range"],.07)
        self.assertLess(report["entities"][c]["stone_percentile_frame_range"],1e-5)
        with tempfile.TemporaryDirectory() as d:
            result=sensitivity.write_sensitivity(baseline,raw_frames,Path(d))
            self.assertEqual(json.loads((Path(d)/"real-support-sensitivity.json").read_text()),result)
            png=Path(d)/"real-support-sensitivity.png"
            self.assertGreater(png.stat().st_size,2500)

    def test_invalid_or_swapped_original_baseline_fails_closed(self):
        scaffold,transfer,raw,gauge,valid=self.setup_data()
        src=handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid)
        src["entities"][0]["supported_pixel_count"]+=1
        with self.assertRaisesRegex(ValueError,"rasterization"):
            sensitivity.sample_sensitivity_frame(scaffold,transfer,raw,gauge,valid,
                                                  baseline_report=src)
        with self.assertRaisesRegex(ValueError,"too few|gauge mask is empty"):
            sensitivity.sample_sensitivity_frame(scaffold,transfer,raw,
                np.zeros_like(gauge),np.zeros_like(valid))
        with self.assertRaisesRegex(ValueError,"finite"):
            bad=raw.copy()
            bad[0,0]=np.nan
            sensitivity.sample_sensitivity_frame(scaffold,transfer,bad,gauge,valid)


if __name__=="__main__":
    unittest.main()
