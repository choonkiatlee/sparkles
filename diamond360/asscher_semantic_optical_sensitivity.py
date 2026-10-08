"""#92: fixed-pixel exposure and support-zone sensitivity, without geometry refits.

A diagnostic only. Original #89 semantic IDs, gauge, transfer decisions,
polygons and original measurement pixels remain fixed. This module makes
counterfactual changes to *intensity* or raster sampling footprint, never
moves a vertex, adjusts a pose, tunes a cut or estimates polished facets.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_semantic_optical_handoff as handoff
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-fixed-support-photometric-sensitivity/1"
POLICY = {
    "input": "existing_80_registered_measurement_brightness_with_frozen_89_transfers",
    "predeclare_image_variants": {
        "gain_0_85": ["multiplicative_gain_no_clipping_expected", 0.85, 0.0],
        "gain_1_10_clipped": ["multiplicative_gain_clip_0_1", 1.10, 0.0],
        "offset_plus_0_05_clipped": ["additive_offset_clip_0_1", 1.0, 0.05],
    },
    "support_zones": ["nominal_frozen_polygon", "one_pixel_eroded_core",
                      "one_pixel_dilated_capped_to_original_valid_stone"],
    "morphology": "one_pixel_cross_connectivity_4_on_rasterized_polygon_union",
    "normalization": "descriptive_frame_valid_stone_q10_q90_contrast_not_vendor_calibration",
    "zero_contrast": "nullable_no_forced_fallback",
    "exposure_only_stress": "post_canonicalization_not_proof_of_vendor_exposure_invariance",
    "facet_correspondence": "unverified_nonexclusive_image_support",
    "no_geometry_refit": True,
    "no_new_scoring_thresholds": True,
    "no_physical_angles_quality_scores_or_optical_calibration": True,
}
_STENCIL = ndi.generate_binary_structure(2, 1)


def _contrast_reference(image, valid):
    pixels = np.asarray(image, float)[valid]
    if not len(pixels):
        return {"q10":None,"q90":None,"median":None,"saturated_fraction":None,
                "status":"unavailable_no_valid_stone_pixels"}
    q10, q90 = np.quantile(pixels, [0.10,0.90])
    return {
        "q10":round(float(q10),8),
        "q90":round(float(q90),8),
        "median":round(float(np.median(pixels)),8),
        "saturated_fraction":round(float(np.mean(pixels>=0.995)),8),
        "status":"descriptive_valid_stone_brightness_quantiles",
    }


def _relative(mean, frame_ref):
    q10,q90=frame_ref["q10"],frame_ref["q90"]
    if mean is None or q10 is None or (q90-q10)<1e-6:
        return None
    return float((mean-q10)/(q90-q10))


def _polygon_union(scaffold, obs, support_map, points, shape):
    mask=np.zeros(shape,bool)
    for sid in obs["support_ids"]:
        sup=support_map.get(sid)
        if sup is None:
            raise ValueError("archived support ID is not in original scaffold")
        if sup.get("attribution_mode") != "nonexclusive_semantic_support":
            raise ValueError("cannot sample exclusive physical facet attribution")
        coords=[points[key] for key in sup["vertex_ids"]]
        mask |= handoff._mask_polygon(coords,shape)
    return mask


def analyse_frame(scaffold, transfer, brightness, gauge_mask, valid_mask):
    """Every geometry-support rule is first checked by merged #166 sampler."""
    fixed=handoff.sample_fixed_frame(
        scaffold, transfer, brightness, gauge_mask, valid_mask
    )
    base=np.asarray(brightness,float)
    gauge=np.asarray(gauge_mask,bool)
    usable=np.asarray(valid_mask,bool)&gauge
    refs={"nominal":_contrast_reference(base,usable)}
    images={"nominal":base}
    for name,(_description,gain,offset) in POLICY["predeclare_image_variants"].items():
        images[name]=np.clip(base*gain+offset,0,1)
        refs[name]=_contrast_reference(images[name],usable)

    vertices=wireframe._scaffold_points_in_gauge(gauge,scaffold)
    support_map={sup["support_id"]:sup for sup in scaffold["semantic_supports"]}
    entity_rows={x["semantic_id"]:x for x in fixed["entities"]}
    outputs=[]
    for entity_id in sorted(entity_rows):
        row=entity_rows[entity_id]
        entry=transfer["entities"][entity_id]
        obs=scaffold["entity_observations"][entity_id]
        if entry["status"]=="unavailable":
            original=np.zeros(base.shape,bool)
        else:
            original=_polygon_union(
                scaffold,obs,support_map,vertices,base.shape)
        nominal=original&usable
        n=int(nominal.sum())
        if n != row["supported_pixel_count"]:
            raise ValueError("sensitivity sampling differs from frozen nominal support")
        nominal_mean=(float(base[nominal].mean()) if n else None)
        if n and abs(nominal_mean-row["raw_mean_brightness"])>1e-9:
            raise ValueError("nominal brightness differs from #166 baseline")

        core=ndi.binary_erosion(original,structure=_STENCIL)&usable
        expanded=ndi.binary_dilation(original,structure=_STENCIL)&usable
        # Never restore a discarded unavailable source-geometry entry.
        if entry["status"]=="unavailable":
            expanded[:]=False
            core[:]=False

        def masked_mean(img,region):
            return float(img[region].mean()) if region.any() else None
        core_mean=masked_mean(base,core)
        expanded_mean=masked_mean(base,expanded)
        stresses={}
        for name in POLICY["predeclare_image_variants"]:
            v=masked_mean(images[name],nominal)
            stresses[name]={
                "raw_mean":v,
                "delta_from_nominal":None if v is None or nominal_mean is None
                                     else v-nominal_mean,
                "quantile_contrast":_relative(v,refs[name]),
                "delta_contrast_from_nominal":(
                    None if v is None or _relative(nominal_mean,refs["nominal"]) is None
                    or _relative(v,refs[name]) is None
                    else _relative(v,refs[name])-_relative(nominal_mean,refs["nominal"])
                ),
            }

        outputs.append({
            "semantic_id":entity_id,
            "source_index":transfer.get("source_index"),
            "geometry_support_status":row["geometry_support_status"],
            "geometry_confidence":row["geometry_confidence"],
            "physical_facet_correspondence":"not_established",
            "inner_C3_table_identity":("review_not_verified" if entity_id.startswith("C3_")
                                       or entity_id=="TABLE" else None),
            "nominal_pixel_count":n,
            "nominal_raw_mean":nominal_mean,
            "nominal_quantile_contrast":_relative(nominal_mean,refs["nominal"]),
            "core_1px_count":int(core.sum()),
            "core_1px_raw_mean":core_mean,
            "core_1px_delta":None if core_mean is None or nominal_mean is None
                              else core_mean-nominal_mean,
            "expanded_1px_count":int(expanded.sum()),
            "expanded_1px_raw_mean":expanded_mean,
            "expanded_1px_delta":None if expanded_mean is None or nominal_mean is None
                                  else expanded_mean-nominal_mean,
            "counterfactual_exposure":stresses,
        })

    return {
        "schema_version":SCHEMA,
        "source_index":transfer.get("source_index"),
        "rotation_phase_deg":transfer.get("rotation_phase_deg"),
        "semantic_gauge_id":fixed["semantic_gauge_id"],
        "unchanged_scaffold":True,
        "unchanged_transfer_support":True,
        "fixed_geometry_refit_count":0,
        "image_reference":refs,
        "entities":outputs,
    }


