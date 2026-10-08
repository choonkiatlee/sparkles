"""#123: Spatial QC atlas of *optical texture* motion, not physical facets.

Reads the immutable #178 original-RGB neighbor-pair results. A common image
translation is reported separately from local residual motion, ambiguous
correlation, search-window-limited shifts, and missing texture. Neither
a large shift nor a colored tile is a verified optical/physical facet.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_validation as validation
from . import asscher_optical_neighbor_motion as neighbor

SCHEMA="diamond360-asscher-optical-motion-atlas/1"
GRID=4
MIN_COMMON_TILES=8
MAX_LOCAL_SHIFT=4
LOCAL_RESIDUAL_TOLERANCE_PX=1.5
REGISTRATION_CAUTION_MASK_IOU=.95
CATEGORIES=(
    "unavailable","ambiguous","search_window_limited",
    "no_common_reference","shared_image_shift","local_residual_shift"
)
COLORS={
    "unavailable":(92,92,99),
    "ambiguous":(193,149,53),
    "search_window_limited":(152,104,184),
    "no_common_reference":(94,124,155),
    "shared_image_shift":(47,124,179),
    "local_residual_shift":(208,96,66),
}
POLICY={
    "schema_version":SCHEMA,
    "input":neighbor.SCHEMA,
    "input_is_immutable_archived_original_camera_RGB_178":True,
    "grid_size":GRID,
    "minimum_unclipped_tiles_for_common_shift":MIN_COMMON_TILES,
    "search_window_limit_px":MAX_LOCAL_SHIFT,
    "local_residual_threshold_px":LOCAL_RESIDUAL_TOLERANCE_PX,
    "registration_caution_mask_iou_below":REGISTRATION_CAUTION_MASK_IOU,
    "reference_motion":"pairwise_median_of_unclipped_confident_2D_optical_shifts",
    "physical_facet_identity":"unavailable",
    "virtual_facet_identity":"unclassified",
    "no_facet_labels_or_angle_or_grading":True,
    "no_estimator_change":True,
    "no_source_stress":True,
}


def _finite_number(x):
    return type(x) in (int,float) and math.isfinite(float(x))


def classify_pair(pair):
    """Classify 4x4 optical shifts and preserve every censored observation."""
    if pair.get("physical_facet_semantic_ids") is not None:
        raise ValueError("physical facet IDs forbidden in optical pair")
    if pair.get("status")!="observed":
        return {
            "status":"unavailable","reason":pair.get("reason","source_pair_unavailable"),
            "tiles":[],"shared_image_shift":None,"confidence_interpretation":"unavailable",
        }
    if pair.get("physical_facet_correspondence")!="unavailable":
        raise ValueError("RGB optical measurements cannot imply physical geometry")
    if not 0 <= float(pair.get("mask_intersection_over_union",-1))<=1:
        raise ValueError("invalid outer silhouette overlap")
    patches=pair.get("patches")
    if not isinstance(patches,list) or len(patches)!=GRID*GRID:
        raise ValueError("missing 4x4 archival patch evidence")
    positions=set()
    unclipped=[]
    for patch in patches:
        grid=patch.get("grid")
        if (not isinstance(grid,list) or len(grid)!=2 or
                any(type(x) is not int or x<0 or x>=GRID for x in grid)):
            raise ValueError("invalid 4x4 tile identity")
        key=tuple(grid)
        if key in positions:
            raise ValueError("duplicate tile index")
        positions.add(key)
        if patch.get("physical_facet_semantic_id") is not None:
            raise ValueError("patch claims physical polished facet identity")
        status=patch.get("status")
        if status not in ("measured","ambiguous","unavailable"):
            raise ValueError("unknown optical patch status")
        if status!="measured":
            if patch.get("apparent_shift_gauge_px") is not None:
                raise ValueError("unmeasured patch cannot supply motion vector")
            continue
        shift=patch.get("apparent_shift_gauge_px")
        if not isinstance(shift,dict):
            raise ValueError("missing measured optical shift")
        dx,dy=shift.get("dx"),shift.get("dy")
        if (type(dx) is not int or type(dy) is not int or
                abs(dx)>MAX_LOCAL_SHIFT or abs(dy)>MAX_LOCAL_SHIFT):
            raise ValueError("invalid search-window shift")
        if not all(_finite_number(patch.get(k)) for k in
                   ("best_gradient_ncc","best_vs_nonlocal_peak_margin")):
            raise ValueError("unverified correlation observation")
        if abs(dx)<MAX_LOCAL_SHIFT and abs(dy)<MAX_LOCAL_SHIFT:
            unclipped.append((dx,dy))

    reference=(np.median(np.asarray(unclipped,float),axis=0)
               if len(unclipped)>=MIN_COMMON_TILES else None)
    tiles=[]
    for patch in patches:
        status=patch["status"]
        row={"grid":patch["grid"],"status":None,
             "measured_shift":patch.get("apparent_shift_gauge_px"),
             "physical_facet_semantic_id":None}
        if status=="unavailable":
            row["status"]="unavailable"
        elif status=="ambiguous":
            row["status"]="ambiguous"
        else:
            shift=patch["apparent_shift_gauge_px"]
            v=np.array([shift["dx"],shift["dy"]],float)
            if np.any(np.abs(v)>=MAX_LOCAL_SHIFT):
                row["status"]="search_window_limited"
            elif reference is None:
                row["status"]="no_common_reference"
            else:
                distance=float(np.linalg.norm(v-reference))
                row["residual_from_shared_shift_px"]=distance
                row["status"]=(
                    "local_residual_shift" if distance>LOCAL_RESIDUAL_TOLERANCE_PX
                    else "shared_image_shift")
        tiles.append(row)
    tiles.sort(key=lambda x:tuple(x["grid"]))
    counts={c:sum(t["status"]==c for t in tiles) for c in CATEGORIES}
    if sum(counts.values())!=GRID*GRID:
        raise AssertionError("tile classification incomplete")
    return {
        "status":"observational_only",
        "shared_image_shift":(
            {"dx":float(reference[0]),"dy":float(reference[1])}
            if reference is not None else None),
        "unclipped_reference_tile_count":len(unclipped),
        "registration_caution":(
            float(pair["mask_intersection_over_union"])<
            REGISTRATION_CAUTION_MASK_IOU),
        "mask_intersection_over_union":float(pair["mask_intersection_over_union"]),
        "tiles":tiles,
        "counts":counts,
        "interpretation":"relative_registered_RGB_optical_texture_only_not_facets",
        "physical_facet_identity_verified":False,
        "not_a_quality_score":True,
    }


def aggregate_maps(pairs):
    """Per-grid frequency of *observational statuses*, not per-facet behavior."""
    results=[]
    for y in range(GRID):
        for x in range(GRID):
            rows=[t for p in pairs for t in p.get("tiles",[])
                  if t["grid"]==[y,x]]
            counts={s:sum(t["status"]==s for t in rows) for s in CATEGORIES}
            valid=sum(counts.values())
            reference_valid=(
                counts["local_residual_shift"]+counts["shared_image_shift"]
            )
            results.append({
                "grid":[y,x],"paired_frame_observations":valid,
                "statuses":counts,
                "local_residual_fraction_when_reference_valid":(
                    counts["local_residual_shift"]/reference_valid
                    if reference_valid else None),
                "search_window_limited_fraction":(
                    counts["search_window_limited"]/valid if valid else None),
                "unresolved_fraction":(
                    (counts["unavailable"]+counts["ambiguous"]+
                     counts["no_common_reference"])/valid if valid else None),
                "facet_semantic_id":None,
            })
    return results


def render_atlas(result,*,title,aggregate=False):
    """Transparent-to-interpret status heatmap; never draw a facet polygon."""
    tile=78
    pad=12
    header=92
    footer=132
    width=GRID*tile+2*pad
    canvas=Image.new("RGB",(width,header+GRID*tile+footer),(17,20,24))
    draw=ImageDraw.Draw(canvas)
    draw.text((pad,10),title[:48],fill=(255,255,255))
    draw.text((pad,30),"OPTICAL TEXTURE ONLY - no physical facets",
              fill=(218,220,222))
    if not aggregate:
        ref=result.get("shared_image_shift")
        legend=("Shared dx/dy: unavailable" if ref is None else
                f"Shared dx={ref['dx']:.1f}, dy={ref['dy']:.1f} gauge px")
        draw.text((pad,52),legend,fill=(188,207,234))
        if result.get("registration_caution"):
            draw.text((pad,70),"LOW OUTLINE IoU: registration caution",
                      fill=(241,179,95))
    else:
        draw.text((pad,52),"Tile color = most frequent evidence category",
                  fill=(188,207,234))
    rows=result["tiles"] if not aggregate else result
    for item in rows:
        y,x=item["grid"]
        if aggregate:
            obs=item["paired_frame_observations"]
            count=item["statuses"]
            winner=max(CATEGORIES,key=lambda s:(count[s],-CATEGORIES.index(s))) if obs else "unavailable"
            text_value=f"{count[winner]}/{obs}"
            status=winner
        else:
            status=item["status"]
            shift=item.get("measured_shift")
            text_value=(f"{shift['dx']:+d},{shift['dy']:+d}"
                        if shift is not None else "—")
        left=pad+x*tile
        top=header+y*tile
        color=COLORS[status]
        draw.rectangle((left+2,top+2,left+tile-2,top+tile-2),
                       fill=color,outline=(205,205,209),width=1)
        draw.text((left+7,top+10),f"r{y} c{x}",fill=(255,255,255))
        draw.text((left+7,top+42),text_value,fill=(255,255,255))
    labels=[
        ("gray","unavailable"),("gold","ambiguous"),
        ("violet","shift at ±4 px limit"),("slate","no common shift"),
        ("blue","shared image shift"),("orange","localized residual"),
    ]
    for i,(nickname,label) in enumerate(labels):
        code=CATEGORIES[i]
        x=pad+(i%2)*int(width/2)
        y=header+GRID*tile+12+(i//2)*29
        draw.rectangle((x,y,x+12,y+12),fill=COLORS[code])
        draw.text((x+18,y),label,fill=(233,233,233))
    draw.text((pad,header+GRID*tile+103),"Research QC only; never physical identity",
              fill=(205,207,210))
    return canvas


def _panel(original,atlas,title):
    original=original.convert("RGB")
    max_width=1220
    if original.width>max_width:
        factor=max_width/original.width
        original=original.resize(
            (max_width,max(1,int(original.height*factor))),
            Image.Resampling.LANCZOS)
    height=max(original.height,atlas.height)
    out=Image.new("RGB",(original.width+atlas.width+9,height),(20,20,20))
    out.paste(original,(0,0))
    out.paste(atlas,(original.width+9,0))
    return out


def build_stone(source_root,output,cert,*,expected_anchor=None):
    source_root=Path(source_root)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    record=json.loads(
        (source_root/"per-stone"/cert/"optical-neighbor-motion.json").read_text())
    if record.get("certificate")!=cert or record.get("production_estimator_changed") is not False:
        raise ValueError("source record/estimator provenance incorrect")
    if record.get("physical_facet_identity")!="not_established":
        raise ValueError("source claims physical facets")
    anchors=record.get("frozen_anchor_source_indices")
    if expected_anchor is not None and anchors!=expected_anchor:
        raise ValueError("frozen #96 anchor mismatch")
    face=record.get("face_identity",{})
    if face.get("status") not in ("likely_crown","uncertain"):
        raise ValueError("crown face status missing")
    pairs=[]
    previews=[]
    indices=set()
    for item in record["pairs"]:
        positions=item.get("positions")
        if (not isinstance(positions,list) or len(positions)!=2 or
                not all(type(x) is int and 0<=x<256 for x in positions)
                or (positions[1]-positions[0])%256!=1):
            raise ValueError("not an adjacent original 360 pair")
        identity=tuple(positions)
        if identity in indices:
            raise ValueError("duplicate adjacent pair")
        indices.add(identity)
        result=classify_pair(item)
        result["positions"]=positions
        result["source_indices"]=item.get("source_indices")
        result["face_identity"]=item.get("face_identity")
        result["raw_median_luminance_ratio_b_over_a"]=item.get(
            "raw_median_luminance_ratio_b_over_a")
        result["median_gain_normalized_abs_change"]=item.get(
            "median_gain_normalized_abs_change")
        qc=item.get("camera_RGB_QC")
        if result["status"]=="observational_only" and qc:
            src=source_root/"per-stone"/cert/qc
            if not src.is_file():
                raise ValueError("archived RGB original pair preview missing")
            title=f"{cert} original neighbors {positions[0]} -> {positions[1]}"
            atlas=render_atlas(result,title=title)
            name=f"optical-atlas-{positions[0]:04d}-{positions[1]:04d}.png"
            atlas.save(output/name)
            pair_name=f"RGB-plus-atlas-{positions[0]:04d}-{positions[1]:04d}.jpg"
            original=Image.open(src)
            rendered=_panel(original,atlas,title)
            rendered.save(output/pair_name,quality=91)
            thumb=rendered.copy()
            thumb.thumbnail((1550,590),Image.Resampling.LANCZOS)
            previews.append(thumb)
            result["atlas_QC"]=name
            result["RGB_plus_atlas_QC"]=pair_name
        pairs.append(result)
    aggregate=aggregate_maps(pairs)
    summary={
        "schema_version":SCHEMA,"certificate":cert,
        "frozen_anchor_source_indices":anchors,
        "face_identity":face,
        "input_pair_count":len(record["pairs"]),
        "mapped_pair_count":sum(x["status"]=="observational_only" for x in pairs),
        "pairs":pairs,"aggregate_tile_status":aggregate,
        "source_run":"#178 immutable original-camera RGB pairs",
        "no_physical_facet_labels":True,
        "no_estimator_change":True,
    }
    render_atlas(aggregate,title=f"{cert} - spatial evidence frequency",
                 aggregate=True).save(output/"aggregate-optical-evidence-atlas.png")
    if previews:
        from . import asscher_wireframe as wireframe
        wireframe._contact_sheet(
            previews,output/"original-RGB-optical-atlas-contact-sheet.jpg",
            columns=1
        )
    (output/"optical-motion-atlas.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n")
    return summary


def run_archive(source_root,output):
    src=Path(source_root)
    original=json.loads((src/"summary.json").read_text())
    if (original.get("schema_version")!=neighbor.SCHEMA
            or original.get("frozen_manifest_canonical_sha256")
            !=validation.BENCHMARK_MANIFEST_CANONICAL_SHA256
            or original.get("no_physical_facet_ids") is not True
            or original.get("no_estimator_change") is not True
            or len(original.get("stones",[]))!=4):
        raise ValueError("source is not frozen #178 optical-only four-stone evidence")
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for stone in original["stones"]:
        cert=stone["certificate"]
        data=build_stone(src,output/"per-stone"/cert,cert,
                         expected_anchor=stone["frozen_anchor_source_indices"])
        totals={s:sum(p["counts"][s] for p in data["pairs"] if "counts" in p)
                for s in CATEGORIES}
        rows.append({
            "certificate":cert,"face_identity":data["face_identity"],
            "frozen_anchor_source_indices":data["frozen_anchor_source_indices"],
            "mapped_pair_count":data["mapped_pair_count"],
            "tile_status_totals":totals,
            "pairs_with_shared_shift":sum(p.get("shared_image_shift") is not None
                                           for p in data["pairs"]),
            "pairs_with_registration_caution":sum(
                p.get("registration_caution",False) for p in data["pairs"]),
            "RGB_contact_sheet":(
                f"per-stone/{cert}/original-RGB-optical-atlas-contact-sheet.jpg"
                if data["mapped_pair_count"] else None),
        })
    result={
        "schema_version":SCHEMA,"policy":POLICY,
        "frozen_manifest_sha256":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":rows,
        "physical_facet_correspondence":"unavailable",
        "not_a_quality_score":True,
        "production_estimator_unchanged":True,
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    report=run_archive(a.source_root,a.output)
    for row in report["stones"]:
        print(row["certificate"],"face",row["face_identity"]["status"],
              "mapped",row["mapped_pair_count"],"tiles",
              row["tile_status_totals"],"shared",
              row["pairs_with_shared_shift"],"IoU cautions",
              row["pairs_with_registration_caution"])


if __name__=="__main__":
    main()
