"""Small real #89 replay: archived fixed ruler, no model refit."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_semantic_optical_real_replay as replay


class ArchivedRealReplayTests(unittest.TestCase):
    def test_pinned_sample_selection_includes_resolved_and_unresolved_roles(self):
        self.assertEqual(set(replay.SELECTED),
                         {"IGI-LG756520111","IGI-LG756580087"})
        self.assertEqual(sum(len(v) for v in replay.SELECTED.values()),8)
        self.assertEqual(replay.SELECTED["IGI-LG756520111"],(0,13,16,19,255))
        self.assertEqual(replay.FROZEN_SOURCE_RUN,37830584391)

    def test_frozen_archived_transfer_is_verified_not_reestimated(self):
        import os
        root = os.environ.get("SPARKLES_FROZEN_STABILITY_ROOT")
        if not root:
            self.skipTest("Exact archived #89 transfer ZIP not present; integration CI provides it")
        for stone in replay.SELECTED:
            with self.subTest(stone=stone):
                result, scaffold, frames=replay.frozen_inputs(stone,root)
                self.assertEqual(result["scaffold"],scaffold)
                self.assertEqual(set(frames),set(replay.SELECTED[stone]))
                self.assertTrue(all(not x["refit_performed"] for x in frames.values()))
                self.assertTrue(all(x["semantic_identity_source"]=="primary_fixed_scaffold"
                                    for x in frames.values()))
                if stone=="IGI-LG756520111":
                    self.assertTrue(all(x["face_role"]=="likely_crown_lobe"
                                        for x in frames.values()))
                else:
                    self.assertTrue(all(x["face_role"]=="unresolved"
                                        for x in frames.values()))

    def test_frozen_source_missing_frame_or_relabel_rejected(self):
        import os
        root=os.environ.get("SPARKLES_FROZEN_STABILITY_ROOT")
        if not root:
            self.skipTest("Archived #89 transfer not present")
        with tempfile.TemporaryDirectory() as td:
            from shutil import copyfile
            stone="IGI-LG756520111"
            orig=Path(root)/"per-stone"/stone
            dst=Path(td)/"per-stone"/stone
            dst.mkdir(parents=True)
            for name in ("primary-wireframe.json","transfer.json"):
                copyfile(orig/name,dst/name)
            data=json.loads((dst/"transfer.json").read_text())
            data["frames"]=[x for x in data["frames"] if x["source_index"]!=13]
            (dst/"transfer.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"selected source frame absent"):
                replay.frozen_inputs(stone,td)
            data=json.loads((orig/"transfer.json").read_text())
            for frame in data["frames"]:
                if frame["source_index"]==13:
                    frame["refit_performed"]=True
            (dst/"transfer.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"invalid fixed-ruler transfer"):
                replay.frozen_inputs(stone,td)

    def test_image_trace_plot_only_sampled_brightness_no_score(self):
        frames=[]
        for idx,value in ((13,.21),(16,.40),(19,.67)):
            frames.append({
                "entities":[{
                    "semantic_id":family,
                    "raw_mean_brightness":value if family!="TABLE" else None,
                    "geometry_support_status":"review",
                    "physical_facet_correspondence":"not_established",
                } for family in replay.HIGHLIGHTS],
                "source_index":idx,
            })
        sample={"certificate":"IGI-LG756520111",
                "selected_source_indices":[13,16,19],
                "face_roles":["likely_crown_lobe"]*3,
                "frames":frames}
        record={"stones":[sample]}
        with tempfile.TemporaryDirectory() as td:
            outfile=Path(td)/"trace.png"
            replay.draw_traces(record,outfile)
            self.assertTrue(outfile.is_file())
            self.assertGreater(outfile.stat().st_size,2500)


if __name__=="__main__":
    unittest.main()
