"""#123: locked perturbation audit of dense source-RGB appearance switching.

No new optical detector, no true/virtual facet classifier, no fitted
registration correction and no diamond grade. Quantify sensitivity of
#186's *image-plane* observations to tiny mismatches in the second
source-camera-to-#80 gauge mapping and to extra silhouette erosion.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_dense_optical_regions as dense
from . import asscher_geometry_rgb_lines as rgb
from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_geometry_junction_graph as junction
from . import asscher_optical_neighbor_motion as neighbor
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA="diamond360-asscher-optical-registration-perturbation/1"
SHIFTS=((0,0),(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
EXTRA_EROSIONS=(0,2)
MEASURES=("median_gain_normalized_abs_change",
          "total_dark_switch_fraction",
          "total_bright_switch_fraction")
POLICY={
    "schema_version":SCHEMA,
    "source_window":dense.POLICY["window"],
    "anchor":"frozen_96_outer_octagon_selected_views",
    "registration_perturbation":"translate_second_RGB_and_its_validity_and_mask_in_gauge",
    "shift_axes":"dy_dx",
    "shifts_dy_dx":[list(x) for x in SHIFTS],
    "extra_silhouette_erosion_gauge_px":list(EXTRA_EROSIONS),
    "per_pair_trial_count":len(SHIFTS)*len(EXTRA_EROSIONS),
    "independent_position_tuning":False,
    "maximum_adjacent_pairs_per_stone":36,
    "unavailable_trials":"explicit_not_filled",
    "no_registration_adjustment_or_causal_claim":True,
    "no_physical_facet_labels":True,
    "no_quality_score_or_surface_model":True,
    "no_source_stress":True,
    "no_production_change":True,
}


def translate_no_wrap(array,dy,dx):
    """Exact integer gauge shift. No wrapped or reflect-filled RGB pixels."""
    src=np.asarray(array)
    if src.ndim!=2:
        raise ValueError("expected one gauged luminance or mask array")
    h,w=src.shape
    result=np.zeros_like(src)
    if abs(dy)>=h or abs(dx)>=w:
        return result
    sy0=max(0,-dy); sy1=min(h,h-dy)
    sx0=max(0,-dx); sx1=min(w,w-dx)
    result[sy0+dy:sy1+dy,sx0+dx:sx1+dx]=src[sy0:sy1,sx0:sx1]
    return result


def perturbation_grid(a,b,mask_a,mask_b,valid_a,valid_b):
    """Recalculate fixed #186 optical stats under predeclared small shifts."""
    samples=[]
    for erosion in EXTRA_EROSIONS:
        if erosion:
            ma=ndi.binary_erosion(mask_a,iterations=erosion)
            mb=ndi.binary_erosion(mask_b,iterations=erosion)
        else:
            ma=np.asarray(mask_a,bool)
            mb=np.asarray(mask_b,bool)
        for dy,dx in SHIFTS:
            changed=translate_no_wrap(b,dy,dx)
            moved_mask=translate_no_wrap(mb,dy,dx)
            moved_valid=translate_no_wrap(valid_b,dy,dx)
            item=dense.region_appearance(
                a,changed,ma,moved_mask,valid_a,moved_valid)
            record={
                "shift_dy_dx":[dy,dx],
                "extra_erosion_gauge_px":erosion,
                "status":item["status"],
                "physical_facet_correspondence":"unavailable",
                "physical_facet_semantic_ids":None,
            }
            if item["status"]=="observed":
                record.update({
                    key:float(item[key]) for key in MEASURES
                })
                record["overlap_pixels"]=item["overlap_pixels"]
                record["mask_intersection_over_union"]=item[
                    "mask_intersection_over_union"]
                record["observed_grid_bin_count"]=sum(
                    row["status"]=="observed" for row in item["bins"]
                )
            else:
                record["reason"]=item.get("reason")
            samples.append(record)
    expected={"shift_dy_dx":[0,0],"extra_erosion_gauge_px":0}
    primary=[r for r in samples if all(
        r[key]==value for key,value in expected.items())]
    if len(primary)!=1:
        raise AssertionError("baseline measured exactly once")
    primary=primary[0]
    comparisons={}
    for key in MEASURES:
        vals=[s[key] for s in samples if s["status"]=="observed"]
        if not vals or primary["status"]!="observed":
            comparisons[key]={
                "baseline":None,"minimum":None,"maximum":None,
                "full_perturbation_range":None,
                "max_abs_delta_from_baseline":None,
            }
        else:
            baseline=primary[key]
            comparisons[key]={
                "baseline":baseline,
                "minimum":float(min(vals)),"maximum":float(max(vals)),
                "full_perturbation_range":float(max(vals)-min(vals)),
                "max_abs_delta_from_baseline":float(max(
                    abs(val-baseline) for val in vals
                )),
            }
    return {
        "status":"evaluated" if primary["status"]=="observed" else "unavailable",
        "baseline":primary,
        "trial_count":len(samples),
        "supported_trial_count":sum(x["status"]=="observed" for x in samples),
        "trials":samples,
        "sensitivity":comparisons,
        "any_physical_facet_correspondence":False,
        "meaning":"image-plane_appearance_perturbation_only_not_facet_motion",
    }


