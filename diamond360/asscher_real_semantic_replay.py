"""#92 real crown-frame optical support replay (one pinned stone; no refit).

Consumes the original #89 archived fixed stone-level scaffold AND its frame
transfer records. Reruns the source preprocessing/pose registration solely
to reconstruct source brightness arrays, not to alter semantic geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import asscher_pose_sequence as pose
from . import asscher_geometry_stability as stability
from . import asscher_semantic_optical_handoff as handoff
from . import pipeline, asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-real-fixed-ruler-optical-replay/1"
CERTIFICATE = "IGI-LG756520111"
FROZEN_PRIMARY_SHA256 = "a675f82e73c2f099c1d55a4f56e82047041fe668f757c616c665912156d64fda"
FROZEN_TRANSFER_SHA256 = "015556c0f2360951fe3458627fe1c49d5bf2f71f07929065fecab52794bf6479"
SELECTED_SOURCE_INDICES = (4, 8, 12, 16, 20, 24, 28)
DISPLAY_IDS = ("C1_N", "C2_N", "C3_N", "P1_N", "TABLE")
POLICY = {
    "benchmark_case": CERTIFICATE,
    "fixed_selected_source_indices": list(SELECTED_SOURCE_INDICES),
    "frozen_89_artifact_run": 37830584391,
    "frozen_89_primary_sha256": FROZEN_PRIMARY_SHA256,
    "frozen_89_transfer_sha256": FROZEN_TRANSFER_SHA256,
    "no_estimator_fit_called": True,
    "brightness": "real_original_source_canonical_lowpass_brightness",
    "preprocessing": "recompute_source_gauge_only_using_frozen_89_code",
    "source_camera_for_qc": "original_rgb_optional_unchanged_scaffold_projection",
    "normalized_brightness": "not_computed_absent_explicit_normalization",
    "facet_identity": "image_plane_support_only_C3_table_uncertain",
    "not_a_quality_score": True,
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen_archive(primary_path, transfer_path):
    if _sha(primary_path) != FROZEN_PRIMARY_SHA256:
        raise ValueError("frozen #89 PRIMARY artifact mismatch")
    if _sha(transfer_path) != FROZEN_TRANSFER_SHA256:
        raise ValueError("frozen #89 TRANSFER artifact mismatch")
    primary=json.loads(Path(primary_path).read_text(encoding="utf-8"))
    transfer=json.loads(Path(transfer_path).read_text(encoding="utf-8"))
    scaffold=primary.get("scaffold")
    if primary.get("status") not in ("ok","review") or not scaffold:
        raise ValueError("frozen primary scaffold unavailable")
    if transfer.get("primary_semantic_gauge_id") != scaffold["semantic_gauge"]["gauge_id"]:
        raise ValueError("frozen #89 primary/transfer semantic gauge mismatch")
    records={v["source_index"]:v for v in transfer["frames"]}
    if any(index not in records for index in SELECTED_SOURCE_INDICES):
        raise ValueError("predeclared real frames absent from #89 transfer")
    if any(records[index].get("transfer_scope") != "crown_view_window"
           for index in SELECTED_SOURCE_INDICES):
        raise ValueError("not all predeclared frames belong to crown window")
    if any(records[index].get("refit_performed") is not False
           for index in SELECTED_SOURCE_INDICES):
        raise ValueError("frozen transfer performed a prohibited refit")
    return scaffold, records


def _plot_traces(report, destination):
    """Simple plot with transparent missing points; no line through unavailable."""
    selected=["C1_N", "C2_N", "C3_N", "P1_N", "TABLE"]
    # #74 uses compass orientations: north may be N or one of the diagonals,
    # never substitute a different ID silently; choose the first matching
    # fixed orientation BEFORE inspecting optical brightness.
    semantic_ids=set(report["fixed_semantic_ids"])
    def choose(family):
        if family=="TABLE":
            return "TABLE" if "TABLE" in semantic_ids else None
        return next((v for v in (family+"_N",family+"_NE",family+"_NW")
                     if v in semantic_ids),None)
    selected=[choose(v) for v in selected]
    selected=[v for v in selected if v is not None]
    width,height=1100,540
    img=Image.new("RGB",(width,height),(250,251,252))
    d=ImageDraw.Draw(img)
    d.text((25,18),"REAL 360 CROWN-VIEW REPLAY: image-plane brightness / FIXED semantic ruler",fill=(20,28,45))
    d.text((25,38),"LG756520111 | original #89 scaffold, no refit | brightness not physical-facet attribution",fill=(65,70,88))
    x0,x1,y0,y1=85,1030,85,410
    d.line((x0,y0,x0,y1,x1,y1),fill=(75,85,97),width=2)
    for k in range(5):
        py=int(y1 - k/4*(y1-y0))
        d.line((x0,py,x1,py),fill=(226,229,233),width=1)
        d.text((48,py-8),f"{k/4:.2f}",fill=(85,90,102))
    colors=[(30,150,70),(12,106,219),(219,103,15),(145,63,196),(171,42,70)]
    frames=report["frames"]
    n=len(frames)
    for i,frame in enumerate(frames):
        x=int(x0 + (i/(n-1) if n>1 else 0)*(x1-x0))
        d.text((x-8,y1+11),str(frame["source_index"]),fill=(60,66,75))
        d.text((x-17,y1+28),f'{frame["entities"][0]["rotation_phase_deg"]:.1f}°',fill=(90,90,90))
    for idx,semantic in enumerate(selected):
        color=colors[idx]
        points=[]
        for i,frame in enumerate(frames):
            record=next(x for x in frame["entities"] if x["semantic_id"]==semantic)
            x=int(x0+(i/(n-1) if n>1 else 0)*(x1-x0))
            b=record["raw_mean_brightness"]
            points.append(None if b is None else (x,int(y1-np.clip(b,0,1)*(y1-y0))))
        for p,q in zip(points,points[1:]):
            if p is not None and q is not None:
                d.line((*p,*q),fill=color,width=3)
        for p in points:
            if p is not None:
                d.ellipse((p[0]-5,p[1]-5,p[0]+5,p[1]+5),fill=color)
        d.text((65+idx*206,475),f"{semantic}",fill=color)
    d.text((380,506),"Source frame / approximate rotation phase; missing brightness is not plotted",fill=(73,75,88))
    img.save(destination)


def _render_examples(processed_path, record_map, report, frozen_scaffold, output):
    """Three real source-camera RGB previews, no semantic ownership claims."""
    picks=(4,16,28)
    images=[]
    for index in picks:
        record=record_map[index]
        _,gauge_mask,_=stability._load_gauged_arrays(output/"pose",record)
        preview=wireframe._draw_scaffold_on_source(
            processed_path,record,gauge_mask,frozen_scaffold
        )
        if preview is None:
            raise ValueError("cannot produce original-camera RGB geometry QC")
        preview.thumbnail((450,400))
        panel=Image.new("RGB",(470,455),(248,249,250))
        d=ImageDraw.Draw(panel)
        d.text((10,10),f"Real RGB src{index} | frozen model overlay, NOT facet truth",fill=(28,31,41))
        panel.paste(preview,((470-preview.width)//2,35))
        images.append(panel)
    output_img=Image.new("RGB",(1410,455),(248,249,250))
    for i,im in enumerate(images):
        output_img.paste(im,(470*i,0))
    output_img.save(output/"real-crown-fixed-ruler-rgb.png")


def replay(source_dir, source_manifest, frozen_primary, frozen_transfer, output):
    scaffold, transfers=verify_frozen_archive(frozen_primary,frozen_transfer)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    proc=output/"processed"
    posed=output/"pose"
    pipeline.run(source_dir,proc,source_manifest,gain=1.0,accept_review=True)
    pose.analyse_processed_sequence(proc,posed,persist_canonical=True)
    source_payload=json.loads((posed/"asscher-pose.json").read_text(encoding="utf-8"))
    gauge_id=wireframe._gauge_id(source_payload)
    if gauge_id != scaffold["semantic_gauge"]["gauge_id"]:
        raise ValueError("reprocessed source gauge differs from original frozen #89")
    by_index={record.get("source_index"):record
              for record in source_payload.get("frames",[])}
    records=[]
    frames=[]
    for index in SELECTED_SOURCE_INDICES:
        record=by_index.get(index)
        if not record or not (record.get("canonical") or {}).get("path"):
            raise ValueError(f"source frame {index} unavailable in recomputed pose")
        transfer=transfers[index]
        meta=stability._metadata(record)
        if meta["position"] != transfer.get("position"):
            raise ValueError("recomputed source position differs from original #89")
        if meta["gauge_quarter_turn"] != transfer.get("gauge_quarter_turn"):
            raise ValueError("recomputed quarter-turn branch differs from #89")
        phase=meta["rotation_phase_deg"]
        frozen_phase=transfer.get("rotation_phase_deg")
        if phase is None or frozen_phase is None or abs(phase-frozen_phase)>1e-8:
            raise ValueError("recomputed source phase differs from original #89")
        brightness,gauge_mask,valid=stability._load_gauged_arrays(posed,record)
        frames.append((transfer,brightness,gauge_mask,valid,None))
        records.append(record)
    report=handoff.sample_sequence(scaffold,frames)
    report.update({
        "replay_schema_version":SCHEMA,
        "real_source_certificate":CERTIFICATE,
        "source_frame_indices":list(SELECTED_SOURCE_INDICES),
        "frozen_primary_sha256":FROZEN_PRIMARY_SHA256,
        "frozen_transfer_sha256":FROZEN_TRANSFER_SHA256,
        "reprocessed_gauge_equals_original":True,
        "has_any_new_geometry_fits":False,
        "face_role":"likely_crown_lobe_frozen_89",
        "source_reading":"canonical_measurement_brightness_not_raw_RGB",
        "normalized_values_present":False,
        "physical_inner_facets_verified":False,
        "quality_or_optical_score_computed":False,
        "interpretation":(
            "These are image-plane pixel mean brightness values from real "
            "source frames, sampled with a frozen stone-level semantic scaffold. "
            "They do not identify a polished facet or separate virtual optics."
        ),
    })
    (output/"real-crown-handoff.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    _plot_traces(report,output/"real-crown-brightness-traces.png")
    _render_examples(proc,{x["source_index"]:x for x in records},report,scaffold,output)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True,type=Path)
    parser.add_argument("--source-manifest",required=True,type=Path)
    parser.add_argument("--frozen-primary",required=True,type=Path)
    parser.add_argument("--frozen-transfer",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    result=replay(args.source,args.source_manifest,args.frozen_primary,
                  args.frozen_transfer,args.output)
    print(json.dumps({
        "status":result["status"],
        "certificate":result["real_source_certificate"],
        "frames":result["counts"]["frames"],
        "entities":result["counts"]["entities"],
        "refit":result["has_any_new_geometry_fits"],
    },sort_keys=True))


if __name__=="__main__":
    main()
