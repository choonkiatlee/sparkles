"""Graph topology tests: no implicit octagon, no false source/RGB evidence."""
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_geometry_rgb_junction_graph as graph
from diamond360 import asscher_geometry_rgb_lines as lines
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


def candidate_rows(outer, *, missing=(), shorten=()):
    result=[]
    for side in lines.outer_side_families(outer):
        i=side["index"]
        # These lines are independent observations; the graph must determine
        # its own corners from their infinite-line intersections plus finite
        # observed segment support.
        xy=lines._line_sample(side,.56)
        start,stop=(10,80) if i not in shorten else (35,60)
        row={
            "fraction":.56,
            "sample_start":xy[start].tolist(),
            "sample_end":xy[stop].tolist(),
            "coverage":.87,
            "longest_contiguous_fraction":.70,
            "score":.92,
        }
        result.append({
            "side":i,
            "detected_candidates":[] if i in missing else [row],
            "selected_line":None if i in missing else row,
        })
    return result


def fixture(*,missing=(),shorten=()):
    outer=wireframe._ideal_outer_vertices()
    mask=np.ones((240,240),bool)
    blank=np.zeros_like(mask,float)
    detection={"gradient_reference":.08,"sides":candidate_rows(
        outer,missing=missing,shorten=shorten
    )}
    return outer,detection,blank,mask


class ObservedRGBJunctionTests(unittest.TestCase):
    def test_policy_immutable_controls_and_no_physical_claim(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(graph.POLICY["no_production_estimator_change"])
        self.assertTrue(graph.POLICY["no_completing_missing_junctions"])
        self.assertTrue(graph.POLICY["no_facet_identity_from_RGB_contrast"])
        self.assertEqual(graph.POLICY["max_line_candidates_per_side"],3)

    def test_synthetic_closed_cycle_requires_eight_measured_junctions(self):
        outer,detected,gray,mask=fixture()
        with patch.object(graph,"_junction_pixel_support",
                          return_value=(True,[{"synthetic":True}]*2)):
            result=graph.candidate_junction_graph(
                outer,detected,gray=gray,valid=mask,mask=mask
            )
        self.assertEqual(len(result["nodes"]),8)
        self.assertEqual(len(result["edges"]),8)
        self.assertTrue(result["has_supported_eight_corner_cycle"])
        self.assertEqual(result["connected_corner_max"],8)
        self.assertTrue(all(
            row["provenance"]=="observed_RGB_line_intersection_hypothesis"
            for row in result["nodes"]
        ))

    def test_missing_one_side_never_completes_graph(self):
        outer,detected,gray,mask=fixture(missing=(3,))
        with patch.object(graph,"_junction_pixel_support",
                          return_value=(True,[{"synthetic":True}]*2)):
            result=graph.candidate_junction_graph(
                outer,detected,gray=gray,valid=mask,mask=mask
            )
        self.assertEqual(len(result["nodes"]),6)
        self.assertFalse(result["has_supported_eight_corner_cycle"])
        self.assertLess(result["connected_corner_max"],8)

    def test_supported_lines_without_local_rgb_junction_abstain(self):
        outer,detected,gray,mask=fixture()
        # This test uses the real native RGB gradient checker.
        result=graph.candidate_junction_graph(
            outer,detected,gray=gray,valid=mask,mask=mask
        )
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["reason"],"no_observed_two_line_RGB_junctions")
        self.assertEqual(len(result["nodes"]),0)
        self.assertFalse(result["has_supported_eight_corner_cycle"])

    def test_segments_far_from_true_intersections_cannot_fabricate_corners(self):
        outer,detected,gray,mask=fixture(shorten=tuple(range(8)))
        with patch.object(graph,"_junction_pixel_support",
                          return_value=(True,[{"synthetic":True}]*2)) as audit:
            result=graph.candidate_junction_graph(
                outer,detected,gray=gray,valid=mask,mask=mask
            )
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["has_supported_eight_corner_cycle"])
        self.assertEqual(len(result["nodes"]),0)
        audit.assert_not_called()

    def test_no_outer_or_native_rgb_evidence_fails_closed(self):
        outer,detected,gray,mask=fixture()
        no_evidence={"sides":detected["sides"],"gradient_reference":None}
        result=graph.candidate_junction_graph(
            outer,no_evidence,gray=gray,valid=mask,mask=mask
        )
        self.assertEqual(result["reason"],"no_RGB_gradient_reference")
        with self.assertRaisesRegex(ValueError,"native RGB"):
            graph.candidate_junction_graph(outer,detected)

    def test_camera_rgb_visual_has_two_real_panels(self):
        from PIL import Image
        outer,detected,gray,mask=fixture()
        result=graph.candidate_junction_graph(
            outer,detected,gray=gray,valid=mask,mask=mask
        )
        src=Image.new("RGB",(240,240),(41,74,98))
        img=graph.render_junction_overlay(
            src,mask,np.eye(3),outer,detected,result,
            source_index=16,face_status="unresolved_no_physical_interpretation"
        )
        self.assertGreater(img.width,src.width)
        self.assertGreater(img.height,100)


if __name__=="__main__":
    unittest.main()