def _stats(values):
    usable=np.asarray([v for v in values if v is not None and math.isfinite(v)],float)
    return {
        "samples":int(len(usable)),
        "median_abs":float(np.median(np.abs(usable))) if len(usable) else None,
        "p90_abs":float(np.quantile(np.abs(usable),.9)) if len(usable) else None,
        "max_abs":float(np.max(np.abs(usable))) if len(usable) else None,
    }


def report(frames, certificate, archived_sha256, face_selection):
    """Descriptive, predeclared paired perturbation statistics, not a quality score."""
    if len(frames)<2:
        raise ValueError("at least two separate 360 observations required")
    src=[f["source_index"] for f in frames]
    if len(set(src))!=len(src):
        raise ValueError("source indices are not distinct")
    ids=[r["semantic_id"] for r in frames[0]["entities"]]
    if any([r["semantic_id"] for r in f["entities"]]!=ids for f in frames):
        raise ValueError("fixed semantic identities changed")
    if not all(f["unchanged_scaffold"] and f["unchanged_transfer_support"]
               and f["fixed_geometry_refit_count"]==0 for f in frames):
        raise ValueError("refit or transfer reassignment detected")
    entities={}
    for ident in ids:
        rows=[next(r for r in f["entities"] if r["semantic_id"]==ident)
              for f in frames]
        nom=[r["nominal_raw_mean"] for r in rows]
        nomgood=[v for v in nom if v is not None]
        variations={
            "core_1px_from_nominal":_stats(r["core_1px_delta"] for r in rows),
            "expanded_1px_from_nominal":_stats(r["expanded_1px_delta"] for r in rows),
        }
        for name in POLICY["predeclare_image_variants"]:
            variations[name+"_raw_from_nominal"]=_stats(
                r["counterfactual_exposure"][name]["delta_from_nominal"] for r in rows
            )
            variations[name+"_contrast_from_nominal"]=_stats(
                r["counterfactual_exposure"][name]["delta_contrast_from_nominal"] for r in rows
            )
        contrast=[r["nominal_quantile_contrast"] for r in rows]
        cg=[x for x in contrast if x is not None]
        entities[ident]={
            "observed_frames":len(nomgood),
            "missing_frames":len(rows)-len(nomgood),
            "nominal_raw_min":float(min(nomgood)) if nomgood else None,
            "nominal_raw_max":float(max(nomgood)) if nomgood else None,
            "nominal_raw_range":float(max(nomgood)-min(nomgood)) if nomgood else None,
            "nominal_contrast_range":float(max(cg)-min(cg)) if cg else None,
            "perturbation_stats":variations,
            "facet_correspondence":"unavailable_not_derived_from_projected_support",
        }
    return {
        "schema_version":SCHEMA,
        "policy":POLICY,
        "status":"descriptive_sensitivity_no_method_selection_or_quality_score",
        "certificate":certificate,
        "frozen_geometry_artifact_hashes":archived_sha256,
        "archived_face_role":face_selection,
        "source_indices":src,
        "semantic_ids":ids,
        "frames":frames,
        "entity_summary":entities,
        "no_refit":True,
        "physical_facet_angles_available":False,
        "vendor_cross_source_calibration_established":False,
    }


