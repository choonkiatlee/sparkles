"""#123: controlled confound sensitivity of native-RGB optical switching.

No virtual/real labels, geometry inference, measurement calibration or grades.
The frozen #186 dense 360 atlas is replayed verbatim and challenged with
predeclared subpixel registration and spatial illumination perturbations.
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
from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_geometry_rgb_lines as rgb
from . import asscher_geometry_junction_graph as junction
from . import asscher_optical_neighbor_motion as neighbor
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA="diamond360-asscher-optical-switch-confounds/1"
POLICY={
    "schema_version":SCHEMA,
    "frozen_source":"four_SHA256_pinned_original_camera_RGB_256_frame_sequences",
    "dense_reference_method":dense.SCHEMA,
    "pair_policy":"exact_same_dense_shortest_circular_arc_as_186",
    "controlled_scenarios":[
        "global_gain_x1p20",
        "x_plus_1px", "x_minus_1px",
        "y_plus_1px", "y_minus_1px",
        "smooth_horizontal_gradient_12pct",
        "smooth_vertical_gradient_12pct",
    ],
    "shift_support":"shift_raw_gauge_RGB_and_matching_valid_and_mask",
    "image_shift":"scipy_ndimage_shift_linear_no_wrap",
    "gradient":"multiplicative_gain_0p94_to_1p06_across_full_view",
    "report":"within_original_pair_perturbation_deltas_no_adjusted_quality_score",
    "physical_interior_geometry":"unavailable",
    "facet_semantic_ids":None,
    "no_estimator_or_92_change":True,
    "no_source_stress":True,
}
METRICS=("median_gain_normalized_abs_change",
         "total_dark_switch_fraction","total_bright_switch_fraction")


def perturb_second(image, mask, valid, name):
    """Return independently perturbed *B* observation and its valid support."""
    b=np.asarray(image,float)
    mask=np.asarray(mask,bool)
    valid=np.asarray(valid,bool)
    if b.ndim!=2 or mask.shape!=b.shape or valid.shape!=b.shape:
        raise ValueError("incompatible gauge arrays")
    if name=="global_gain_x1p20":
        return b*1.20,mask.copy(),valid.copy()
    if name in ("x_plus_1px","x_minus_1px",
                "y_plus_1px","y_minus_1px"):
        shift={
            "x_plus_1px":(0,1),"x_minus_1px":(0,-1),
            "y_plus_1px":(1,0),"y_minus_1px":(-1,0),
        }[name]
        moved=ndi.shift(b,shift=shift,order=1,mode="constant",cval=0.)
        mask_new=ndi.shift(mask.astype(np.uint8),shift=shift,
                           order=0,mode="constant",cval=0)>0
        valid_new=ndi.shift(valid.astype(np.uint8),shift=shift,
                            order=0,mode="constant",cval=0)>0
        return moved,mask_new,valid_new
    if name in ("smooth_horizontal_gradient_12pct",
                "smooth_vertical_gradient_12pct"):
        axis=1 if name.startswith("smooth_horizontal") else 0
        n=b.shape[axis]
        gain=np.linspace(.94,1.06,n)
        gain=gain[None,:] if axis==1 else gain[:,None]
        return b*gain,mask.copy(),valid.copy()
    raise ValueError("unrecognized predeclared optical confound "+str(name))


def _score(row):
    if row.get("status")!="observed":
        return None
    return {
        name:float(row[name]) for name in METRICS
    }


def run_pair(a,b,mask_a,mask_b,valid_a,valid_b):
    """Baseline plus nuisance response; never optimize a geometry model."""
    baseline=dense.region_appearance(
        a,b,mask_a,mask_b,valid_a,valid_b
    )
    if baseline["status"]!="observed":
        return {"status":"unavailable","reason":baseline.get("reason"),
                "baseline":None,"scenarios":[]}
    scores=_score(baseline)
    scenarios=[]
    for name in POLICY["controlled_scenarios"]:
        changed,changed_mask,changed_valid=perturb_second(
            b,mask_b,valid_b,name
        )
        result=dense.region_appearance(
            a,changed,mask_a,changed_mask,valid_a,changed_valid
        )
        current=_score(result)
        scenarios.append({
            "scenario":name,
            "status":result["status"],
            "reason":result.get("reason"),
            "overlap_pixels":result.get("overlap_pixels"),
            "overlap_change_pixels":(result.get("overlap_pixels",0)
                                     -baseline["overlap_pixels"]),
            "metrics":current,
            "delta_from_unperturbed":{
                metric:float(current[metric]-scores[metric])
                for metric in METRICS
            } if current is not None else None,
        })
    return {
        "status":"observed",
        "baseline":scores,
        "baseline_overlap_pixels":baseline["overlap_pixels"],
        "scenarios":scenarios,
        "physical_facet_correspondence":"unavailable",
        "facet_semantic_ids":None,
        "not_an_optical_quality_score":True,
    }


def _plot_stone(rows,output,certificate):
    """Compact per-pair visualization; exposure, shift and light are confounds."""
    width,height=1260,max(300,120+len(rows)*28)
    canvas=Image.new("RGB",(width,height),(249,249,249))
    d=ImageDraw.Draw(canvas)
    d.text((14,10),f"{certificate}: normalized optical switching sensitivity",
           fill=(20,20,20))
    d.text((14,30),"No facet labels. Bars show relative dark-switch change; dashed concept = baseline.",
           fill=(60,60,60))
    labels=[("baseline",(30,30,30)),
            ("x_plus_1px",(185,55,58)),
            ("smooth_horizontal_gradient_12pct",(50,100,200))]
    d.text((250,55),"Median dark-switch fraction (0..1) for source pairs",fill=(20,20,20))
    for row_i,row in enumerate(rows):
        y=80+28*row_i
        d.text((15,y),f"{row['positions'][0]:03d}->{row['positions'][1]:03d}",
               fill=(30,30,30))
        result=row.get("sensitivity")
        if result is None or result["status"]!="observed":
            d.text((260,y),"unavailable",fill=(115,115,115))
            continue
        values={"baseline":result["baseline"]["total_dark_switch_fraction"]}
        values.update({r["scenario"]:r["metrics"]["total_dark_switch_fraction"]
                       for r in result["scenarios"] if r["metrics"] is not None})
        for j,(key,color) in enumerate(labels):
            val=values.get(key)
            if val is None:
                continue
            x0=260
            length=int(min(1.,max(0.,val))*860)
            d.rectangle((x0,y+j*6,x0+length,y+j*6+4),fill=color)
        if row_i%5==0:
            d.text((1140,y),f"{values['baseline']:.3f}",fill=(50,50,50))
    d.text((15,height-26),
           "Black=observed; red=+1px registration; blue=smooth lighting gradient. No ranking.",
           fill=(55,55,55))
    canvas.save(output)


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _,anchors,_,_=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD
    )
    face=junction.face_identity_state(pose,anchors)
    report={
        "schema_version":SCHEMA,"certificate":certificate,
        "face_identity":face,
        "selected_source_indices":[r["source_index"] for r in anchors],
        "selected_positions":[r["position"] for r in anchors],
        "pairs":[],"physical_facet_identity":"unavailable",
        "production_estimator_changed":False,
    }
    if len(anchors)<3:
        report.update(status="unavailable",reason="insufficient_frozen_anchors")
        return report
    pairs,policy=dense.dense_pairs(report["selected_positions"])
    report["dense_window_policy"]=policy
    frames=pose["frames"]
    if len(frames)!=256 or [r.get("position") for r in frames]!=list(range(256)):
        raise ValueError("not a frozen complete 256 source-frame sequence")
    cache={}
    def read(position):
        if position in cache:
            return cache[position]
        record=frames[position]
        if not neighbor._valid_record(record):
            cache[position]=None
            return None
        _,mask,_=stability._load_gauged_arrays(pose_dir,record)
        original=Image.open(Path(processed)/record["source_camera_path"]).convert("RGB")
        image,valid=rgb.image_to_gauge(
            original,mask,
            record["sequence_coordinate"]["sequence_gauge_to_camera_xy"]
        )
        cache[position]=(image,valid,mask)
        return cache[position]
    for i,j in pairs:
        first,second=frames[i],frames[j]
        row={
            "positions":[i,j],
            "source_indices":[first["source_index"],second["source_index"]],
            "face_identity":face["status"],
            "status":"unavailable",
            "facet_semantic_ids":None,
            "physical_facet_correspondence":"unavailable",
        }
        if face["status"]=="likely_crown" and (
            first.get("face_role")!="likely_crown_lobe"
            or second.get("face_role")!="likely_crown_lobe"
        ):
            row["reason"]="neighbor_outside_likely_crown_lobe"
        else:
            aa=read(i);bb=read(j)
            if aa is None or bb is None:
                row["reason"]="original_RGB_or_pose_unavailable"
            else:
                result=run_pair(
                    aa[0],bb[0],aa[2],bb[2],aa[1],bb[1]
                )
                row["sensitivity"]=result
                row["status"]=result["status"]
                if result["status"]!="observed":
                    row["reason"]=result.get("reason")
        report["pairs"].append(row)
    report["measured_pair_count"]=sum(
        r["status"]=="observed" for r in report["pairs"]
    )
    report["status"]="observational_only" if report["measured_pair_count"] else "unavailable"
    report["all_physical_facet_identity_unavailable"]=True
    summary={}
    for name in POLICY["controlled_scenarios"]:
        vals=[]
        for row in report["pairs"]:
            r=row.get("sensitivity")
            if r is None or r["status"]!="observed":
                continue
            match=next(s for s in r["scenarios"] if s["scenario"]==name)
            if match["status"]=="observed":
                vals.append(match["delta_from_unperturbed"])
        summary[name]={
            "available_pair_count":len(vals),
            "median_abs_delta":{
                m:float(np.median([abs(v[m]) for v in vals]))
                if vals else None for m in METRICS
            },
            "p90_abs_delta":{
                m:float(np.percentile([abs(v[m]) for v in vals],90))
                if vals else None for m in METRICS
            }
        }
    report["perturbation_summary"]=summary
    (output/"perturbation-sensitivity.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n"
    )
    _plot_stone(report["pairs"],output/"sensitivity-by-adjacent-pair.png",certificate)
    return report


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    stones=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-optical-confounds-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            order=Path(bundle["source_manifest"])
            if not order.is_absolute():
                order=Path.cwd()/order
            pipeline.run(
                Path(source_root).resolve()/cert,processed,order,
                gain=1.,accept_review=True
            )
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            report=run_stone(pose,processed,output/"per-stone"/cert,
                             certificate=cert)
            stones.append({
                "certificate":cert,"status":report["status"],
                "face_identity":report["face_identity"],
                "selected_source_indices":report["selected_source_indices"],
                "pair_count":len(report["pairs"]),
                "measured_pair_count":report["measured_pair_count"],
                "median_unperturbed_abs_change":(
                    float(np.median([
                        p["sensitivity"]["baseline"]["median_gain_normalized_abs_change"]
                        for p in report["pairs"] if p["status"]=="observed"
                    ])) if report["measured_pair_count"] else None),
                "scenario_summary":report["perturbation_summary"],
                "detail_path":f"per-stone/{cert}/perturbation-sensitivity.json",
                "plot_path":f"per-stone/{cert}/sensitivity-by-adjacent-pair.png",
            })
    result={
        "schema_version":SCHEMA,"policy":POLICY,
        "frozen_manifest_canonical_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":stones,"not_a_physical_facet_or_quality_score":True,
        "no_estimator_change":True,
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--bundle-manifest",type=Path,
                        default=Path("docs/360/benchmark/source-bundles.json"))
    args=parser.parse_args()
    result=run_source_benchmark(args.source_root,args.output,args.bundle_manifest)
    for r in result["stones"]:
        print(r["certificate"],r["face_identity"]["status"],
              "pairs",r["measured_pair_count"],"/",r["pair_count"],
              "median unperturbed optical change",
              r["median_unperturbed_abs_change"])
        for name,s in r["scenario_summary"].items():
            print(" ",name,s["available_pair_count"],
                  s["median_abs_delta"]["total_dark_switch_fraction"])


if __name__=="__main__":
    main()
