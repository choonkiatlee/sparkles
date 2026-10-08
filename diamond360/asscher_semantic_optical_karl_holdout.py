"""Karl_K external D360 holdout, using frozen #96 method and #92 sampler.

The two original 256-frame PriceScope sequences are catalogued and hashed in
#64/#65. Expert labels, pairwise preferences, physical-angle targets and
per-stone tuning are deliberately NOT read by geometry or photometry.
One *stone-level* primary scaffold is fitted using the pre-existing frozen
outer_octagon_v2 rule; every subsequent view uses that same fixed ruler.
If the method cannot obtain a supported scaffold, report unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_pose_sequence as pose
from . import asscher_semantic_optical_handoff as handoff
from . import asscher_semantic_optical_sensitivity as sensitivity
from . import asscher_wireframe as wireframe
from . import external_media
from . import pipeline

SCHEMA="diamond360-asscher-pricescope-fixed-ruler-holdout/1"
SAMPLES=("asscher-eval-crispest","asscher-eval-glittery")
PLOT_IDS=("C1_N","C2_N","C3_N","P1_N","P2_N","P3_N")
SAMPLE_FRACTIONS=(-1.0,-.8,-.6,-.4,-.2,0.0,.2,.4,.6,.8,1.0)
EXPECTED_MANIFEST_SHA={
    "asscher-eval-crispest":"4f854efe658bbf17008c3772f23360346d676ed327babe12c3d180ac28e579a7",
    "asscher-eval-glittery":"9763542ad5153cdd0de4785692bc33dda4465637fde0a435948c3a9fa4a10c8a",
}
POLICY={
    "samples":list(SAMPLES),
    "frozen_geometry_method":validation.OUTER_METHOD,
    "frozen_method_revision_only_not_frozen_holdout_scaffold":True,
    "geometry_fit_frequency":"once_per_holdout_stone_never_on_sampled_transfer_frame",
    "view_selection":"existing_73_crown_lobe_or_primary_medoid_no_expert_label",
    "view_sampling_normalized_offsets":list(SAMPLE_FRACTIONS),
    "source_media":"exact_256_original_jpgs_hash_pinned_v3_archive",
    "target_labels_loaded_into_fit":False,
    "physical_facet_correspondence":"unidentified",
    "calibrated_source_photometry":False,
    "metric_interpretation":"image_plane_brightness_rank_and_polygon_sensitivity_only",
    "quality_score":None,
}


def _hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def source_metadata(catalog_path, sample_id):
    """Extract only media/provenance fields, never expose a label to fitting."""
    if sample_id not in SAMPLES:
        raise ValueError("source is not a predeclared blinded Karl pair holdout")
    catalog=json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    if catalog.get("schema_version")!="sparkles-external-benchmark/1":
        raise ValueError("external source manifest schema mismatch")
    matches=[x for x in catalog["samples"] if x["sample_id"]==sample_id]
    if len(matches)!=1:
        raise ValueError("holdout source identity missing or duplicated")
    row=matches[0]
    seq=row.get("media",{}).get("sequence")
    if not seq or seq.get("frame_count")!=256:
        raise ValueError("external holdout has no complete source 360")
    if seq.get("manifest_sha256")!=EXPECTED_MANIFEST_SHA[sample_id]:
        raise ValueError("original 360 member manifest SHA changed")
    # Construct a *new* dict without labels, source opinions or pairwise rank.
    return {
        "sample_id":sample_id,
        "viewer_url":row["identity"]["viewer_url"],
        "source_url":row["source_url"],
        "sequence":seq,
        "expert_labels_read_by_pipeline":False,
    }


def selected_crown_records(pose_payload, selected):
    """Return fixed-offset views, not visually cherry-picked bright frames."""
    all_records, window=stability._eligible_transfer_records(pose_payload,selected)
    size=len(pose_payload.get("frames",[]))
    if not size:
        raise ValueError("source has no registered sequence")
    by_position={int(row["position"]):row for row in all_records}
    radius=int(window["radius_frames"])
    centre=int(window["centre_position"])
    desired=[(centre+round(radius*f))%size for f in SAMPLE_FRACTIONS]
    # Collision possible when very narrow source lobes; never duplicate frames.
    if len(set(desired))!=len(desired):
        return [],window,{"status":"unavailable","reason":"narrow_crown_lobe_collapses_predeclared_offsets",
                         "desired_positions":desired}
    chosen=[by_position[x] for x in desired if x in by_position]
    return chosen,window,{
        "status":"ok" if len(chosen)==len(desired) else "partial_missing_registered_views",
        "desired_positions":desired,
        "missing_positions":[x for x in desired if x not in by_position],
        "source_indices":[x["source_index"] for x in chosen],
        "positions":[x["position"] for x in chosen],
    }


def _unavailable(sample_id, reason, source=None, details=None):
    return {
        "schema_version":SCHEMA,"sample_id":sample_id,
        "status":"unavailable",
        "reason":reason,"details":details,
        "source":source,"policy":POLICY,
        "geometry_supported":False,
        "quality_score":None,
        "source_label_or_karl_rank_used":False,
        "frames":[],
    }


def run_holdout(sample_id, archive_root, catalog_path, destination):
    """Blind original-source processing; comparison labels remain inaccessible."""
    validation.assert_frozen_method(validation.OUTER_METHOD)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    source=source_metadata(catalog_path,sample_id)
    archive_root=Path(archive_root)
    manifest=archive_root/source["sequence"]["manifest_path"]
    if not manifest.is_file() or _hash(manifest)!=EXPECTED_MANIFEST_SHA[sample_id]:
        raise ValueError("archived source frame manifest bytes do not match")
    adapted=destination/"input-original-360"
    external_media.adapt_archived_sequence(
        archive_root,source["sequence"],adapted,
        provenance={"sample_id":sample_id,
                    "viewer_url":source["viewer_url"],
                    "purpose":"strict_label_blind_92_holdout"},
    )
    manifest_path=adapted/"source-manifest.json"
    if len(json.loads(manifest_path.read_text())["frames"])!=256:
        raise ValueError("adapted sequence did not preserve all 256 sources")
    processed=destination/"processed"
    pose_out=destination/"pose"
    pipeline.run(adapted,processed,manifest_path,gain=1.0,accept_review=True)
    pose.analyse_processed_sequence(processed,pose_out,persist_canonical=True)
    poses=json.loads((pose_out/"asscher-pose.json").read_text())
    primary,primary_frames,_,_=stability._primary_fit(
        pose_out,poses,method=validation.OUTER_METHOD)
    if primary.get("scaffold") is None:
        out=_unavailable(sample_id,"frozen_method_no_usable_stone_level_scaffold",
                         source=source,details={
                             "primary_status":primary.get("status"),
                             "primary_reason":primary.get("reason"),
                             "source_indices":[r.get("source_index") for r in primary_frames],
                         })
        write_result(out,destination)
        return out

    frozen=primary["scaffold"]
    frame_records,window,sample_selection=selected_crown_records(poses,primary_frames)
    if not frame_records:
        out=_unavailable(sample_id,"no_predeclared_compatible_fixed_ruler_views",
                         source=source,details={
                            "sample_selection":sample_selection,
                            "primary_source_indices":[r["source_index"] for r in primary_frames]})
        write_result(out,destination)
        return out

    before=json.dumps(frozen,sort_keys=True)
    output=[]
    face=poses.get("face_selection") or {}
    centre=face.get("likely_crown_peak_position")
    if centre is None:
        centre=window["centre_position"]
    for record in frame_records:
        brightness,mask,valid=stability._load_gauged_arrays(pose_out,record)
        u,evidence=wireframe.extract_sector_evidence(brightness,mask,valid)
        transfer=stability.transfer_fixed_ruler_frame(
            evidence,u,primary,frame_metadata=stability._metadata(record),
            crown_peak_position=centre,sequence_size=len(poses["frames"]),
            in_primary_fit=any(record.get("position")==f.get("position")
                              for f in primary_frames),
        )
        image=handoff.sample_fixed_frame(frozen,transfer,brightness,mask,valid)
        diagnostic=sensitivity.sample_sensitivity_frame(
            frozen,transfer,brightness,mask,valid,baseline_report=image)
        output.append({
            "source_index":record.get("source_index"),
            "position":record.get("position"),
            "phase_deg":(record.get("sequence_coordinate") or {}).get("rotation_phase_deg"),
            "face_role":record.get("face_role"),
            "sample":image,
            "sensitivity":diagnostic,
            "per_frame_geometry_refitted":False,
        })
    if json.dumps(frozen,sort_keys=True)!=before:
        raise ValueError("holdout scaffold mutated during brightness sampling")
    result={
        "schema_version":SCHEMA,
        "sample_id":sample_id,
        "status":"observational_image_plane_handoff" if len(output)==len(SAMPLE_FRACTIONS)
                   else "review_incomplete_source_support",
        "source":source,
        "policy":POLICY,
        "geometry_supported":True,
        "primary_method":validation.OUTER_METHOD,
        "primary_semantic_gauge_id":primary["semantic_gauge_id"],
        "primary_source_indices":[r.get("source_index") for r in primary_frames],
        "source_frame_count":len(poses["frames"]),
        "face_selection_status":face.get("status"),
        "crown_peak_selection_provenance":window["provenance"],
        "source_frame_selection":sample_selection,
        "sampled_frame_count":len(output),
        "geometry_fit_count":1,
        "per_frame_geometry_fit_count":0,
        "source_label_or_karl_rank_used":False,
        "physical_facet_correspondence":"not_established",
        "vendor_photometric_calibration":"not_established",
        "quality_score":None,
        "frames":output,
    }
    write_result(result,destination)
    return result


def write_result(result,destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    (destination/"blind-92-holdout.json").write_text(
        json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")
    if result.get("frames"):
        render_trace(result,destination/"blind-92-holdout.png")


def render_trace(result, path):
    W,H=1130,605
    im=Image.new("RGB",(W,H),(253,253,253))
    d=ImageDraw.Draw(im)
    d.text((30,19),result["sample_id"]+" | holdout #92 (unseen to model tuning)",fill=(29,43,54))
    d.text((30,40),"1 stone-level fit; 0 per-frame refits; image support NOT identified polished facets",fill=(65,78,90))
    x0,y0,w,h=65,86,1025,390
    frames=result["frames"]
    for v in (0,.25,.5,.75,1):
        y=y0+(1-v)*h
        d.line((x0,y,x0+w,y),fill=(229,230,235))
        d.text((26,y-7),str(v),fill=(80,90,100))
    for i,row in enumerate(frames):
        x=x0+i*w/max(1,len(frames)-1)
        d.text((x-7,y0+h+12),str(row["source_index"]),fill=(85,95,110))
    colors=[(25,106,181),(220,138,43),(153,76,174),
            (29,143,104),(213,76,75),(88,95,106)]
    for j,identity in enumerate(PLOT_IDS):
        prior=None
        for i,fr in enumerate(frames):
            ent=next((e for e in fr["sample"]["entities"]
                       if e["semantic_id"]==identity),None)
            v=None if ent is None else ent["raw_mean_brightness"]
            if v is None:
                prior=None
                continue
            pt=(x0+i*w/max(1,len(frames)-1),y0+(1-float(np.clip(v,0,1)))*h)
            if prior is not None:
                d.line((*prior,*pt),fill=colors[j],width=3)
            d.ellipse((pt[0]-3,pt[1]-3,pt[0]+3,pt[1]+3),fill=colors[j])
            prior=pt
        lx=45+180*j
        d.line((lx,550,lx+24,550),fill=colors[j],width=4)
        d.text((lx+28,542),identity,fill=(30,41,54))
    d.text((68,510),"Source index selected from frozen #73 pose window; not a physical angle or quality ranking.",fill=(81,88,98))
    im.save(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root",required=True,type=Path)
    p.add_argument("--catalog",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    report={}
    for sample in SAMPLES:
        info=run_holdout(sample,args.archive_root,args.catalog,args.output/sample)
        report[sample]={
            "status":info["status"],
            "frames":len(info["frames"]),
            "reason":info.get("reason"),
            "geometry_fit_count":info.get("geometry_fit_count",0),
        }
        print(sample,json.dumps(report[sample],sort_keys=True))
    (args.output/"summary.json").write_text(
        json.dumps({"schema_version":SCHEMA,"cases":report,
                    "labels_accessed_during_fitting":False,
                    "physical_facet_scores_available":False},
                   sort_keys=True,indent=2)+"\n")


if __name__=="__main__":
    main()
