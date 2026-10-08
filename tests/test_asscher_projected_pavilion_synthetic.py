"""Source-independent Asscher projected-pavilion generator + blind fit contracts."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_profile_projected_fit as estimator
from diamond360 import asscher_profile_synthetic as synthetic
from diamond360 import asscher_profile_synthetic_benchmark as benchmark


class SyntheticPavilionGeometryTests(unittest.TestCase):
    def scene(self, l, r=None, **kwargs):
        return synthetic.Scene(
            synthetic.Side(tuple(l[0]),tuple(l[1])),
            synthetic.Side(tuple((r or l)[0]),tuple((r or l)[1])),
            seed=29,noise_std_px=0.25,**kwargs
        )

    def test_one_two_three_clean_visible_stretches_each_side(self):
        profiles=(
            ((),(0.88,)),
            ((0.42,),(1.80,0.40)),
            ((0.25,0.64),(1.9,0.39,1.69)),
        )
        for count,(knots,slopes) in enumerate(profiles,start=1):
            with self.subTest(count=count):
                scene=self.scene((knots,slopes))
                sample=synthetic.sample_scene(scene)
                result=estimator.fit_observations(sample["observations"])
                for side in ("left","right"):
                    fit=result["sides"][side]
                    self.assertIn(fit["status"],("candidate_only","ambiguous"))
                    self.assertEqual(fit["segment_count"],count)
                    ground=sample["truth"][side+"_break_y_px"]
                    inferred=fit["candidate_break_y_px"]
                    self.assertEqual(len(ground),len(inferred))
                    self.assertTrue(all(abs(a-b)<=8 for a,b in zip(ground,inferred)))
                    self.assertIsNone(fit["physical_angles"])
                self.assertEqual(result["physical_facet_angles"],"all_unavailable")

    def test_asymmetric_geometry_must_not_be_regularized_to_mirror(self):
        sample=synthetic.sample_scene(self.scene(
            ((0.36,),(1.66,0.48)),
            ((0.22,0.70),(1.82,0.43,1.58)),
        ))
        fit=estimator.fit_observations(sample["observations"])
        self.assertEqual(fit["sides"]["left"]["segment_count"],2)
        self.assertEqual(fit["sides"]["right"]["segment_count"],3)
        self.assertNotEqual(fit["sides"]["left"]["candidate_break_y_px"],
                            fit["sides"]["right"]["candidate_break_y_px"])
        self.assertTrue(fit["policy"]["no_forced_symmetry"])

    def test_affine_image_shear_does_not_create_fake_knots(self):
        scene=self.scene(((),(0.81,)),shear_dx_per_dy=0.23)
        fit=estimator.fit_observations(synthetic.sample_scene(scene)["observations"])
        for side in ("left","right"):
            self.assertEqual(fit["sides"][side]["segment_count"],1)
            self.assertEqual(fit["sides"][side]["candidate_break_y_px"],[])

    def test_optical_distractors_do_not_enter_estimator(self):
        plain=self.scene(((0.41,),(1.73,0.43)))
        virtual=self.scene(((0.41,),(1.73,0.43)),inner_distractors=True)
        a=synthetic.sample_scene(plain)
        b=synthetic.sample_scene(virtual)
        self.assertEqual(a["observations"],b["observations"])
        self.assertNotEqual(a["optical_distractors_never_fit_inputs"],
                            b["optical_distractors_never_fit_inputs"])
        self.assertEqual(estimator.fit_observations(a["observations"]),
                         estimator.fit_observations(b["observations"]))

    def test_generator_truth_never_enters_estimator(self):
        sample=synthetic.sample_scene(self.scene(((0.36,),(1.65,0.48))))
        self.assertNotIn("truth",json.dumps(sample["observations"]))
        changed=deepcopy(sample["observations"])
        changed["truth"]=sample["truth"]
        with self.assertRaisesRegex(ValueError,"truth/targets"):
            estimator.fit_observations(changed)
        changed=deepcopy(sample["observations"])
        changed["contours"]["left"][0]["internal_reflection_x_px"]=999
        with self.assertRaisesRegex(ValueError,"ground truth / optical"):
            estimator.fit_observations(changed)
        self.assertFalse(estimator.fit_observations(sample["observations"])
                         ["target_parameters_loaded"])

    def test_missing_entire_right_side_abstains_without_mirroring_left(self):
        record=synthetic.sample_scene(self.scene(((0.38,),(1.7,0.47))))["observations"]
        record["contours"]["right"]=[
            dict(row,x_px=None) for row in record["contours"]["right"]
        ]
        result=estimator.fit_observations(record)
        self.assertEqual(result["sides"]["right"]["status"],"unavailable")
        self.assertEqual(result["sides"]["left"]["segment_count"],2)
        self.assertNotIn("candidate_break_y_px",result["sides"]["right"])

    def test_short_observed_span_abstains_without_extrapolating_tip_or_girdle(self):
        record=synthetic.sample_scene(self.scene(((0.42,),(1.6,0.4))))["observations"]
        record["contours"]["left"]=[
            dict(row,x_px=None) if row["y_px"]>90 else row
            for row in record["contours"]["left"]
        ]
        result=estimator.fit_observations(record)
        self.assertEqual(result["sides"]["left"]["status"],"unavailable")

    def test_roi_and_input_validation_rejects_false_evidence(self):
        record=synthetic.sample_scene(self.scene(((),(1.0,))))["observations"]
        for invalid in (
            dict(record,pavilion_roi_y_px=[200,60]),
            dict(record,source_kind="known_physical_facet_angles"),
            dict(record,contours={"left":[]}),
        ):
            with self.assertRaises(ValueError):
                estimator.fit_observations(invalid)
        bad=deepcopy(record)
        bad["contours"]["left"][4]["x_px"]=float("nan")
        with self.assertRaises(ValueError):
            estimator.fit_observations(bad)

    def test_reproducible_serialized_observations_and_model(self):
        scene=self.scene(((0.45,),(1.61,0.5)),dropout=0.18)
        a=synthetic.sample_scene(scene)
        b=synthetic.sample_scene(scene)
        self.assertEqual(a,b)
        fa=estimator.fit_observations(a["observations"])
        self.assertEqual(fa,estimator.fit_observations(b["observations"]))
        self.assertEqual(
            estimator.fit_json_text(json.dumps(a["observations"])),
            json.dumps(fa,sort_keys=True,indent=2)+"\n",
        )

    def test_predeclared_holdout_coverage_and_failure_reporting(self):
        catalogue=benchmark.holdout_cases()
        self.assertEqual([name for name,_ in catalogue],
                         benchmark.POLICY["holdout_case_ids"])
        self.assertEqual(len({scene.seed for _,scene in catalogue}),len(catalogue))
        self.assertTrue(all(scene.seed!=29 for _,scene in catalogue))
        with tempfile.TemporaryDirectory() as td:
            result=benchmark.run_benchmark(Path(td))
            self.assertEqual(len(result["cases"]),12)
            self.assertEqual(result["summary"]["left_right_side_evaluations"],24)
            self.assertFalse(result["external_DiaGem_and_Sergey_used_for_tuning"])
            self.assertFalse(result["physical_pavilion_angles_claimed"])
            self.assertEqual(json.loads(
                (Path(td)/"synthetic-holdout-report.json").read_text()),result)
            self.assertTrue((Path(td)/"synthetic-pavilion-montage.png").is_file())
            self.assertTrue(all(
                "missed_true_breaks" in metrics and "false_positive_breaks" in metrics
                for case in result["cases"] for metrics in case["sides"].values()
            ))


if __name__=="__main__":
    unittest.main()
