"""#123: dense consecutive optical brightness/contrast atlas; no facet labels.

Frozen #96 outer selected views define the *arc to observe*, not physical
interior geometry. The 4x4 rectangular bins are arbitrary image-plane bins,
not a cut model, and capture dark/bright switches, not facet identity.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_geometry_junction_graph as junction
from . import asscher_geometry_rgb_lines as rgb
from . import asscher_optical_neighbor_motion as neighbor
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA="diamond360-asscher-dense-optical-regions/1"
POLICY={
    "schema_version":SCHEMA,
    "sequence_size":256,
    "anchor":"frozen_96_outer_octagon_selected_views",
    "window":"shortest_circular_arc_covering_all_anchors_plus_2_each_end",
    "maximum_adjacent_pairs":36,
    "grid_rows":4,"grid_cols":4,
    "minimum_interior_pixels":500,
    "minimum_bin_pixels":80,
    "dark_relative_to_frame_median":0.70,
    "bright_relative_to_frame_median":1.30,
    "normalization":"raw_camera_RGB_luminance_per_frame_median_common_eroded_silhouette",
    "view_identity":"resolved_likely_crown_or_uncertain_no_promotion",
    "observables":"image_plane_dark_bright_occupancy_and_normalized_change",
    "physical_facet_identity":"unavailable",
    "no_real_vs_virtual_facet_classifier":True,
    "no_quality_score":True,
    "no_source_stress":True,
    "no_estimator_change":True,
}


def dense_pairs(anchors, *, size=256, pad=2, max_pairs=36):
    """Fill unsampled ordinal gaps in the shortest cycle arc of all anchors.

    On a cycle there is no unique left/right start. Remove the largest
    circular gap; choose deterministic earlier start on ties. A bound
    must not silently truncate selected anchors.
    """
    pos=sorted(set(int(x) for x in anchors))
    if len(pos)<2 or len(pos)!=len(anchors) or any(
        type(x) is not int or not 0<=x<size for x in anchors
    ):
        raise ValueError("invalid or duplicate selected positions")
    gaps=[((pos[(i+1)%len(pos)]-pos[i])%size,i)
          for i in range(len(pos))]
    gap,i=max(gaps,key=lambda x:(x[0],-x[1]))
    start=pos[(i+1)%len(pos)]
    covered=(pos[i]-start)%size
    total=covered+pad*2
    if total>max_pairs:
        raise ValueError("selected circular source arc exceeds research window cap")
    origin=(start-pad)%size
    pairs=[((origin+j)%size,(origin+j+1)%size)
           for j in range(total)]
    assert all(any(a==p or b==p for a,b in pairs)
               for p in pos)
    return pairs,{
        "circular_start_position":start,
        "circular_end_position":pos[i],
        "largest_excluded_gap":gap,
        "pad_on_each_side":pad,
        "pair_count":len(pairs),
        "frozen_anchor_positions":pos,
        "all_anchors_covered":True,
    }


def region_appearance(a,b,mask_a,mask_b,valid_a,valid_b,*,grid=4):
    """Photometry-only relative dark/light transitions in overlap pixels."""
    aa=np.asarray(a,float);bb=np.asarray(b,float)
    arr=[np.asarray(x,bool) for x in
         (mask_a,mask_b,valid_a,valid_b)]
    if aa.ndim!=2 or aa.shape!=bb.shape or any(
        x.shape!=aa.shape for x in arr
    ) or not (np.isfinite(aa).all() and np.isfinite(bb).all()):
        raise ValueError("camera RGB gauge arrays or masks incompatible")
    overlap=arr[0]&arr[1]&arr[2]&arr[3]
    erode=max(3,int(min(aa.shape)*.015))
    roi=ndi.binary_erosion(overlap,iterations=erode)
    npixels=int(roi.sum())
    if npixels<POLICY["minimum_interior_pixels"]:
        return {"status":"unavailable","reason":"insufficient_common_interior",
                "overlap_pixels":npixels,"bins":[]}
    ga=float(np.median(aa[roi]));gb=float(np.median(bb[roi]))
    if min(ga,gb)<neighbor.POLICY["minimum_raw_frame_median"]:
        return {"status":"unavailable","reason":"low_original_RGB_brightness",
                "overlap_pixels":npixels,"bins":[]}
    normalized_a=aa/ga; normalized_b=bb/gb
    diff=normalized_b-normalized_a
    low=POLICY["dark_relative_to_frame_median"]
    high=POLICY["bright_relative_to_frame_median"]
    before_dark=normalized_a<low
    after_dark=normalized_b<low
    before_bright=normalized_a>high
    after_bright=normalized_b>high
    h,w=aa.shape
    ys,xs=np.nonzero(roi)
    x0,x1=int(xs.min()),int(xs.max())+1
    y0,y1=int(ys.min()),int(ys.max())+1
    bins=[]
    for r in range(grid):
        for c in range(grid):
            xa=x0+(x1-x0)*c//grid
            xb=x0+(x1-x0)*(c+1)//grid
            ya=y0+(y1-y0)*r//grid
            yb=y0+(y1-y0)*(r+1)//grid
            part=roi[ya:yb,xa:xb]
            n=int(part.sum())
            item={"bin_id":f"r{r}c{c}","grid":[r,c],
                  "bounding_box_gauge_px":[xa,ya,xb,yb],
                  "supported_pixels":n,
                  "physical_facet_semantic_id":None}
            if n<POLICY["minimum_bin_pixels"]:
                item.update(status="unavailable",reason="insufficient_bin_overlap")
            else:
                da=before_dark[ya:yb,xa:xb][part]
                db=after_dark[ya:yb,xa:xb][part]
                ba=before_bright[ya:yb,xa:xb][part]
                bz=after_bright[ya:yb,xa:xb][part]
                local=diff[ya:yb,xa:xb][part]
                item.update({
                    "status":"observed",
                    "dark_occupancy_before_after":[float(da.mean()),float(db.mean())],
                    "bright_occupancy_before_after":[float(ba.mean()),float(bz.mean())],
                    "dark_state_switch_fraction":float(np.mean(da!=db)),
                    "bright_state_switch_fraction":float(np.mean(ba!=bz)),
                    "dark_to_bright_fraction":float(np.mean(da&bz)),
                    "bright_to_dark_fraction":float(np.mean(ba&db)),
                    "median_signed_normalized_change":float(np.median(local)),
                    "median_abs_normalized_change":float(np.median(abs(local))),
                    "p90_abs_normalized_change":float(np.percentile(abs(local),90)),
                })
            bins.append(item)
    return {
        "status":"observed","overlap_pixels":npixels,
        "gauge_roi_size":[w,h],
        "mask_intersection_over_union":float(
            np.sum(arr[0]&arr[1])/max(1,np.sum(arr[0]|arr[1]))),
        "raw_median_luminance_before_after":[ga,gb],
        "raw_luminance_ratio_b_over_a":gb/ga,
        "median_gain_normalized_abs_change":float(np.median(abs(diff[roi]))),
        "p90_gain_normalized_abs_change":float(np.percentile(abs(diff[roi]),90)),
        "total_dark_switch_fraction":float(np.mean((before_dark^after_dark)[roi])),
        "total_bright_switch_fraction":float(np.mean((before_bright^after_bright)[roi])),
        "bins":bins,
        "physical_facet_correspondence":"unavailable",
        "can_claim_virtual_facets":False,
        "_render_input":{"dark_map_before":before_dark,
                         "dark_map_after":after_dark,
                         "difference":diff,"roi":roi},
    }


def _serialize_measure(measure):
    return {k:v for k,v in measure.items() if k!="_render_input"}


def render_pair(source_a,source_b,mask_a,mask_b,matrix_a,matrix_b,measure,indices):
    """Original RGB pair + masked signed brightness-change map and grid."""
    left=neighbor._source_crop(source_a,mask_a,matrix_a)
    middle=neighbor._source_crop(source_b,mask_b,matrix_b)
    target_w=max(left.width,middle.width,220)
    target_h=max(left.height,middle.height,220)
    header=65
    canvas=Image.new("RGB",(3*target_w+18,target_h+header),(19,19,19))
    for i,img in enumerate((left,middle)):
        pic=img.copy();pic.thumbnail((target_w,target_h),Image.Resampling.LANCZOS)
        canvas.paste(pic,(i*(target_w+6),header))
    renderer=measure.get("_render_input")
    if renderer is not None:
        diff=renderer["difference"]
        mask=renderer["roi"]
        intensity=np.clip(np.abs(diff)/0.75,0,1)
        data=np.zeros((*diff.shape,3),dtype=np.uint8)
        pos=(diff>0)&mask
        neg=(diff<0)&mask
        data[pos,0]=(255*intensity[pos]).astype(np.uint8)
        data[neg,2]=(255*intensity[neg]).astype(np.uint8)
        data[mask,1]=(40*intensity[mask]).astype(np.uint8)
        heat=Image.fromarray(data).resize((target_w,target_h),
                                          Image.Resampling.NEAREST)
        draw=ImageDraw.Draw(heat)
        h,w=mask.shape
        for item in measure["bins"]:
            xa,ya,xb,yb=item["bounding_box_gauge_px"]
            draw.rectangle((xa*target_w/w,ya*target_h/h,
                            xb*target_w/w,yb*target_h/h),
                           outline=(145,145,145),width=1)
        canvas.paste(heat,(2*(target_w+6),header))
    labels=[f"Original RGB src {indices[0]}",f"Original RGB src {indices[1]}",
            "GAIN-NORMALIZED SIGNED OPTICAL CHANGE"]
    draw=ImageDraw.Draw(canvas)
    for i,label in enumerate(labels):
        draw.text((i*(target_w+6)+7,8),label,fill=(255,255,255))
        draw.text((i*(target_w+6)+7,29),
                  "NO true/virtual facet labels. Red brighter; blue darker.",
                  fill=(210,210,210))
    return canvas


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _,selected,_,_=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD)
    face=junction.face_identity_state(pose,selected)
    record={
        "schema_version":SCHEMA,"certificate":certificate,
        "selected_source_indices":[x["source_index"] for x in selected],
        "selected_positions":[x["position"] for x in selected],
        "face_identity":face,
        "pairs":[],"physical_facet_identity":"unavailable",
        "production_estimator_changed":False,
    }
    if len(selected)<3:
        record.update(status="unavailable",reason="insufficient_frozen_outer_anchors")
        return record
    window,policy=dense_pairs(record["selected_positions"])
    record["dense_window_policy"]=policy
    frames=pose["frames"]
    if len(frames)!=POLICY["sequence_size"] or [r.get("position") for r in frames]!=list(range(POLICY["sequence_size"])):
        raise ValueError("not a complete ordered 256-frame pose sequence")
    cached={}
    def load_at(position):
        if position in cached:
            return cached[position]
        view=frames[position]
        if not neighbor._valid_record(view):
            cached[position]=None
            return None
        _,mask,_=stability._load_gauged_arrays(pose_dir,view)
        source=Image.open(Path(processed)/view["source_camera_path"]).convert("RGB")
        matrix=np.asarray(view["sequence_coordinate"]["sequence_gauge_to_camera_xy"],float)
        lum,valid=rgb.image_to_gauge(source,mask,matrix)
        cached[position]=(lum,valid,mask,source,matrix)
        return cached[position]
    for a,b in window:
        first,second=frames[a],frames[b]
        row={
            "positions":[a,b],
            "source_indices":[first.get("source_index"),second.get("source_index")],
            "rotation_phases_deg":[
                (view.get("sequence_coordinate") or {}).get("rotation_phase_deg")
                for view in (first,second)],
            "face_role_status":face["status"],
            "status":"unavailable",
            "physical_facet_semantic_ids":None,
        }
        if face["status"]=="likely_crown" and any(
            view.get("face_role")!="likely_crown_lobe"
            for view in (first,second)
        ):
            row["reason"]="neighbor_not_in_resolved_crown_lobe"
        else:
            aa=load_at(a);bb=load_at(b)
            if aa is None or bb is None:
                row["reason"]="original_RGB_or_canonical_pose_unavailable"
            else:
                measure=region_appearance(aa[0],bb[0],aa[2],bb[2],aa[1],bb[1])
                row.update(_serialize_measure(measure))
                if row["status"]=="observed":
                    name=f"dense-pos-{a:04d}-{b:04d}.jpg"
                    render_pair(aa[3],bb[3],aa[2],bb[2],aa[4],bb[4],
                                measure,row["source_indices"]).save(
                                    output/name,quality=90)
                    row["original_RGB_QC"]=name
        record["pairs"].append(row)
    record["status"]="observational_only" if any(
        x["status"]=="observed" for x in record["pairs"]) else "unavailable"
    record["measured_pair_count"]=sum(x["status"]=="observed"
                                      for x in record["pairs"])
    record["unavailable_pair_count"]=len(window)-record["measured_pair_count"]
    record["total_optical_bin_count"]=sum(
        x["status"]=="observed"
        for row in record["pairs"] for x in row.get("bins",[]))
    (output/"dense-optical-regions.json").write_text(
        json.dumps(record,indent=2,allow_nan=False)+"\n")
    all_images=[]
    for row in record["pairs"]:
        if "original_RGB_QC" in row:
            im=Image.open(output/row["original_RGB_QC"])
            im.thumbnail((1350,460),Image.Resampling.LANCZOS)
            all_images.append(im.copy())
    if all_images:
        from . import asscher_wireframe as wireframe
        wireframe._contact_sheet(
            all_images,output/"dense-optical-contact-sheet.jpg",columns=1)
    return record


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-optical-regions-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            m=Path(bundle["source_manifest"])
            if not m.is_absolute():m=Path.cwd()/m
            pipeline.run(Path(source_root).resolve()/cert,processed,m,
                         gain=1.,accept_review=True)
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            record=run_stone(pose,processed,output/"per-stone"/cert,
                             certificate=cert)
            measured=[p for p in record["pairs"] if p["status"]=="observed"]
            rows.append({
                "certificate":cert,"status":record["status"],
                "selected_source_indices":record["selected_source_indices"],
                "selected_positions":record["selected_positions"],
                "face_identity":record["face_identity"],
                "dense_window_policy":record.get("dense_window_policy"),
                "measured_pair_count":record.get("measured_pair_count",0),
                "unavailable_pair_count":record.get("unavailable_pair_count",0),
                "total_optical_bin_count":record.get("total_optical_bin_count",0),
                "median_gain_normalized_abs_change":(
                    float(np.median([p["median_gain_normalized_abs_change"]
                                     for p in measured])) if measured else None),
                "camera_RGB_QC_contact_sheet":(
                    f"per-stone/{cert}/dense-optical-contact-sheet.jpg"
                    if measured else None),
            })
    summary={
        "schema_version":SCHEMA,"policy":POLICY,
        "manifest_sha256":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":rows,
        "physical_facet_correspondence":"unavailable",
        "no_quality_score":True,
        "no_estimator_change":True,
    }
    (output/"summary.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n")
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--bundle-manifest",type=Path,
                        default=Path("docs/360/benchmark/source-bundles.json"))
    args=parser.parse_args()
    report=run_source_benchmark(args.source_root,args.output,args.bundle_manifest)
    for row in report["stones"]:
        print(row["certificate"],row["face_identity"]["status"],
              "adjacent dense pairs",row["measured_pair_count"],
              "/",row["dense_window_policy"]["pair_count"],
              "optical bins",row["total_optical_bin_count"])


if __name__=="__main__":
    main()
