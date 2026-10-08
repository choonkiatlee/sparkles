"""The real #92 replay consumes frozen #89 geometry, never refits it."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_topology as topology
from diamond360 import asscher_semantic_optical_real_replay as replay


class RealReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scaffold = topology.canonical_synthetic_scaffold(gauge_id="fixture-gauge")
        cls.rows = {
            sid: {
                "semantic_id": sid,
                "status": "ok" if obs["support_ids"] else "unavailable",
                "confidence": .8 if obs["support_ids"] else 0,
                "support_kind": "fixed_image_polygon",
            }
            for sid,obs in cls.scaffold["entity_observations"].items()
        }
        cls.transfer = {
            "schema_version": stability.TRANSFER_SCHEMA,
            "geometry_mode":stability.TRANSFER_POLICY,
            "semantic_identity_source":"primary_fixed_scaffold",
            "semantic_gauge_id":"fixture-gauge",
            "refit_performed":False,
            "entities":cls.rows,
        }

    def test_frozen_archive_requires_all_cyclic_source_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"per-stone"/replay.STONES[0]
            root.mkdir(parents=True)
            primary={"status":"ok","scaffold":self.scaffold,
                     "semantic_gauge_id":"fixture-gauge"}
            transfer={
                "schema_version":stability.TRANSFER_SCHEMA,
                "policy":stability.TRANSFER_POLICY,
                "primary_semantic_gauge_id":"fixture-gauge",
                "frames":[dict(self.transfer,source_index=i) for i in replay.SOURCE_INDICES],
            }
            (root/"primary-wireframe.json").write_text(json.dumps(primary))
            (root/"transfer.json").write_text(json.dumps(transfer))
            p,t,hashes=replay._load_stone_archived(Path(temp),replay.STONES[0])
            self.assertEqual(p["scaffold"],self.scaffold)
            self.assertEqual(set(t),set(replay.SOURCE_INDICES))
            self.assertEqual(hashes["primary_wireframe_sha256"],
                             hashlib.sha256((root/"primary-wireframe.json").read_bytes()).hexdigest())
            transfer["frames"].pop()
            (root/"transfer.json").write_text(json.dumps(transfer))
            with self.assertRaisesRegex(ValueError,"requested source indices"):
                replay._load_stone_archived(Path(temp),replay.STONES[0])
            transfer["frames"].append(dict(self.transfer,source_index=replay.SOURCE_INDICES[-1],
                                           refit_performed=True))
            (root/"transfer.json").write_text(json.dumps(transfer))
            with self.assertRaisesRegex(ValueError,"per-frame refitting"):
                replay._load_stone_archived(Path(temp),replay.STONES[0])

    def test_real_report_visual_trace_preserves_missing_not_zero(self):
        ids=("C1_N","C2_N","C3_N","P1_N","P2_N","P3_N")
        def make_frame(index):
            rows=[]
            for sid in ids:
                missing=sid=="C3_N" and index in (0,2)
                rows.append({"semantic_id":sid,
                             "raw_mean_brightness":None if missing else .2+index*.01,
                             "geometry_support_status":"unavailable" if missing else "review",
                             "supported_pixel_count":0 if missing else 23,
                             "physical_facet_correspondence":"not_established"})
            return {"source_index":index,"entities":rows}
        payload={
            "certificate":replay.STONES[0],
            "sampled_source_indices":[0,2,5,8],
            "frames":[make_frame(i) for i in (0,2,5,8)],
            "archived_crown_face_selection":"unresolved_not_safe_to_call_crown"
        }
        with tempfile.TemporaryDirectory() as temp:
            image=Path(temp)/"traces.png"
            replay.render_traces(payload,image)
            self.assertTrue(image.is_file())
            self.assertGreater(image.stat().st_size,2000)
        self.assertIsNone(payload["frames"][0]["entities"][2]["raw_mean_brightness"])

    def test_unlisted_stone_refused(self):
        with self.assertRaisesRegex(ValueError,"predeclared"):
            replay.replay_stone("IGI-NONEXISTENT","", "", "", "")

    def test_frozen_artifact_replay_does_not_offer_fit_api(self):
        import inspect
        text=inspect.getsource(replay.replay_stone)
        for forbidden in ("_fit_records(", "fit_from_sector_evidence(", "_primary_fit(",
                          "transfer_fixed_ruler_frame(", "run_stone("):
            self.assertNotIn(forbidden,text)
        self.assertIn("stability._load_gauged_arrays",text)
        self.assertIn("handoff.sample_fixed_frame",text)

    def test_explicit_source_indices_straddle_cyclic_255_0(self):
        ids=replay.SOURCE_INDICES
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn(255,ids)
        self.assertIn(0,ids)
        self.assertLess(ids.index(255),ids.index(0))
        self.assertTrue(replay.POLICY["no_geometry_fitting"])


if __name__ == "__main__":
    unittest.main()
