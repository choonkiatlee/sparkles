"""QC hypotheses are not true-facet labels; no estimator changes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from diamond360 import asscher_geometry_c3_hypothesis_qc as qc
from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_wireframe as wireframe


def fixture():
    u=np.linspace(0,1,160)
    def peak(centre,amp):
        return amp*np.exp(-.5*((u-centre)/.008)**2)
    profile=(peak(.48,2.5)+peak(.579,2.2)+
             peak(.73,2.4)+peak(.87,2.1))
    evidence=np.tile(profile,(5,8,1))
    return u,evidence,wireframe._ideal_outer_vertices()


class C3GeometryQCTests(unittest.TestCase):
    def test_predeclared_candidate_policy_and_frozen_estimator(self):
        self.assertTrue(qc.POLICY["no_method_revision_or_production_change"])
        self.assertEqual(qc.POLICY["hypothesis_count"],2)
        self.assertEqual(qc.WINDOW,(.42,.60))
        for method in (validation.OUTER_METHOD,validation.WINDOW_METHOD):
            self.assertTrue(validation.assert_frozen_method(method))

    def test_competing_octagons_are_distinct_and_physically_unclaimed(self):
        u,evidence,outer=fixture()
        case=qc.hypothesis_case(
            evidence,u,outer,source_indices=[1,2,3,4,5]
        )
        self.assertEqual(case["status"],"two_hypotheses")
        self.assertEqual([h["display_id"] for h in case["hypotheses"]],
                         ["A","B"])
        a,b=case["hypotheses"]
        self.assertGreater(abs(a["u"]-b["u"]),.085)
        self.assertEqual(np.asarray(a["vertices_topology_order"]).shape,(8,2))
        self.assertNotEqual(
            a["polygon_geometry"]["area_absolute"],
            b["polygon_geometry"]["area_absolute"])
        for h in (a,b):
            self.assertTrue(h["polygon_geometry"]["convex_octagon"])
            self.assertTrue(h["polygon_geometry"]["all_vertices_inside_C2_C3"])
            self.assertEqual(h["per_frame_evidence"]["frame_count"],5)
            self.assertEqual(len(h["per_frame_evidence"]["frames"]),5)
        self.assertIn("not truth",case["note"])

    def test_held_out_frame_cannot_change_candidate_decision(self):
        u,evidence,outer=fixture()
        without=qc.hypothesis_case(
            evidence[:-1],u,outer,source_indices=[1,2,3,4]
        )
        changed=evidence.copy()
        changed[-1]=500*np.random.default_rng(0).random(
            (8,len(u))
        )
        without_changed=qc.hypothesis_case(
            changed[:-1],u,outer,source_indices=[1,2,3,4]
        )
        self.assertEqual(
            [h["u"] for h in without["hypotheses"]],
            [h["u"] for h in without_changed["hypotheses"]])
        self.assertEqual(
            without["v3_selected_c3_u"],
            without_changed["v3_selected_c3_u"])

    def test_two_hypothesis_requirement_does_not_invent_second_edge(self):
        u,evidence,outer=fixture()
        # Remove the second C3 peak; no raw top-pixel fallback is permitted.
        gaussian=np.exp(-.5*((u-.579)/.008)**2)
        data=evidence-2.2*gaussian[None,None,:]
        case=qc.hypothesis_case(data,u,outer,source_indices=[1,2,3,4,5])
        self.assertLessEqual(len(case["hypotheses"]),1)
        self.assertNotEqual(case["status"],"two_hypotheses")

    def test_gauge_to_camera_projection_and_native_RGB_render(self):
        u,evidence,outer=fixture()
        case=qc.hypothesis_case(evidence,u,outer,
                                source_indices=[1,2,3,4,5])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"camera").mkdir()
            Image.new("RGB",(160,160),(12,50,82)).save(root/"camera/a.png")
            mask=np.zeros((160,160),bool)
            mask[15:145,15:145]=True
            record={
                "source_index":1,"position":1,
                "source_camera_path":"camera/a.png",
                "sequence_coordinate":{
                    "sequence_gauge_to_camera_xy":np.eye(3).tolist()
                },
            }
            with patch.object(qc.stability,"_load_gauged_arrays",
                              return_value=(np.ones((160,160)),mask,mask)):
                qc_result=qc.render_case(
                    root,root,[record],evidence[:1],u,case,
                    root/"out"
                )
            self.assertTrue((root/"out"/"source-0001-RGB.jpg").is_file())
            self.assertTrue(
                (root/"out"/qc_result["contact_sheet"]).is_file())
            self.assertEqual(qc_result["frames"][0]["status"],
                             "camera_RGB_projected")
            img=Image.open(root/"out"/"source-0001-RGB.jpg")
            self.assertGreater(img.width,160)
            self.assertGreater(img.height,100)

    def test_invalid_projection_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"nonprojectable"):
            qc._camera_crop(
                Image.new("RGB",(100,100)),
                np.ones((100,100),bool),
                np.zeros((3,3)),
            )

    def test_method_does_not_modify_existing_candidate_selection(self):
        u,evidence,outer=fixture()
        from diamond360 import asscher_steps as steps
        before=steps.discover_template(
            evidence,u,peak_policy=steps.WINDOW_PEAK_POLICY
        )
        case=qc.hypothesis_case(evidence,u,outer,
                                source_indices=[1,2,3,4,5])
        self.assertEqual(
            before["controls"][0]["global_u"],
            case["v3_selected_c3_u"])


if __name__=="__main__":
    unittest.main()
