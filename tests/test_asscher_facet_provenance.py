"""#123: optical observations cannot silently become polished facet labels."""
from copy import deepcopy
import unittest

from diamond360 import asscher_facet_provenance as p
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


def fixtures():
    selected=[11,13,16]
    outer=wireframe._ideal_outer_vertices().tolist()
    line_rows=[]
    junction_rows=[]
    for i,source in enumerate(selected):
        sides=[]
        for sector in range(8):
            candidates=[]
            if sector==0 and i<2:
                candidates=[{
                    "fraction":.55+.01*i,
                    "coverage":.7,
                    "longest_contiguous_fraction":.6,
                    "sample_start":[.1,-.3],
                    "sample_end":[.1,.3],
                }]
            sides.append({"side":sector,"detected_candidates":candidates})
        line_rows.append({
            "source_index":source,
            "camera_RGB_QC":f"source-{source}-native-RGB.jpg",
            "sides":sides,
        })
        nodes=[{
            "id":0,"corner_index":7,
            "position_gauge_normalized_xy":[.3,.25],
        }] if i==1 else []
        junction_rows.append({
            "source_index":source,
            "source_camera_QC":f"source-{source}-junction-RGB.jpg",
            "junction_evidence":{"nodes":nodes},
        })
    lines={
        "certificate":"IGI-LG000000001",
        "selected_source_indices":selected,
        "outer_vertices_topology_order":outer,
        "frames":line_rows,
    }
    graph={
        "certificate":"IGI-LG000000001",
        "selected_source_indices":selected,
        "face_identity":{"status":"uncertain","selection_status":"not_needed"},
        "frames":junction_rows,
    }
    return lines,graph


class ProvenanceBoundaryTests(unittest.TestCase):
    def test_frozen_method_and_exact_external_silhouette_only(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        lines,graph=fixtures()
        out=p.build_stone_record(lines,graph)
        outside=out["physical_geometry"]["silhouette"]
        self.assertTrue(p.require_physical_support(outside))
        self.assertEqual(outside["semantic_id"],"GIRDLE_OUTLINE")
        self.assertEqual(outside["source_indices"],[11,13,16])
        self.assertEqual(out["counts"]["physical_interior_boundaries_validated"],0)
        for boundary in out["physical_geometry"]["interior_facet_boundaries"]:
            self.assertEqual(boundary["status"],"unavailable")
            self.assertIsNone(boundary["vertices"])
            with self.assertRaises(ValueError):
                p.require_physical_support(boundary)

    def test_reflections_and_intersections_are_always_optical_unverified(self):
        lines,graph=fixtures()
        report=p.build_stone_record(lines,graph)
        optical=report["optical_appearance"]
        self.assertEqual(len(optical["segments"]),2)
        self.assertEqual(len(optical["junction_candidates"]),1)
        for row in optical["segments"]+optical["junction_candidates"]:
            self.assertEqual(row["physical_facet_correspondence"],"not_established")
            self.assertEqual(row["optical_vs_structural"],"unresolved")
            self.assertIsNone(row["physical_facet_semantic_id"])
            with self.assertRaisesRegex(ValueError,"physical geometry requires"):
                p.require_physical_support(row)
        self.assertEqual(optical["confirmed_virtual_facet_labels"],[])
        self.assertTrue(report["no_optical_to_physical_promotion"])
        self.assertTrue(report["no_estimator_change"])

    def test_pairwise_repeated_reflection_does_not_promote_to_facet(self):
        lines,graph=fixtures()
        report=p.build_stone_record(lines,graph)
        side=report["cross_view_optical_consistency"]["per_side"]["0"]
        self.assertEqual(side["observed_source_count"],2)
        self.assertEqual(side["tested_source_pair_count"],1)
        self.assertEqual(side["close_pair_count"],1)
        self.assertEqual(report["counts"]["physical_interior_boundaries_validated"],0)
        self.assertEqual(report["physical_geometry"]["physical_correspondence_verified"],False)

    def test_identity_requires_matching_exact_frozen_views_and_certificates(self):
        lines,graph=fixtures()
        bad=deepcopy(graph)
        bad["selected_source_indices"]=[11,13,18]
        with self.assertRaisesRegex(ValueError,"selected views disagree"):
            p.build_stone_record(lines,bad)
        bad=deepcopy(graph)
        bad["certificate"]="another"
        with self.assertRaisesRegex(ValueError,"certificates disagree"):
            p.build_stone_record(lines,bad)
        bad=deepcopy(graph)
        bad["frames"]=bad["frames"][:-1]
        with self.assertRaisesRegex(ValueError,"omitted a selected source"):
            p.build_stone_record(lines,bad)

    def test_unresolved_crown_is_not_silently_assumed(self):
        lines,graph=fixtures()
        a=p.build_stone_record(lines,graph)
        self.assertEqual(a["crown_face_identity"]["status"],"uncertain")
        self.assertTrue(all(r["crown_view_status"]=="uncertain"
                            for r in a["optical_appearance"]["segments"]))
        graph["face_identity"]={"status":"likely_crown"}
        b=p.build_stone_record(lines,graph)
        self.assertTrue(all(r["crown_view_status"]=="likely_crown"
                            for r in b["optical_appearance"]["segments"]))
        self.assertEqual(b["counts"]["physical_interior_boundaries_validated"],0)

    def test_no_fabricated_segments_or_synthetic_junction_labels(self):
        lines,graph=fixtures()
        for r in lines["frames"]:
            for side in r["sides"]:
                side["detected_candidates"]=[]
        for r in graph["frames"]:
            r["junction_evidence"]["nodes"]=[]
        out=p.build_stone_record(lines,graph)
        self.assertEqual(out["optical_appearance"]["segments"],[])
        self.assertEqual(out["optical_appearance"]["junction_candidates"],[])
        self.assertEqual(out["cross_view_optical_consistency"]["per_side"]["0"]
                         ["observed_source_count"],0)
        self.assertEqual(out["counts"]["physical_silhouette_count"],1)

    def test_malformed_line_provenance_or_corners_fail_closed(self):
        lines,graph=fixtures()
        lines["frames"][0]["sides"][0]["detected_candidates"][0]["fraction"]=float("nan")
        with self.assertRaisesRegex(ValueError,"malformed observed RGB segment"):
            p.build_stone_record(lines,graph)
        lines,graph=fixtures()
        graph["frames"][1]["junction_evidence"]["nodes"][0]["corner_index"]=8
        with self.assertRaisesRegex(ValueError,"invalid junction"):
            p.build_stone_record(lines,graph)


if __name__=="__main__":
    unittest.main()
