"""Fail-closed image-line research diagnostic without production estimator edits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from diamond360 import asscher_geometry_native_line_qc as line
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


class NativeLineGeometryTests(unittest.TestCase):
    def test_policy_freezes_no_ring_fit_and_original_estimator(self):
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))
        self.assertTrue(line.POLICY["no_fixed_C3_radius_or_ring_fit"])
        self.assertFalse(line.POLICY["physical_facet_identity_claim"])
        self.assertTrue(line.POLICY["unavailable_if_no_supported_polygon"])

    def test_outline_families_preserve_eight_observed_sides(self):
        outer=wireframe._ideal_outer_vertices()
        family=line.outline_families(outer)
        self.assertEqual(len(family),8)
        self.assertTrue(all(f["outer_offset"]>0 for f in family))
        for r in family:
            self.assertAlmostEqual(
                np.dot(r["tangent"],r["normal"]),0.0,places=9
            )

    def test_finite_segment_intersections_no_distant_extrapolation(self):
        a={"p0":[40.,40.],"p1":[100.,40.],"family":0,
           "length_px":60.}
        b={"p0":[100.,40.],"p1":[126.,66.],"family":1,
           "length_px":36.77}
        pt=line.segment_intersection(a,b,max_extension_px=3.0)
        np.testing.assert_allclose(pt,[100.,40.])
        c={"p0":[200.,100.],"p1":[225.,125.],"family":1,
           "length_px":35.35}
        self.assertIsNone(line.segment_intersection(a,c,max_extension_px=3.0))

    def test_corner_requires_actual_observed_adjacent_segments(self):
        a={"p0":[40.,40.],"p1":[100.,40.],"family":0,
           "length_px":60.}
        b={"p0":[100.,40.],"p1":[126.,66.],"family":1,
           "length_px":36.77}
        mask=np.ones((256,256),bool)
        rows=line.observed_junctions([a,b],mask,diameter=160)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["family_pair"],[0,1])
        self.assertEqual(line.observed_junctions([a],mask,diameter=160),[])
        mask[40,100]=False
        self.assertEqual(line.observed_junctions([a,b],mask,diameter=160),[])

    def test_lsd_detection_classifies_observed_segment(self):
        outer=wireframe._ideal_outer_vertices()*100
        fam=line.outline_families(outer)
        centre=outer.mean(axis=0)
        first=fam[0]
        mid=centre+0.6*first["outer_offset"]*np.asarray(first["normal"])
        tangent=np.asarray(first["tangent"])
        a=mid-25*tangent
        b=mid+25*tangent
        segment=line._segment_projection(
            [*a,*b],fam,centre,diameter=220
        )
        self.assertIsNotNone(segment)
        self.assertEqual(segment["family"],0)
        self.assertAlmostEqual(segment["normal_fraction_of_outer"],.6,places=6)

    def test_exact_source_gauge_warp_and_RGB_panels(self):
        source=Image.new("RGB",(240,240),(20,110,220))
        identity=np.eye(3).tolist()
        record={
            "sequence_coordinate":{"sequence_gauge_to_camera_xy":identity},
            "source_index":16,"position":16,
            "face_role":"likely_crown_lobe",
            "source_camera_path":"original.png",
        }
        rgb,matrix=line._gauge_rgb(source,record,(240,240))
        self.assertEqual(tuple(rgb[120,120]),(20,110,220))
        np.testing.assert_allclose(matrix,np.eye(3))
        mask=np.ones((240,240),bool)
        mask[:30,:]=False
        with tempfile.TemporaryDirectory() as tmp:
            result=line._original_rgb_qc(
                source,record,mask,[],[],
                wireframe._ideal_outer_vertices(),matrix,
                Path(tmp)/"qc.jpg"
            )
            self.assertEqual(result,"qc.jpg")
            self.assertTrue((Path(tmp)/result).is_file())

    def test_invalid_source_transform_rejected(self):
        record={"sequence_coordinate":{
            "sequence_gauge_to_camera_xy":[[1,0,0],[0,1,0],[.02,0,1]]}}
        with self.assertRaisesRegex(ValueError,"non-affine"):
            line._gauge_rgb(Image.new("RGB",(100,100)),record,(100,100))

    def test_frame_output_abstains_on_unproven_junctions(self):
        outer=wireframe._ideal_outer_vertices()
        mask=np.ones((240,240),bool)
        record={
            "sequence_coordinate":{
                "sequence_gauge_to_camera_xy":np.eye(3).tolist()
            },
            "source_index":16,"position":16,
            "face_role":"likely_crown_lobe",
            "source_camera_path":"original.png",
            "assessment":{"status":"ok"}
        }
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"original.png"
            Image.new("RGB",(240,240),(20,110,220)).save(path)
            with patch.object(line,"_detect_lsd_segments",return_value=[]):
                row=line.inspect_frame(
                    path,record,mask,outer,
                    destination=Path(tmp)/"qc.jpg"
                )
            self.assertEqual(row["candidate_segment_count"],0)
            self.assertEqual(row["junctions"],[])
            self.assertEqual(row["polygon_fit_status"],
                             "unavailable_not_attempted_without_tracked_junction_cycle")
            self.assertFalse(row["physical_facet_identity_claim"])


if __name__=="__main__":
    unittest.main()
