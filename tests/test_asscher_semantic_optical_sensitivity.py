"""Optical support sensitivity remains target-blind and NEVER moves geometry."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tests.test_asscher_semantic_optical_handoff import fixture
from diamond360 import asscher_semantic_optical_handoff as handoff
from diamond360 import asscher_semantic_optical_sensitivity as sens


class FixedOpticalSupportSensitivityTests(unittest.TestCase):
    def test_nominal_reproduces_unchanged_handoff_for_all_55_ids(self):
        scaffold,transfer,_,gauge,valid=fixture()
        geom_before=deepcopy(scaffold)
        transfer_before=deepcopy(transfer)
        y,x=np.indices(gauge.shape)
        brightness=.08+.004*x+.003*y
        a=sens.analyse_frame(scaffold,transfer,brightness,gauge,valid)
        b=handoff.sample_fixed_frame(scaffold,transfer,brightness,gauge,valid)
        self.assertEqual(scaffold,geom_before)
        self.assertEqual(transfer,transfer_before)
        self.assertTrue(a["unchanged_scaffold"])
        self.assertEqual(a["fixed_geometry_refit_count"],0)
        self.assertEqual(len(a["entities"]),55)
        expected={item["semantic_id"]:item for item in b["entities"]}
        for item in a["entities"]:
            original=expected[item["semantic_id"]]
            self.assertEqual(item["geometry_confidence"],original["geometry_confidence"])
            self.assertEqual(item["geometry_support_status"],original["geometry_support_status"])
            self.assertEqual(item["nominal_pixel_count"],original["supported_pixel_count"])
            self.assertEqual(item["nominal_raw_mean"],original["raw_mean_brightness"])
            self.assertEqual(item["physical_facet_correspondence"],"not_established")
            self.assertIsNone(item["inner_C3_table_identity"] if not
                              item["semantic_id"].startswith("C3_") and
                              item["semantic_id"]!="TABLE" else None)

    def test_core_expansion_change_only_footprint_and_preserve_semantics(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        y,x=np.indices(raw.shape)
        gradient=.05+.006*x+.001*y
        result=sens.analyse_frame(scaffold,transfer,gradient,gauge,valid)
        available=[r for r in result["entities"] if r["nominal_pixel_count"]>=12]
        self.assertGreater(len(available),12)
        self.assertTrue(all(r["core_1px_count"]<=r["nominal_pixel_count"]<=r["expanded_1px_count"] for r in available))
        self.assertTrue(any(r["core_1px_count"]<r["nominal_pixel_count"] for r in available))
        self.assertTrue(any(r["expanded_1px_count"]>r["nominal_pixel_count"] for r in available))
        self.assertTrue(any(abs(r["core_1px_delta"])>1e-5 for r in available if r["core_1px_delta"] is not None))
        self.assertTrue(all(r["expanded_1px_count"]<=int(gauge.sum()) for r in available))
        self.assertTrue(all(r["physical_facet_correspondence"]=="not_established" for r in result["entities"]))

    def test_predeclared_perturbations_are_exact_when_not_saturated(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        y,x=np.indices(raw.shape)
        image=.15+.0025*x+.0015*y
        a=sens.analyse_frame(scaffold,transfer,image,gauge,valid)
        observed=[r for r in a["entities"] if r["nominal_raw_mean"] is not None]
        self.assertGreater(len(observed),10)
        for row in observed:
            v=row["nominal_raw_mean"]
            self.assertAlmostEqual(row["counterfactual_exposure"]["gain_0_85"]["raw_mean"],.85*v)
            self.assertAlmostEqual(row["counterfactual_exposure"]["gain_1_10_clipped"]["raw_mean"],1.10*v)
            self.assertAlmostEqual(row["counterfactual_exposure"]["offset_plus_0_05_clipped"]["raw_mean"],v+.05)
            for s in a["image_reference"]:
                contrast=row["counterfactual_exposure"].get(s,{}).get("quantile_contrast")
                if contrast is not None:
                    self.assertAlmostEqual(contrast,row["nominal_quantile_contrast"],places=6)

    def test_clipping_is_exposed_as_counterexample_to_easy_exposure_correction(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        y,x=np.indices(raw.shape)
        # Some light areas saturate after +10%, so percentile contrast is
        # no longer guaranteed invariant to the synthetic exposure change.
        image=.65+.004*x
        result=sens.analyse_frame(scaffold,transfer,image,gauge,valid)
        self.assertLess(result["image_reference"]["nominal"]["saturated_fraction"],
                        result["image_reference"]["gain_1_10_clipped"]["saturated_fraction"])
        rows=[r for r in result["entities"] if
              r["counterfactual_exposure"]["gain_1_10_clipped"]["delta_contrast_from_nominal"] is not None]
        self.assertTrue(any(abs(r["counterfactual_exposure"]["gain_1_10_clipped"]["delta_contrast_from_nominal"])>0.01 for r in rows))

    def test_unavailable_geometry_never_has_fabricated_brightness(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        key=next(k for k in transfer["entities"] if k.startswith("P2_"))
        transfer["entities"][key]["status"]="unavailable"
        transfer["entities"][key]["confidence"]=0
        output=sens.analyse_frame(scaffold,transfer,raw,gauge,valid)
        item=next(x for x in output["entities"] if x["semantic_id"]==key)
        self.assertEqual(item["nominal_pixel_count"],0)
        self.assertEqual(item["core_1px_count"],0)
        self.assertEqual(item["expanded_1px_count"],0)
        self.assertIsNone(item["nominal_raw_mean"])
        self.assertIsNone(item["nominal_quantile_contrast"])
        self.assertTrue(all(a["raw_mean"] is None for a in item["counterfactual_exposure"].values()))

    def test_constant_brightness_has_no_claimed_normalization(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        data=sens.analyse_frame(scaffold,transfer,raw,gauge,valid)
        sampled=[r for r in data["entities"] if r["nominal_pixel_count"]]
        self.assertTrue(all(r["nominal_quantile_contrast"] is None for r in sampled))
        self.assertAlmostEqual(data["image_reference"]["nominal"]["q10"],
                               data["image_reference"]["nominal"]["q90"])
        self.assertTrue(all(r["counterfactual_exposure"]["gain_0_85"]["quantile_contrast"] is None
                            for r in sampled))

    def test_zero_valid_pixels_keeps_all_sensitivity_values_null(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        missing=np.zeros_like(valid,dtype=bool)
        output=sens.analyse_frame(scaffold,transfer,raw,gauge,missing)
        self.assertEqual(output["image_reference"]["nominal"]["status"],
                         "unavailable_no_valid_stone_pixels")
        for row in output["entities"]:
            self.assertEqual(row["nominal_pixel_count"],0)
            self.assertEqual(row["core_1px_count"],0)
            self.assertEqual(row["expanded_1px_count"],0)
            self.assertIsNone(row["nominal_raw_mean"])
            self.assertIsNone(row["nominal_quantile_contrast"])
            self.assertTrue(all(v["raw_mean"] is None
                                for v in row["counterfactual_exposure"].values()))

    def test_invalid_geometry_rejected_before_perturbation(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        bad=deepcopy(transfer)
        bad["refit_performed"]=True
        with self.assertRaisesRegex(ValueError,"geometry must remain fixed"):
            sens.analyse_frame(scaffold,bad,raw,gauge,valid)
        bad=deepcopy(transfer)
        bad["semantic_gauge_id"]="another"
        with self.assertRaisesRegex(ValueError,"gauge"):
            sens.analyse_frame(scaffold,bad,raw,gauge,valid)

    def test_two_frame_summary_reports_unavailable_and_no_scores(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        first=sens.analyse_frame(scaffold,transfer,raw,gauge,valid)
        other=deepcopy(transfer)
        other["source_index"]=12
        second=sens.analyse_frame(scaffold,other,raw*.72,gauge,valid)
        report=sens.report([first,second],"SYNTHETIC-ONLY",
                           {"primary_wireframe_sha256":"pinned-test"},
                           "unresolved_not_safe_to_call_crown")
        self.assertEqual(report["status"],
                         "descriptive_sensitivity_no_method_selection_or_quality_score")
        self.assertEqual(len(report["semantic_ids"]),55)
        self.assertEqual(report["source_indices"],[11,12])
        self.assertTrue(report["no_refit"])
        self.assertFalse(report["physical_facet_angles_available"])
        self.assertFalse(report["vendor_cross_source_calibration_established"])
        self.assertGreater(report["entity_summary"]["C1_N"]["observed_frames"],0)
        self.assertIn("expanded_1px_from_nominal",
                      report["entity_summary"]["C1_N"]["perturbation_stats"])

    def test_duplicate_source_or_swapped_entities_fail_closed(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        first=sens.analyse_frame(scaffold,transfer,raw,gauge,valid)
        with self.assertRaisesRegex(ValueError,"source indices"):
            sens.report([first,first],"fixture",{},"unknown")
        swapped=deepcopy(first)
        swapped["source_index"]=12
        swapped["entities"].reverse()
        with self.assertRaisesRegex(ValueError,"semantic identities"):
            sens.report([first,swapped],"fixture",{},"unknown")
        wrong=deepcopy(first)
        wrong["source_index"]=12
        wrong["unchanged_scaffold"]=False
        with self.assertRaisesRegex(ValueError,"refit"):
            sens.report([first,wrong],"fixture",{},"unknown")

    def test_report_json_and_visualization(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        y,x=np.indices(raw.shape)
        image=.12+.004*x+.002*y
        a=sens.analyse_frame(scaffold,transfer,image,gauge,valid)
        other=deepcopy(transfer)
        other["source_index"]=12
        b=sens.analyse_frame(scaffold,other,image*.8,gauge,valid)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report=sens.write_report([a,b],"SYNTHETIC-CHECK",
                                     {"transfer_sha256":"archived"},
                                     "unresolved",root/"sensitivity.json")
            sens.draw_perturbation_summary(report,root/"sensitivity.png")
            self.assertTrue((root/"sensitivity.png").stat().st_size>1800)
            self.assertEqual(json.loads((root/"sensitivity.json").read_text()),report)


if __name__=="__main__":
    unittest.main()
