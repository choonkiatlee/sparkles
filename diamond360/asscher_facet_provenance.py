"""#123: explicit physical silhouette versus unresolved optical contrast support.

Consumes *archived* #146/#162 original-RGB observational diagnostics. Nothing
here changes the #96 estimator, infers facet geometry, or labels a virtual
facet from an RGB edge without independent physical corroboration.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

from . import asscher_geometry_validation as validation

SCHEMA = "diamond360-asscher-physical-optical-provenance/1"
POLICY = {
    "schema_version": SCHEMA,
    "supported_physical_geometry": "GIRDLE_OUTLINE_silhouette_only",
    "unproven_inner_physical_boundaries": [
        "C1_C2", "C2_C3", "C3_TABLE",
    ],
    "optical_input": "source_camera_RGB_observed_lines_and_junction_candidates",
    "optical_facet_classification": "unresolved_never_auto_virtual_or_polished",
    "multi_view_correspondence": (
        "all-pairs proximity diagnostics only; agreement across frames "
        "is not proof of polished-facet correspondence"
    ),
    "matched_offset_tolerance": .025,
    "status_on_ambiguous_inner_features": "unavailable",
    "no_synthetic_missing_edges": True,
    "no_estimator_change": True,
    "no_quality_score_or_3D_angle": True,
}


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _polygon(points):
    if not isinstance(points, list) or len(points) != 8:
        raise ValueError("eight original outer vertices required")
    if any(not isinstance(p, list) or len(p) != 2
           or not all(_finite(x) for x in p) for p in points):
        raise ValueError("invalid frozen physical outline coordinates")
    return points


def _index_rows(rows, label):
    found={}
    for row in rows:
        index=row.get("source_index")
        if type(index) is not int or index in found:
            raise ValueError(f"{label} contains invalid or duplicate source index")
        found[index]=row
    return found


def require_physical_support(observation):
    """Fail closed: an interior optical edge can NEVER be silently upgraded."""
    if (observation.get("provenance_class") != "physical_silhouette"
            or observation.get("semantic_id") != "GIRDLE_OUTLINE"
            or observation.get("evidence_kind") != "observed_external_contour"
            or observation.get("status") != "observed"):
        raise ValueError(
            "physical geometry requires the separately observed external "
            "GIRDLE_OUTLINE; interior RGB lines/junctions are unverified"
        )
    return True


def pairwise_support(observations, selected):
    """Pairwise *proximity* only; no transitive tracking or physical IDs.

    Returns all frame pairs for which at least one segment offset pair
    overlaps in the already-frozen silhouette-normalized gauge. A repeated
    reflection can also satisfy this, so no label is assigned.
    """
    observed={i: [] for i in selected}
    for row in observations:
        observed[row["source_index"]].append(row["outer_distance_fraction"])
    pairs=[]
    for i,j in itertools.combinations(selected,2):
        before,after=observed[i],observed[j]
        if not before or not after:
            continue
        minimum=min(abs(a-b) for a in before for b in after)
        pairs.append({
            "source_a":i,
            "source_b":j,
            "minimum_offset_separation":float(minimum),
            "close_candidate_pair":bool(
                minimum<=POLICY["matched_offset_tolerance"]
            ),
        })
    return {
        "observed_source_count":sum(bool(v) for v in observed.values()),
        "tested_source_pair_count":len(pairs),
        "close_pair_count":sum(v["close_candidate_pair"] for v in pairs),
        "pairs":pairs,
        "interpretation":"contrast-position similarity only, physical identity not established",
    }


def build_stone_record(lines, junctions):
    """Merge independent source-RGB evidence while preserving provenance.

    A previous contract accepted input diagnostic claims without checking
    whether they had already promoted an optical edge or polygon into
    purported physical geometry. Reject such upstream claims explicitly.
    """
    if lines.get("original_outer_method_unchanged") is not True:
        raise ValueError("frozen observed outer silhouette provenance required")
    if lines.get("physical_facet_claim") is not False:
        raise ValueError("RGB line input cannot claim physical facet identity")
    if junctions.get("production_estimator_changed") is not False:
        raise ValueError("junction input must preserve frozen estimator")
    if junctions.get("physical_facet_identity_verified") is not False:
        raise ValueError("junction input cannot assert physical facet identity")
    certificate=lines.get("certificate")
    if not certificate or certificate != junctions.get("certificate"):
        raise ValueError("line and junction certificates disagree")
    selected=lines.get("selected_source_indices")
    if (not isinstance(selected,list) or len(selected)<3
            or len(set(selected))!=len(selected)
            or any(type(v) is not int for v in selected)
            or selected!=junctions.get("selected_source_indices")):
        raise ValueError("frozen selected views disagree")
    raw_line=_index_rows(lines.get("frames",[]),"line")
    raw_junction=_index_rows(junctions.get("frames",[]),"junction")
    if set(raw_line)!=set(selected) or set(raw_junction)!=set(selected):
        raise ValueError("RGB diagnostic omitted a selected source frame")
    points=_polygon(lines["outer_vertices_topology_order"])
    face=junctions.get("face_identity") or {}
    face_state=face.get("status")
    if face_state not in ("likely_crown","uncertain"):
        raise ValueError("unrecognized crown-facing evidence")
    physical={
        "semantic_id":"GIRDLE_OUTLINE",
        "provenance_class":"physical_silhouette",
        "evidence_kind":"observed_external_contour",
        "status":"observed",
        "topology_vertex_count":8,
        "vertices_image_plane_normalized":points,
        "source_indices":list(selected),
        "coordinate_semantics":"frozen_96_normalized_outer_gauge",
        "interpretation":"observed stone-background boundary, not internal facet labels",
    }
    require_physical_support(physical)
    unavailable=[
        {
            "semantic_id":name,
            "provenance_class":"unavailable_physical_correspondence",
            "status":"unavailable",
            "reason":"no_independent_physical_facet_junction_correspondence",
            "vertices":None,
            "source_indices":list(selected),
        }
        for name in POLICY["unproven_inner_physical_boundaries"]
    ]
    optical=[]
    junction_obs=[]
    for source in selected:
        row=raw_line[source]
        jrow=raw_junction[source]
        raw_sides=row.get("sides") or []
        if len(raw_sides) not in (0,8):
            raise ValueError("partial side-family inventory cannot be matched")
        for sector,side in enumerate(raw_sides):
            if side.get("side")!=sector:
                raise ValueError("line candidate side order changed")
            for rank,candidate in enumerate(side.get("detected_candidates") or []):
                if candidate.get("rendered_segment_policy") != "only_contiguous_observed_RGB_gradient_pixels":
                    raise ValueError("RGB line is not an observed contiguous segment")
                fraction=candidate.get("fraction")
                start,end=(candidate.get("sample_start"),
                           candidate.get("sample_end"))
                if (not _finite(fraction) or not 0<float(fraction)<1
                        or any(not isinstance(p,list) or len(p)!=2
                               or not all(_finite(x) for x in p)
                               for p in (start,end))):
                    raise ValueError("malformed observed RGB segment")
                optical.append({
                    "observation_id":f"src{source:04d}-side{sector}-candidate{rank}",
                    "provenance_class":"optical_image_plane_observation",
                    "feature_kind":"oriented_contrast_line_segment",
                    "source_index":source,
                    "side_orientation_index":sector,
                    "candidate_index":rank,
                    "outer_distance_fraction":float(fraction),
                    "segment_gauge_normalized_xy":[start,end],
                    "contrast_coverage":candidate.get("coverage"),
                    "longest_contiguous_fraction":candidate.get(
                        "longest_contiguous_fraction"),
                    "source_camera_RGB_path":row.get("camera_RGB_QC"),
                    "crown_view_status":face_state,
                    "optical_vs_structural":"unresolved",
                    "physical_facet_correspondence":"not_established",
                    "physical_facet_semantic_id":None,
                })
        graph=jrow.get("junction_evidence") or {}
        if graph.get("physical_facet_identity_verified") is not False:
            raise ValueError("local RGB junction cannot be verified physical")
        if graph.get("polygon") is not None:
            raise ValueError("optical junction polygon cannot claim physical geometry")
        nodes=graph.get("nodes") or []
        valid_line_refs=set()
        for observed_side in raw_sides:
            sector=observed_side["side"]
            for rank in range(len(observed_side.get("detected_candidates") or [])):
                valid_line_refs.add((str(sector),rank))
        for node in nodes:
            refs=node.get("line_candidate_indices") or {}
            if (len(refs)!=2 or
                    any(type(rank) is not int or (sid,rank) not in valid_line_refs
                        for sid,rank in refs.items())):
                raise ValueError("junction references unobserved RGB line segment")
            if (type(node.get("id")) is not int or
                    type(node.get("corner_index")) is not int or
                    not 0<=node["corner_index"]<8):
                raise ValueError("invalid junction identity or corner slot")
            point=node.get("position_gauge_normalized_xy")
            if (not isinstance(point,list) or len(point)!=2
                    or not all(_finite(x) for x in point)):
                raise ValueError("invalid junction image coordinates")
            junction_obs.append({
                "observation_id":f"src{source:04d}-junction{node['id']}",
                "provenance_class":"optical_image_plane_observation",
                "feature_kind":"locally_connected_RGB_gradient_intersection",
                "source_index":source,
                "candidate_corner_slot":node["corner_index"],
                "point_gauge_normalized_xy":point,
                "source_camera_RGB_path":jrow.get("source_camera_QC"),
                "crown_view_status":face_state,
                "optical_vs_structural":"unresolved",
                "physical_facet_correspondence":"not_established",
                "physical_facet_semantic_id":None,
            })

    by_side={}
    for index in range(8):
        relevant=[r for r in optical if r["side_orientation_index"]==index]
        by_side[str(index)]=pairwise_support(relevant,selected)

    return {
        "schema_version":SCHEMA,
        "certificate":certificate,
        "selected_source_indices":list(selected),
        "crown_face_identity":face,
        "physical_geometry":{
            "silhouette":physical,
            "interior_facet_boundaries":unavailable,
            "physical_correspondence_verified":False,
        },
        "optical_appearance":{
            "segments":optical,
            "junction_candidates":junction_obs,
            "frame_provenance":"original_RGB_transformed_to_frozen_sequence_gauge",
            "possible_virtual_or_reflected_facets":True,
            "confirmed_virtual_facet_labels":[],
            "any_physical_facet_labels":False,
        },
        "cross_view_optical_consistency":{
            "per_side":by_side,
            "identity_policy":"proximity_only_no_track_or_physical_facet_claim",
        },
        "counts":{
            "optical_segment_observations":len(optical),
            "optical_junction_observations":len(junction_obs),
            "physical_interior_boundaries_validated":0,
            "physical_silhouette_count":1,
        },
        "no_estimator_change":True,
        "no_optical_to_physical_promotion":True,
    }


def run(line_root,junction_root,output,manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    raw=json.loads(Path(manifest).read_text())
    validation.assert_frozen_benchmark_manifest(raw)
    certificates=[r["certificate"] for r in raw["bundles"]]
    if len(certificates)!=4 or len(set(certificates))!=4:
        raise ValueError("unexpected frozen four-stone certificate set")
    line_root=Path(line_root)
    junction_root=Path(junction_root)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    stones=[]
    for cert in certificates:
        lines=json.loads((line_root/"per-stone"/cert/"line-evidence.json").read_text())
        junctions=json.loads((junction_root/"per-stone"/cert/
                              "junction-evidence.json").read_text())
        result=build_stone_record(lines,junctions)
        destination=output/"per-stone"/cert
        destination.mkdir(parents=True,exist_ok=True)
        (destination/"facet-provenance.json").write_text(
            json.dumps(result,indent=2,allow_nan=False)+"\n")
        stones.append({
            "certificate":cert,
            "counts":result["counts"],
            "crown_face_identity":result["crown_face_identity"]["status"],
            "selected_source_indices":result["selected_source_indices"],
            "physical_interior_correspondence":"unavailable",
            "provenance_path":f"per-stone/{cert}/facet-provenance.json",
        })
    report={
        "schema_version":SCHEMA,"policy":POLICY,
        "frozen_manifest_sha256":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "source_artifacts":{
            "native_RGB_lines":"#146 native-RGB line-evidence",
            "native_RGB_junctions":"#162 observed-only junction-evidence",
        },
        "stones":stones,
        "all_interior_physical_boundaries_unavailable":True,
        "no_estimator_change":True,
    }
    (output/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line-root",type=Path,required=True)
    p.add_argument("--junction-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-manifest",type=Path,
                   default=Path("docs/360/benchmark/source-bundles.json"))
    args=p.parse_args()
    report=run(args.line_root,args.junction_root,args.output,args.source_manifest)
    for stone in report["stones"]:
        print(stone["certificate"],stone["crown_face_identity"],
              stone["counts"],stone["physical_interior_correspondence"])


if __name__=="__main__":
    main()
