"""#123: Neighbor-view appearance can change without proving facet motion."""
from copy import deepcopy
import unittest

import numpy as np
from scipy import ndimage as ndi

from diamond360 import asscher_optical_neighbor_motion as motion
from diamond360 import asscher_geometry_validation as validation


class NeighborOpticalMotionTests(unittest.TestCase):
    def test_frozen_geometry_and_no_physical_facet_claim(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(motion.POLICY["no_physical_facet_labels"])
        self.assertTrue(motion.POLICY["no_production_estimator_change"])
        self.assertEqual(motion.POLICY["max_local_shift_px"],4)

    def test_adjacent_ordinal_pair_selection_no_distant_or_duplicate_pairs(self):
        frames=[{"position":i} for i in range(10)]
        payload={"frames":frames}
        selected=[frames[2],frames[3],frames[9]]
        pairs=motion.neighboring_pairs(payload,selected,limit=12)
        self.assertEqual(pairs,[(1,2),(2,3),(3,4),(8,9),(9,0)])
        self.assertEqual(len(pairs),len(set(pairs)))
        self.assertTrue(all((b-a)%10==1 for a,b in pairs))
        with self.assertRaisesRegex(ValueError,"complete ordered"):
            motion.neighboring_pairs({"frames":frames[:-1]+[{"position":3}]},selected)

    def test_identical_original_appearance_is_zero_change(self):
        rng=np.random.default_rng(33)
        image=.3+.25*rng.random((144,144))
        mask=np.ones_like(image,bool)
        report=motion.measure_pair(image,image,mask,mask,mask,mask)
        self.assertEqual(report["status"],"observed")
        self.assertAlmostEqual(report["median_gain_normalized_abs_change"],0.,places=10)
        self.assertAlmostEqual(report["mean_gain_normalized_edge_change"],0.,places=10)
        self.assertIsNone(report["physical_facet_correspondence"] if False else None)
        self.assertEqual(report["physical_facet_correspondence"],"unavailable")

    def test_simple_exposure_gain_does_not_look_like_apparent_motion(self):
        rng=np.random.default_rng(8)
        image=.2+.35*rng.random((144,144))
        mask=np.ones_like(image,bool)
        report=motion.measure_pair(image,image*1.7,mask,mask,mask,mask)
        self.assertAlmostEqual(report["raw_median_luminance_ratio_b_over_a"],1.7,places=8)
        self.assertLess(report["median_gain_normalized_abs_change"],1e-8)
        self.assertLess(report["mean_gain_normalized_edge_change"],1e-8)

    def test_spatially_moving_optical_texture_detectable_as_shift_not_a_facet(self):
        h=w=180
        rng=np.random.default_rng(9)
        raw=ndi.gaussian_filter(rng.random((h,w)),sigma=1.)
        a=motion._edge(raw)
        # Only interior is valid, so no wrap-around can be misread.
        b=np.zeros_like(a)
        b[2:,3:]=a[:-2,:-3]
        valid=np.ones_like(a,bool)
        valid[:6]=False
        valid[:,:6]=False
        patches=motion.measure_patch_shifts(a,b,valid,grid=4,max_shift=4)
        confident=[r for r in patches if r["status"]=="measured"]
        self.assertGreaterEqual(len(confident),5)
        self.assertTrue(all(r["physical_facet_semantic_id"] is None
                            for r in patches if "physical_facet_semantic_id" in r))
        self.assertTrue(any(r["apparent_shift_gauge_px"]=={"dx":3,"dy":2}
                            for r in confident))

    def test_flat_patch_never_fabricates_translation(self):
        a=np.ones((144,144),float)*.4
        patches=motion.measure_patch_shifts(a,a,np.ones_like(a,bool))
        self.assertTrue(all(r["status"]=="unavailable" for r in patches))
        pair=motion.measure_pair(a,a,np.ones_like(a,bool),
                                 np.ones_like(a,bool),
                                 np.ones_like(a,bool),
                                 np.ones_like(a,bool))
        self.assertEqual(pair["measured_optical_shift_tile_count"],0)

    def test_missing_overlap_abstains(self):
        a=np.full((144,144),.5)
        mask=np.zeros_like(a,bool)
        mask[:12,:12]=True
        report=motion.measure_pair(a,a,mask,mask,mask,mask)
        self.assertEqual(report["status"],"unavailable")
        self.assertEqual(report["reason"],"insufficient_common_interior")

    def test_rgb_change_heatmap_masks_off_stone_and_mismatched_edges(self):
        from PIL import Image
        # The two masks disagree at the edge; the diagnostic heat panel
        # must not display artificial bright motion outside their common
        # interior, even though their source camera crops remain original.
        a=np.full((144,144),.4)
        b=np.full((144,144),.45)
        mask_a=np.zeros_like(a,bool)
        mask_b=np.zeros_like(a,bool)
        mask_a[10:130,10:130]=True
        mask_b[18:140,18:140]=True
        report=motion.measure_pair(a,b,mask_a,mask_b,mask_a,mask_b)
        self.assertEqual(report["status"],"observed")
        source_a=Image.fromarray(np.uint8(a*255)).convert("RGB")
        source_b=Image.fromarray(np.uint8(b*255)).convert("RGB")
        panel=motion.render_pair(
            source_a,source_b,mask_a,mask_b,np.eye(3),np.eye(3),
            a,b,report,(15,16)
        )
        # The heatmap is drawn in third panel with a fixed padding.
        panel_w=max(source_a.width,source_b.width,220)
        heat_start=2*(panel_w+6)
        self.assertEqual(
            panel.getpixel((heat_start+2,60)),(10,14,24)
        )

    def test_invalid_pose_neighbor_remains_unavailable(self):
        rec={"assessment":{"status":"ok"},
             "canonical":{"path":"canonical/0000.npz"},
             "source_camera_path":"camera/0000.png",
             "sequence_coordinate":{"gauge_status":"available",
                                    "sequence_gauge_to_camera_xy":np.eye(3).tolist()}}
        self.assertTrue(motion._valid_record(rec))
        bad=deepcopy(rec);bad["sequence_coordinate"]["gauge_status"]="unavailable"
        self.assertFalse(motion._valid_record(bad))
        bad=deepcopy(rec);bad["source_camera_path"]=None
        self.assertFalse(motion._valid_record(bad))


if __name__=="__main__":
    unittest.main()
