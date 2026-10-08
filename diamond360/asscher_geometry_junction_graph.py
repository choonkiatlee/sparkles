"""Observed connected line-junction graph on native RGB Asscher views.

A bounded diagnostic on #146's independent line fragments. Not a facet
estimator: an optical crossing, even persistent, is not a polished junction.
No radial peak or corner is synthesized to complete a missing polygon.
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
from . import asscher_outer_octagon as outer_octagon
from . import pipeline
from . import asscher_wireframe as wireframe
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-rgb-junction-graph/1"
POLICY = {
    "schema_version": SCHEMA,
    "parent_line_evidence_schema": rgb_lines.SCHEMA,
    "input_candidate_policy": "all_passing_RGB_contiguous_segments_up_to_three_per_side",
    "adjacent_line_pair_only": True,
    "maximum_corner_to_supported_segment_distance": .045,
    "maximum_corner_line_fraction": .85,
    "minimum_corner_line_fraction": .30,
    "local_gradient_probe_radius": .045,
    "corner_probe_samples_per_side": 17,
    "minimum_gradient_hits_per_orientation": 2,
    "gradient_threshold_fraction_of_frame_reference": .50,
    "minimum_independent_sector_orientation_dot_cross": .15,
    "selection": "report_all_supported_junctions_and_connected_chains",
    "full_polygon_from_missing_data": False,
    "crown_view_status": "resolved_likely_crown_lobe_only",
    "missing_or_uncertain_view": "explicit_review_not_physical_junction",
    "holdout_policy": "leave_one_view_out_summaries_never_refit_a_c3_polygon",
    "physical_facet_identity_claim": False,
    "changes_estimator": False,
}


def _segment_nearest_distance(point, start, end):
    point=np.asarray(point,float)
    start=np.asarray(start,float)
    end=np.asarray(end,float)
    direction=end-start
    denom=float(np.dot(direction,direction))
    if denom<1e-12:
        return float(np.linalg.norm(point-start))
    t=float(np.clip(np.dot(point-start,direction)/denom,0.,1.))
    return float(np.linalg.norm(point-(start+t*direction)))


def _candidate_intersection(family_a, candidate_a, family_b, candidate_b):
    """True intersection of observed line equations, not averaged outer radii."""
    normals=np.vstack((family_a["normal"],family_b["normal"]))
    if abs(float(np.linalg.det(normals))) < POLICY["minimum_independent_sector_orientation_dot_cross"]:
        return None
    distances=np.array([
        family_a["outer_distance"]*candidate_a["fraction"],
        family_b["outer_distance"]*candidate_b["fraction"],
    ],float)
    centre=family_a["center"]
    pt=centre+np.linalg.solve(normals,distances)
    for family in (family_a,family_b):
        fraction=float(
            np.dot(pt-centre,family["normal"])/family["outer_distance"]
        )
        if (fraction<POLICY["minimum_corner_line_fraction"]
                or fraction>POLICY["maximum_corner_line_fraction"]):
            return None
    dists=[
        _segment_nearest_distance(
            pt, candidate["sample_start"],candidate["sample_end"]
        )
        for candidate in (candidate_a,candidate_b)
    ]
    if max(dists)>POLICY["maximum_corner_to_supported_segment_distance"]:
        return None
    return pt,dists


def _oriented_local_hits(gx,gy,mask,point,normal,tangent,scale,center,base):
    """Two oriented gradients must arrive in the same small corner patch."""
    samples=np.linspace(-POLICY["local_gradient_probe_radius"],
                         POLICY["local_gradient_probe_radius"],
                         POLICY["corner_probe_samples_per_side"])
    pts=point[None,:]+samples[:,None]*tangent[None,:]
    xy=center[None,:]+pts*scale
    coords=[xy[:,1],xy[:,0]]
    valid=ndi.map_coordinates(
        mask.astype(np.uint8),coords,order=0,mode="constant",cval=0
    )>0
    directed=np.abs(
        ndi.map_coordinates(gx,coords,order=1,mode="constant",cval=0)*normal[0]+
        ndi.map_coordinates(gy,coords,order=1,mode="constant",cval=0)*normal[1]
    )
    thresh=float(base)*POLICY["gradient_threshold_fraction_of_frame_reference"]
    hits=valid & (directed>=thresh)
    return int(np.sum(hits)),int(np.sum(valid))


def connected_components(node_count,edges):
    """Graph of observed junctions linked by the *same* measured segment."""
    neighbors=[set() for _ in range(node_count)]
    for row in edges:
        a,b=int(row["node_a"]),int(row["node_b"])
        if a==b or a>=node_count or b>=node_count:
            raise ValueError("invalid segment-edge topology")
        neighbors[a].add(b)
        neighbors[b].add(a)
    seen=set()
    parts=[]
    for i in range(node_count):
        if i in seen:
            continue
        stack=[i]
        seen.add(i)
        part=[]
        while stack:
            n=stack.pop()
            part.append(n)
            for j in neighbors[n]:
                if j not in seen:
                    seen.add(j)
                    stack.append(j)
        parts.append(sorted(part))
    return sorted(parts,key=lambda v:(-len(v),v[0]))


def detect_junction_graph(gray,valid,mask,outer,detection):
    """Join only locally intersecting observed fragments with oriented RGB QC.

    Every neighboring-side hypothesis pair is evaluated, not just v146's
    highest-scoring line per family. Never join unrelated candidates on one
    side to complete a graph.
    """
    if len(detection.get("sides",[]))!=8:
        return {"status":"unavailable","reason":"no_eight_side_families",
                "nodes":[],"edges":[],"components":[]}
    families=rgb_lines.outer_side_families(outer)
    center,scale=rgb_lines.normalized_gauge(mask)
    smooth=ndi.gaussian_filter(np.asarray(gray,float),1.)
    gx=ndi.sobel(smooth,axis=1)/8.
    gy=ndi.sobel(smooth,axis=0)/8.
    reference=detection.get("gradient_reference")
    if reference is None or float(reference)<=1e-8:
        return {"status":"unavailable","reason":"no_RGB_reference_gradient",
                "nodes":[],"edges":[],"components":[]}
    nodes=[]
    reject={"intersection_outside_supported_segment":0,
            "no_dual_orientation_gradient":0}
    for i in range(8):
        previous=(i-1)%8
        candidates_left=detection["sides"][previous]["detected_candidates"]
        candidates_right=detection["sides"][i]["detected_candidates"]
        for a,prev in enumerate(candidates_left):
            for b,curr in enumerate(candidates_right):
                ans=_candidate_intersection(
                    families[previous],prev,families[i],curr
                )
                if ans is None:
                    reject["intersection_outside_supported_segment"]+=1
                    continue
                point,distances=ans
                hits=[]
                for fam in (families[previous],families[i]):
                    num,nvalid=_oriented_local_hits(
                        gx,gy,valid & mask,point,fam["normal"],
                        fam["tangent"],scale,center,reference,
                    )
                    hits.append({"oriented_hits":num,"valid_samples":nvalid})
                if any(x["oriented_hits"] <
                       POLICY["minimum_gradient_hits_per_orientation"]
                       for x in hits):
                    reject["no_dual_orientation_gradient"]+=1
                    continue
                nodes.append({
                    "id":len(nodes),
                    "corner_index":i,
                    "line_candidate_indices":{str(previous):a,str(i):b},
                    "position_gauge_normalized_xy":point.tolist(),
                    "measured_segment_endpoint_distances":distances,
                    "local_orientation_hits":hits,
                    "image_plane_only":True,
                })
    # Edges between neighboring corners share one AND the same observed line.
    edges=[]
    for side in range(8):
        prev_nodes=[
            n for n in nodes if n["corner_index"]==side
            and str(side) in n["line_candidate_indices"]
        ]
        next_nodes=[
            n for n in nodes if n["corner_index"]==(side+1)%8
            and str(side) in n["line_candidate_indices"]
        ]
        for a in prev_nodes:
            for b in next_nodes:
                if (a["line_candidate_indices"][str(side)]
                        ==b["line_candidate_indices"][str(side)]):
                    edges.append({"side_index":side,"line_candidate_index":
                                  a["line_candidate_indices"][str(side)],
                                  "node_a":a["id"],"node_b":b["id"]})
    components=connected_components(len(nodes),edges)
    supported_corner_slots=sorted({n["corner_index"] for n in nodes})
    # Even an eight-cycle remains a candidate until physical provenance is
    # established across views; never produce a polished-facet polygon here.
    return {
        "status":"connected_fragments" if edges else (
            "isolated_junction_hypotheses" if nodes else "unavailable"),
        "reason":None if nodes else "no_dual_supported_line_intersections",
        "nodes":nodes,"edges":edges,"components":components,
        "supported_corner_slots":supported_corner_slots,
        "candidate_intersection_count":len(nodes),
        "distinct_corner_slots":len(supported_corner_slots),
        "largest_connected_component_nodes":max(map(len,components),default=0),
        "rejected_pair_reasons":reject,
        "physical_facet_identity_verified":False,
        "polygon":None,
    }


def face_identity_state(pose,records):
    """A metadata gate, not a guess that an unresolved lobe is the crown."""
    selected=pose.get("face_selection") or {}
    role=[r.get("face_role") for r in records]
    if (selected.get("status")=="resolved" and role
            and all(x=="likely_crown_lobe" for x in role)):
        return {"status":"likely_crown","reason":
                "face_lobe_resolved_and_selected_views_likely_crown"}
    return {"status":"uncertain","reason":
            "not_all_selected_views_resolved_as_likely_crown",
            "selection_status":selected.get("status"),
            "selected_roles":role}


def draw_junctions(source,mask,matrix,outer,detection,graph,
                   *,source_index,face_state):
    """Native camera RGB, observed contiguous segments, candidate junctions."""
    source=source.convert("RGB")
    bbox=rgb_lines._points_to_camera(np.asarray(outer,float),mask,matrix)
    left,top=bbox.min(axis=0)
    right,bottom=bbox.max(axis=0)
    pad=.11*max(right-left,bottom-top)
    crop=(max(0,int(left-pad)),max(0,int(top-pad)),
          min(source.width,int(right+pad)),min(source.height,int(bottom+pad)))
    if crop[2]<=crop[0] or crop[3]<=crop[1]:
        raise ValueError("invalid camera RGB crop")
    width=max(2,int(max(source.size)/260))
    panels=[]
    for mode in range(3):
        pane=source.copy()
        draw=ImageDraw.Draw(pane)
        if mode:
            for row in detection.get("sides",[]):
                for candidate in row.get("detected_candidates",[]):
                    points=rgb_lines._points_to_camera(
                        [candidate["sample_start"],candidate["sample_end"]],
                        mask,matrix
                    )
                    draw.line([tuple(xy) for xy in points],
                              fill=rgb_lines.COLORS[row["side"]],
                              width=width+1)
            if mode==2 and graph.get("nodes"):
                normpoints=np.asarray([
                    n["position_gauge_normalized_xy"] for n in graph["nodes"]
                ],float)
                coords=rgb_lines._points_to_camera(normpoints,mask,matrix)
                by_id={n["id"]:tuple(xy) for n,xy in zip(graph["nodes"],coords)}
                for edge in graph["edges"]:
                    draw.line([by_id[edge["node_a"]],by_id[edge["node_b"]]],
                              fill=(120,250,90),width=width+1)
                for x,y in coords:
                    radius=3*width
                    draw.ellipse((x-radius,y-radius,x+radius,y+radius),
                                 outline=(255,255,255),width=width)
        cropped=pane.crop(crop)
        part=Image.new("RGB",(cropped.width,cropped.height+54),(14,14,14))
        part.paste(cropped,(0,54))
        header=["Original RGB","All passing observed fragments",
                "Supported intersection graph (NOT verified facet)"][mode]
        role=("likely crown" if face_state["status"]=="likely_crown"
              else "CROWN UNCERTAIN")
        drawer=ImageDraw.Draw(part)
        drawer.text((7,5),f"src {source_index}: {header}",fill="white")
        drawer.text((7,27),
                    f"{role} | {len(graph.get('nodes',[]))} candidates "
                    f"/ {len(graph.get('edges',[]))} connected edges",
                    fill=(220,220,220))
        panels.append(part)
    result=Image.new("RGB",(
        sum(x.width for x in panels)+8,max(x.height for x in panels)
    ),(20,20,20))
    x=0
    for pane in panels:
        result.paste(pane,(x,0))
        x+=pane.width+4
    return result


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    pose=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    _,records,_,_=stability._primary_fit(
        pose_dir,pose,method=validation.OUTER_METHOD
    )
    face=face_identity_state(pose,records)
    report={
        "schema_version":SCHEMA,"certificate":certificate,
        "face_identity":face,
        "selected_source_indices":[r["source_index"] for r in records],
        "frames":[],"leave_one_out_support":[],
        "physical_facet_identity_verified":False,
        "production_estimator_changed":False,
    }
    if len(records)<3:
        report["status"]="unavailable"
        report["reason"]="fewer_than_three_compatible_crown_views"
        return report
    _,_,masks,_,metadata=stability._load_evidence(pose_dir,records)
    outer=outer_octagon.fit_consensus(masks,frame_metadata=metadata)
    vertices=np.asarray(outer["vertices_topology_order"],float)
    results=[]
    frames=[]
    for record,mask in zip(records,masks):
        path=record.get("source_camera_path")
        matrix=(record.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy")
        if path is None or matrix is None:
            frames.append({"source_index":record["source_index"],
                           "status":"unavailable",
                           "reason":"missing_RGB_or_gauge_matrix"})
            continue
        source=Image.open(Path(processed)/path).convert("RGB")
        gray,valid=rgb_lines.image_to_gauge(source,mask,matrix)
        detected=rgb_lines.extract_frame_lines(gray,valid,mask,vertices)
        graph=detect_junction_graph(gray,valid,mask,vertices,detected)
        pic=draw_junctions(source,mask,matrix,vertices,detected,graph,
                           source_index=record["source_index"],
                           face_state=face)
        name=f"source-{int(record['source_index']):04d}-junction-RGB.jpg"
        pic.save(output/name,quality=91)
        frames.append({
            "source_index":record["source_index"],
            "position":record.get("position"),
            "status":graph["status"],"junction_evidence":graph,
            "line_side_count":detected.get("detected_side_count",0),
            "source_camera_QC":name,
            "view_role_status":face["status"],
        })
    report["frames"]=frames
    for corner in range(8):
        sources=[r["source_index"] for r in frames
                 if corner in r.get("junction_evidence",{}).get(
                     "supported_corner_slots",[])]
        report.setdefault("corner_coverage",[]).append({
            "corner_slot":corner,"source_indices":sources,
            "frame_support":len(sources),
            "crown_identity_resolved":face["status"]=="likely_crown",
        })
    for row in frames:
        kept=[r for r in frames if r["source_index"]!=row["source_index"]]
        report["leave_one_out_support"].append({
            "omitted_source_index":row["source_index"],
            "support_count_by_corner_slot":[sum(
                corner in r.get("junction_evidence",{}).get(
                    "supported_corner_slots",[])
                for r in kept
            ) for corner in range(8)],
            "note":"diagnostic count only; no polygon refit",
        })
    report["status"]=(
        "review" if face["status"]=="uncertain"
        else ("observational_only" if any(
            r.get("junction_evidence",{}).get("nodes") for r in frames
        ) else "unavailable")
    )
    (output/"junction-evidence.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n"
    )
    sheets=[]
    for r in frames:
        if not r.get("source_camera_QC"):
            continue
        image=Image.open(output/r["source_camera_QC"])
        image.thumbnail((1300,460),Image.Resampling.LANCZOS)
        sheets.append(image.copy())
    if sheets:
        wireframe._contact_sheet(
            sheets,output/"junction-camera-RGB-contact-sheet.jpg",columns=1
        )
    return report


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-crown-junctions-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            source_manifest=Path(bundle["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest=Path.cwd()/source_manifest
            pipeline.run(
                Path(source_root).resolve()/cert,
                processed,source_manifest,gain=1.0,accept_review=True
            )
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            r=run_stone(pose,processed,output/"per-stone"/cert,
                        certificate=cert)
            results.append({
                "certificate":cert,"status":r["status"],
                "selected_source_indices":r["selected_source_indices"],
                "face_identity":r["face_identity"],
                "frame_counts":[{
                    "source_index":row["source_index"],
                    "junction_candidates":len(
                        row.get("junction_evidence",{}).get("nodes",[])),
                    "connected_edges":len(
                        row.get("junction_evidence",{}).get("edges",[])),
                    "largest_component_nodes":row.get(
                        "junction_evidence",{}).get(
                            "largest_connected_component_nodes",0),
                } for row in r["frames"]],
                "corner_coverage":r.get("corner_coverage",[]),
                "RGB_contact_sheet":(
                    f"per-stone/{cert}/junction-camera-RGB-contact-sheet.jpg"
                    if r["status"]!="unavailable" else None),
            })
    report={
        "schema_version":SCHEMA,"policy":POLICY,
        "pinned_source_manifest_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":results,"estimator_modified":False,
        "physical_facet_identity_verified":False,
    }
    (output/"summary.json").write_text(
        json.dumps(report,indent=2,allow_nan=False)+"\n"
    )
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--bundle-manifest",type=Path,
                   default=Path("docs/360/benchmark/source-bundles.json"))
    args=p.parse_args()
    report=run_source_benchmark(args.source_root,args.output,
                                args.bundle_manifest)
    for s in report["stones"]:
        print(s["certificate"],"face",s["face_identity"]["status"],
              "status",s["status"])
        for r in s["frame_counts"]:
            print(" ",r["source_index"],"junctions",
                  r["junction_candidates"],"connected edges",
                  r["connected_edges"],"largest component",
                  r["largest_component_nodes"])


if __name__=="__main__":
    main()
