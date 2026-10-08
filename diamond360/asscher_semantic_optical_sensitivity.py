"""Target-blind photometric and fixed-support-zone sensitivity audit for #92.

No refitting and no semantic reassignment. The reference distribution is
only the same frame's valid gauge-mask pixels. Percentile ranks are
invariant to *positive affine* exposure changes without clipping; their
changes do not establish polished-facet behaviour or physical lighting.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from . import asscher_semantic_optical_handoff as handoff
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-fixed-support-photometric-sensitivity/1"
POLICY = {
    "experiment": "frozen_image_region_exposure_and_boundary_perturbation",
    "input": "existing_80_registered_measurement_brightness",
    "reference": "same_frame_valid_gauge_stone_pixels_not_outside_background",
    "relative_metric": "within_frame_midrank_percentile_among_valid_stone_pixels",
    "affine_exposure_invariance": "positive_affine_without_clipping_only",
    "support_variants": ["baseline", "inset_1px", "inset_2px", "outset_1px"],
    "support_variants_are_not_reestimated_semantic_boundaries": True,
    "outset_is_exploratory_and_can_include_adjacent_image_regions": True,
    "missing_support": "null_never_impute_or_interpolate",
    "geometry": "immutable_89_transfer_and_74_scaffold",
    "max_support_shift_px": 2,
    "uncertain_C3_table": "image_plane_only_physical_identity_unverified",
    "no_expert_targets_or_threshold_tuning": True,
    "no_quality_metric_or_physical_facet_angle": True,
}


def midranks(values, ordered):
    """Mid-tie empirical percentile of each value against stone pixels."""
    x=np.asarray(values,float)
    ordered=np.asarray(ordered,float)
    if len(ordered)==0 or not np.isfinite(ordered).all():
        raise ValueError("reference stone distribution must be finite/nonempty")
    left=np.searchsorted(ordered,x,side="left")
    right=np.searchsorted(ordered,x,side="right")
    return (left+right)/(2*len(ordered))


def _stats(region, raw, ordered):
    n=int(np.count_nonzero(region))
    if not n:
        return {"pixels":0,"mean_raw":None,"mean_stone_percentile":None}
    vals=raw[region]
    return {
        "pixels":n,
        "mean_raw":round(float(np.mean(vals)),7),
        "mean_stone_percentile":round(float(np.mean(midranks(vals,ordered))),7),
    }


def sample_sensitivity_frame(scaffold, transferred, brightness,
                             gauge_mask, valid_mask, *, baseline_report=None):
    """External-only diagnostic; validate via frozen handoff before sampling."""
    baseline=baseline_report or handoff.sample_fixed_frame(
        scaffold,transferred,brightness,gauge_mask,valid_mask)
    if (baseline.get("schema_version")!=handoff.SCHEMA
        or baseline.get("scaffold_unchanged") is not True
        or baseline.get("refit_performed") is not False):
        raise ValueError("baseline provenance is not a frozen handoff")
    raw=np.asarray(brightness,float)
    gauge=np.asarray(gauge_mask,bool)
    valid=np.asarray(valid_mask,bool)
    if raw.ndim!=2 or gauge.shape!=raw.shape or valid.shape!=raw.shape:
        raise ValueError("invalid registered pixel arrays")
    if not np.isfinite(raw).all():
        raise ValueError("non-finite input pixels")
    active=gauge & valid
    n=int(active.sum())
    if n<3:
        raise ValueError("too few valid gauge pixels for photometric reference")
    ordered=np.sort(raw[active])
    median=float(np.median(ordered))
    q25,q75=(float(x) for x in np.percentile(ordered,[25,75]))
    iqr=q75-q25
    points=wireframe._scaffold_points_in_gauge(gauge,scaffold)
    ref_by_id={s["support_id"]:s for s in scaffold["semantic_supports"]}
    out=[]
    baseline_by_id={row["semantic_id"]:row for row in baseline["entities"]}
    if set(baseline_by_id)!=set(scaffold["entity_observations"]):
        raise ValueError("baseline semantic IDs differ from immutable scaffold")

    # Exactly the frozen per-entity union used by the original handoff, then
    # bounded rasterized *sampling* perturbations; no polygon vertices move.
    cache={}
    for semantic_id in sorted(baseline_by_id):
        reference=baseline_by_id[semantic_id]
        status=reference["geometry_support_status"]
        roi=np.zeros(raw.shape,bool)
        if status!="unavailable":
            for support_id in scaffold["entity_observations"][semantic_id]["support_ids"]:
                s=ref_by_id.get(support_id)
                if (s is None or semantic_id not in s["semantic_ids"]
                    or s.get("attribution_mode")!="nonexclusive_semantic_support"):
                    raise ValueError("invalid or exclusive semantic support")
                if support_id not in cache:
                    cache[support_id]=handoff._mask_polygon(
                        [points[v] for v in s["vertex_ids"]],raw.shape)
                roi |= cache[support_id]
        # Morphological variants use valid/gauge eligibility but NEVER make
        # unsupported entities available.
        variants={
            "baseline": roi & active,
            "inset_1px":ndimage.binary_erosion(roi,iterations=1) & active,
            "inset_2px":ndimage.binary_erosion(roi,iterations=2) & active,
            "outset_1px":ndimage.binary_dilation(roi,iterations=1) & active,
        }
        vals={name:_stats(region,raw,ordered) for name,region in variants.items()}
        if vals["baseline"]["pixels"] != reference["supported_pixel_count"]:
            raise ValueError("geometry support or rasterization changed from baseline")
        if reference["raw_mean_brightness"] is None:
            if vals["baseline"]["mean_raw"] is not None:
                raise ValueError("missing baseline was silently imputed")
        elif abs(vals["baseline"]["mean_raw"]-reference["raw_mean_brightness"])>1e-5:
            raise ValueError("baseline brightness drift")
        base_rank=vals["baseline"]["mean_stone_percentile"]
        zone_deltas={
            zone:(None if base_rank is None or vals[zone]["mean_stone_percentile"] is None
                  else round(vals[zone]["mean_stone_percentile"]-base_rank,7))
            for zone in ("inset_1px","inset_2px","outset_1px")
        }
        out.append({
            "semantic_id":semantic_id,
            "geometry_support_status":status,
            "geometry_confidence":reference["geometry_confidence"],
            "physical_facet_correspondence":"not_established",
            "inner_C3_table_identity":(
                "review_not_verified"
                if semantic_id.startswith("C3_") or semantic_id=="TABLE" else None),
            "variants":vals,
            "rank_delta_from_baseline":zone_deltas,
            "normalized_raw_mean_minus_stone_median_over_iqr":(
                None if vals["baseline"]["mean_raw"] is None or iqr<=1e-12
                else round((vals["baseline"]["mean_raw"]-median)/iqr,7)
            ),
            "no_physical_facet_partition":True,
        })

    return {
        "schema_version":SCHEMA,
        "source_index":transferred.get("source_index"),
        "rotation_phase_deg":transferred.get("rotation_phase_deg"),
        "scaffold_refitted":False,
        "reference_stone_pixels":n,
        "stone_reference_median":round(median,7),
        "stone_reference_iqr":round(iqr,7),
        "stone_reference_percentiles":{
            "p10":round(float(np.percentile(ordered,10)),7),
            "p90":round(float(np.percentile(ordered,90)),7),
        },
        "entities":out,
    }


def _range(values):
    finite=[float(v) for v in values if v is not None and np.isfinite(v)]
    return None if not finite else round(max(finite)-min(finite),7)


def summarize_sensitivity(certificate, original, sensitivity_frames):
    if len(original["frames"])!=len(sensitivity_frames):
        raise ValueError("sensitivity replay frame count differs from raw replay")
    if not original.get("frozen_artifact_sha256") or original.get("scaffold_was_refitted"):
        raise ValueError("source archive or ruler was not proven frozen")
    by_frame={f["source_index"]:f for f in sensitivity_frames}
    if set(by_frame)!=set(original["sampled_source_indices"]):
        raise ValueError("source frame indices drifted")
    entity_ids={row["semantic_id"] for row in original["frames"][0]["entities"]}
    comparison={}
    for ident in sorted(entity_ids):
        rows=[
            next(row for row in by_frame[idx]["entities"] if row["semantic_id"]==ident)
            for idx in original["sampled_source_indices"]
        ]
        baselines=[row["variants"]["baseline"] for row in rows]
        zone_stats={}
        for v in ("inset_1px","inset_2px","outset_1px"):
            delta=[abs(row["rank_delta_from_baseline"][v])
                   for row in rows if row["rank_delta_from_baseline"][v] is not None]
            zone_stats[v]={
                "comparable_frames":len(delta),
                "median_abs_rank_delta":round(float(np.median(delta)),7) if delta else None,
                "maximum_abs_rank_delta":round(float(max(delta)),7) if delta else None,
            }
        comparison[ident]={
            "valid_brightness_frames":sum(z["mean_raw"] is not None for z in baselines),
            "raw_mean_frame_range":_range(z["mean_raw"] for z in baselines),
            "stone_percentile_frame_range":_range(
                z["mean_stone_percentile"] for z in baselines),
            "zone_sensitivity":zone_stats,
            "physical_facet_identity":"not_established",
        }
    return {
        "schema_version":SCHEMA,
        "policy":POLICY,
        "certificate":certificate,
        "source_indices":original["sampled_source_indices"],
        "archived_crown_face_selection":original["archived_crown_face_selection"],
        "archived_primary_transfer_sha256":original["frozen_artifact_sha256"],
        "scaffold_refitted":False,
        "source_sequence_reused_without_additional_download_or_fit":True,
        "outlier_threshold_or_quality_score":None,
        "physical_facet_angle_claim":False,
        "stone_intensity_reference":[
            {"source_index":f["source_index"],"median":f["stone_reference_median"],
             "iqr":f["stone_reference_iqr"],"valid_pixels":f["reference_stone_pixels"]}
            for f in sensitivity_frames
        ],
        "entities":comparison,
        "frames":sensitivity_frames,
    }


PLOT_ENTITIES=("C1_N","C2_N","C3_N","P1_N","P2_N","P3_N")
COLORS=((12,100,175),(236,125,30),(145,90,200),
        (25,153,113),(209,66,84),(111,111,125))


def render_sensitivity(report, path):
    """One chart for exposure-normalized trace and a footprint variation table."""
    width,height=1160,750
    img=Image.new("RGB",(width,height),(253,253,253))
    d=ImageDraw.Draw(img)
    d.text((27,16),report["certificate"]+" | #89 FROZEN ruler | same-frame stone-percentile brightness",fill=(27,33,45))
    d.text((27,37),"Rank normalization suppresses uniform exposure scaling; NOT a physical facet or quality score.",fill=(69,76,89))
    x0,y0,w,h=64,85,1025,375
    for p in (0,.25,.5,.75,1):
        yy=y0+(1-p)*h
        d.line((x0,yy,x0+w,yy),fill=(227,230,235))
        d.text((19,yy-7),str(p),fill=(73,79,93))
    for i,source in enumerate(report["source_indices"]):
        xx=x0+w*i/max(1,len(report["source_indices"])-1)
        d.line((xx,y0,xx,y0+h),fill=(243,244,247))
        d.text((xx-7,y0+h+8),str(source),fill=(70,80,95))
    for j,ident in enumerate(PLOT_ENTITIES):
        last=None
        for i,frame in enumerate(report["frames"]):
            row=next((e for e in frame["entities"] if e["semantic_id"]==ident),None)
            value=row["variants"]["baseline"]["mean_stone_percentile"] if row else None
            if value is None:
                last=None
                continue
            point=(x0+w*i/max(1,len(report["frames"])-1),y0+(1-value)*h)
            if last is not None:
                d.line((*last,*point),fill=COLORS[j],width=3)
            d.ellipse((point[0]-4,point[1]-4,point[0]+4,point[1]+4),fill=COLORS[j])
            last=point
    d.text((x0+250,490),"Nominal viewer frames (255 -> 0 cyclic wrap); NOT physical rotation calibration",fill=(70,76,87))
    d.text((27,522),"Support-variant sensitivity (median |rank delta| across supported frames):",fill=(28,35,48))
    labels=("1 px inset","2 px inset","1 px outset")
    for k,ident in enumerate(PLOT_ENTITIES):
        ix=k%3;iy=k//3
        x=40+380*ix;y=550+75*iy
        d.line((x,y+7,x+25,y+7),fill=COLORS[k],width=4)
        d.text((x+35,y),ident+"  ("+str(report["entities"][ident]["valid_brightness_frames"])+"/"+str(len(report["frames"]))+" frames)",fill=(35,40,50))
        zones=report["entities"][ident]["zone_sensitivity"]
        txt=[]
        for tag,zone in zip(labels,("inset_1px","inset_2px","outset_1px")):
            val=zones[zone]["median_abs_rank_delta"]
            txt.append(tag+": "+("n/a" if val is None else f"{val:.3f}"))
        d.text((x+2,y+25)," | ".join(txt[:2]),fill=(70,79,89))
        d.text((x+2,y+43),txt[2],fill=(70,79,89))
    if report["archived_crown_face_selection"].startswith("unresolved"):
        d.text((28,715),"FACE ROLE UNRESOLVED: all results are image-plane optical support only.",fill=(171,76,53))
    else:
        d.text((28,715),"Likely crown lobe, but physical C3/table facet correspondence UNVERIFIED.",fill=(85,88,95))
    img.save(path)


def write_sensitivity(original, frames, output_root):
    output=Path(output_root)
    output.mkdir(parents=True,exist_ok=True)
    report=summarize_sensitivity(original["certificate"],original,frames)
    (output/"real-support-sensitivity.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    render_sensitivity(report,output/"real-support-sensitivity.png")
    return report
