"""Target-blind exposure and eroded-support sensitivity of a frozen semantic ruler."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from diamond360 import asscher_semantic_optical_handoff as handoff
from diamond360 import asscher_semantic_optical_sensitivity as sensitivity
from tests.test_asscher_semantic_optical_handoff import fixture


def make_scene(gain=1.0,offset=0.0):
    scaffold,transferred,_,mask,valid=fixture()
    yy,xx=np.indices(mask.shape)
    # Deliberately varying interior texture on 96x96, no clipping after affine exposure.
    image=.25+.0028*xx+.0015*yy
    raw=gain*image+offset
    baseline=handoff.sample_fixed_frame(scaffold,transferred,raw,mask,valid)
    return scaffold,transferred,raw,mask,valid,baseline


class FixedRulerSensitivityTests(unittest.TestCase):
    def test_affine_global_exposure_changes_raw_but_not_within_frame_q10_q90(self):
        a=make_scene()
        b=make_scene(gain=1.22,offset=.045)
        ra=sensitivity.sample_frame_sensitivity(*a)
        rb=sensitivity.sample_frame_sensitivity(*b)
        self.assertTrue(ra["contrast_proxy_available"])
        self.assertTrue(rb["contrast_proxy_available"])
        ma={v["semantic_id"]:v for v in ra["entities"]}
        mb={v["semantic_id"]:v for v in rb["entities"]}
        seen=0
        for key in ma:
            if ma[key]["raw_full_mean"] is None:
                self.assertIsNone(mb[key]["raw_full_mean"])
                continue
            seen+=1
            self.assertNotAlmostEqual(ma[key]["raw_full_mean"],mb[key]["raw_full_mean"])
            self.assertAlmostEqual(ma[key]["within_frame_quantile_contrast_full"],
                                   mb[key]["within_frame_quantile_contrast_full"],places=10)
            self.assertEqual(ma[key]["full_pixel_count"],mb[key]["full_pixel_count"])
            self.assertEqual(ma[key]["eroded_2px_pixel_count"],mb[key]["eroded_2px_pixel_count"])
            if ma[key]["raw_eroded_2px_mean"] is not None:
                self.assertAlmostEqual(
                    ma[key]["within_frame_quantile_contrast_eroded_2px"],
                    mb[key]["within_frame_quantile_contrast_eroded_2px"],places=10)
        self.assertGreater(seen,20)

    def test_two_pixel_inward_support_never_exceeds_original_and_may_disappear(self):
        result=sensitivity.sample_frame_sensitivity(*make_scene())
        counts=[(x["full_pixel_count"],x["eroded_2px_pixel_count"]) for x in result["entities"]]
        self.assertTrue(all(0<=eroded<=full for full,eroded in counts))
        self.assertTrue(any(eroded<full for full,eroded in counts if full>0))
        self.assertTrue(all(x["physical_facet_correspondence"]=="not_established"
                            and not x["normalization_calibrated"]
                            and not x["support_pixel_partition_exclusive"]
                            for x in result["entities"]))

    def test_flat_reference_abstains_instead_of_dividing_by_zero(self):
        scaffold,transfer,_,mask,valid,_=make_scene()
        raw=np.full(mask.shape,.48)
        baseline=handoff.sample_fixed_frame(scaffold,transfer,raw,mask,valid)
        record=sensitivity.sample_frame_sensitivity(
            scaffold,transfer,raw,mask,valid,baseline)
        self.assertFalse(record["contrast_proxy_available"])
        for e in record["entities"]:
            self.assertIsNone(e["within_frame_quantile_contrast_full"])
            self.assertIsNone(e["within_frame_quantile_contrast_eroded_2px"])
            if e["raw_full_mean"] is not None:
                self.assertAlmostEqual(e["raw_full_mean"],.48)

    def test_unavailable_support_and_refit_guards(self):
        a=make_scene()
        scaffold,transfer,raw,mask,valid,baseline=a
        unavailable=next(v for v in baseline["entities"]
                         if v["raw_mean_brightness"] is not None)
        updated=deepcopy(transfer)
        updated["entities"][unavailable["semantic_id"]]["status"]="unavailable"
        base2=handoff.sample_fixed_frame(scaffold,updated,raw,mask,valid)
        rec=sensitivity.sample_frame_sensitivity(scaffold,updated,raw,mask,valid,base2)
        row=next(v for v in rec["entities"] if v["semantic_id"]==unavailable["semantic_id"])
        self.assertEqual(row["full_pixel_count"],0)
        self.assertIsNone(row["raw_full_mean"])
        self.assertIsNone(row["within_frame_quantile_contrast_full"])
        corrupt=deepcopy(baseline)
        obs=next(v for v in corrupt["entities"] if v["raw_mean_brightness"] is not None)
        obs["raw_mean_brightness"]+=.01
        with self.assertRaisesRegex(ValueError,"baseline changed"):
            sensitivity.sample_frame_sensitivity(*a[:-1],corrupt)
        bad=deepcopy(transfer)
        bad["refit_performed"]=True
        with self.assertRaisesRegex(ValueError,"ruler"):
            sensitivity.sample_frame_sensitivity(scaffold,bad,raw,mask,valid,baseline)

    def test_summary_no_quality_claims_and_null_aware_rank(self):
        f1=sensitivity.sample_frame_sensitivity(*make_scene())
        f2=sensitivity.sample_frame_sensitivity(*make_scene(gain=1.2,offset=.02))
        # Vary a second appearance sequence, while never shifting its support.
        f2["source_index"]=12
        report=sensitivity.summarize("IGI-SYNTHETIC",[f1,f2],
                                     {"primary_wireframe_sha256":"test",
                                      "transfer_sha256":"test"},
                                     "unresolved_not_safe_to_call_crown")
        self.assertEqual(report["frame_count"],2)
        self.assertEqual(report["entity_count"],55)
        self.assertIsNone(report["optical_quality_score"])
        self.assertFalse(report["scaffold_refitted"])
        self.assertEqual(report["policy"]["alternate_support"],
                         "2_pixel_binary_erosion_of_same_frozen_polygon_union")
        self.assertTrue(all(v["rank_correlation_raw_vs_contrast_proxy"] is None
                            for v in report["entity_sensitivity"].values()))
        self.assertTrue(any(v["paired_core_frames"]>0
                            for v in report["entity_sensitivity"].values()))

    def test_artifact_pair_is_reproducible(self):
        f1=sensitivity.sample_frame_sensitivity(*make_scene())
        f2=sensitivity.sample_frame_sensitivity(*make_scene(gain=1.08))
        f2["source_index"]=12
        record=sensitivity.summarize("IGI-SYNTHETIC",[f1,f2],
                                     {"primary_wireframe_sha256":"test"},
                                     "resolved")
        with tempfile.TemporaryDirectory() as tmp:
            sensitivity.save(record,tmp)
            p=Path(tmp)
            self.assertEqual(record,json.loads((p/"exposure-support-sensitivity.json").read_text()))
            self.assertGreater((p/"exposure-support-sensitivity.png").stat().st_size,3000)


if __name__=="__main__":
    unittest.main()
