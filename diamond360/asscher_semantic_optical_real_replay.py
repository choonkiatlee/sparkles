"""Replay real #89 crown-frame brightness against *archived* fixed rulers.

Only original source pipeline + #73/#80 canonical registration is rerun to
obtain pixels. The fitted stone-level #75/#96 scaffold and every #89 transfer
row are read from an independently archived CI artifact, never refitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_stability as stability
from . import asscher_semantic_optical_handoff as handoff
from . import asscher_semantic_optical_sensitivity as sensitivity
from . import asscher_pose_sequence as pose
from . import pipeline
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-real-fixed-ruler-brightness-replay/1"
FROZEN_89_RUN_ID = 37830584391
FROZEN_89_ARTIFACT = "asscher-geometry-stability-outer-v2"
# Intentionally NOT cherry-picked for appearance; frozen source indices that
# straddle source-view cyclic zero (255 -> 0), plus the original fit views.
SOURCE_INDICES = (250, 252, 255, 0, 2, 5, 8, 11, 13, 16, 19)
STONES = ("IGI-LG756520111", "IGI-LG756580087")
PLOT_ENTITIES = ("C1_N", "C2_N", "C3_N", "P1_N", "P2_N", "P3_N")
COLORS = ((16, 105, 167), (241, 140, 30), (151, 86, 192),
          (35, 145, 99), (204, 69, 81), (94, 92, 108))
POLICY = {
    "fixed_scaffold_source": "independent_89_ci_artifact_not_regenerated",
    "frozen_89_run_id": FROZEN_89_RUN_ID,
    "frozen_89_artifact": FROZEN_89_ARTIFACT,
    "source_indices": list(SOURCE_INDICES),
    "only_original_benchmark_stones": list(STONES),
    "pixel_preparation": "existing_pipeline_and_73_80_pose_canonicalization",
    "no_geometry_fitting": True,
    "intensity": "mean_existing_canonical_measurement_brightness",
    "normalization": "not_supplied_all_null",
    "physical_correspondence": "not_established",
    "C3_TABLE": "image_plane_review_not_physical",
    "sequence_phase": "approximate_viewer_phase_not_physical_rotation",
    "semantic_partition": "nonexclusive_overlapping",
    "no_optical_quality_metric": True,
}


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_stone_archived(frozen_root, certificate):
    stone = Path(frozen_root) / "per-stone" / certificate
    primary_path = stone / "primary-wireframe.json"
    transfer_path = stone / "transfer.json"
    pbytes = primary_path.read_bytes()
    tbytes = transfer_path.read_bytes()
    primary, transfer = (json.loads(x) for x in (pbytes, tbytes))
    if primary.get("status") not in ("ok", "review") or not primary.get("scaffold"):
        raise ValueError("archived primary geometry unavailable")
    if transfer.get("schema_version") != stability.TRANSFER_SCHEMA:
        raise ValueError("archived #89 fixed-ruler transfer schema mismatch")
    if transfer.get("policy") != stability.TRANSFER_POLICY:
        raise ValueError("archive contains refit-mode transfer")
    if primary["semantic_gauge_id"] != transfer["primary_semantic_gauge_id"]:
        raise ValueError("archived primary and transfer gauge disagree")
    selected = {int(row["source_index"]): row for row in transfer["frames"]}
    if not all(i in selected for i in SOURCE_INDICES):
        raise ValueError("requested source indices absent from frozen transfer")
    if any(row["refit_performed"] is not False
           for row in selected.values()):
        raise ValueError("a frozen transfer claims per-frame refitting")
    return primary, selected, {
        "primary_wireframe_sha256": hashlib.sha256(pbytes).hexdigest(),
        "transfer_sha256": hashlib.sha256(tbytes).hexdigest(),
    }


def replay_stone(cert, source, source_manifest, frozen_root, output):
    if cert not in STONES:
        raise ValueError("stone not in predeclared replay group")
    output = Path(output)
    primary, archived, digests = _load_stone_archived(frozen_root, cert)
    scaffold = primary["scaffold"]

    # Only pixels are reprocessed. The algorithm below MUST NOT call any
    # geometry fitting or the #89 transfer re-evaluator.
    processed = output / "processed"
    pose_output = output / "pose"
    pipeline.run(Path(source), processed, Path(source_manifest),
                 gain=1.0, accept_review=True)
    pose.analyse_processed_sequence(processed, pose_output,
                                    persist_canonical=True)
    poses = json.loads((pose_output / "asscher-pose.json").read_text())
    by_source = {int(row["source_index"]): row for row in poses["frames"]}
    if len(by_source) != len(poses["frames"]):
        raise ValueError("reconstructed sequence has duplicate source indexes")
    # Global #80 reference frame and quarter-turn are independently checked
    # before any photometry is sampled from the new pose registration.
    reconstructed_gauge = wireframe._gauge_id(poses)
    if reconstructed_gauge != primary["semantic_gauge_id"]:
        raise ValueError("reconstructed #80 gauge ID differs from archived #89")
    # The #89 transfer has the authoritative fixed semantic gauge ID; each
    # canonical frame is only used when its per-source gauge record agrees.
    rows = []
    sensitivity_frames = []
    records = []
    for idx in SOURCE_INDICES:
        record = by_source.get(idx)
        if record is None:
            raise ValueError(f"source {idx} missing from re-canonicalized 360")
        expected = archived[idx]
        coordinate = record.get("sequence_coordinate") or {}
        if coordinate.get("gauge_id") not in (None, expected["semantic_gauge_id"]):
            raise ValueError(f"frame {idx} gauge changed from archived ruler")
        if coordinate.get("gauge_status") not in ("available", "review"):
            raise ValueError(f"frame {idx} has no usable source gauge")
        if record.get("canonical", {}).get("path") is None:
            raise ValueError(f"canonical arrays missing for source {idx}")
        expected_turn = expected.get("gauge_quarter_turn")
        if coordinate.get("gauge_quarter_turn") != expected_turn:
            raise ValueError(f"frame {idx} gauge quarter-turn differs from archived #89")
        bright, mask, valid = stability._load_gauged_arrays(pose_output, record)
        report = handoff.sample_fixed_frame(
            scaffold, expected, bright, mask, valid,
            normalized_brightness=None)
        report["face_role_archived"] = expected.get("face_role")
        report["pose_status_archived"] = expected.get("pose_status")
        report["frame_support_status_archived"] = expected.get("status")
        report["viewer_phase_is_calibrated_physical_rotation"] = False
        sensitivity_frames.append(
            sensitivity.sample_frame_sensitivity(
                scaffold, expected, bright, mask, valid, report
            )
        )
        rows.append(report)
        records.append(record)

    frames = {row["source_index"]: row for row in rows}
    if set(frames) != set(SOURCE_INDICES):
        raise ValueError("did not cover predeclared source-frame indices")
    entities = list(rows[0]["entities"])
    if any([x["semantic_id"] for x in row["entities"]] !=
           [x["semantic_id"] for x in entities] for row in rows):
        raise ValueError("semantic IDs changed across real source frames")
    counts = {}
    for ident in (x["semantic_id"] for x in entities):
        data = [next(x for x in row["entities"] if x["semantic_id"] == ident)
                for row in rows]
        counts[ident] = {
            "sampled_frames": sum(x["raw_mean_brightness"] is not None for x in data),
            "unsupported_frames": sum(x["raw_mean_brightness"] is None for x in data),
            "support_statuses": {
                key: sum(x["geometry_support_status"] == key for x in data)
                for key in ("ok", "review", "unavailable")
            },
        }
    payload = {
        "schema_version": SCHEMA,
        "policy": POLICY,
        "certificate": cert,
        "frozen_artifact_sha256": digests,
        "archived_semantic_gauge_id": primary["semantic_gauge_id"],
        "archived_crown_face_selection": (
            "resolved" if all(row.get("face_role_archived") == "likely_crown_lobe"
                              for row in rows) else "unresolved_not_safe_to_call_crown"
        ),
        "sampled_source_indices": list(SOURCE_INDICES),
        "frame_count": len(rows),
        "semantic_id_count": len(entities),
        "scaffold_was_refitted": False,
        "all_physical_facets_verified": False,
        "physical_facet_angle_estimates": None,
        "optical_quality_score": None,
        "entity_support_summary": counts,
        "frames": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "real-fixed-ruler-brightness.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_traces(payload, output / "real-fixed-ruler-traces.png")
    sensitivity_report = sensitivity.summarize(
        cert, sensitivity_frames, digests, payload["archived_crown_face_selection"]
    )
    sensitivity.save(sensitivity_report, output)
    # Keep no intermediate 256-frame canonical image arrays in final artifact.
    return payload


def render_traces(payload, output):
    width, height = 1160, 640
    image = Image.new("RGB", (width, height), (253, 253, 253))
    d = ImageDraw.Draw(image)
    title = (
        f"{payload['certificate']} | real 360 crown-window source frames "
        f"| #89 scaffold FROZEN"
    )
    d.text((32, 18), title, fill=(20, 30, 42))
    d.text((32, 38), "Brightness is image-plane support, NOT polished facet light return.", fill=(75, 80, 87))
    d.text((32, 55), "Same geometry ruler; null/missing points stay unconnected. No physical facet scores.", fill=(75,80,87))
    x0, y0, w, h = 72, 100, 1020, 375
    for val in (0, .25, .5, .75, 1):
        y = y0+h*(1-val)
        d.line((x0,y,x0+w,y),fill=(228,231,236),width=1)
        d.text((28,y-6),str(val),fill=(70,80,92))
    sources=payload["sampled_source_indices"]
    def xy(i,v):
        return (x0 + w*i/max(1,len(sources)-1), y0+h*(1-v))
    for i,src in enumerate(sources):
        x=xy(i,0)[0]
        d.line((x,y0,x,y0+h),fill=(240,242,245),width=1)
        d.text((x-9,y0+h+10),str(src),fill=(70,80,92))
    d.text((x0+270,y0+h+36),"Source frame (wrapped 250 ... 255 | 0 ... 19); nominal viewer phase only",fill=(76,82,88))
    for k,ident in enumerate(PLOT_ENTITIES):
        color = COLORS[k]
        old = None
        for i,frame in enumerate(payload["frames"]):
            row=next((r for r in frame["entities"] if r["semantic_id"]==ident),None)
            v=row and row["raw_mean_brightness"]
            if v is None or not np.isfinite(v):
                old=None
                continue
            point=xy(i,float(np.clip(v,0,1)))
            if old is not None:
                d.line((*old,*point),fill=color,width=3)
            d.ellipse((point[0]-4,point[1]-4,point[0]+4,point[1]+4),fill=color)
            old=point
        ax = 38+175*k
        d.line((ax,590,ax+23,590),fill=color,width=4)
        d.text((ax+27,583),ident,fill=(35,40,48))
    if payload["archived_crown_face_selection"].startswith("unresolved"):
        d.text((x0,558),"FACE ROLE UNRESOLVED: labels denote fixed IMAGE-PLANE SUPPORT only.",fill=(169,65,45))
    else:
        d.text((x0,558),"#73 face selection: likely crown lobe (not proof of polished facet identity).",fill=(68,87,103))
    image.save(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate",required=True,choices=STONES)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--source-manifest",type=Path,required=True)
    parser.add_argument("--frozen-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    o=replay_stone(args.certificate,args.source_root/args.certificate,
                   args.source_manifest,args.frozen_root,args.output/args.certificate)
    print(json.dumps({
        "certificate":o["certificate"],
        "samples":o["frame_count"],
        "semantic_ids":o["semantic_id_count"],
        "scaffold_refitted":o["scaffold_was_refitted"],
        "face":o["archived_crown_face_selection"],
        "example_support":{k:o["entity_support_summary"][k] for k in PLOT_ENTITIES[:3]},
        "exposure_support_sensitivity": "exposure-support-sensitivity.json",
    },sort_keys=True))


if __name__=="__main__":
    main()
