"""#123: neighbor-view optical appearance change without physical facet tracking.

Uses untouched camera RGB reprojected through each existing #80 gauge matrix,
the frozen #96 selected views solely as research anchor positions, and only
direct adjacent ordinal frame pairs. This module never names a polished facet.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_geometry_rgb_lines as rgb
from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_geometry_junction_graph as junction
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA="diamond360-asscher-neighbor-optical-appearance/1"
POLICY={
    "schema_version":SCHEMA,
    "anchor_method":validation.OUTER_METHOD,
    "pairs":"adjacent_ordinal_frames_at_frozen_96_crown_anchor_positions",
    "max_pairs_per_stone":12,
    "neighbor_radius_frames":1,
    "grid_size":4,
    "max_local_shift_px":4,
    "minimum_pair_interior_pixels":500,
    "minimum_patch_overlap_pixels":80,
    "minimum_gradient_std":.0015,
    "minimum_peak_ncc":.25,
    "minimum_peak_margin":.035,
    "minimum_raw_frame_median":.02,
    "pair_gain_policy":"normalize_each_frame_by_same_overlap_median",
    "photometry":"raw_camera_RGB_luminance_plus_gain_normalized_difference",
    "geometry":"frozen_source_silhouette_only",
    "motion_meaning":"gauge_space_apparent_optical_texture_shift_not_facet_motion",
    "virtual_facet_class":"optical_or_structural_unresolved",
    "crown_identity":"propagate_73_resolved_or_uncertain_no_promotion",
    "no_physical_facet_labels":True,
    "no_source_stress":True,
    "no_production_estimator_change":True,
}


def neighboring_pairs(payload, selected, *, limit=12):
    """Choose only observed-adjacent ordinal pairs, deduplicated at sequence wrap."""
    frames=payload.get("frames") or []
    size=len(frames)
    positions=[r.get("position") for r in frames]
    if size<3 or positions!=list(range(size)):
        raise ValueError("neighbor comparisons need a complete ordered 360 sequence")
    if not bool(payload.get("sequence_complete",False)):
        # Pose payloads may omit the boolean but have full ordered frames.
        # Do not infer wrap from this alone: wrap is allowed only if #80 gauge
        # metadata explicitly confirms closure and poses are available.
        pass
    anchors=[int(r["position"]) for r in selected]
    if len(set(anchors))!=len(anchors):
        raise ValueError("duplicate frozen anchor positions")
    seen=set()
    pairs=[]
    for anchor in anchors:
        for n in ((anchor-1)%size,(anchor+1)%size):
            a,b=(n,anchor) if n==(anchor-1)%size else (anchor,n)
            # Keep the physical ordinal forward direction even across 255->0.
            key=(a,b)
            if key not in seen:
                seen.add(key)
                pairs.append((a,b))
    return pairs[:limit]


def _valid_record(rec):
    return (
        rec.get("assessment",{}).get("status") in ("ok","review")
        and (rec.get("canonical") or {}).get("path") is not None
        and rec.get("source_camera_path")
        and (rec.get("sequence_coordinate") or {}).get("gauge_status")
             in ("available","review")
        and (rec.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy") is not None
    )


def _edge(gray):
    smooth=ndi.gaussian_filter(gray,1.)
    return np.hypot(ndi.sobel(smooth,axis=0)/8.,
                    ndi.sobel(smooth,axis=1)/8.)


def _ncc(a,b):
    aa=a-np.mean(a); bb=b-np.mean(b)
    sa=float(np.linalg.norm(aa)); sb=float(np.linalg.norm(bb))
    if min(sa,sb)<1e-8:
        return None
    return float(np.dot(aa,bb)/(sa*sb))


def measure_patch_shifts(a,b,valid,*,grid=4,max_shift=4):
    """Local optical texture correlation only, no spatial feature IDs.

    Uses the SAME fixed reference-pixel region for each displacement; also
    checks translated target support. Avoid np.roll and wraparound matches.
    """
    a=np.asarray(a,float); b=np.asarray(b,float)
    valid=np.asarray(valid,bool)
    if a.shape!=b.shape or valid.shape!=a.shape or a.ndim!=2:
        raise ValueError("incompatible optical arrays")
    h,w=a.shape
    ys,xs=np.nonzero(valid)
    if not len(xs):
        return []
    left,right=int(xs.min()),int(xs.max())+1
    top,bottom=int(ys.min()),int(ys.max())+1
    result=[]
    for row in range(grid):
        y0=top+int((bottom-top)*row/grid)
        y1=top+int((bottom-top)*(row+1)/grid)
        for col in range(grid):
            x0=left+int((right-left)*col/grid)
            x1=left+int((right-left)*(col+1)/grid)
            reference=valid[y0:y1,x0:x1]
            center=[float((x0+x1)/2),float((y0+y1)/2)]
            if int(reference.sum()) < POLICY["minimum_patch_overlap_pixels"]:
                result.append({"grid":[row,col],"center_gauge_xy":center,
                               "status":"unavailable","reason":"insufficient_patch_overlap"})
                continue
            ranked=[]
            for dy in range(-max_shift,max_shift+1):
                for dx in range(-max_shift,max_shift+1):
                    if min(y0+dy,x0+dx)<0 or y1+dy>h or x1+dx>w:
                        continue
                    m=reference & valid[y0+dy:y1+dy,x0+dx:x1+dx]
                    if int(m.sum())<POLICY["minimum_patch_overlap_pixels"]:
                        continue
                    av=a[y0:y1,x0:x1][m]
                    bv=b[y0+dy:y1+dy,x0+dx:x1+dx][m]
                    if (np.std(av)<POLICY["minimum_gradient_std"] or
                            np.std(bv)<POLICY["minimum_gradient_std"]):
                        continue
                    corr=_ncc(av,bv)
                    if corr is not None:
                        ranked.append((corr,dy,dx,int(m.sum())))
            if not ranked:
                result.append({"grid":[row,col],"center_gauge_xy":center,
                               "status":"unavailable","reason":"low_texture_or_no_supported_shift"})
                continue
            ranked.sort(reverse=True)
            best=ranked[0]
            second=next((v for v in ranked[1:] if
                         (v[1]-best[1])**2+(v[2]-best[2])**2>=4),
                        ranked[1] if len(ranked)>1 else None)
            margin=(best[0]-second[0]) if second is not None else 1.
            zero=next((v[0] for v in ranked if v[1:3]==(0,0)),None)
            status=("measured" if best[0]>=POLICY["minimum_peak_ncc"]
                    and margin>=POLICY["minimum_peak_margin"] else "ambiguous")
            result.append({
                "grid":[row,col],"center_gauge_xy":center,
                "status":status,
                "apparent_shift_gauge_px":{"dx":best[2],"dy":best[1]}
                if status=="measured" else None,
                "best_gradient_ncc":best[0],
                "zero_shift_gradient_ncc":zero,
                "best_vs_nonlocal_peak_margin":float(margin),
                "overlap_pixels":best[3],
                "physical_facet_semantic_id":None,
            })
    return result


def measure_pair(a,b,mask_a,mask_b,valid_a,valid_b):
    """Normalize photometric gain separately from registered texture motion."""
    a=np.asarray(a,float); b=np.asarray(b,float)
    masks=[np.asarray(x,bool) for x in (mask_a,mask_b,valid_a,valid_b)]
    if any(x.shape!=a.shape for x in masks) or b.shape!=a.shape:
        raise ValueError("registered camera frames incompatible")
    intersection=masks[0]&masks[1]&masks[2]&masks[3]
    roi=ndi.binary_erosion(intersection,iterations=max(3,int(min(a.shape)*.015)))
    n=int(roi.sum())
    if n<POLICY["minimum_pair_interior_pixels"]:
        return {"status":"unavailable","reason":"insufficient_common_interior",
                "overlap_pixels":n,"patches":[]}
    gain_a=float(np.median(a[roi])); gain_b=float(np.median(b[roi]))
    if min(gain_a,gain_b)<POLICY["minimum_raw_frame_median"]:
        return {"status":"unavailable","reason":"low_raw_camera_brightness",
                "overlap_pixels":n,"patches":[]}
    aa=a/gain_a; bb=b/gain_b
    # Robust change captures appearance differences even when the best local
    # texture shift is ambiguous. These remain two distinct measurements.
    diff=np.abs(aa-bb)
    ea=_edge(aa); eb=_edge(bb)
    patches=measure_patch_shifts(ea,eb,roi)
    motions=[r for r in patches if r["status"]=="measured"]
    result={
        "status":"observed",
        "overlap_pixels":n,
        "mask_intersection_over_union":float(
            np.sum(masks[0]&masks[1])/max(1,np.sum(masks[0]|masks[1]))),
        "raw_median_luminance":[gain_a,gain_b],
        "raw_median_luminance_ratio_b_over_a":gain_b/gain_a,
        "median_gain_normalized_abs_change":float(np.median(diff[roi])),
        "p90_gain_normalized_abs_change":float(np.percentile(diff[roi],90)),
        "mean_gain_normalized_edge_change":float(
            np.mean(np.abs(ea-eb)[roi])),
        "patches":patches,
        "measured_optical_shift_tile_count":len(motions),
        "ambiguous_tile_count":sum(r["status"]=="ambiguous" for r in patches),
        "unavailable_tile_count":sum(r["status"]=="unavailable" for r in patches),
        "physical_facet_correspondence":"unavailable",
        "feature_interpretation":"image_plane_appearance_only_including_possible_virtual_facets",
    }
    return result


def _source_crop(source,mask,matrix):
    # Bound the original RGB crop with the actual gauge mask mapped to camera.
    yy,xx=np.nonzero(mask)
    if len(xx)==0:
        return source.copy()
    center,scale=rgb.normalized_gauge(mask)
    points=np.array([[xx.min(),yy.min()],[xx.max(),yy.min()],
                     [xx.max(),yy.max()],[xx.min(),yy.max()]],float)
    norm=(points-center)/scale
    camera=rgb._points_to_camera(norm,mask,matrix)
    lo=np.min(camera,axis=0); hi=np.max(camera,axis=0)
    pad=.08*max(*(hi-lo))
    bounds=(max(0,int(lo[0]-pad)),max(0,int(lo[1]-pad)),
            min(source.width,int(hi[0]+pad)),min(source.height,int(hi[1]+pad)))
    if bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:
        return source.copy()
    return source.crop(bounds)


def render_pair(source_a,source_b,mask_a,mask_b,matrix_a,matrix_b,
                a,b,measurement,source_indices):
    """Show original RGB pair + registered *appearance* change, no facet masks."""
    im_a=_source_crop(source_a,mask_a,matrix_a)
    im_b=_source_crop(source_b,mask_b,matrix_b)
    w=max(im_a.width,im_b.width,220)
    h=max(im_a.height,im_b.height,220)
    canvas=Image.new("RGB",(3*w+12,h+55),(18,18,18))
    for i,im in enumerate((im_a,im_b)):
        panel=im.copy(); panel.thumbnail((w,h),Image.Resampling.LANCZOS)
        canvas.paste(panel,(i*(w+6),55))
    if measurement["status"]=="observed":
        g0,g1=measurement["raw_median_luminance"]
        normalized=np.abs(a/g0-b/g1)
        # Display ONLY the common, eroded stone interior that was
        # eligible for quantitative comparison. Unregistered silhouette
        # margins and off-stone pixels otherwise form fictitious orange
        # "motion" bars at the boundary of a heatmap.
        common=np.asarray(mask_a,bool)&np.asarray(mask_b,bool)
        common=ndi.binary_erosion(
            common,iterations=max(3,int(min(a.shape)*.015))
        )
        mag=np.clip(normalized/0.75,0,1)
        rgb_map=np.stack([mag*255, np.sqrt(mag)*100,
                          (1-mag)*36],axis=-1).astype(np.uint8)
        rgb_map[~common]=(10,14,24)
        heat=Image.fromarray(rgb_map).resize((w,h),Image.Resampling.NEAREST)
        d=ImageDraw.Draw(heat)
        sy=h/a.shape[0]; sx=w/a.shape[1]
        for r in measurement["patches"]:
            if r["status"]!="measured":
                continue
            center=r["center_gauge_xy"]
            shift=r["apparent_shift_gauge_px"]
            x,y=center[0]*sx,center[1]*sy
            dx,dy=shift["dx"]*sx*2,shift["dy"]*sy*2
            d.line([(x,y),(x+dx,y+dy)],fill=(255,255,255),width=2)
            d.ellipse((x+dx-2,y+dy-2,x+dx+2,y+dy+2),fill=(255,255,255))
        canvas.paste(heat,(2*(w+6),55))
    labels=[f"original RGB source {source_indices[0]}",
            f"original RGB source {source_indices[1]}",
            "registered appearance change / optical arrows"]
    drawer=ImageDraw.Draw(canvas)
    for i,label in enumerate(labels):
        drawer.text((i*(w+6)+6,8),label,fill=(255,255,255))
        drawer.text((i*(w+6)+6,27),
                    "NO physical facet identity",fill=(180,180,180))
    return canvas


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _,anchors,_,_=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD)
    face=junction.face_identity_state(pose,anchors)
    report={
        "schema_version":SCHEMA,"certificate":certificate,
        "frozen_anchor_source_indices":[r["source_index"] for r in anchors],
        "face_identity":face,
        "candidate_pair_count":0,"pairs":[],
        "physical_facet_identity":"not_established",
        "production_estimator_changed":False,
    }
    if len(anchors)<3:
        report["status"]="unavailable"
        report["reason"]="insufficient_frozen_primary_anchors"
        return report
    pairs=neighboring_pairs(pose,anchors,limit=POLICY["max_pairs_per_stone"])
    report["candidate_pair_count"]=len(pairs)
    frames=pose["frames"]
    results=[]
    for pa,pb in pairs:
        a,b=frames[pa],frames[pb]
        row={
            "source_indices":[a["source_index"],b["source_index"]],
            "positions":[pa,pb],
            "rotation_phases_deg":[
                (r.get("sequence_coordinate") or {}).get("rotation_phase_deg")
                for r in (a,b)],
            "face_identity":face["status"],
            "status":"unavailable",
            "physical_facet_semantic_ids":None,
        }
        if not (_valid_record(a) and _valid_record(b)):
            row["reason"]="pose_or_gauge_or_RGB_unavailable"
            results.append(row); continue
        # Never compare known crown to an explicitly different lobe.
        if (face["status"]=="likely_crown" and
                (a.get("face_role")!="likely_crown_lobe" or
                 b.get("face_role")!="likely_crown_lobe")):
            row["reason"]="neighbor_outside_resolved_crown_lobe"
            results.append(row); continue
        samples=[]
        for record in (a,b):
            _,mask,_=stability._load_gauged_arrays(pose_dir,record)
            source=Image.open(
                Path(processed)/record["source_camera_path"]
            ).convert("RGB")
            matrix=np.asarray(
                record["sequence_coordinate"]["sequence_gauge_to_camera_xy"],
                float)
            image,valid=rgb.image_to_gauge(source,mask,matrix)
            samples.append((image,valid,mask,source,matrix))
        (lum_a,valid_a,mask_a,src_a,mat_a),(lum_b,valid_b,mask_b,src_b,mat_b)=samples
        measure=measure_pair(lum_a,lum_b,mask_a,mask_b,valid_a,valid_b)
        row.update(measure)
        row["interpretation"]="adjacent_camera_RGB_optical_appearance_not_facets"
        results.append(row)
        # Generate all observed-pair QC, not only favorable/high-motion cases.
        if measure["status"]=="observed":
            name=f"adjacent-pos-{pa:04d}-{pb:04d}.jpg"
            render_pair(src_a,src_b,mask_a,mask_b,mat_a,mat_b,
                        lum_a,lum_b,measure,row["source_indices"]).save(
                            output/name,quality=90)
            row["camera_RGB_QC"]=name
    report["pairs"]=results
    report["status"]="observational_only" if any(
        r["status"]=="observed" for r in results) else "unavailable"
    report["measured_pair_count"]=sum(
        r["status"]=="observed" for r in results)
    report["skipped_pair_reasons"]={
        reason:sum(r.get("reason")==reason for r in results)
        for reason in sorted({r.get("reason") for r in results if r.get("reason")})
    }
    (output/"optical-neighbor-motion.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n")
    pictures=[]
    for row in results:
        if row.get("camera_RGB_QC"):
            picture=Image.open(output/row["camera_RGB_QC"]).convert("RGB")
            picture.thumbnail((1600,550),Image.Resampling.LANCZOS)
            pictures.append(picture.copy())
    if pictures:
        # All eligible views stay auditable, not just a cherry-picked subset.
        from . import asscher_wireframe as wireframe
        wireframe._contact_sheet(
            pictures,output/"adjacent-camera-RGB-contact-sheet.jpg",columns=1)
    return report


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-optical-neighbor-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            m=Path(bundle["source_manifest"])
            if not m.is_absolute():
                m=Path.cwd()/m
            pipeline.run(Path(source_root).resolve()/cert,processed,m,
                         gain=1.,accept_review=True)
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            record=run_stone(pose,processed,output/"per-stone"/cert,
                             certificate=cert)
            rows.append({
                "certificate":cert,"status":record["status"],
                "frozen_anchor_source_indices":record["frozen_anchor_source_indices"],
                "face_identity":record["face_identity"],
                "candidate_pair_count":record["candidate_pair_count"],
                "measured_pair_count":record.get("measured_pair_count",0),
                "skipped_pair_reasons":record.get("skipped_pair_reasons",{}),
                "median_gain_normalized_abs_change":(
                    float(np.median([r["median_gain_normalized_abs_change"]
                                     for r in record["pairs"]
                                     if r["status"]=="observed"]))
                    if any(r["status"]=="observed" for r in record["pairs"])
                    else None),
                "camera_RGB_QC_contact_sheet":(
                    f"per-stone/{cert}/adjacent-camera-RGB-contact-sheet.jpg"
                    if record.get("measured_pair_count",0)>0 else None),
            })
    summary={
        "schema_version":SCHEMA,"policy":POLICY,
        "frozen_manifest_canonical_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":rows,"no_physical_facet_ids":True,
        "no_estimator_change":True,
        "not_an_optical_quality_score":True,
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
              "adjacent pairs",row["measured_pair_count"],
              "/",row["candidate_pair_count"],
              "gain-normalized appearance change",
              row["median_gain_normalized_abs_change"])
if __name__=="__main__":
    main()
