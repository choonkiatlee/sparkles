"""Regression: no optical feature becomes physical facet geometry."""
from copy import deepcopy
import tempfile
import unittest

from diamond360 import asscher_optical_physical_provenance as prov
from diamond360 import asscher_wireframe as wireframe


def fixture():
    line={
        "certificate":"SYNTHETIC",
        "selected_source_indices":[13,16],
        "original_outer_method_unchanged":True,
        "physical_facet_claim":False,
        "outer_vertices_topology_order":wireframe._ideal_outer_vertices().tolist(),
        "frames":[],
    }
    junction={
        "certificate":"SYNTHETIC",
        "selected_source_indices":[13,16],
        "production_estimator_changed":False,
        "physical_facet_identity_verified":False,
        "face_identity":{"status":"likely_crown"},
        "frames":[],
    }
    for src in [13,16]:
        sides=[{"side":i,"detected_candidates":[]} for i in range(8)]
        for sid in (0,7):
            sides[sid]["detected_candidates"]=[{
                "fraction":.55,
                "sample_start":[-.50,-.50],
                "sample_end":[-.40,-.40],
                "coverage":.7,
                "longest_contiguous_fraction":.5,
                "rendered_segment_policy":"only_contiguous_observed_RGB_gradient_pixels",
            }]
        line["frames"].append({"source_index":src,"sides":sides})
        junction["frames"].append({
            "source_index":src,
            "junction_evidence":{
                "physical_facet_identity_verified":False,
                "polygon":None,
                "nodes":[{
                    "id":0,"line_candidate_indices":{"7":0,"0":0},
                    "position_gauge_normalized_xy":[-.46,-.46],
                }],
                "edges":[],
            },
        })
    return line,junction


class OpticalPhysicalContractTests(unittest.TestCase):
    def test_two_independent_provenance_lanes(self):
        line,junction=fixture()
        a=deepcopy(line)
        b=deepcopy(junction)
        result=prov.adapt_stone(line,junction)
        self.assertEqual((line,junction),(a,b))
        self.assertEqual(result["physical_geometry"]["external_silhouette"]
                         ["provenance_class"],prov.OUTER_CLASS)
        for name in prov.INTERIOR_BOUNDARIES:
            physical=result["physical_geometry"]["interior_boundaries"][name]
            self.assertEqual(physical["status"],"unavailable")
            self.assertIsNone(physical["vertices_topology_order"])
            with self.assertRaisesRegex(ValueError,"unavailable"):
                prov.require_physical_boundary(result,name)
        self.assertFalse(result["can_use_as_physical_facet_geometry"])
        self.assertEqual(len(result["optical_appearance"]["frames"]),2)
        for row in result["optical_appearance"]["frames"]:
            self.assertEqual(len(row["line_segment_candidates"]),2)
            self.assertEqual(len(row["junction_candidates"]),1)
            self.assertEqual(row["junction_candidates"][0]
                             ["physical_correspondence"],prov.UNKNOWN_PHYSICAL_CLASS)
            self.assertIsNone(row["junction_candidates"][0]["facet_semantic_id"])
            self.assertTrue(row["junction_candidates"][0]
                            ["possible_virtual_or_reflected_facet"])
        self.assertEqual(result["optical_appearance"]
                         ["cross_view_observed_line_family_counts"]["7"],2)

    def test_repeatability_or_resolved_crown_does_not_grant_physical_identity(self):
        line,junction=fixture()
        result=prov.adapt_stone(line,junction)
        self.assertEqual(result["face_identity"]["status"],"likely_crown")
        self.assertEqual(result["physical_interior_facet_status"],"unavailable")

    def test_uncertain_crown_retains_optical_but_never_physical(self):
        line,junction=fixture()
        junction["face_identity"]={"status":"uncertain"}
        result=prov.adapt_stone(line,junction)
        self.assertEqual(result["face_identity"]["status"],"uncertain")
        self.assertEqual(len(result["optical_appearance"]["frames"][0]
                             ["line_segment_candidates"]),2)
        self.assertFalse(result["can_use_as_physical_facet_geometry"])

    def test_forbid_claiming_verified_physical_junction_or_polygon(self):
        for mutation in ("physical","polygon"):
            line,junction=fixture()
            if mutation=="physical":
                junction["frames"][0]["junction_evidence"][
                    "physical_facet_identity_verified"]=True
            else:
                junction["frames"][0]["junction_evidence"]["polygon"]=[
                    [0,0],[1,1]
                ]
            with self.assertRaisesRegex(ValueError,"physical identity or polygon"):
                prov.adapt_stone(line,junction)

    def test_cannot_upgrade_unobserved_line_to_synthetic_junction(self):
        line,junction=fixture()
        junction["frames"][0]["junction_evidence"]["nodes"][0][
            "line_candidate_indices"]["7"]=3
        with self.assertRaisesRegex(ValueError,"unobserved line"):
            prov.adapt_stone(line,junction)

    def test_mismatched_frame_identity_rejected(self):
        line,junction=fixture()
        junction["selected_source_indices"]=[13,18]
        with self.assertRaisesRegex(ValueError,"view selection"):
            prov.adapt_stone(line,junction)

    def test_mismatched_source_facet_claim_rejected(self):
        line,junction=fixture()
        line["physical_facet_claim"]=True
        with self.assertRaisesRegex(ValueError,"physical facet identity"):
            prov.adapt_stone(line,junction)

    def test_empty_evidence_stays_explicitly_unavailable(self):
        line,junction=fixture()
        for row in line["frames"]:
            row["sides"]=[{"side":i,"detected_candidates":[]} for i in range(8)]
        for row in junction["frames"]:
            row["junction_evidence"]={"physical_facet_identity_verified":False,
                                       "polygon":None,"nodes":[],"edges":[]}
        result=prov.adapt_stone(line,junction)
        self.assertEqual(sum(len(row["line_segment_candidates"])
                             for row in result["optical_appearance"]["frames"]),0)
        self.assertEqual(result["physical_interior_facet_status"],"unavailable")

    def test_untrusted_source_coordinates_checked(self):
        line,junction=fixture()
        line["frames"][0]["sides"][0]["detected_candidates"][0]["sample_end"]=[
            float("nan"),0.
        ]
        with self.assertRaisesRegex(ValueError,"invalid line end"):
            prov.adapt_stone(line,junction)


if __name__=="__main__":
    unittest.main()
