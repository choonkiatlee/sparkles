"""#123: audit registration/overlap confounding of optical appearance change.

Read-only analysis of #178's immutable neighbor RGB diagnostics. Does not
estimate a physical facet, correct an appearance measure, or infer causality.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from . import asscher_geometry_validation as validation
from . import asscher_optical_neighbor_motion as motion

SCHEMA="diamond360-asscher-optical-registration-confounds/1"
POLICY={
    "schema_version":SCHEMA,
    "source_schema":motion.SCHEMA,
    "overlap_thresholds":{"low_below":.95,"high_from":.98},
    "local_shift_confidence":{"low_below":.50,"high_from":.75},
    "tile_count":16,
    "pairwise_comparison":"descriptive_within_stone_no_global_quality_ranking",
    "minimum_pairs_for_spearman":5,
    "reported_correlation":"association_only_not_causal_camera_registration_estimate",
    "registered_texture_shifts":"apparent_motion_not_physical_or_virtual_facet_identity",
    "source":"immutable_successful_178_original_camera_RGB_artifact",
    "no_facet_geometry_or_quality_inference":True,
    "no_production_or_92_handoff_change":True,
    "no_source_stress":True,
}


def _finite_number(value,label,*,lower=None,upper=None):
    if type(value) not in (int,float) or not math.isfinite(float(value)):
        raise ValueError(f"invalid {label}: require finite numeric value")
    value=float(value)
    if (lower is not None and value<lower) or (upper is not None and value>upper):
        raise ValueError(f"invalid {label}: out of domain")
    return value


def _status_with_threshold(value,low,high):
    return ("low" if value<low else "high" if value>=high else "intermediate")


def analyze_pair(row,*,source_count=256):
    """Two *separate* axes: silhouette overlap and optical matching ambiguity."""
    p=row.get("positions")
    src=row.get("source_indices")
    if (not isinstance(p,list) or not isinstance(src,list)
            or len(p)!=2 or len(src)!=2
            or any(type(x) is not int for x in p+src)):
        raise ValueError("missing adjacent original frame provenance")
    if (p[1]-p[0])%source_count!=1:
        raise ValueError("nonadjacent ordinal source pair")
    if row.get("physical_facet_semantic_ids") is not None:
        raise ValueError("source claims physical facet ID")
    result={
        "source_indices":list(src),
        "positions":list(p),
        "status":row.get("status"),
        "face_identity":row.get("face_identity"),
        "facet_identity":"unavailable",
        "physical_interior_geometry":"unavailable",
    }
    if row.get("status")!="observed":
        if row.get("status")!="unavailable":
            raise ValueError("unrecognized pair status")
        result["reason"]=row.get("reason") or "unavailable"
        result["overlap_class"]="unavailable"
        result["local_match_class"]="unavailable"
        return result
    if row.get("physical_facet_correspondence")!="unavailable":
        raise ValueError("optical pair cannot assert verified physical correspondence")
    overlap=_finite_number(row.get("mask_intersection_over_union"),
                           "outer silhouette overlap",lower=0.,upper=1.)
    change=_finite_number(row.get("median_gain_normalized_abs_change"),
                          "normalized appearance difference",lower=0.)
    p90=_finite_number(row.get("p90_gain_normalized_abs_change"),
                       "p90 appearance difference",lower=0.)
    if p90+1e-12<change:
        raise ValueError("appearance quantiles inconsistent")
    gain=_finite_number(row.get("raw_median_luminance_ratio_b_over_a"),
                        "raw gain ratio",lower=1e-10)
    patches=row.get("patches")
    if not isinstance(patches,list) or len(patches)!=POLICY["tile_count"]:
        raise ValueError("expected the same predeclared 4x4 patch grid")
    seen=set()
    displacements=[]
    counts=Counter()
    for item in patches:
        cell=item.get("grid")
        if (not isinstance(cell,list) or len(cell)!=2 or
                any(type(x) is not int or not 0<=x<4 for x in cell) or
                tuple(cell) in seen):
            raise ValueError("missing/duplicate local patch grid identity")
        seen.add(tuple(cell))
        if item.get("physical_facet_semantic_id") is not None:
            raise ValueError("patch attempts optical-to-physical promotion")
        status=item.get("status")
        if status not in ("measured","ambiguous","unavailable"):
            raise ValueError("invalid local match status")
        counts[status]+=1
        shift=item.get("apparent_shift_gauge_px")
        if status=="measured":
            if not isinstance(shift,dict):
                raise ValueError("missing measured optical shift")
            dx,dy=shift.get("dx"),shift.get("dy")
            if (type(dx) is not int or type(dy) is not int or
                    max(abs(dx),abs(dy))>4):
                raise ValueError("apparent local shift outside fixed search")
            displacements.append((dx,dy))
        elif shift is not None:
            raise ValueError("uncertain tile cannot have a measured shift")
    if (counts["measured"]!=row.get("measured_optical_shift_tile_count")
        or counts["ambiguous"]!=row.get("ambiguous_tile_count")
        or counts["unavailable"]!=row.get("unavailable_tile_count")):
        raise ValueError("saved patch-status totals disagree")
    certainty=counts["measured"]/len(patches)
    common=Counter(displacements).most_common(1)
    modal_shift=common[0][0] if common else None
    coherence=common[0][1]/len(displacements) if common else None
    result.update({
        "silhouette_overlap_iou":overlap,
        "overlap_class":_status_with_threshold(
            overlap,POLICY["overlap_thresholds"]["low_below"],
            POLICY["overlap_thresholds"]["high_from"]),
        "median_gain_normalized_abs_change":change,
        "p90_gain_normalized_abs_change":p90,
        "raw_luminance_gain_ratio":gain,
        "local_match_class":_status_with_threshold(
            certainty,POLICY["local_shift_confidence"]["low_below"],
            POLICY["local_shift_confidence"]["high_from"]),
        "matched_tile_fraction":certainty,
        "ambiguous_tile_fraction":counts["ambiguous"]/16.,
        "unavailable_tile_fraction":counts["unavailable"]/16.,
        "modal_apparent_shift_gauge_pixels":(
            {"dx":modal_shift[0],"dy":modal_shift[1]}
            if modal_shift is not None else None),
        "exact_modal_shift_fraction_of_measured_tiles":coherence,
        "interpretation":"overlap_and_patch_texture_associations_not_camera_correction_or_facet_motion",
    })
    return result


def _median(items,key):
    values=[x[key] for x in items]
    return float(np.median(values)) if values else None


def summarize_stone(detail):
    if detail.get("schema_version")!=motion.SCHEMA:
        raise ValueError("not the frozen optical neighbor schema")
    if detail.get("production_estimator_changed") is not False:
        raise ValueError("input altered production geometry")
    if detail.get("physical_facet_identity")!="not_established":
        raise ValueError("input claims recovered physical facet identity")
    cert=detail.get("certificate")
    if not isinstance(cert,str) or not cert:
        raise ValueError("missing certificate")
    face=detail.get("face_identity") or {}
    if face.get("status") not in ("likely_crown","uncertain"):
        raise ValueError("crown/view identity missing or claimed confirmed")
    rows=detail.get("pairs")
    if not isinstance(rows,list):
        raise ValueError("missing original adjacent source comparisons")
    pairs=[analyze_pair(x) for x in rows]
    if len({tuple(x["positions"]) for x in pairs})!=len(pairs):
        raise ValueError("duplicate camera-RGB pair")
    if any(p["face_identity"]!=face["status"] for p in pairs):
        raise ValueError("pair-level crown identity does not match stone")
    measured=[p for p in pairs if p["status"]=="observed"]
    if len(measured)!=detail.get("measured_pair_count"):
        raise ValueError("original pair count changed")
    classes=("low","intermediate","high")
    bins={}
    for label in classes:
        selected=[p for p in measured if p["overlap_class"]==label]
        bins[label]={
            "pair_count":len(selected),
            "median_gain_normalized_abs_change":_median(
                selected,"median_gain_normalized_abs_change"),
            "median_ambiguous_tile_fraction":_median(
                selected,"ambiguous_tile_fraction"),
            "median_matched_tile_fraction":_median(
                selected,"matched_tile_fraction"),
        }
    correlation=None
    if len(measured)>=POLICY["minimum_pairs_for_spearman"]:
        x=[p["silhouette_overlap_iou"] for p in measured]
        y=[p["median_gain_normalized_abs_change"] for p in measured]
        if len(set(x))>1 and len(set(y))>1:
            statistic,pvalue=spearmanr(x,y)
            if math.isfinite(float(statistic)) and math.isfinite(float(pvalue)):
                correlation={
                    "statistic":float(statistic),
                    "two_sided_p_value_descriptive_only":float(pvalue),
                    "sample_pairs":len(measured),
                    "caveat":"neighbor_pairs_share_frames_and_are_not_independent_random_samples",
                }
    high,low=bins["high"],bins["low"]
    if high["pair_count"] and low["pair_count"]:
        low_high_contrast={
            "available":True,
            "low_minus_high_overlap_bin_median_change":(
                low["median_gain_normalized_abs_change"]
                -high["median_gain_normalized_abs_change"]),
            "interpretation":"association_only_not_proof_of_registration_causality",
        }
    else:
        low_high_contrast={"available":False,
                           "reason":"requires_both_overlap_bins_in_same_stone"}
    return {
        "schema_version":SCHEMA,
        "certificate":cert,
        "face_identity":face,
        "selected_anchor_source_indices":detail.get("frozen_anchor_source_indices"),
        "pair_count":len(pairs),
        "measured_pair_count":len(measured),
        "overlap_bins":bins,
        "within_stone_spearman_overlap_vs_appearance_change":correlation,
        "low_vs_high_overlap_contrast":low_high_contrast,
        "pairs":pairs,
        "physical_facet_correspondence":"unavailable",
        "no_camera_registration_correction_performed":True,
        "no_quality_score":True,
    }


def run_archive(source_dir,output):
    source_dir=Path(source_dir)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    summary=json.loads((source_dir/"summary.json").read_text())
    if summary.get("schema_version")!=motion.SCHEMA:
        raise ValueError("archive motion schema mismatch")
    if (summary.get("frozen_manifest_canonical_sha256")
            !=validation.BENCHMARK_MANIFEST_CANONICAL_SHA256):
        raise ValueError("archive is not the immutable four-stone cohort")
    if (summary.get("no_physical_facet_ids") is not True or
            summary.get("no_estimator_change") is not True):
        raise ValueError("original optical research claimed a physical facet/estimator revision")
    overview=[]
    original=summary.get("stones") or []
    if len(original)!=4 or len({x["certificate"] for x in original})!=4:
        raise ValueError("expected four frozen stones")
    for metadata in original:
        cert=metadata["certificate"]
        detail=json.loads((source_dir/"per-stone"/cert/"optical-neighbor-motion.json").read_text())
        result=summarize_stone(detail)
        if (result["selected_anchor_source_indices"]
                !=metadata.get("frozen_anchor_source_indices")
                or result["measured_pair_count"]!=metadata["measured_pair_count"]
                or result["face_identity"]!=metadata["face_identity"]):
            raise ValueError("stone metadata or original frozen anchors changed")
        path=output/"per-stone"/cert/"overlap-confound-audit.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
        overview.append({
            "certificate":cert,
            "face_identity":result["face_identity"]["status"],
            "selected_anchor_source_indices":result["selected_anchor_source_indices"],
            "measured_pair_count":result["measured_pair_count"],
            "overlap_bins":result["overlap_bins"],
            "low_vs_high_overlap_contrast":result["low_vs_high_overlap_contrast"],
            "within_stone_spearman_overlap_vs_appearance_change":
                result["within_stone_spearman_overlap_vs_appearance_change"],
            "report_path":f"per-stone/{cert}/overlap-confound-audit.json",
        })
    result={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "frozen_manifest_canonical_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "source_178_schema":motion.SCHEMA,
        "stone_count":len(overview),
        "measured_pair_count":sum(x["measured_pair_count"] for x in overview),
        "stones":overview,
        "hypothesis":"does_silhouette_overlap_co_vary_with_optical_appearance_and_patch_ambiguity",
        "interpretation":"association_only_not_a_causal_registration_adjustment",
        "quality_score":None,
        "physical_facet_identity_claim":False,
        "no_new_rgb_download_or_geometry_fit":True,
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n"
    )
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    result=run_archive(args.source,args.output)
    for item in result["stones"]:
        print(item["certificate"],"crown",item["face_identity"],
              "pairs",item["measured_pair_count"],
              "overlap bin counts",
              {k:v["pair_count"] for k,v in item["overlap_bins"].items()},
              "paired contrast",item["low_vs_high_overlap_contrast"])


if __name__=="__main__":
    main()