def render_sensitivity(base_a,base_b,mask_a,mask_b,valid_a,valid_b,
                       analysis,*,source_indices):
    """Two measured difference maps; show the most divergent predeclared trial."""
    base=analysis["baseline"]
    observed=[x for x in analysis["trials"] if x["status"]=="observed"]
    target=max(observed,key=lambda r: (
        abs(r["median_gain_normalized_abs_change"]-
            base["median_gain_normalized_abs_change"]),
        r["shift_dy_dx"],r["extra_erosion_gauge_px"],
    )) if observed else None
    h,w=base_a.shape
    panel=Image.new("RGB",(w*2+8,h+55),(20,20,20))
    draw=ImageDraw.Draw(panel)
    if target is None:
        draw.text((10,15),"No common supported optical region",fill="white")
        return panel
    for idx,trial in enumerate((base,target)):
        dy,dx=trial["shift_dy_dx"]; erosion=trial["extra_erosion_gauge_px"]
        mb=(ndi.binary_erosion(mask_b,iterations=erosion)
            if erosion else mask_b)
        ma=(ndi.binary_erosion(mask_a,iterations=erosion)
            if erosion else mask_a)
        shifted=translate_no_wrap(base_b,dy,dx)
        footprint=(np.asarray(ma,bool)&translate_no_wrap(mb,dy,dx)
                   &valid_a&translate_no_wrap(valid_b,dy,dx))
        roi=ndi.binary_erosion(
            footprint,iterations=max(3,int(min(base_a.shape)*.015)))
        # Use the same frame-wise median normalization as #186 for each trial.
        if roi.any():
            ga=float(np.median(base_a[roi]))
            gb=float(np.median(shifted[roi]))
            mag=np.abs(base_a/max(ga,1e-10)-shifted/max(gb,1e-10))
            mag=np.clip(mag/.7,0,1)
            map_rgb=np.zeros((h,w,3),dtype=np.uint8)
            map_rgb[...,0]=(mag*245).astype(np.uint8)
            map_rgb[...,1]=(mag*80).astype(np.uint8)
            map_rgb[...,2]=(np.sqrt(mag)*85).astype(np.uint8)
            map_rgb[~roi]=[18,18,18]
            panel.paste(Image.fromarray(map_rgb),(idx*(w+8),55))
        label=("frozen gauge baseline" if idx==0
               else f"max-delta trial dy={dy},dx={dx},extra-erode={erosion}")
        draw.text((idx*(w+8)+4,5),label,fill="white")
        draw.text((idx*(w+8)+4,26),
                  f"src {source_indices[0]}->{source_indices[1]}; optical not facets",
                  fill=(200,200,200))
    return panel


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _,anchors,_,_=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD)
    face=junction.face_identity_state(pose,anchors)
    report={
        "schema_version":SCHEMA,"certificate":certificate,
        "selected_source_indices":[x["source_index"] for x in anchors],
        "selected_positions":[x["position"] for x in anchors],
        "face_identity":face,
        "physical_facet_identity":"unavailable",
        "production_estimator_changed":False,
        "pairs":[],
    }
    if len(anchors)<3:
        report.update(status="unavailable",reason="insufficient_frozen_anchors")
        return report
    positions,window=dense.dense_pairs(report["selected_positions"])
    report["dense_window_policy"]=window
    frames=pose["frames"]
    if len(frames)!=256 or [row.get("position") for row in frames]!=list(range(256)):
        raise ValueError("source sequence missing canonical original ordinal positions")
    cache={}
    def source_arrays(index):
        if index not in cache:
            rec=frames[index]
            if not neighbor._valid_record(rec):
                cache[index]=None
            else:
                _,mask,_=stability._load_gauged_arrays(pose_dir,rec)
                img=Image.open(Path(processed)/rec["source_camera_path"]).convert("RGB")
                matrix=rec["sequence_coordinate"]["sequence_gauge_to_camera_xy"]
                light,valid=rgb.image_to_gauge(img,mask,matrix)
                cache[index]=(light,mask,valid)
        return cache[index]

    for before,after in positions:
        first,second=frames[before],frames[after]
        row={
            "positions":[before,after],
            "source_indices":[first["source_index"],second["source_index"]],
            "face_identity_status":face["status"],
            "physical_facet_semantic_ids":None,
            "status":"unavailable",
        }
        if (face["status"]=="likely_crown" and
                any(rec.get("face_role")!="likely_crown_lobe"
                    for rec in (first,second))):
            row["reason"]="neighbor_not_in_resolved_crown_lobe"
        else:
            a=source_arrays(before);b=source_arrays(after)
            if a is None or b is None:
                row["reason"]="original_camera_RGB_or_pose_unavailable"
            else:
                report_pair=perturbation_grid(
                    a[0],b[0],a[1],b[1],a[2],b[2])
                row.update(report_pair)
                if report_pair["status"]=="evaluated":
                    name=f"perturb-pos-{before:04d}-{after:04d}.jpg"
                    render_sensitivity(
                        a[0],b[0],a[1],b[1],a[2],b[2],
                        report_pair,source_indices=row["source_indices"]
                    ).save(output/name,quality=91)
                    row["gauge_difference_QC"]=name
        report["pairs"].append(row)
    report["status"]="observational_only"
    report["evaluated_pair_count"]=sum(
        r["status"]=="evaluated" for r in report["pairs"])
    (output/"optical-perturbation.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n")
    images=[]
    for row in report["pairs"]:
        if row.get("gauge_difference_QC"):
            im=Image.open(output/row["gauge_difference_QC"])
            im.thumbnail((900,450),Image.Resampling.LANCZOS)
            images.append(im.copy())
    if images:
        from . import asscher_wireframe as wireframe
        wireframe._contact_sheet(
            images,output/"optical-perturbation-contact-sheet.jpg",columns=1)
    return report


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    stones=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-optical-perturb-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            source_manifest=Path(bundle["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest=Path.cwd()/source_manifest
            pipeline.run(Path(source_root).resolve()/cert,processed,
                         source_manifest,gain=1.0,accept_review=True)
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            r=run_stone(pose,processed,output/"per-stone"/cert,
                        certificate=cert)
            observed=[x for x in r["pairs"] if x["status"]=="evaluated"]
            stones.append({
                "certificate":cert,
                "selected_source_indices":r["selected_source_indices"],
                "face_identity":r["face_identity"],
                "total_pair_count":len(r["pairs"]),
                "evaluated_pair_count":r["evaluated_pair_count"],
                "median_baseline_appearance":(
                    float(np.median([x["sensitivity"][
                        "median_gain_normalized_abs_change"]["baseline"]
                        for x in observed])) if observed else None),
                "median_max_appearance_perturbation_delta":(
                    float(np.median([x["sensitivity"][
                        "median_gain_normalized_abs_change"][
                            "max_abs_delta_from_baseline"] for x in observed]))
                    if observed else None),
                "perturbation_QC_contact_sheet":(
                    f"per-stone/{cert}/optical-perturbation-contact-sheet.jpg"
                    if observed else None),
            })
    result={
        "schema_version":SCHEMA,"policy":POLICY,
        "manifest_sha256":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":stones,
        "no_physical_facet_labels":True,
        "no_quality_score":True,
        "no_production_estimator_change":True,
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--bundle-manifest",type=Path,
                   default=Path("docs/360/benchmark/source-bundles.json"))
    args=p.parse_args()
    summary=run_source_benchmark(
        args.source_root,args.output,args.bundle_manifest)
    for s in summary["stones"]:
        print(s["certificate"],"evaluated",s["evaluated_pair_count"],
              "/",s["total_pair_count"],
              "median appearance",s["median_baseline_appearance"],
              "median max perturbation delta",
              s["median_max_appearance_perturbation_delta"])

if __name__=="__main__":
    main()
