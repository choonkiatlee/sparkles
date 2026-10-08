"""#92 sensitivity of *fixed* semantic image supports to exposure and edge choice.

Science diagnostic only. Uses previously sampled frozen #89 semantic polygon
geometry, never changes boundaries or assumes physical facet identity.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.stats import spearmanr

from . import asscher_semantic_optical_handoff as handoff
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-semantic-optical-sensitivity/1"
POLICY = {
    "reference_region": "all_valid_pixels_within_frozen_stone_gauge_mask",
    "reference_quantiles": [0.10, 0.90],
    "exposure_proxy": "support_mean_minus_frame_stone_p10_over_p90_minus_p10",
    "exposure_proxy_is_not": "calibrated_vendor_photometric_normalization",
    "uncalibrated_out_of_0_1_values": "retained_not_clipped",
    "reference_flat_span": "unavailable_not_zero",
    "alternate_support": "2_pixel_binary_erosion_of_same_frozen_polygon_union",
    "support_erosion_is_not": "a_new_faceted_region_fit",
    "raw_input": "existing_canonical_measurement_brightness",
    "control": "no_geometry_or_transfer_refit_and_no_optical_quality_score",
    "physical_facet_correspondence": "not_established",
}
PLOT_ENTITIES=("C1_N","C3_N","P1_N","P2_N")
PLOT_COLORS=((20,106,167),(190,91,170),(50,141,96),(229,134,37))


def sample_frame_sensitivity(scaffold, transfer, brightness, gauge_mask, valid_mask,
                             baseline):
    """Contrast proxy and 2px inward perturbation from *same frozen support*.

    The baseline #166 image-plane sample is compared to new full support
    quantile indices and an eroded support; it is never altered.
    """
    raw=np.asarray(brightness,float)
    gauge=np.asarray(gauge_mask,bool)
    valid=np.asarray(valid_mask,bool)
    if raw.ndim != 2 or gauge.shape != raw.shape or valid.shape != raw.shape:
        raise ValueError("image and masks are not registered")
    if not np.isfinite(raw).all():
        raise ValueError("source brightness not finite")
    if transfer.get("refit_performed") is not False or not baseline.get("scaffold_unchanged"):
        raise ValueError("ruler must remain frozen")
    if baseline.get("semantic_gauge_id") != scaffold["semantic_gauge"]["gauge_id"]:
        raise ValueError("semantic gauge changed")
    if baseline.get("source_index") != transfer.get("source_index"):
        raise ValueError("source index does not match original frame measurement")
    if baseline.get("physical_facet_angle_status") != "unavailable":
        raise ValueError("unexpected polished-facet-angle claim")
    region_mask=gauge & valid
    if not region_mask.any():
        raise ValueError("valid stone reference is empty")
    q10,q50,q90=[float(x) for x in np.quantile(raw[region_mask],(.10,.50,.90))]
    span=q90-q10
    usable=span>1e-6
    coord=wireframe._scaffold_points_in_gauge(gauge,scaffold)
    support_by_id={s["support_id"]:s for s in scaffold["semantic_supports"]}
    refrows={x["semantic_id"]:x for x in baseline["entities"]}
    if set(refrows) != set(scaffold["entity_observations"]):
        raise ValueError("frozen semantic ID correspondence changed")
    rows=[]
    for semantic_id in sorted(refrows):
        row=refrows[semantic_id]
        status=row["geometry_support_status"]
        union=np.zeros(raw.shape,bool)
        if status!="unavailable":
            for support_id in scaffold["entity_observations"][semantic_id]["support_ids"]:
                support=support_by_id[support_id]
                if semantic_id not in support["semantic_ids"] or support["attribution_mode"] != "nonexclusive_semantic_support":
                    raise ValueError("a support was reassigned or made exclusive")
                union |= handoff._mask_polygon([coord[v] for v in support["vertex_ids"]],raw.shape)
        full=union & region_mask
        if int(full.sum())!=row["supported_pixel_count"]:
            raise ValueError("baseline and sensitivity use different pixel supports")
        m=float(raw[full].mean()) if full.any() else None
        if m is None:
            if row["raw_mean_brightness"] is not None:
                raise ValueError("unexpected baseline non-null for unsupported image")
        elif abs(m-row["raw_mean_brightness"])>1e-9:
            raise ValueError("baseline changed while testing support sensitivity")
        # Shrink only the fixed polygon support (not the source intensity).
        core=ndi.binary_erosion(union,iterations=2,border_value=0) & region_mask
        c=float(raw[core].mean()) if core.any() else None
        rows.append({
            "semantic_id":semantic_id,
            "geometry_support_status":status,
            "raw_full_mean":m,
            "raw_eroded_2px_mean":c,
            "raw_eroded_minus_full":None if m is None or c is None else float(c-m),
            "full_pixel_count":int(full.sum()),
            "eroded_2px_pixel_count":int(core.sum()),
            "within_frame_quantile_contrast_full":(float((m-q10)/span)
                                                   if m is not None and usable else None),
            "within_frame_quantile_contrast_eroded_2px":(float((c-q10)/span)
                                                        if c is not None and usable else None),
            "physical_facet_correspondence":"not_established",
            "normalization_calibrated":False,
            "support_pixel_partition_exclusive":False,
        })
    return {
        "source_index":transfer["source_index"],
        "source_phase_deg":transfer.get("rotation_phase_deg"),
        "frame_stone_valid_pixel_count":int(region_mask.sum()),
        "frame_stone_brightness_p10":q10,
        "frame_stone_brightness_p50":q50,
        "frame_stone_brightness_p90":q90,
        "quantile_span":span,
        "contrast_proxy_available":usable,
        "entities":rows,
    }


def _finite(values):
    return [float(x) for x in values if x is not None and np.isfinite(x)]


def _amplitude(values):
    v=_finite(values)
    return float(max(v)-min(v)) if len(v)>=2 else None


def _spearman(a,b):
    pairs=[(float(x),float(y)) for x,y in zip(a,b)
           if x is not None and y is not None and np.isfinite(x) and np.isfinite(y)]
    if len(pairs)<4:
        return None
    x,y=np.array(pairs).T
    if np.ptp(x)<1e-9 or np.ptp(y)<1e-9:
        return None
    rho=float(spearmanr(x,y).statistic)
    return rho if np.isfinite(rho) else None


def summarize(certificate,frames,frozen_digests,face_selection):
    if not frames:
        raise ValueError("no preselected frames to summarize")
    ids=[row["semantic_id"] for row in frames[0]["entities"]]
    if any([v["semantic_id"] for v in f["entities"]]!=ids for f in frames):
        raise ValueError("cannot summarize changing semantic IDs")
    entity_stats={}
    for i,semantic_id in enumerate(ids):
        entries=[frame["entities"][i] for frame in frames]
        raw=[e["raw_full_mean"] for e in entries]
        adj=[e["within_frame_quantile_contrast_full"] for e in entries]
        core=[e["raw_eroded_2px_mean"] for e in entries]
        differences=_finite(e["raw_eroded_minus_full"] for e in entries)
        paired=sum(x is not None and y is not None for x,y in zip(raw,core))
        entity_stats[semantic_id]={
            "sampled_frames":sum(x is not None for x in raw),
            "paired_core_frames":paired,
            "mean_abs_support_erosion_delta":(float(np.mean(np.abs(differences)))
                                              if differences else None),
            "max_abs_support_erosion_delta":(float(max(abs(x) for x in differences))
                                             if differences else None),
            "raw_amplitude":_amplitude(raw),
            "within_frame_contrast_amplitude":_amplitude(adj),
            "rank_correlation_full_vs_eroded":_spearman(raw,core),
            "rank_correlation_raw_vs_contrast_proxy":_spearman(raw,adj),
        }
    return {
        "schema_version":SCHEMA,
        "policy":POLICY,
        "status":"descriptive_sensitivity_not_physical_optics_validation",
        "certificate":certificate,
        "face_status":face_selection,
        "frozen_geometry_artifact_sha256":frozen_digests,
        "source_indices":[x["source_index"] for x in frames],
        "frame_count":len(frames),
        "entity_count":len(ids),
        "scaffold_refitted":False,
        "optical_quality_score":None,
        "frame_reference_variation":{
            "p10_amplitude":_amplitude([x["frame_stone_brightness_p10"] for x in frames]),
            "p50_amplitude":_amplitude([x["frame_stone_brightness_p50"] for x in frames]),
            "p90_amplitude":_amplitude([x["frame_stone_brightness_p90"] for x in frames]),
            "quantile_span_amplitude":_amplitude([x["quantile_span"] for x in frames]),
            "quantile_available_frames":sum(x["contrast_proxy_available"] for x in frames),
        },
        "entity_sensitivity":entity_stats,
        "frames":frames,
    }


def render(report,filename):
    """Paired raw vs within-frame reference charts, with eroded lines dashed."""
    width,height=1130,785
    image=Image.new("RGB",(width,height),(252,253,254))
    d=ImageDraw.Draw(image)
    title=report["certificate"]+" | fixed semantic supports: exposure proxy and polygon sensitivity"
    d.text((34,14),title,fill=(15,26,40))
    d.text((34,32),"Relative q10-q90 is within-frame; NOT vendor-calibrated. 2px erosion uses the SAME frozen geometry.",fill=(66,75,88))
    d.text((34,49),"Solid: full support. Faint/dotted: 2px inner support. Gaps/nulls never interpolated.",fill=(66,75,88))
    frame_count=len(report["frames"])
    plot_specs=(("raw_full_mean","raw_eroded_2px_mean","Raw measurement-frame brightness",.0,1.0),
                ("within_frame_quantile_contrast_full","within_frame_quantile_contrast_eroded_2px",
                 "Within-frame stone q10-q90 contrast index (no clipping)",None,None))
    for panel,(key,core_key,label,low,high) in enumerate(plot_specs):
        x0,y0,w,h=80,100+panel*305,995,215
        vals=_finite(e[key] for f in report["frames"] for e in f["entities"])
        vals+=_finite(e[core_key] for f in report["frames"] for e in f["entities"])
        if low is None:
            low=min(vals) if vals else 0.0
            high=max(vals) if vals else 1.0
            pad=max(0.025,(high-low)*.08)
            low-=pad;high+=pad
        d.text((x0,y0-21),label,fill=(34,43,57))
        for yfrac in (0,.25,.5,.75,1):
            y=y0+h*(1-yfrac)
            val=low+(high-low)*yfrac
            d.line((x0,y,x0+w,y),fill=(225,229,234),width=1)
            d.text((16,y-5),f"{val:.2f}",fill=(67,80,91))
        def loc(i,v):
            return (x0+w*i/max(1,frame_count-1),
                    y0+h*(1-(float(v)-low)/(high-low)))
        for i,frame in enumerate(report["frames"]):
            x=loc(i,low)[0]
            d.line((x,y0,x,y0+h),fill=(237,239,243),width=1)
            d.text((x-9,y0+h+7),str(frame["source_index"]),fill=(75,78,87))
        for ident,color in zip(PLOT_ENTITIES,PLOT_COLORS):
            for field,style in ((core_key,"faint"),(key,"full")):
                previous=None
                for i,frame in enumerate(report["frames"]):
                    entry=next((x for x in frame["entities"] if x["semantic_id"]==ident),None)
                    val=entry and entry[field]
                    if val is None:
                        previous=None
                        continue
                    pos=loc(i,val)
                    ink=tuple((x+235)//2 for x in color) if style=="faint" else color
                    if previous is not None:
                        if style=="full":
                            d.line((*previous,*pos),fill=ink,width=3)
                        else:
                            for fraction in (0,.32,.64,.96):
                                p1=(previous[0]+(pos[0]-previous[0])*fraction,
                                    previous[1]+(pos[1]-previous[1])*fraction)
                                p2=(previous[0]+(pos[0]-previous[0])*min(fraction+.15,1),
                                    previous[1]+(pos[1]-previous[1])*min(fraction+.15,1))
                                d.line((*p1,*p2),fill=ink,width=2)
                    if style=="full":
                        d.ellipse((pos[0]-3,pos[1]-3,pos[0]+3,pos[1]+3),fill=ink)
                    previous=pos
    for k,(ident,color) in enumerate(zip(PLOT_ENTITIES,PLOT_COLORS)):
        x=110+k*225
        d.line((x,739,x+32,739),fill=color,width=4)
        d.text((x+38,732),ident,fill=(40,45,51))
    if report["face_status"].startswith("unresolved"):
        d.text((82,765),"FACE ROLE UNRESOLVED. Image-plane brightness only; not polished crown-facet light return.",fill=(156,58,41))
    else:
        d.text((82,765),"Likely crown-view by original #73; facet correspondence still NOT established.",fill=(75,82,91))
    image.save(filename)


def save(report,root):
    out=Path(root)
    out.mkdir(parents=True,exist_ok=True)
    (out/"exposure-support-sensitivity.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    render(report,out/"exposure-support-sensitivity.png")
    return report
