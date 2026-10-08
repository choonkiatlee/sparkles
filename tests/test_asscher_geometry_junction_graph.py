"""Negative controls for a no-physical-facet-claim RGB junction graph."""
import unittest

import numpy as np

from diamond360 import asscher_geometry_junction_graph as graph
from diamond360 import asscher_geometry_rgb_lines as lines
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe
from tests.test_asscher_geometry_rgb_lines import synthetic_scene


def supported_rows(outer, fraction=.53):
    rows=[]
    for side in lines.outer_side_families(outer):
        samples=lines._line_sample(side,fraction)
        rows.append({
            "side":side["index"],
            "detected_candidates":[{
                "fraction":fraction,
                "sample_start":samples[0].tolist(),
                "sample_end":samples[-1].tolist(),
                "longest_contiguous_fraction":1.0,
                "coverage":1.0,
            }]
        })
    return rows


class JunctionGraphTests(unittest.TestCase):
    def test_frozen_method_and_zero_facet_claim(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertFalse(graph.POLICY["changes_estimator"])
        self.assertFalse(graph.POLICY["physical_facet_identity_claim"])
        self.assertFalse(graph.POLICY["full_polygon_from_missing_data"])

    def test_intersection_uses_both_observed_line_segments(self):
        outer=wireframe._ideal_outer_vertices()
        sides=lines.outer_side_families(outer)
        rows=supported_rows(outer,.55)
        prev,curr=sides[7],sides[0]
        a,b=rows[7]["detected_candidates"][0],rows[0]["detected_candidates"][0]
        result=graph._candidate_intersection(prev,a,curr,b)
        self.assertIsNotNone(result)
        point,distances=result
        np.testing.assert_allclose(point,np.asarray(outer[0])*.55,atol=1e-9)
        self.assertLess(max(distances),.045)
        # A long extrapolated crossing cannot create a junction.
        tiny={**a,"sample_start":a["sample_start"],
              "sample_end":a["sample_start"]}
        self.assertIsNone(graph._candidate_intersection(prev,tiny,curr,b))

    def test_no_gradient_means_no_junction_even_with_eight_fake_lines(self):
        outer=wireframe._ideal_outer_vertices()
        gray=np.zeros((240,240),float)
        mask=np.ones_like(gray,bool)
        candidate={
            "gradient_reference":.02,
            "sides":supported_rows(outer),
        }
        result=graph.detect_junction_graph(gray,mask,mask,outer,candidate)
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["nodes"],[])
        self.assertEqual(result["edges"],[])
        self.assertIsNone(result["polygon"])

    def test_missing_side_cannot_invent_closure(self):
        outer=wireframe._ideal_outer_vertices()
        gray,mask,_=synthetic_scene()
        segments=supported_rows(outer)
        segments[4]["detected_candidates"]=[]
        result=graph.detect_junction_graph(
            gray,mask,mask,outer,{"sides":segments,
                                  "gradient_reference":.001}
        )
        self.assertFalse(any(n["corner_index"] in (4,5)
                             for n in result["nodes"]))
        self.assertIsNone(result["polygon"])
        self.assertFalse(result.get("physical_facet_identity_verified",False))

    def test_graph_edges_only_connect_same_segment_candidate(self):
        self.assertEqual(
            graph.connected_components(5,[
                {"node_a":0,"node_b":1},
                {"node_a":1,"node_b":2},
                {"node_a":3,"node_b":4},
            ]),
            [[0,1,2],[3,4]]
        )
        self.assertEqual(graph.connected_components(3,[]),[[0],[1],[2]])

    def test_crown_gate_requires_resolved_likely_crown(self):
        frames=[{"face_role":"likely_crown_lobe"} for _ in range(5)]
        ok=graph.face_identity_state(
            {"face_selection":{"status":"resolved"}},frames)
        self.assertEqual(ok["status"],"likely_crown")
        for payload,roles in [
            ({"face_selection":{"status":"not_needed"}},frames),
            ({"face_selection":{"status":"resolved"}},
             frames[:-1]+[{"face_role":"unresolved"}]),
            ({"face_selection":{"status":"unavailable"}},frames),
        ]:
            self.assertEqual(
                graph.face_identity_state(payload,roles)["status"],
                "uncertain"
            )

    def test_structural_candidate_never_proves_true_junction(self):
        gray,mask,outer=synthetic_scene()
        candidates={
            "gradient_reference":.001,
            "sides":supported_rows(outer,.55),
        }
        r=graph.detect_junction_graph(gray,mask,mask,outer,candidates)
        self.assertIn(r["status"],("connected_fragments",
                                   "isolated_junction_hypotheses",
                                   "unavailable"))
        self.assertIsNone(r["polygon"])
        self.assertFalse(r.get("physical_facet_identity_verified",False))
        for node in r["nodes"]:
            self.assertLess(max(node["measured_segment_endpoint_distances"]),
                            graph.POLICY["maximum_corner_to_supported_segment_distance"])
            self.assertTrue(all(hit["oriented_hits"]>=2
                                for hit in node["local_orientation_hits"]))


if __name__=="__main__":
    unittest.main()
