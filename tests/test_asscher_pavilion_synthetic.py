"""General pavilion synthetic observability benchmark; NO DiaGem photo inputs."""
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from diamond360 import asscher_pavilion_synthetic as model


class SyntheticPavilionTests(unittest.TestCase):
    def setUp(self):
        self.shape=model.Shape((0,.30,.60,1),(.02,.20,.51,1),.20)
        self.camera=model.Camera()

    def test_validated_three_band_closed_octagonal_mesh(self):
        vertices, faces=model.mesh(self.shape)
        self.assertEqual(vertices.shape,(32,3))
        self.assertEqual(faces.shape,(60,3))
        self.assertTrue(np.isfinite(vertices).all())
        self.assertTrue(np.isfinite(faces).all())
        for k,y in enumerate(self.shape.levels_y):
            ring=vertices[8*k:8*(k+1)]
            self.assertTrue(np.allclose(ring[:,1],y))
        self.assertTrue(all(0<=i<32 for i in faces.flatten()))
        self.assertEqual(len(model.GENERATOR_POLICY["tier_order_top_to_bottom"]),3)

    def test_invalid_height_radius_corner_asymmetry_are_rejected(self):
        bad=(
            replace(self.shape,levels_y=(0,.60,.50,1)),
            replace(self.shape,radii=(.02,.50,.30,1)),
            replace(self.shape,radii=(.02,.20,.51,.99)),
            replace(self.shape,corner_cut=.02),
            replace(self.shape,left_width=1.30),
            replace(self.shape,levels_y=(0,.29,float("nan"),1)),
        )
        for x in bad:
            with self.subTest(x=x),self.assertRaises(ValueError):
                model.mesh(x)
        with self.assertRaises(ValueError):
            model.project(model.mesh(self.shape)[0],replace(self.camera,tilt_deg=38))

    def test_level_symmetry_and_strictly_increasing_width_toward_girdle(self):
        edge=model.silhouette(self.shape,self.camera)
        self.assertGreater(len(edge),100)
        self.assertTrue(np.all(np.diff(edge[:,1])==1))
        self.assertTrue(np.all(edge[:,0]<=edge[:,2]))
        self.assertLess(np.max(np.abs(edge[:,0]+edge[:,2]-410)),.01)
        self.assertAlmostEqual(float(edge[-1,2]-edge[-1,0]),2*self.camera.scale_px,delta=.5)
        self.assertAlmostEqual(float(edge[0,1]),self.camera.tip_y_px,delta=1)

    def test_nonconvex_silhouette_is_not_overwritten_by_vertex_convex_hull(self):
        shape=model.Shape((0,.25,.50,1),(.01,.08,.18,1),.20)
        env=model.silhouette(shape,self.camera)
        tip_y=self.camera.tip_y_px
        girdle_y=tip_y+self.camera.scale_px
        mid_y=tip_y+self.camera.scale_px*.50
        actual=float(env[np.argmin(abs(env[:,1]-mid_y)),2])
        tip=float(env[np.argmin(abs(env[:,1]-tip_y)),2])
        girdle=float(env[np.argmin(abs(env[:,1]-girdle_y)),2])
        straight_chord=tip+.5*(girdle-tip)
        self.assertGreater(straight_chord-actual,25.0,
            "a convex hull would erase the physical inward bend")
        self.assertAlmostEqual(actual,self.camera.center_x_px+.18*self.camera.scale_px,delta=1)

    def test_left_and_right_asymmetric_outline_remains_separate(self):
        asym=replace(self.shape,left_width=.89,right_width=1.11)
        edge=model.silhouette(asym,self.camera)
        center=(edge[:,0]+edge[:,2])/2
        self.assertGreater(abs(float(center[-1])-self.camera.center_x_px),8)
        self.assertTrue(np.all(np.diff(edge[:,2])>=-1e-6))
        self.assertNotEqual(float(edge[-1,2]-205),float(205-edge[-1,0]))

    def test_oblique_camera_changes_projection_without_changing_physical_tiers(self):
        level=model.silhouette(self.shape,self.camera)
        pose=replace(self.camera,yaw_deg=23,tilt_deg=9,roll_deg=-3)
        oblique=model.silhouette(self.shape,pose)
        self.assertGreater(len(oblique),60)
        self.assertFalse(np.array_equal(level,oblique))
        self.assertEqual(self.shape.levels_y,replace(self.shape).levels_y)

    def test_seeded_noise_and_missing_rows_reproducible_no_filled_holes(self):
        env=model.silhouette(self.shape,self.camera)
        a=model.observe(env,seed=123,missing_intervals=((91,107),),noise_px=.7)
        b=model.observe(env,seed=123,missing_intervals=((91,107),),noise_px=.7)
        c=model.observe(env,seed=124,missing_intervals=((91,107),),noise_px=.7)
        self.assertEqual(a,b)
        self.assertNotEqual(a,c)
        for side in ("left","right"):
            self.assertFalse(any(91<=p["xy_px"][1]<=107 for p in a[side]))
            self.assertEqual([p["xy_px"][1] for p in a[side]],
                             sorted(p["xy_px"][1] for p in a[side]))

    def test_internal_virtual_stripes_not_used_for_exterior_fitting(self):
        a=model.synthetic_scene(self.shape,self.camera,seed=123,
                                noise_px=.45,stripes=False)
        b=model.synthetic_scene(self.shape,self.camera,seed=123,
                                noise_px=.45,stripes=True)
        self.assertEqual(a["source_observations"],b["source_observations"])
        self.assertEqual(model.evaluate_scene(a),model.evaluate_scene(b))
        self.assertFalse(a["internal_optical_stripes_present_but_excluded"])
        self.assertTrue(b["internal_optical_stripes_present_but_excluded"])

    def test_physical_three_bands_do_not_force_three_visible_segments(self):
        level=model.Shape((0,.33,.66,1),(.02,.345,.667,1))
        env=model.silhouette(level,self.camera)
        points=model.observe(env,seed=5)
        from diamond360.asscher_profile_pavilion_refinement import _fit
        left=_fit(points["left"],80)
        self.assertIsNotNone(left)
        self.assertEqual(left["segment_count"],1,
            "three physical tier boundaries may be collinear in projection")
        self.assertEqual(len(level.levels_y)-1,3)

    def test_honest_train_holdout_metrics_and_no_angle_claims(self):
        case=model.synthetic_scene(self.shape,self.camera,123,
                                   missing_intervals=((93,110),),noise_px=.6)
        result=model.evaluate_scene(case)
        for side in ("left","right"):
            report=result[side]
            self.assertEqual(report["status"],"synthetic_image_plane_evaluation")
            self.assertTrue(math.isfinite(report["heldout_outer_edge_rmse_px"]))
            self.assertGreater(report["heldout_rows"],5)
            self.assertGreater(report["training_rows"],report["heldout_rows"])
            self.assertIn(report["selected_projected_stretches"],(1,2,3))
            self.assertIn("not_P1_P2_P3",report["provenance"])
        self.assertIsNone(case["physical_plane_angles_from_image"])
        self.assertEqual(case["geometry_provenance"],
                         "fully_synthetic_and_expert_target_blind")

    def test_synthetic_oracle_counts_one_two_three_visible_stretches(self):
        shape1=model.Shape((0,.30,.60,1),(.02,.314,.608,1))
        shape2=model.Shape((0,.30,.60,1),(.02,.26,.57,1))
        shape3=model.Shape((0,.30,.60,1),(.02,.16,.48,1))
        expected=(1,2,3)
        for shape,visible in zip((shape1,shape2,shape3),expected):
            with self.subTest(expected=visible):
                truth=model.projected_tier_visibility(shape,self.camera)
                self.assertEqual(truth["status"],
                                 "synthetic_untilted_profile_oracle_only")
                self.assertEqual(truth["physical_band_count"],3)
                self.assertEqual(truth["observable_stretch_count"],visible)
                self.assertEqual(sum(truth["per_ring_junction_visible"])+1,visible)
        tilted=model.projected_tier_visibility(shape3,replace(self.camera,tilt_deg=12))
        self.assertIsNone(tilted["observable_stretch_count"])
        self.assertEqual(tilted["projected_ring_break_correspondence"],"unknown")

    def test_deterministic_splits_diverse_heldout_and_pinned_report(self):
        r1=model.benchmark()
        r2=model.benchmark()
        self.assertEqual(r1,r2)
        self.assertEqual(r1["schema_version"],model.SCHEMA)
        self.assertFalse(r1["real_diamond_photo_used"])
        self.assertFalse(r1["expert_targets_loaded"])
        self.assertEqual(r1["physical_tier_identity_from_source_image"],"unavailable")
        cases=r1["cases"]
        self.assertEqual(len(cases),8)
        self.assertEqual([x["split"] for x in cases].count("dev"),3)
        self.assertEqual([x["split"] for x in cases].count("holdout"),5)
        self.assertEqual(len(set(c["name"] for c in cases)),len(cases))
        self.assertTrue(all(c["physical_tier_band_count"]==3 for c in cases))
        self.assertTrue(all("UNKNOWN" in c["projected_transition_identity"] for c in cases))

    def test_cli_style_audit_artifacts_source_independent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            record=model.write_benchmark(root)
            self.assertEqual(json.loads((root/"synthetic-pavilion-benchmark.json").read_text()),record)
            self.assertTrue((root/"synthetic-pavilion-cases.png").is_file())
            self.assertGreater((root/"synthetic-pavilion-cases.png").stat().st_size,1500)
            self.assertFalse(any("diagem" in str(v).lower() for v in record["cases"]))


if __name__=="__main__":
    unittest.main()
