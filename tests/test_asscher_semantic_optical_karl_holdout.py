"""External Karl_K holdouts must stay fully blind and fail closed."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_semantic_optical_karl_holdout as holdout


def synthetic_catalog():
    return {
        "schema_version":"sparkles-external-benchmark/1",
        "samples":[{
            "sample_id":name,
            "source_url":"https://www.pricescope.com/community/threads/asscher-cut-evaluation.281114/",
            "identity":{"viewer_url":"https://d360.tech/view.html?d=FAKE"},
            "media":{"sequence":{"frame_count":256,"manifest_path":"d360/"+name+"/source-manifest.json",
                                 "manifest_sha256":holdout.EXPECTED_MANIFEST_SHA[name]}},
            "labels":[{"expert":"Karl K","target_quality_score":-9999,
                       "title":"DO NOT USE AS FIT TARGET"}],
        } for name in holdout.SAMPLES],
    }


class KarlHoldoutTests(unittest.TestCase):
    def test_labels_not_exposed_to_geometry_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"source.json"
            path.write_text(json.dumps(synthetic_catalog()))
            for sample in holdout.SAMPLES:
                source=holdout.source_metadata(path,sample)
                self.assertEqual(source["sample_id"],sample)
                self.assertEqual(source["sequence"]["frame_count"],256)
                self.assertFalse(source["expert_labels_read_by_pipeline"])
                self.assertNotIn("labels",source)
                self.assertNotIn("target_quality_score",json.dumps(source))

    def test_unpinned_source_manifest_or_extra_stone_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"source.json"
            data=synthetic_catalog()
            data["samples"][0]["media"]["sequence"]["manifest_sha256"]="wrong"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"SHA"):
                holdout.source_metadata(path,holdout.SAMPLES[0])
            with self.assertRaisesRegex(ValueError,"predeclared"):
                holdout.source_metadata(path,"asscher-eval-target-centre")

    def test_fixed_normalized_crown_window_offsets(self):
        records=[{"source_index":i,"position":i,
                  "canonical":{"path":f"frame-{i}.npz"},
                  "sequence_coordinate":{"gauge_status":"available"}}
                 for i in range(256)]
        pose={"frames":records,"face_selection":{
            "status":"resolved","likely_crown_peak_position":254,
            "lobe_radius_frames":30,
        }}
        picked,window,summary=holdout.selected_crown_records(pose,[])
        self.assertEqual(len(picked),11)
        self.assertEqual(summary["status"],"ok")
        self.assertEqual(summary["desired_positions"],[
            (254+round(30*f))%256 for f in holdout.SAMPLE_FRACTIONS])
        self.assertEqual(window["provenance"],"resolved_73_crown_lobe")
        self.assertTrue(any(x >= 248 for x in summary["positions"]))
        self.assertTrue(any(x < 16 for x in summary["positions"]))

    def test_missing_gauge_rows_are_not_interpolated(self):
        records=[{"source_index":i,"position":i,
                  "canonical":{"path":f"frame-{i}.npz"},
                  "sequence_coordinate":{"gauge_status":(
                      "unavailable" if i in (254,0,4) else "available"
                  )}}
                 for i in range(256)]
        pose={"frames":records,"face_selection":{
            "status":"resolved","likely_crown_peak_position":254,
            "lobe_radius_frames":30,
        }}
        picked,window,summary=holdout.selected_crown_records(pose,[])
        self.assertLess(len(picked),11)
        self.assertEqual(summary["status"],"partial_missing_registered_views")
        self.assertIn(254,summary["missing_positions"])
        self.assertTrue(all(x["position"] not in summary["missing_positions"] for x in picked))

    def test_missing_primary_scaffold_remains_unavailable_no_fabricated_quality(self):
        state=holdout._unavailable(holdout.SAMPLES[0],"no_scaffold")
        self.assertEqual(state["status"],"unavailable")
        self.assertFalse(state["geometry_supported"])
        self.assertIsNone(state["quality_score"])
        self.assertEqual(state["frames"],[])
        with tempfile.TemporaryDirectory() as tmp:
            holdout.write_result(state,Path(tmp))
            self.assertTrue((Path(tmp)/"blind-92-holdout.json").is_file())
            self.assertFalse((Path(tmp)/"blind-92-holdout.png").exists())

    def test_policy_has_no_per_stone_tuning_or_angle_targets(self):
        self.assertEqual(holdout.POLICY["frozen_geometry_method"],
                         "outer_octagon_v2")
        self.assertEqual(holdout.POLICY["quality_score"],None)
        self.assertFalse(holdout.POLICY["target_labels_loaded_into_fit"])
        self.assertEqual(len(holdout.PLOT_IDS),6)
        self.assertEqual(len(holdout.SAMPLE_FRACTIONS),11)
        self.assertEqual(set(holdout.SAMPLES),
                         {"asscher-eval-crispest","asscher-eval-glittery"})

    def test_render_scaffold_support_traces_no_quality_score(self):
        frames=[]
        for i in range(11):
            frames.append({"source_index":i*6,
                           "sample":{"entities":[
                               {"semantic_id":sid,"raw_mean_brightness":.2+.04*i}
                               for sid in holdout.PLOT_IDS]}})
        report={"sample_id":holdout.SAMPLES[0],"frames":frames}
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"blind.png"
            holdout.render_trace(report,file)
            self.assertGreater(file.stat().st_size,2000)


if __name__=="__main__":
    unittest.main()
