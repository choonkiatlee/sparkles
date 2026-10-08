"""Four-stone optical atlas cannot turn texture drift into facet motion."""
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy

import numpy as np

from diamond360 import asscher_optical_motion_atlas as atlas


def patch(row,col,shift=(0,0),status="measured"):
    return {
        "grid":[row,col],"status":status,
        "apparent_shift_gauge_px":(
            {"dx":shift[0],"dy":shift[1]} if status=="measured" else None),
        "best_gradient_ncc":.85,
        "best_vs_nonlocal_peak_margin":.14,
        "physical_facet_semantic_id":None,
    }


def sample_pair(shifts=None):
    shifts=shifts or {(i,j):(1,0) for i in range(4) for j in range(4)}
    patches=[patch(i,j,shifts[i,j]) for i in range(4) for j in range(4)]
    return {
        "positions":[13,14],"source_indices":[13,14],
        "status":"observed","physical_facet_semantic_ids":None,
        "physical_facet_correspondence":"unavailable",
        "mask_intersection_over_union":.98,
        "patches":patches,
    }


class OpticalMotionAtlasTests(unittest.TestCase):
    def test_uniform_shared_image_shift_is_not_local_motion(self):
        result=atlas.classify_pair(sample_pair())
        self.assertEqual(result["shared_image_shift"],{"dx":1.,"dy":0.})
        self.assertEqual(result["counts"]["shared_image_shift"],16)
        self.assertEqual(result["counts"]["local_residual_shift"],0)
        self.assertFalse(result["physical_facet_identity_verified"])
        self.assertTrue(result["not_a_quality_score"])

    def test_one_localized_residual_is_visible_and_unverified(self):
        shifts={(i,j):(1,0) for i in range(4) for j in range(4)}
        shifts[2,1]=(-2,1)
        result=atlas.classify_pair(sample_pair(shifts))
        self.assertEqual(result["counts"]["local_residual_shift"],1)
        self.assertEqual(result["counts"]["shared_image_shift"],15)
        cell=next(t for t in result["tiles"] if t["grid"]==[2,1])
        self.assertEqual(cell["status"],"local_residual_shift")
        self.assertIsNone(cell["physical_facet_semantic_id"])

    def test_search_window_saturation_is_censored_not_residual(self):
        shifts={(i,j):(0,0) for i in range(4) for j in range(4)}
        shifts[0,1]=(4,0)
        shifts[2,3]=(1,-4)
        result=atlas.classify_pair(sample_pair(shifts))
        self.assertEqual(result["counts"]["search_window_limited"],2)
        self.assertEqual(result["counts"]["shared_image_shift"],14)
        self.assertEqual(result["counts"]["local_residual_shift"],0)

    def test_few_unclipped_tiles_no_invented_shared_reference(self):
        pair=sample_pair()
        for p in pair["patches"][:9]:
            p["apparent_shift_gauge_px"]={"dx":4,"dy":0}
        result=atlas.classify_pair(pair)
        self.assertIsNone(result["shared_image_shift"])
        self.assertEqual(result["counts"]["search_window_limited"],9)
        self.assertEqual(result["counts"]["no_common_reference"],7)

    def test_missing_and_ambiguous_never_fabricate_zero_shift(self):
        pair=sample_pair()
        for i,p in enumerate(pair["patches"][:3]):
            p["status"]="ambiguous" if i<2 else "unavailable"
            p["apparent_shift_gauge_px"]=None
        result=atlas.classify_pair(pair)
        self.assertEqual(result["counts"]["ambiguous"],2)
        self.assertEqual(result["counts"]["unavailable"],1)
        self.assertEqual(result["counts"]["shared_image_shift"],13)
        self.assertEqual(len(result["tiles"]),16)

    def test_ambiguous_patch_with_fake_vector_fails_closed(self):
        pair=sample_pair()
        pair["patches"][0]["status"]="ambiguous"
        with self.assertRaisesRegex(ValueError,"unmeasured"):
            atlas.classify_pair(pair)

    def test_bad_provenance_and_forged_facet_id_rejected(self):
        for mutation in ("pair","patch","duplicate","nonadjacent","overshift"):
            pair=sample_pair()
            if mutation=="pair":
                pair["physical_facet_correspondence"]="validated_polished_facet"
            elif mutation=="patch":
                pair["patches"][3]["physical_facet_semantic_id"]="TABLE"
            elif mutation=="duplicate":
                pair["patches"][3]["grid"]=[0,0]
            elif mutation=="nonadjacent":
                pair["physical_facet_semantic_ids"]=["C3_TABLE"]
            else:
                pair["patches"][3]["apparent_shift_gauge_px"]={"dx":5,"dy":0}
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                atlas.classify_pair(pair)

    def test_crown_uncertainty_and_registration_caution_survive(self):
        pair=sample_pair()
        pair["mask_intersection_over_union"]=.91
        result=atlas.classify_pair(pair)
        self.assertTrue(result["registration_caution"])
        self.assertIsNone(result["tiles"][0]["physical_facet_semantic_id"])

    def test_aggregation_and_rendering_are_observational_only(self):
        a=atlas.classify_pair(sample_pair())
        b=atlas.classify_pair(sample_pair())
        b["tiles"][0]["status"]="ambiguous"
        data=atlas.aggregate_maps([a,b])
        self.assertEqual(len(data),16)
        self.assertEqual(data[0]["statuses"]["ambiguous"],1)
        self.assertEqual(data[0]["paired_frame_observations"],2)
        self.assertIsNone(data[0]["facet_semantic_id"])
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"atlas.png"
            atlas.render_atlas(a,title="Original RGB pair 13-14").save(file)
            self.assertGreater(file.stat().st_size,1000)
            other=Path(tmp)/"aggregate.png"
            atlas.render_atlas(data,title="Stone aggregate",aggregate=True).save(other)
            self.assertGreater(other.stat().st_size,1000)


if __name__=="__main__":
    unittest.main()
