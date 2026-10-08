"""Research #123: image-plane optical movement is not polished-facet motion."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import asscher_optical_neighbor_dynamics as motion
from diamond360 import asscher_optical_physical_provenance as provenance
from tests.test_asscher_optical_physical_provenance import fixture


def observed(source, fraction, *, side=0, gradient=.35, coverage=.70):
    return {
        "candidate_id": f"src{source:04d}:side{side}:line0",
        "source_index": source,
        "side_orientation_family": side,
        "fraction": fraction,
        "gauge_midpoint_xy": [fraction, .25],
        "gradient_strength": gradient,
        "gradient_coverage": coverage,
        "physical_facet_semantic_id": None,
    }


def paired_input():
    line, junction = fixture()
    line["selected_source_indices"] = [16,17]
    junction["selected_source_indices"] = [16,17]
    for row, source in zip(line["frames"],(16,17)):
        row["source_index"] = source
        row["position"] = source
        for side in row["sides"]:
            for candidate in side["detected_candidates"]:
                candidate["strength"]=.3 if source==16 else .5
    for row, source in zip(junction["frames"],(16,17)):
        row["source_index"] = source
    return line, junction


class OpticalNeighborTests(unittest.TestCase):
    def test_circular_neighbor_order_and_unsampled_gaps(self):
        frames=[
            {"source_index":252,"position":252},
            {"source_index":0,"position":0},
            {"source_index":1,"position":1},
            {"source_index":5,"position":5},
        ]
        included, skipped=motion.selected_neighbor_pairs(frames)
        self.assertEqual(
            [(x["from_position"],x["to_position"],x["frame_gap"]) for x in included],
            [(0,1,1)]
        )
        self.assertEqual(len(skipped),3)
        self.assertEqual([x["frame_gap"] for x in skipped],[4,247,4])

    def test_exact_neighbors_vs_intermediate_censoring(self):
        frames=[
            {"source_index":13,"position":13},
            {"source_index":16,"position":16},
            {"source_index":17,"position":17},
        ]
        included, skipped=motion.selected_neighbor_pairs(frames)
        self.assertEqual([r["frame_gap"] for r in included],[3,1])
        self.assertEqual(
            [r["number_unsampled_intervening_frames"] for r in included],[2,0]
        )
        self.assertEqual([r["is_exact_consecutive_frame"] for r in included],
                         [False,True])
        self.assertEqual(len(skipped),1)

    def test_optical_motion_signed_and_brightness_changes_not_facet(self):
        result=motion._pair_candidates(
            [observed(16,.55,gradient=.25,coverage=.78)],
            [observed(17,.58,gradient=.40,coverage=.55)],1
        )
        self.assertEqual(result["number_tentative_pairs"],1)
        self.assertEqual(result["number_newly_detected"],0)
        self.assertEqual(result["number_not_redetected"],0)
        paired=result["candidate_pairs"][0]
        self.assertAlmostEqual(paired["signed_radial_fraction_delta"],.03)
        self.assertAlmostEqual(paired["gradient_strength_delta"],.15)
        self.assertAlmostEqual(paired["coverage_delta"],-.23)
        self.assertTrue(paired["possible_virtual_or_reflected_facet"])
        self.assertEqual(paired["physical_facet_correspondence"],"not_established")

    def test_outside_gate_is_censored_not_physical_disappearance(self):
        result=motion._pair_candidates([observed(13,.42)], [observed(16,.61)],3)
        self.assertEqual(result["candidate_pairs"],[])
        self.assertEqual(result["number_not_redetected"],1)
        self.assertEqual(result["number_newly_detected"],1)
        self.assertIn("NOT proof",result["note"])

    def test_must_share_original_silhouette_side_family(self):
        result=motion._pair_candidates([observed(13,.54,side=0)],
                                        [observed(16,.54,side=1)],3)
        self.assertEqual(result["number_tentative_pairs"],0)

    def test_cannot_reuse_one_destination_for_two_source_lines(self):
        result=motion._pair_candidates(
            [observed(13,.53),observed(13,.56)],
            [observed(16,.55)],3
        )
        self.assertEqual(result["number_tentative_pairs"],1)
        self.assertEqual(result["number_not_redetected"],1)

    def test_unverified_crown_is_not_upgraded_by_repetition(self):
        lines,junctions=paired_input()
        before=deepcopy((lines,junctions))
        r=motion.analyse_stone(lines,junctions)
        self.assertEqual((lines,junctions),before)
        self.assertEqual(r["crown_face_status"],"likely_crown")
        self.assertEqual(r["total_exact_consecutive_windows"],1)
        self.assertTrue(r["no_physical_or_virtual_facet_auto_labels"])
        self.assertEqual(r["physical_geometry"]["C3_TABLE"],"unavailable")
        junctions["face_identity"]={"status":"uncertain"}
        r=motion.analyse_stone(lines,junctions)
        self.assertEqual(r["crown_face_status"],"uncertain")
        self.assertEqual(r["total_exact_consecutive_windows"],1)
        self.assertEqual(r["physical_geometry"]["C3_TABLE"],"unavailable")

    def test_forged_RGB_physical_label_rejected_by_provenance_gate(self):
        lines,junctions=paired_input()
        junctions["physical_facet_identity_verified"]=True
        with self.assertRaisesRegex(ValueError,"source cannot claim"):
            motion.analyse_stone(lines,junctions)

    def test_bad_source_segment_rejected(self):
        lines,junctions=paired_input()
        lines["frames"][0]["sides"][0]["detected_candidates"][0][
            "rendered_segment_policy"]="fabricated"
        with self.assertRaises(ValueError):
            motion.analyse_stone(lines,junctions)

    def test_source_RGB_comparison_crops_first_unannotated_panel(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"qc.jpg"
            image=Image.new("RGB",(608,180),(255,0,0))
            from PIL import ImageDraw
            d=ImageDraw.Draw(image)
            d.rectangle((200,0,400,179),fill=(0,255,0))
            d.rectangle((405,0,607,179),fill=(0,0,255))
            image.save(path,quality=100,subsampling=0)
            panel=motion._original_rgb_crop(path)
            self.assertEqual(panel.size,(200,180))
            self.assertGreater(np.asarray(panel)[90,90,0],240)
            self.assertLess(np.asarray(panel)[90,90,1],15)

    def test_missing_and_duplicate_rotation_positions_rejected(self):
        with self.assertRaises(ValueError):
            motion.selected_neighbor_pairs([{"source_index":1,"position":3},
                                            {"source_index":2,"position":3}])
        with self.assertRaises(ValueError):
            motion.selected_neighbor_pairs([{"source_index":1,"position":None},
                                            {"source_index":2,"position":4}])


if __name__=="__main__":
    unittest.main()