def write_report(frames, certificate, archived_sha256, face_selection, output):
    result=report(frames,certificate,archived_sha256,face_selection)
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return result


def draw_perturbation_summary(result, destination):
    """Per-family paired sensitivity under fixed source pixels: not angle fit."""
    family=("C1_N","C2_N","C3_N","P1_N","P2_N","P3_N")
    opts=("core_1px_from_nominal","expanded_1px_from_nominal",
          "gain_1_10_clipped_raw_from_nominal")
    palette=((23,146,108),(235,142,45),(133,90,194))
    image=Image.new("RGB",(1090,490),(250,251,252))
    d=ImageDraw.Draw(image)
    d.text((20,16),result["certificate"]+" | FIXED semantic support sensitivity",fill=(23,32,43))
    d.text((20,37),"Median |brightness difference|, original pixels vs support-zone and exposure changes.",fill=(69,78,89))
    d.text((20,57),"C3/table identities unresolved. Contrast normalisation is descriptive, not vendor calibration.",fill=(112,75,64))
    y0=102
    valid=[result["entity_summary"][e]["perturbation_stats"][o]["median_abs"]
           for e in family for o in opts]
    maxval=max([v for v in valid if v is not None]+[.005])
    maxval=maxval*1.12
    left,right=208,980
    for i,ident in enumerate(family):
        yy=y0+i*51
        d.text((26,yy+7),ident,fill=(30,42,54))
        for j,key in enumerate(opts):
            v=result["entity_summary"][ident]["perturbation_stats"][key]["median_abs"]
            if v is None: continue
            start=yy+7+9*j
            end=left+(right-left)*v/maxval
            d.rectangle((left,start,end,start+7),fill=palette[j])
    foot=426
    for j,name in enumerate(("1px eroded core","1px expanded zone","clipped +10% brightness")):
        x=25+j*345
        d.rectangle((x,foot,x+15,foot+12),fill=palette[j])
        d.text((x+24,foot-1),name,fill=(47,56,68))
    d.text((25,461),"All masks overlap if needed; source region membership and #89 semantics are unchanged.",fill=(77,83,91))
    image.save(destination)
