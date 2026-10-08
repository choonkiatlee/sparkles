"""Observed RGB line-junction graph for Asscher interior geometry (#123/#124).

Diagnostic only. Graph nodes require real, finite adjacent line intersections
near both independently observed contiguous source-RGB segments, and oriented
RGB gradients near that vertex in *both* directions. Edges connect nodes only
through the SAME observed segment candidate. Do not fill absent corners.
Even a closed optical graph is not proof of a physical facet boundary.
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

from . import asscher_geometry_rgb_lines as rgb_lines
from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-observed-RGB-junction-graph/1"
POLICY = {
    "schema_version": SCHEMA,
    "input": "unmodified_original_camera_RGB_and_independently_supported_line_segments_from_146",
    "max_line_candidates_per_side": 3,
    "allowed_intersection_to_observed_segment_distance": 0.025,
    "minimum_intersection_normal_determinant": 0.15,
    "gradient_probe_normalized_distance": 0.010,
    "gradient_probe_count_each_direction": 5,
    "minimum_fraction_oriented_gradient_probes": 0.40,
    "gradient_fraction_of_146_frame_reference": 0.70,
    "minimum_connected_edge_endpoint_separation": 0.025,
    "full_cycle": "eight_direct_observed_junctions_with_consistent_shared_side_candidates",
    "face_identity_requirement": "resolved_likely_crown_for_physical_interpretation",
    "view_confidence_fallback": "unresolved_not_pavilion_or_crown_inferred",
    "no_completing_missing_junctions": True,
    "no_facet_identity_from_RGB_contrast": True,
    "no_production_estimator_change": True,
}
NODE_COLOR=(240,240,240)
EDGE_COLOR=(40,225,135)
UNCERTAIN_COLOR=(255,193,92)


def _segment_distance(point, line):
    """Euclidean normalized distance to finite observed RGB segment."""
    p=np.asarray(point,float)
    a=np.asarray(line["sample_start"],float)
    b=np.asarray(line["sample_end"],float)
    vector=b-a
    norm2=float(vector@vector)
    if norm2<1e-12:
        return None
    t=float(np.clip(((p-a)@vector)/norm2,0,1))
    return float(np.linalg.norm(p-(a+t*vector)))


def _junction_pixel_support(gray,valid,mask,vertex,sides,base):
    """Require native-RGB oriented edge signals on both adjacent segments.

    Probe *along* each directly detected segment near its measured corner.
    A bright point without continued line evidence is insufficient.
    """
    smooth=ndi.gaussian_filter(np.asarray(gray,float),1.)
    gx=ndi.sobel(smooth,axis=1)/8.
    gy=ndi.sobel(smooth,axis=0)/8.
    centre,scale=rgb_lines.normalized_gauge(mask)
    results=[]
    for side in sides:
        line=side["line"]
        tangent=np.asarray(side["tangent"],float)
        normal=np.asarray(side["normal"],float)
        a=np.asarray(line["sample_start"],float)
        b=np.asarray(line["sample_end"],float)
        point=np.asarray(vertex,float)
        # Probe inward along the observed segment rather than extending it.
        projection=float((point-a)@tangent)
        centre_a=float((a-a)@tangent)
        centre_b=float((b-a)@tangent)
        signs=[1.,-1.]
        # Decide a single direction towards the longer measured part.
        lengths=[
            max(0., float((b-point)@tangent)),
            max(0., float((point-a)@tangent)),
        ]
        sign=signs[int(np.argmax(lengths))]
        distances=np.arange(1,POLICY["gradient_probe_count_each_direction"]+1,
                            dtype=float)*POLICY["gradient_probe_normalized_distance"]
        candidates=point[None,:]+sign*distances[:,None]*tangent[None,:]
        along=((candidates-a)@tangent)
        lower,upper=sorted((centre_a,centre_b))
        within=(along>=lower-1e-8)&(along<=upper+1e-8)
        px=centre[None,:]+scale*candidates
        coords=[px[:,1],px[:,0]]
        in_valid=(ndi.map_coordinates(valid.astype(float),coords,order=0,
                                      mode="constant",cval=0)>.5)
        oriented=np.abs(
            ndi.map_coordinates(gx,coords,order=1,mode="constant",cval=0)*normal[0]
            +ndi.map_coordinates(gy,coords,order=1,mode="constant",cval=0)*normal[1]
        )
        above=(oriented>=base*POLICY["gradient_fraction_of_146_frame_reference"])
        hits=int(np.count_nonzero(within&in_valid&above))
        result={
            "probes_in_observed_span":int(np.count_nonzero(within&in_valid)),
            "supported_probe_count":hits,
            "fraction_of_predeclared_probes":float(hits/len(distances)),
        }
        results.append(result)
    passed=all(
        r["fraction_of_predeclared_probes"] >=
            POLICY["minimum_fraction_oriented_gradient_probes"]
        for r in results
    )
    return passed,results


def candidate_junction_graph(outer, detected, *, gray=None, valid=None, mask=None):
    """Enumerate all supported nodes/edges, never select one likely table ring."""
    families=rgb_lines.outer_side_families(outer)
    all_sides=detected.get("sides") or []
    empty={
        "schema_version":SCHEMA,
        "status":"unavailable",
        "nodes":[],"edges":[],"components":[],
        "connected_corner_max":0,"has_supported_eight_corner_cycle":False,
        "reason":None,
    }
    if len(all_sides)!=8:
        return {**empty,"reason":"no_eight_side_candidate_families"}
    if any(x is None for x in (gray,valid,mask)):
        raise ValueError("native RGB and gauge mask required for junction verification")
    base=detected.get("gradient_reference")
    if base is None or not np.isfinite(base) or base<=0:
        return {**empty,"reason":"no_RGB_gradient_reference"}

    nodes=[]
    for corner in range(8):
        previous=(corner-1)%8
        sides=(previous,corner)
        for ai, candidate_a in enumerate(
            all_sides[previous]["detected_candidates"][:3]
        ):
            for bi,candidate_b in enumerate(
                all_sides[corner]["detected_candidates"][:3]
            ):
                fam_a,fam_b=(families[previous],families[corner])
                normals=np.vstack([fam_a["normal"],fam_b["normal"]])
                if abs(np.linalg.det(normals)) < POLICY["minimum_intersection_normal_determinant"]:
                    continue
                fractions=(candidate_a["fraction"],candidate_b["fraction"])
                rhs=np.array([
                    fam_a["outer_distance"]*fractions[0],
                    fam_b["outer_distance"]*fractions[1],
                ])
                point=fam_a["center"]+np.linalg.solve(normals,rhs)
                if not np.isfinite(point).all():
                    continue
                distance_a=_segment_distance(point,candidate_a)
                distance_b=_segment_distance(point,candidate_b)
                if distance_a is None or distance_b is None:
                    continue
                maximum=POLICY["allowed_intersection_to_observed_segment_distance"]
                if max(distance_a,distance_b)>maximum:
                    continue
                # Guard against invented corners outside the observed silhouette.
                if any(
                    np.dot(point-fam["center"],fam["normal"])>
                        fam["outer_distance"]+1e-6
                    for fam in families
                ):
                    continue
                verified,evidence=_junction_pixel_support(
                    gray,valid,mask,point,(
                        {"line":candidate_a,"normal":fam_a["normal"],
                         "tangent":fam_a["tangent"]},
                        {"line":candidate_b,"normal":fam_b["normal"],
                         "tangent":fam_b["tangent"]},
                    ),float(base)
                )
                if not verified:
                    continue
                nodes.append({
                    "id":f"c{corner}-p{ai}-q{bi}",
                    "corner_index":corner,
                    "side_candidate_indices":{
                        str(previous):ai,str(corner):bi,
                    },
                    "point_normalized_xy":point.tolist(),
                    "distances_to_observed_segment":[distance_a,distance_b],
                    "RGB_gradient_support":evidence,
                    "provenance":"observed_RGB_line_intersection_hypothesis",
                })

    edges=[]
    by_corner={i:[] for i in range(8)}
    for node in nodes:
        by_corner[node["corner_index"]].append(node)
    for side in range(8):
        for a in by_corner[side]:
            for b in by_corner[(side+1)%8]:
                index=a["side_candidate_indices"].get(str(side))
                if index is None or b["side_candidate_indices"].get(str(side))!=index:
                    continue
                separation=float(np.linalg.norm(
                    np.asarray(a["point_normalized_xy"])-
                    np.asarray(b["point_normalized_xy"])
                ))
                if separation < POLICY["minimum_connected_edge_endpoint_separation"]:
                    continue
                edges.append({
                    "side":side,"source_node":a["id"],"target_node":b["id"],
                    "segment_candidate_index":index,
                    "distance_between_observed_junctions":separation,
                    "provenance":"same_contiguous_RGB_segment_candidate",
                })

    adjacent={n["id"]:set() for n in nodes}
    for edge in edges:
        adjacent[edge["source_node"]].add(edge["target_node"])
        adjacent[edge["target_node"]].add(edge["source_node"])
    lookup={n["id"]:n for n in nodes}
    seen=set()
    components=[]
    for node in nodes:
        if node["id"] in seen:
            continue
        work=[node["id"]]
        members=[]
        while work:
            key=work.pop()
            if key in seen:continue
            seen.add(key)
            members.append(key)
            work.extend(adjacent[key]-seen)
        corners=sorted({lookup[key]["corner_index"] for key in members})
        components.append({
            "node_ids":sorted(members),
            "observed_corner_indices":corners,
            "unique_corner_count":len(corners),
            "multiple_hypotheses_possible":len(members)!=len(corners),
        })
    components.sort(key=lambda x:-x["unique_corner_count"])

    # Search an explicitly consistent eight-corner cycle. Graph can be
    # branched, so a high count alone must never be mistaken for a loop.
    outgoing={}
    for edge in edges:
        outgoing.setdefault(edge["source_node"],set()).add(edge["target_node"])
    closed=False
    for start in by_corner[0]:
        frontier={start["id"]}
        for corner in range(7):
            frontier={
                nxt for current in frontier for nxt in outgoing.get(current,())
                if lookup[nxt]["corner_index"] == corner+1
            }
            if not frontier:break
        if frontier and any(
            start["id"] in outgoing.get(end,()) for end in frontier
        ):
            closed=True
            break
    return {
        **empty,
        "status":"connected_partial" if edges else (
            "isolated_junctions" if nodes else "unavailable"
        ),
        "reason":None if nodes else "no_observed_two_line_RGB_junctions",
        "nodes":nodes,
        "edges":edges,
        "components":components,
        "connected_corner_max":max(
            (c["unique_corner_count"] for c in components),default=0
        ),
        "has_supported_eight_corner_cycle":closed,
        "interpretation":(
            "These are RGB-supported line-intersection hypotheses, not "
            "verified polished facet junctions or a physical 3D table boundary."
        ),
    }


def _camera_points(points, mask, matrix):
    return rgb_lines._points_to_camera(points,mask,matrix)


def render_junction_overlay(source,mask,matrix,outer,detected,graph,*,source_index,
                            face_status):
    source=source.convert("RGB")
    original=source.copy()
    over=source.copy()
    draw=ImageDraw.Draw(over)
    width=max(2,int(max(source.size)/280))
    polygon=_camera_points(np.asarray(outer,float),mask,matrix)
    draw.line([tuple(p) for p in polygon]+[tuple(polygon[0])],
              fill=(242,242,242),width=width)
    # Draw observed subsegments only; no inferred full octagonal sides.
    for row in detected.get("sides",[]):
        for candidate in row.get("detected_candidates",[]):
            pts=_camera_points([candidate["sample_start"],
                                candidate["sample_end"]],mask,matrix)
            draw.line([tuple(p) for p in pts],fill=(155,185,228),
                      width=width)
    for edge in graph["edges"]:
        a=next(x for x in graph["nodes"] if x["id"]==edge["source_node"])
        b=next(x for x in graph["nodes"] if x["id"]==edge["target_node"])
        # Highlight supported graph connection only along the same segment.
        pts=_camera_points([a["point_normalized_xy"],
                            b["point_normalized_xy"]],mask,matrix)
        draw.line([tuple(p) for p in pts],fill=EDGE_COLOR,width=width+1)
    for node in graph["nodes"]:
        (x,y),=_camera_points([node["point_normalized_xy"]],mask,matrix)
        draw.ellipse((x-width*2,y-width*2,x+width*2,y+width*2),
                     outline=NODE_COLOR,width=width)
    corner_pixels=polygon
    lo=corner_pixels.min(axis=0)
    hi=corner_pixels.max(axis=0)
    pad=.11*max(hi-lo)
    box=(max(0,int(lo[0]-pad)),max(0,int(lo[1]-pad)),
         min(source.width,int(hi[0]+pad)),min(source.height,int(hi[1]+pad)))
    if box[2]<=box[0] or box[3]<=box[1]:
        raise ValueError("invalid image crop")
    panels=[original.crop(box),over.crop(box)]
    combined=Image.new("RGB",(
        sum(i.width for i in panels)+5,
        max(i.height for i in panels)+48
    ),(17,17,17))
    d=ImageDraw.Draw(combined)
    d.text((7,5),f"src {source_index} | {face_status} | original camera RGB",
           fill="white")
    d.text((panels[0].width+12,5),
           f"RGB junctions {len(graph['nodes'])} nodes / {len(graph['edges'])} links",
           fill="white")
    d.text((panels[0].width+12,24),
           "WHITE measured corners; GREEN connected; BLUE observed segments",
           fill=(195,195,195))
    combined.paste(panels[0],(0,48))
    combined.paste(panels[1],(panels[0].width+5,48))
    return combined


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    baseline=rgb_lines.run_stone(
        pose_dir,processed,output/"line-baseline",certificate=certificate
    )
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _, records, _, _=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD
    )
    role_values={r.get("face_role") for r in records}
    face_resolution=(pose.get("face_selection") or {}).get("status")
    crown_eligible=(
        face_resolution=="resolved"
        and role_values=={"likely_crown_lobe"}
    )
    record_by_source={r["source_index"]:r for r in records}
    outer=baseline.get("outer_vertices_topology_order")
    frames=[]
    for row in baseline["frames"]:
        entry={
            "source_index":row["source_index"],
            "face_role":row.get("face_role"),
            "face_identity_status":(
                "candidate_crown_resolved" if crown_eligible else
                "unresolved_no_physical_interpretation"
            ),
        }
        record=record_by_source.get(row["source_index"])
        if (outer is None or not record or not row.get("sides")
                or not record.get("source_camera_path")):
            entry.update(status="unavailable",
                         reason="missing_line_or_camera_source")
            frames.append(entry)
            continue
        matrix=(record.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy")
        if matrix is None:
            entry.update(status="unavailable",reason="missing_gauge_map")
            frames.append(entry)
            continue
        source=Image.open(
            Path(processed)/record["source_camera_path"]
        ).convert("RGB")
        _,mask,_=stability._load_gauged_arrays(pose_dir,record)
        gray,valid=rgb_lines.image_to_gauge(source,mask,matrix)
        graph=candidate_junction_graph(
            outer,row,gray=gray,valid=valid,mask=mask
        )
        name=f"source-{int(row['source_index']):04d}-junctions.jpg"
        sheet=render_junction_overlay(
            source,mask,matrix,outer,row,graph,
            source_index=row["source_index"],
            face_status=entry["face_identity_status"],
        )
        sheet.save(output/name,quality=92)
        frames.append({
            **entry,"status":graph["status"],
            "RGB_QC_path":name,
            "graph":graph,
            "physical_facet_identity_verified":False,
        })
    summary={
        "schema_version":SCHEMA,
        "certificate":certificate,
        "selected_source_indices":baseline["selected_source_indices"],
        "face_selection_status":face_resolution,
        "selected_roles":sorted(str(x) for x in role_values),
        "physical_crown_inference_eligible":crown_eligible,
        "frames":frames,
        "total_supported_junction_hypotheses":sum(
            len(f.get("graph",{}).get("nodes",[])) for f in frames
        ),
        "total_graph_links":sum(
            len(f.get("graph",{}).get("edges",[])) for f in frames
        ),
        "closed_cycle_frame_count":sum(
            bool(f.get("graph",{}).get("has_supported_eight_corner_cycle"))
            for f in frames
        ),
        "frozen_production_method_unchanged":True,
        "physical_facet_identity_verified":False,
    }
    (output/"junction-evidence.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n"
    )
    qc=[]
    for f in frames:
        if f.get("RGB_QC_path"):
            im=Image.open(output/f["RGB_QC_path"]).convert("RGB")
            im.thumbnail((1280,470),Image.Resampling.LANCZOS)
            qc.append(im.copy())
    if qc:
        rgb_lines.wireframe._contact_sheet(
            qc,output/"source-RGB-junction-contact-sheet.jpg",columns=1
        )
    return summary


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    source_root=Path(source_root).resolve()
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-RGB-junctions-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            source_manifest=Path(bundle["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest=Path.cwd()/source_manifest
            pipeline.run(source_root/cert,processed,source_manifest,
                         gain=1.,accept_review=True)
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            result=run_stone(
                pose,processed,output/"per-stone"/cert,certificate=cert
            )
            rows.append({
                "certificate":cert,
                "selected_source_indices":result["selected_source_indices"],
                "face_selection_status":result["face_selection_status"],
                "physical_crown_inference_eligible":result[
                    "physical_crown_inference_eligible"],
                "junction_count":result["total_supported_junction_hypotheses"],
                "graph_links":result["total_graph_links"],
                "closed_cycle_frame_count":result["closed_cycle_frame_count"],
                "RGB_QC_path":f"per-stone/{cert}/source-RGB-junction-contact-sheet.jpg",
                "frame_results":[{
                    "source_index":x["source_index"],
                    "status":x["status"],
                    "junction_count":len(x.get("graph",{}).get("nodes",[])),
                    "graph_links":len(x.get("graph",{}).get("edges",[])),
                    "max_connected_corners":x.get("graph",{}).get("connected_corner_max",0),
                    "closed_cycle":x.get("graph",{}).get(
                        "has_supported_eight_corner_cycle",False
                    ),
                } for x in result["frames"]],
            })
    report={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "frozen_benchmark_manifest_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":rows,
        "no_estimator_changes":True,
        "physical_facet_identity_verified":False,
    }
    (output/"summary.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n"
    )
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--bundle-manifest",type=Path,
                   default=Path("docs/360/benchmark/source-bundles.json"))
    args=p.parse_args()
    report=run_source_benchmark(
        args.source_root,args.output,args.bundle_manifest
    )
    for stone in report["stones"]:
        print(stone["certificate"],
              "crown_eligible",stone["physical_crown_inference_eligible"],
              "RGB junction hypotheses",stone["junction_count"],
              "connected links",stone["graph_links"],
              "full cycles",stone["closed_cycle_frame_count"])
        for frame in stone["frame_results"]:
            print(" ",frame)


if __name__=="__main__":
    main()
