"""#123: fail-closed provenance boundary for Asscher 360 optical evidence.

Inputs are archived #146 RGB contrast-line and #162 junction diagnostics.
No contrast segment, intersection, or repeatable optical feature may be
assigned a physical polished-facet identity by this adapter. The frozen
outer silhouette has separate provenance. This is a research-only seam,
not a 3-D facet or diamond-quality estimator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_geometry_validation as validation
from . import asscher_geometry_rgb_lines as lines
from . import asscher_geometry_junction_graph as graph

SCHEMA = "diamond360-asscher-optical-physical-provenance/1"
INTERIOR_BOUNDARIES = ("C1_C2", "C2_C3", "C3_TABLE")
OPTICAL_CLASS = "image_plane_optical_contrast_candidate"
UNKNOWN_PHYSICAL_CLASS = "physical_correspondence_unavailable"
OUTER_CLASS = "observed_external_silhouette"

POLICY = {
    "schema_version": SCHEMA,
    "input_line_schema": lines.SCHEMA,
    "input_junction_schema": graph.SCHEMA,
    "outer_silhouette": OUTER_CLASS,
    "interior_contrast": OPTICAL_CLASS,
    "interior_physical_correspondence": UNKNOWN_PHYSICAL_CLASS,
    "physical_promotion_policy": "requires independent corroboration_not_supported",
    "cross_view_support": "descriptive_optical_only_not_physical_identity",
    "missing_evidence": "retain_unavailable_without_synthetic_fill",
    "no_physical_facet_semantic_labels_from_image_gradients": True,
    "no_estimator_or_quality_score_change": True,
}


def _positive_int(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {label}: must be nonnegative integer")
    return value


def _point(value, label):
    if (not isinstance(value, (list, tuple)) or len(value) != 2 or
            any(type(x) not in (int, float) or not -10.0 < float(x) < 10.0
                for x in value)):
        raise ValueError(f"invalid {label}: require finite image-plane XY")
    return [float(v) for v in value]


def _require_unverified(payload, key):
    if payload.get(key) is not False:
        raise ValueError(f"source cannot claim verified physical identity: {key}")


def _validate_source_rows(line, junction):
    if not line.get("original_outer_method_unchanged") is True:
        raise ValueError("frozen outer estimator provenance absent")
    if junction.get("production_estimator_changed") is not False:
        raise ValueError("junction diagnostic modified production estimator")
    _require_unverified(junction, "physical_facet_identity_verified")
    if line.get("physical_facet_claim") is not False:
        raise ValueError("line input asserts physical facet identity")
    if line.get("certificate") != junction.get("certificate"):
        raise ValueError("line/junction stone identity mismatch")
    if (line.get("selected_source_indices")
            != junction.get("selected_source_indices")):
        raise ValueError("line/junction frozen view selection mismatch")
    if len(set(line["selected_source_indices"])) != len(line["selected_source_indices"]):
        raise ValueError("duplicate source frame indices")
    lrows={r["source_index"]:r for r in line["frames"]}
    jrows={r["source_index"]:r for r in junction["frames"]}
    if (set(lrows) != set(jrows) or
            set(lrows) != set(line["selected_source_indices"])):
        raise ValueError("line/junction frame provenance mismatch")
    return lrows,jrows


def adapt_stone(line, junction):
    """Produce disjoint optical and physical lanes without inferring identity."""
    lrows,jrows=_validate_source_rows(line,junction)
    outer=line.get("outer_vertices_topology_order")
    if not isinstance(outer,list) or len(outer)!=8:
        raise ValueError("missing eight-vertex independently observed silhouette")
    outer=[_point(v,"outer vertex") for v in outer]
    face=junction.get("face_identity") or {}
    if face.get("status") not in ("likely_crown","uncertain"):
        raise ValueError("unknown crown-role provenance")
    optical=[]
    repeat_counts={str(i):0 for i in range(8)}
    for source_index in line["selected_source_indices"]:
        _positive_int(source_index,"source index")
        lr,jr=lrows[source_index],jrows[source_index]
        if lr.get("source_index") != jr.get("source_index"):
            raise ValueError("source alignment error")
        line_features=[]
        candidates_by_side={}
        for side in lr.get("sides",[]):
            sid=_positive_int(side.get("side"),"side index")
            if sid >= 8 or sid in candidates_by_side:
                raise ValueError("invalid duplicate or out-of-range side")
            candidates=side.get("detected_candidates",[])
            candidates_by_side[sid]=candidates
            if candidates:
                repeat_counts[str(sid)]+=1
            for j,candidate in enumerate(candidates):
                # Preserve actual contiguous *observed* line endpoints.
                if candidate.get("rendered_segment_policy") != "only_contiguous_observed_RGB_gradient_pixels":
                    raise ValueError("line is not bounded by observed RGB evidence")
                fraction=float(candidate["fraction"])
                if not 0.0 < fraction < 1.0:
                    raise ValueError("invalid line coordinate")
                line_features.append({
                    "optical_id":f"{source_index}:side{sid}:line{j}",
                    "feature_type":"contrast_line_segment",
                    "provenance_class":OPTICAL_CLASS,
                    "possible_virtual_or_reflected_facet":True,
                    "facet_semantic_id":None,
                    "physical_correspondence":UNKNOWN_PHYSICAL_CLASS,
                    "gauge_normalized_endpoints_xy":[
                        _point(candidate["sample_start"],"line start"),
                        _point(candidate["sample_end"],"line end"),
                    ],
                    "outer_side_orientation_family":sid,
                    "outer_distance_fraction":fraction,
                    "gradient_coverage":float(candidate["coverage"]),
                    "longest_contiguous_fraction":float(
                        candidate["longest_contiguous_fraction"]),
                    "source_index":source_index,
                })
        if set(candidates_by_side) not in (set(),set(range(8))):
            raise ValueError("expected all eight side families or explicit unavailable")
        candidate_nodes=[]
        g=jr.get("junction_evidence") or {}
        if g.get("physical_facet_identity_verified") is True or g.get("polygon"):
            raise ValueError("physical identity or polygon cannot be promoted")
        for node in g.get("nodes",[]):
            node_id=_positive_int(node.get("id"),"node id")
            refs=[]
            for side_key,rank in node["line_candidate_indices"].items():
                sid=int(side_key)
                rank=_positive_int(rank,"candidate rank")
                if sid not in candidates_by_side or rank >= len(candidates_by_side[sid]):
                    raise ValueError("junction refers to unobserved line")
                refs.append(f"{source_index}:side{sid}:line{rank}")
            if len(refs)!=2:
                raise ValueError("junction needs exactly two observed orientations")
            candidate_nodes.append({
                "optical_id":f"{source_index}:junction{node_id}",
                "feature_type":"intersecting_optical_line_candidates",
                "provenance_class":OPTICAL_CLASS,
                "possible_virtual_or_reflected_facet":True,
                "facet_semantic_id":None,
                "physical_correspondence":UNKNOWN_PHYSICAL_CLASS,
                "gauge_normalized_xy":_point(
                    node["position_gauge_normalized_xy"],"junction coordinate"),
                "observed_optical_line_refs":sorted(refs),
                "source_index":source_index,
            })
        known_ids={n["optical_id"] for n in candidate_nodes}
        observed_edges=[]
        for e in g.get("edges",[]):
            a=f"{source_index}:junction{_positive_int(e['node_a'],'edge node')}"
            b=f"{source_index}:junction{_positive_int(e['node_b'],'edge node')}"
            if a not in known_ids or b not in known_ids or a==b:
                raise ValueError("graph edge references unobserved corner")
            observed_edges.append({"source_optical_junction_ids":[a,b],
                                   "provenance_class":OPTICAL_CLASS,
                                   "physical_correspondence":UNKNOWN_PHYSICAL_CLASS})
        optical.append({
            "source_index":source_index,
            "view_role_status":face["status"],
            "line_segment_candidates":line_features,
            "junction_candidates":candidate_nodes,
            "optical_graph_connections":observed_edges,
            "physical_facet_claim":False,
        })
    return {
        "schema_version":SCHEMA,
        "certificate":line["certificate"],
        "semantic_gauge":"frozen_80_sequence_gauge",
        "face_identity":face,
        "selected_source_indices":list(line["selected_source_indices"]),
        "physical_geometry":{
            "external_silhouette":{
                "provenance_class":OUTER_CLASS,
                "vertices_topology_order":outer,
                "source":"frozen_96_source_mask_outline",
            },
            "interior_boundaries":{
                name:{
                    "provenance_class":UNKNOWN_PHYSICAL_CLASS,
                    "status":"unavailable",
                    "vertices_topology_order":None,
                    "reason":"RGB_contrast_and_junctions_do_not_prove_polished_facet_identity",
                } for name in INTERIOR_BOUNDARIES
            },
        },
        "optical_appearance":{
            "feature_provenance_class":OPTICAL_CLASS,
            "frames":optical,
            "cross_view_observed_line_family_counts":repeat_counts,
            "cross_view_interpretation":"descriptive_only_no_physical_tracking_or_claim",
        },
        "physical_interior_facet_status":"unavailable",
        "can_use_as_physical_facet_geometry":False,
        "no_estimator_change":True,
    }


def require_physical_boundary(report, boundary):
    """Fail closed: optical candidates cannot serve as geometry consumers."""
    row=report["physical_geometry"]["interior_boundaries"][boundary]
    if (row["status"] != "ok" or row["provenance_class"]
            != "independently_validated_physical_junction"):
        raise ValueError(f"{boundary}: independently corroborated physical geometry unavailable")
    return row["vertices_topology_order"]


def adapt_archive(line_root, junction_root, output):
    """Transform existing checked artifacts, not source stress or estimation."""
    line_root=Path(line_root)
    junction_root=Path(junction_root)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    baseline_line=json.loads((line_root/"summary.json").read_text())
    baseline_junction=json.loads((junction_root/"summary.json").read_text())
    if (baseline_line.get("benchmark_manifest_canonical_sha256")
            != validation.BENCHMARK_MANIFEST_CANONICAL_SHA256 or
            baseline_junction.get("pinned_source_manifest_sha256")
            != validation.BENCHMARK_MANIFEST_CANONICAL_SHA256):
        raise ValueError("benchmarks are not the frozen source manifest")
    if baseline_line.get("method_change") is not False or baseline_junction.get("estimator_modified") is not False:
        raise ValueError("source diagnostic was not estimator-isolated")
    if baseline_junction.get("physical_facet_identity_verified") is not False:
        raise ValueError("source implies confirmed physical facet")
    names_line=[r["certificate"] for r in baseline_line["stones"]]
    names_junction=[r["certificate"] for r in baseline_junction["stones"]]
    if names_line!=names_junction or len(names_line)!=4:
        raise ValueError("frozen benchmark stones differ")
    summaries=[]
    for certificate in names_line:
        l=json.loads((line_root/"per-stone"/certificate/"line-evidence.json").read_text())
        j=json.loads((junction_root/"per-stone"/certificate/"junction-evidence.json").read_text())
        report=adapt_stone(l,j)
        dst=output/"per-stone"/certificate
        dst.mkdir(parents=True,exist_ok=True)
        (dst/"provenance.json").write_text(
            json.dumps(report,indent=2,allow_nan=False)+"\n"
        )
        rows=report["optical_appearance"]["frames"]
        summaries.append({
            "certificate":certificate,
            "face_identity":report["face_identity"]["status"],
            "source_indices":report["selected_source_indices"],
            "optical_line_count":sum(len(r["line_segment_candidates"]) for r in rows),
            "optical_junction_count":sum(len(r["junction_candidates"]) for r in rows),
            "optical_connection_count":sum(len(r["optical_graph_connections"]) for r in rows),
            "physical_interior_facet_status":"unavailable",
        })
    result={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "benchmark_manifest_sha256":validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":summaries,
        "physical_facet_identity_from_RGB":False,
        "production_estimator_unchanged":True,
        "interpretation":"optical feature inventory separate from physical geometry",
    }
    (output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line-root",type=Path,required=True)
    p.add_argument("--junction-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    report=adapt_archive(a.line_root,a.junction_root,a.output)
    for row in report["stones"]:
        print(row["certificate"],"optical lines",row["optical_line_count"],
              "junction candidates",row["optical_junction_count"],
              "physical",row["physical_interior_facet_status"])


if __name__=="__main__":
    main()
