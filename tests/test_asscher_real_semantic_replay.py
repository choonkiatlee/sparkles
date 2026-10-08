"""#92 real replay: fixed archived source contract and visual smoke tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from diamond360 import asscher_real_semantic_replay as replay
from diamond360 import asscher_topology as topo
from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_semantic_optical_handoff as handoff


def example():
    scaffold=topo.canonical_synthetic_scaffold(gauge_id="mock-gauge")
    entities={}
    for key,row in scaffold["entity_observations"].items():
        exists=bool(row["support_ids"])
        entities[key]={
            "semantic_id":key,"status":"review" if exists else "unavailable",
            "confidence":0.5 if exists else 0,
            "support_kind":"synthetic_reference",
        }
    rows=[]
    for index in replay.SELECTED_SOURCE_INDICES:
        rows.append({
            "source_index":index,"position":index,
            "transfer_scope":"crown_view_window",
            "refit_performed":False,
            "rotation_phase_deg":index*360/256,
            "semantic_gauge_id":"mock-gauge",
            "schema_version":stability.TRANSFER_SCHEMA,
            "semantic_identity_source":"primary_fixed_scaffold",
            "geometry_mode":stability.TRANSFER_POLICY,
            "entities":deepcopy(entities),
        })
    return {"status":"ok","scaffold":scaffold}, {
        "primary_semantic_gauge_id":"mock-gauge","frames":rows,
    }


class RealFixedReplayContractTests(unittest.TestCase):
    def test_exact_archive_hashes_required_and_selected_real_indices_preserved(self):
        primary,transfer=example()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"primary.json"
            t=Path(td)/"transfer.json"
            p.write_text(json.dumps(primary))
            t.write_text(json.dumps(transfer))
            with mock.patch.object(replay,"FROZEN_PRIMARY_SHA256",replay._sha(p)), \
                 mock.patch.object(replay,"FROZEN_TRANSFER_SHA256",replay._sha(t)):
                scaffold,records=replay.verify_frozen_archive(p,t)
                self.assertEqual(scaffold,primary["scaffold"])
                self.assertEqual(sorted(records),list(replay.SELECTED_SOURCE_INDICES))
                t.write_text(t.read_text()+" ")
                with self.assertRaisesRegex(ValueError,"TRANSFER artifact"):
                    replay.verify_frozen_archive(p,t)

    def test_archive_missing_frame_or_transfer_refit_abstains(self):
        primary,transfer=example()
        for modification in ("missing","refit","noncrown","wronggauge"):
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/"p.json";t=Path(td)/"t.json"
                b=deepcopy(transfer)
                if modification=="missing": b["frames"].pop()
                if modification=="refit": b["frames"][0]["refit_performed"]=True
                if modification=="noncrown": b["frames"][0]["transfer_scope"]="cyclic_wrap_control"
                if modification=="wronggauge": b["primary_semantic_gauge_id"]="other"
                p.write_text(json.dumps(primary));t.write_text(json.dumps(b))
                with mock.patch.object(replay,"FROZEN_PRIMARY_SHA256",replay._sha(p)), \
                     mock.patch.object(replay,"FROZEN_TRANSFER_SHA256",replay._sha(t)):
                    with self.subTest(modification=modification),self.assertRaises(ValueError):
                        replay.verify_frozen_archive(p,t)

    def test_trace_preview_uses_real_fixed_semantic_ids_and_null_holes(self):
        primary,transfer=example()
        raw=np.full((96,96),.25)
        mask=np.zeros((96,96),bool);mask[14:82,14:82]=True
        frames=[]
        for i,record in enumerate(transfer["frames"]):
            temp=deepcopy(record)
            raw_frame=raw+i*.06
            frames.append((temp,raw_frame,mask,mask,None))
        report=handoff.sample_sequence(primary["scaffold"],frames)
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"traces.png"
            replay._plot_traces(report,dest)
            self.assertTrue(dest.exists())
            self.assertGreater(dest.stat().st_size,4500)
            self.assertEqual(report["counts"]["frames"],7)
            self.assertTrue(all(not frame["refit_performed"] for frame in report["frames"]))
            self.assertTrue(all(
                row["physical_facet_correspondence"]=="not_established"
                for frame in report["frames"] for row in frame["entities"]))


if __name__=="__main__":
    unittest.main()
