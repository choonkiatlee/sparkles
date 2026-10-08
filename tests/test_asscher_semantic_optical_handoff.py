"""Smoke only: fixed #89 source support samples brightness without moving geometry."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from diamond360 import asscher_topology as topology
from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_semantic_optical_handoff as handoff


def fixture():
    scaffold=topology.canonical_synthetic_scaffold(gauge_id="frozen-synthetic-gauge")
    entries={}
    for key,obs in scaffold["entity_observations"].items():
        available=bool(obs.get("support_ids"))
        entries[key]={
            "semantic_id":key,
            "status":"ok" if available else "unavailable",
            "confidence":0.75 if available else 0,
            "support_kind":"fixed_nonexclusive_image_support",
        }
    transferred={
        "schema_version":stability.TRANSFER_SCHEMA,
        "source_index":11,
        "rotation_phase_deg":19.0,
        "semantic_gauge_id":"frozen-synthetic-gauge",
        "semantic_identity_source":"primary_fixed_scaffold",
        "geometry_mode":stability.TRANSFER_POLICY,
        "refit_performed":False,
        "entities":entries,
    }
    raw=np.full((96,96),0.24,float)
    gauge=np.zeros((96,96),bool)
    gauge[14:82,14:82]=True
    valid=gauge.copy()
    return scaffold, transferred, raw, gauge, valid


class FixedRulerBrightnessHandoffTests(unittest.TestCase):
    def test_brightness_changes_without_moving_semantic_ruler(self):
        scaffold,transfer,first,mask,valid=fixture()
        original=deepcopy(scaffold)
        other=deepcopy(transfer)
        other["source_index"]=12
        other["rotation_phase_deg"]=20.3
        second=np.full_like(first,0.81)
        result=handoff.sample_sequence(scaffold,[
            (transfer,first,mask,valid,None),
            (other,second,mask,valid,None),
        ])
        self.assertEqual(scaffold,original)
        self.assertEqual(result["counts"]["frames"],2)
        self.assertTrue(result["no_physical_angles_or_quality_scores"])
        self.assertEqual(result["frames"][0]["scaffold_unchanged"],True)
        self.assertEqual(result["frames"][1]["scaffold_unchanged"],True)
        self.assertEqual(result["frames"][0]["physical_facet_angle_status"],"unavailable")
        left={row["semantic_id"]:row for row in result["frames"][0]["entities"]}
        right={row["semantic_id"]:row for row in result["frames"][1]["entities"]}
        self.assertEqual(set(left),set(right))
        self.assertEqual(set(left),set(scaffold["entity_observations"]))
        observed=[key for key,row in left.items() if row["supported_pixel_count"]>0]
        self.assertGreater(len(observed),8)
        for key in observed:
            self.assertAlmostEqual(left[key]["raw_mean_brightness"],0.24)
            self.assertAlmostEqual(right[key]["raw_mean_brightness"],0.81)
            self.assertEqual(left[key]["supported_pixel_count"],
                             right[key]["supported_pixel_count"])
            self.assertEqual(left[key]["image_support_attribution"],
                             "nonexclusive_overlapping_not_polished_facet")
            self.assertIsNone(left[key]["normalized_mean_brightness"])

    def test_duplicate_polygon_supports_can_be_shared_between_semantic_ids(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        ids=list(scaffold["entity_observations"])
        a=next(key for key in ids if key.startswith("C1_"))
        b=next(key for key in ids if key.startswith("P3_"))
        support_id=scaffold["entity_observations"][a]["support_ids"][0]
        support=next(row for row in scaffold["semantic_supports"]
                     if row["support_id"]==support_id)
        support["semantic_ids"].append(b)
        scaffold["entity_observations"][b]["support_ids"]=[support_id]
        result=handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid)
        rows={row["semantic_id"]:row for row in result["entities"]}
        self.assertGreater(rows[a]["supported_pixel_count"],0)
        self.assertEqual(rows[a]["supported_pixel_count"],
                         rows[b]["supported_pixel_count"])
        self.assertEqual(rows[a]["physical_facet_correspondence"],"not_established")
        self.assertEqual(rows[b]["physical_facet_correspondence"],"not_established")

    def test_uncertain_inner_C3_table_support_stays_review(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        c3=next(key for key in scaffold["entity_observations"] if key.startswith("C3_"))
        transfer["entities"][c3]["status"]="review"
        transfer["entities"][c3]["confidence"]=0.3
        result=handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid)
        row=next(v for v in result["entities"] if v["semantic_id"]==c3)
        self.assertEqual(row["geometry_support_status"],"review")
        self.assertEqual(row["inner_ring_physical_identity"],"review_not_verified")
        self.assertEqual(row["geometry_confidence"],0.3)
        self.assertGreater(row["supported_pixel_count"],0)

    def test_unavailable_rows_do_not_get_brightness_even_with_visible_pixels(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        key=next(key for key in scaffold["entity_observations"] if key.startswith("P1_"))
        transfer["entities"][key]["status"]="unavailable"
        transfer["entities"][key]["confidence"]=0
        output=handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid,
                                           normalized_brightness=raw*0.6)
        row=next(v for v in output["entities"] if v["semantic_id"]==key)
        self.assertEqual(row["supported_pixel_count"],0)
        self.assertIsNone(row["raw_mean_brightness"])
        self.assertIsNone(row["normalized_mean_brightness"])
        other=next(v for v in output["entities"] if v["supported_pixel_count"]>0)
        self.assertAlmostEqual(other["normalized_mean_brightness"],.144)

    def test_wrong_gauge_refit_identity_or_brightness_geometry_fails_closed(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        scenarios=[("semantic_gauge_id","another-gauge"),
                   ("refit_performed",True),
                   ("geometry_mode","refit_each_frame")]
        for field,value in scenarios:
            test=deepcopy(transfer)
            test[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                handoff.sample_fixed_frame(scaffold,test,raw,gauge,valid)
        test=deepcopy(transfer)
        test["entities"].pop(next(iter(test["entities"])))
        with self.assertRaisesRegex(ValueError,"Semantic|semantic"):
            handoff.sample_fixed_frame(scaffold,test,raw,gauge,valid)
        with self.assertRaisesRegex(ValueError,"share 2D shape"):
            handoff.sample_fixed_frame(scaffold,transfer,raw,gauge,valid[:10,:])
        with self.assertRaisesRegex(ValueError,"gauge mask is empty"):
            handoff.sample_fixed_frame(scaffold,transfer,raw,np.zeros_like(gauge),valid)

    def test_serialized_smoke_contains_only_fixed_source_measurement(self):
        scaffold,transfer,raw,gauge,valid=fixture()
        with tempfile.TemporaryDirectory() as temp:
            outfile=Path(temp)/"handoff.json"
            result=handoff.save_report(scaffold,[(transfer,raw,gauge,valid,None)],outfile)
            self.assertEqual(result,json.loads(outfile.read_text()))
            self.assertEqual(result["frames"][0]["schema_version"],handoff.SCHEMA)
            self.assertEqual(result["frames"][0]["optic_quality_score"],None)


if __name__=="__main__":
    unittest.main()
