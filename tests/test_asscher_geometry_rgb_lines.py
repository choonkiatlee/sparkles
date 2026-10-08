"""Tests for source-RGB line evidence, geometric intersections and no infill."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_geometry_rgb_lines as lines
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


def fake_side_rows(outer, fraction=.55):
    result=[]
    for family in lines.outer_side_families(outer):
        endpoints=lines._line_sample(family,fraction)
        result.append({
            "side":family["index"],
            "selected_line":{
                "fraction":float(fraction),
                "sample_start":endpoints[0].tolist(),
                "sample_end":endpoints[-1].tolist(),
            },
        })
    return result


def synthetic_scene(size=240):
    outer=wireframe._ideal_outer_vertices()
    mask_image=Image.new("L",(size,size),0)
    points=[(int((x+1)*.5*(size-32)+16),
             int((y+1)*.5*(size-32)+16)) for x,y in outer]
    ImageDraw.Draw(mask_image).polygon(points,fill=255)
    mask=np.asarray(mask_image)>0
    centre,scale=lines.normalized_gauge(mask)
    y,x=np.indices(mask.shape)
    p=np.stack(((x-centre[0])/scale,(y-centre[1])/scale),axis=-1)
    families=lines.outer_side_families(outer)
    signed=np.stack([
        (p-family["center"])@family["normal"]/family["outer_distance"]
        for family in families
    ])
    # An octagonal intensity *step*: long straight line segments, not dots.
    signed_distance=np.max(signed,axis=0)
    image=.2+.6/(1+np.exp(np.clip((signed_distance-.55)/.006,-60,60)))
    return image,mask,outer


class LineAndCornerDiagnosticTests(unittest.TestCase):
    def test_policy_does_not_change_frozen_estimator(self):
        self.assertTrue(lines.POLICY["no_production_estimator_change"])
        self.assertTrue(lines.POLICY["no_radial_peak_selection"])
        self.assertTrue(lines.POLICY["no_unobserved_side_infill"])
        self.assertFalse(lines.POLICY["physical_facet_identity_claim"])
        self.assertTrue(validation.assert_frozen_method(validation.OUTER_METHOD))

    def test_true_side_geometry_and_measured_intersections(self):
        outer=wireframe._ideal_outer_vertices()
        families=lines.outer_side_families(outer)
        self.assertEqual(len(families),8)
        rows=fake_side_rows(outer,.53)
        result=lines.intersect_measured_sides(outer,rows)
        self.assertIsNotNone(result)
        self.assertTrue(result["all_sides_directly_supported"])
        self.assertFalse(result["physical_facet_identity_verified"])
        actual=np.asarray(result["vertices_topology_order"])
        expected=outer*.53
        np.testing.assert_allclose(actual,expected,atol=1e-9)

    def test_fails_closed_for_one_missing_side(self):
        outer=wireframe._ideal_outer_vertices()
        rows=fake_side_rows(outer)
        rows[2]["selected_line"]=None
        self.assertIsNone(lines.intersect_measured_sides(outer,rows))

    def test_fails_closed_for_incoherent_ring_distances(self):
        outer=wireframe._ideal_outer_vertices()
        rows=fake_side_rows(outer)
        rows[2]["selected_line"]["fraction"]=.78
        self.assertIsNone(lines.intersect_measured_sides(outer,rows))

    def test_flat_original_image_never_invents_lines(self):
        mask=np.zeros((240,240),bool)
        mask[18:222,18:222]=True
        result=lines.extract_frame_lines(
            np.ones((240,240),float)*.4,mask,mask,
            wireframe._ideal_outer_vertices()
        )
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["polygon"])

    def test_real_straight_edges_have_measurable_directed_support(self):
        im,mask,outer=synthetic_scene()
        result=lines.extract_frame_lines(im,mask,mask,outer)
        # Raw extended-line evidence, independent of any radial peak maximum.
        self.assertGreaterEqual(result["detected_side_count"],2)
        for row in result["sides"]:
            for candidate in row["detected_candidates"]:
                self.assertGreaterEqual(candidate["coverage"],
                                         lines.POLICY["minimum_coverage"])
                self.assertGreaterEqual(
                    candidate["longest_contiguous_fraction"],
                    lines.POLICY["minimum_longest_contiguous"]
                )

    def test_camera_reprojection_exact_for_identity(self):
        im,mask,outer=synthetic_scene()
        source=Image.fromarray((im*255).astype(np.uint8)).convert("RGB")
        sampled,valid=lines.image_to_gauge(source,mask,np.eye(3))
        self.assertTrue(valid[120,120])
        self.assertFalse(valid[0,0])
        self.assertAlmostEqual(sampled[120,120],
                               np.asarray(source)[120,120,0]/255.,places=5)

    def test_native_rgb_three_panel_qc_shows_no_fabricated_polygon(self):
        im,mask,outer=synthetic_scene()
        source=Image.fromarray((im*255).astype(np.uint8)).convert("RGB")
        result=lines.extract_frame_lines(im,mask,mask,outer)
        result["polygon"]=None  # Explicit unverified geometry.
        image=lines.draw_frame(source,mask,np.eye(3),outer,result,
                               source_index=16)
        self.assertGreater(image.width,source.width*2)
        self.assertGreater(image.height,source.height*.5)
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/"native-RGB.jpg"
            image.save(dest)
            self.assertTrue(dest.exists())


if __name__=="__main__":
    unittest.main()
