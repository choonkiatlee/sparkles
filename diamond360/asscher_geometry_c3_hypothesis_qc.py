"""Geometry-first, camera-RGB C3/table hypothesis audit for #124.

Diagnostic only. The two hypotheses are kept side-by-side and NEVER
written back into the frozen estimator or called physical facet junctions.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_outer_octagon as outer_octagon
from . import asscher_steps as steps
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-c3-hypothesis-geometry/1"
WINDOW = steps.BOUNDARY_WINDOWS[0]
POLICY = {
    "schema_version": SCHEMA,
    "candidate_pool": "predeclared_v3_window_local_supported_C3_peaks",
    "hypothesis_count": 2,
    "reference_ruler": "same_full_view_outer_octagon_for_full_and_all_leave_one_out",
    "context_ruler": "v3_C2_C3_candidate_without_changing_C2",
    "ranking": "existing_v3_aggregate_score_only_for_display_order",
    "rendering": "original_camera_RGB_with_exact_sequence_gauge_to_camera_transform",
    "candidate_labels": "competing_image_plane_hypotheses_not_physical_facets",
    "no_method_revision_or_production_change": True,
    "source_stress": "omitted",
}


def _value(value):
    return None if value is None or not np.isfinite(value) else float(value)


def _closed_polygon_metrics(vertices):
    """Report QC descriptors, without using them to choose a winner."""
    polygon = np.asarray(vertices, float)
    if polygon.shape != (8, 2) or not np.isfinite(polygon).all():
        raise ValueError("expected finite eight-vertex polygon")
    shifted = np.roll(polygon, -1, axis=0)
    area = 0.5 * float(np.sum(polygon[:, 0] * shifted[:, 1]
                               - shifted[:, 0] * polygon[:, 1]))
    sides = shifted - polygon
    cross = np.cross(sides, np.roll(sides, -1, axis=0))
    tol = max(1e-10, abs(area) * 1e-7)
    convex = bool(np.all(cross > -tol) or np.all(cross < tol))
    radii = np.linalg.norm(polygon, axis=1)
    return {
        "area_absolute": abs(area),
        "convex_octagon": convex,
        "radius_min": float(radii.min()),
        "radius_max": float(radii.max()),
        "radius_coefficient_of_variation": float(np.std(radii)/np.mean(radii)),
        "max_neighbour_vertex_radius_difference": float(np.max(
            np.abs(np.diff(np.r_[radii, radii[0]]))
        )),
        "opposite_vertex_radius_difference_max": float(np.max(
            np.abs(radii[:4]-radii[4:])
        )),
    }


def _candidate_geometry(candidate, u, evidence, outer_vertices, c2_vertices):
    """Reconstruct exactly the predeclared eight-sector #19/#75 hypothesis."""
    control = steps._control_from_candidate(candidate, WINDOW, u)
    sector_u = np.asarray(control["sector_u"], float)
    ring = wireframe._ring_vertices(
        outer_vertices, wireframe._topology_order(sector_u)
    )
    geometry = _closed_polygon_metrics(ring)
    geometry["max_neighbour_sector_u_jump"] = float(np.max(np.abs(
        np.diff(np.r_[sector_u, sector_u[0]])
    )))
    if c2_vertices is not None:
        gap = np.linalg.norm(c2_vertices, axis=1) - np.linalg.norm(ring, axis=1)
        geometry["minimum_radial_clearance_to_C2_C3"] = float(gap.min())
        geometry["all_vertices_inside_C2_C3"] = bool(np.all(gap > 0))
    else:
        geometry["minimum_radial_clearance_to_C2_C3"] = None
        geometry["all_vertices_inside_C2_C3"] = None
    temporal = steps.candidate_frame_persistence(evidence, u, candidate)
    return {
        "u": float(candidate["u"]),
        "prominence": float(candidate["prominence"]),
        "sector_support": float(candidate["sector_support"]),
        "sector_u_step_order": sector_u.tolist(),
        "observed_sector_indices": np.flatnonzero(control["observed"]).tolist(),
        "vertices_topology_order": ring.tolist(),
        "polygon_geometry": geometry,
        "per_frame_evidence": temporal,
    }


def hypothesis_case(evidence, u, outer_vertices, *, source_indices):
    """Evaluate both v3 C3 hypotheses on only the specified included views."""
    evidence = np.asarray(evidence, float)
    u = np.asarray(u, float)
    if len(source_indices) != len(evidence):
        raise ValueError("source indices and evidence frames must agree")
    template = steps.discover_template(
        evidence, u, peak_policy=steps.WINDOW_PEAK_POLICY
    )
    candidates = template.get("candidates", [])
    positive = np.asarray(
        [float(c["prominence"]) for c in candidates if c["prominence"] > 0]
    )
    scale = max(float(np.median(positive)) if positive.size else 0, 1e-6)
    eligible = [
        c for c in candidates
        if WINDOW[0] <= c["u"] <= WINDOW[1] and c["sector_support"] >= .25
    ]
    eligible.sort(key=lambda c: (
        -(float(np.log1p(c["prominence"]/scale) + 1.25*c["sector_support"])),
        float(c["u"]),
    ))
    c2 = (template.get("controls") or
          list((template.get("partial_controls") or {}).values()))
    c2_control = None
    if template.get("controls"):
        c2_control = template["controls"][1]
    elif (template.get("partial_controls") or {}).get("inner_middle"):
        c2_control = template["partial_controls"]["inner_middle"]
    c2_vertices = None
    if c2_control is not None:
        c2_vertices = wireframe._ring_vertices(
            outer_vertices,
            wireframe._topology_order(c2_control["sector_u"]),
        )
    displayed = eligible[:2]
    hypotheses = []
    for rank, c in enumerate(displayed):
        hypothesis = _candidate_geometry(c, u, evidence, outer_vertices,
                                         c2_vertices)
        hypothesis["display_id"] = ("A", "B")[rank]
        hypothesis["v3_aggregate_selection_score"] = float(
            np.log1p(c["prominence"]/scale)+1.25*c["sector_support"]
        )
        hypotheses.append(hypothesis)

    chosen_u = (
        float(template["controls"][0]["global_u"])
        if template.get("controls") else
        (float(template["partial_controls"]["centre_inner"]["global_u"])
         if (template.get("partial_controls") or {}).get("centre_inner")
         else None)
    )
    return {
        "included_source_indices": list(source_indices),
        "template_status": template["status"],
        "template_reason": template.get("reason"),
        "v3_selected_c3_u": chosen_u,
        "eligible_c3_candidate_count": len(eligible),
        "status": "two_hypotheses" if len(displayed) == 2 else
                  "one_hypothesis" if len(displayed) == 1 else "unavailable",
        "hypotheses": hypotheses,
        "context_C2_C3_vertices_topology_order": (
            None if c2_vertices is None else c2_vertices.tolist()
        ),
        "outer_octagon_vertices_topology_order": np.asarray(
            outer_vertices, float
        ).tolist(),
        "note": (
            "A/B order reflects frozen v3 aggregate ranking, not truth. "
            "All spatial tests are descriptive and held-out views cannot "
            "vote for a candidate being fitted."
        ),
    }


def _camera_crop(source, mask, matrix):
    h, w = mask.shape
    yy, xx = np.nonzero(mask)
    if not len(xx):
        raise ValueError("no registered silhouette to map")
    corners = np.array([
        [xx.min(), yy.min(), 1],
        [xx.max(), yy.min(), 1],
        [xx.max(), yy.max(), 1],
        [xx.min(), yy.max(), 1],
    ], float).T
    mapped = matrix @ corners
    if np.any(abs(mapped[2]) < 1e-12):
        raise ValueError("nonprojectable source mask footprint")
    points = mapped[:2] / mapped[2:3]
    left, top = points.min(axis=1)
    right, bottom = points.max(axis=1)
    pad = .08 * max(right-left, bottom-top)
    box = (
        max(0, int(math.floor(left-pad))),
        max(0, int(math.floor(top-pad))),
        min(source.width, int(math.ceil(right+pad))),
        min(source.height, int(math.ceil(bottom+pad))),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("invalid camera RGB crop")
    return box


def _map_points(gauge_points, matrix):
    x = np.column_stack((np.asarray(gauge_points, float),
                         np.ones(len(gauge_points), float)))
    mapped = (matrix @ x.T).T
    if np.any(abs(mapped[:, 2]) < 1e-12):
        raise ValueError("invalid camera projection")
    return mapped[:, :2] / mapped[:, 2, None]


def _gauge_polygon(mask, vertices):
    """Use the exact #80 canvas centring/scale convention from #75."""
    points = {
        f"V{j}": list(xy)
        for j, xy in enumerate(np.asarray(vertices, float))
    }
    transformed = wireframe._scaffold_points_in_gauge(
        mask, {"vertices": points}
    )
    return np.asarray([transformed[f"V{j}"] for j in range(8)], float)


def _draw_ring(draw, ring, mask, matrix, *, color, width):
    camera_points = _map_points(_gauge_polygon(mask, ring), matrix)
    points = [tuple(map(float, xy)) for xy in camera_points]
    draw.line(points + points[:1], fill=color, width=width)


def _frame_peak_dots(draw, frame_sector, u, candidate_u, mask, matrix, *,
                     color, width):
    angles = np.arange(8) * (np.pi/4)
    _, outline_radius, _, _ = steps._ray_geometry(mask, angles)
    h, w = mask.shape
    center = np.array([(w-1)/2,(h-1)/2])
    supported = []
    for sector, angle in enumerate(angles):
        peak = steps._local_peak(
            frame_sector[sector], u, candidate_u, radius=.025
        )
        if peak is None or peak["z"] is None or peak["z"] < .8:
            continue
        radius = outline_radius[sector]*peak["u"]
        xy = center + radius*np.array([np.cos(angle), np.sin(angle)])
        supported.append(xy)
    if supported:
        for x, y in _map_points(np.asarray(supported), matrix):
            draw.ellipse([x-width*1.5,y-width*1.5,
                          x+width*1.5,y+width*1.5],
                         outline=color, width=max(1,width//2))
    return len(supported)


def _annotated_panel(source, crop, record, mask, u, frame_sector, case,
                     hypothesis=None, *, held_out=False):
    panel = source.copy()
    matrix = np.asarray(
        (record.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy"
        ), float
    )
    if matrix.shape != (3, 3):
        raise ValueError("source frame lacks #80 gauge-to-camera transform")
    draw = ImageDraw.Draw(panel)
    width = max(2, int(round(max(source.size)/280)))
    _draw_ring(draw, case["outer_octagon_vertices_topology_order"], mask,
               matrix, color=(240,240,240), width=width)
    c2 = case.get("context_C2_C3_vertices_topology_order")
    if c2 is not None:
        _draw_ring(draw, c2, mask, matrix, color=(255,195,85), width=width)
    match_count = None
    if hypothesis is not None:
        color = ((255,55,115) if hypothesis["display_id"] == "A"
                 else (30,220,250))
        _draw_ring(draw, hypothesis["vertices_topology_order"], mask,
                   matrix, color=color, width=width+1)
        match_count = _frame_peak_dots(
            draw, frame_sector, u, hypothesis["u"], mask,
            matrix, color=(95,255,95), width=width+1
        )
    panel = panel.crop(crop)
    tag = ("source RGB / outer+C2" if hypothesis is None else
           f"{hypothesis['display_id']} u={hypothesis['u']:.3f} "
           f"frame sectors={match_count}/8")
    if held_out:
        tag += "  [HELD OUT]"
    header = Image.new("RGB", (panel.width, 40), (14,14,14))
    ImageDraw.Draw(header).text(
        (8, 6),
        f"src {record.get('source_index')} pos {record.get('position')} | "+tag,
        fill=(255,255,255)
    )
    output = Image.new("RGB", (panel.width, panel.height+40), "black")
    output.paste(header, (0,0))
    output.paste(panel,(0,40))
    return output


def render_case(processed, pose_output, records, all_evidence, u, case,
                destination, *, omitted=None):
    """Camera RGB triptychs: fixed original, hypothesis A, hypothesis B."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    thumbnails = []
    source_rows = []
    for index, record in enumerate(records):
        image_path = record.get("source_camera_path")
        if not image_path:
            source_rows.append({"source_index":record.get("source_index"),
                                "status":"unavailable", "reason":"no_original_RGB"})
            continue
        source = Image.open(Path(processed)/image_path).convert("RGB")
        _, mask, _ = stability._load_gauged_arrays(pose_output, record)
        matrix = np.asarray(
            (record.get("sequence_coordinate") or {}).get(
                "sequence_gauge_to_camera_xy"), float)
        if matrix.shape != (3,3):
            raise ValueError("missing gauge-to-camera transform")
        crop = _camera_crop(source, mask, matrix)
        args = (source, crop, record, mask, u, all_evidence[index], case)
        panels = [_annotated_panel(*args, hypothesis=h,
                     held_out=record.get("source_index")==omitted)
                  for h in [None]+case["hypotheses"]]
        # If the second supported hypothesis does not exist, do not invent one.
        spacing = 4
        sheet = Image.new("RGB", (
            sum(p.width for p in panels)+spacing*(len(panels)-1),
            max(p.height for p in panels)), (20,20,20))
        x = 0
        for panel in panels:
            sheet.paste(panel,(x,0))
            x+=panel.width+spacing
        name = f"source-{int(record['source_index']):04d}-RGB.jpg"
        sheet.save(destination/name,quality=91)
        thumb = sheet.copy()
        thumb.thumbnail((1260,520),Image.Resampling.LANCZOS)
        thumbnails.append(thumb)
        source_rows.append({
            "source_index":record.get("source_index"),
            "position":record.get("position"),
            "held_out":record.get("source_index")==omitted,
            "status":"camera_RGB_projected",
            "image":name,
        })
    if thumbnails:
        name = wireframe._contact_sheet(
            thumbnails, destination/"camera-RGB-contact-sheet.jpg", columns=1
        )
    else:
        name = None
    return {"contact_sheet":name, "frames":source_rows}


def _case_delta(full, candidate):
    a = full.get("v3_selected_c3_u")
    b = candidate.get("v3_selected_c3_u")
    return None if a is None or b is None else abs(a-b)


def run_stone(pose_dir, processed, output, *, certificate):
    output=Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    primary, selected, _, _ = stability._primary_fit(
        pose_dir, payload, method=validation.WINDOW_METHOD
    )
    summary={
        "certificate":certificate,
        "selected_source_indices":[r.get("source_index") for r in selected],
        "v3_primary_status":primary.get("status"),
        "v3_primary_reason":primary.get("reason"),
        "status":"unavailable",
        "cases":[],
    }
    if len(selected)<4:
        summary["reason"]="fewer_than_four_selected_views_for_ablation"
        return summary
    evidence,u,masks,_,meta=stability._load_evidence(pose_dir,selected)
    outer=outer_octagon.fit_consensus(masks,frame_metadata=meta)
    vertices=np.asarray(outer["vertices_topology_order"],float)
    full=hypothesis_case(evidence,u,vertices,source_indices=[
        r.get("source_index") for r in selected
    ])
    full["case_id"]="full"
    all_cases=[full]
    for index,record in enumerate(selected):
        case=hypothesis_case(
            np.delete(evidence,index,axis=0),u,vertices,
            source_indices=[
                r.get("source_index") for j,r in enumerate(selected)
                if j!=index
            ],
        )
        case["case_id"]=f"omit-{int(record['source_index']):04d}"
        case["omitted_source_index"]=record["source_index"]
        case["absolute_selected_C3_change_from_full"]=_case_delta(full,case)
        all_cases.append(case)
    selected_for_qc=["full"]
    ranked=sorted(
        all_cases[1:],
        key=lambda r: (-(
            r["absolute_selected_C3_change_from_full"]
            if r["absolute_selected_C3_change_from_full"] is not None
            else -1
        ), r["case_id"])
    )
    selected_for_qc.extend(row["case_id"] for row in ranked[:2])
    # The frozen LG756520111 frame-13/16 counterfactuals are predeclared.
    if certificate=="IGI-LG756520111":
        for omitted in (13,16):
            key=f"omit-{omitted:04d}"
            if key in [c["case_id"] for c in all_cases] and key not in selected_for_qc:
                selected_for_qc.append(key)
    for case in all_cases:
        if case["case_id"] in selected_for_qc:
            case["camera_RGB_QC"]=render_case(
                processed,pose_dir,selected,evidence,u,case,
                output/case["case_id"],omitted=case.get("omitted_source_index"),
            )
        summary["cases"].append(case)
    summary.update({
        "status":"measured",
        "outer_ruler":"same_full_view_octagon_in_every_leave_one_out_case",
        "outer_octagon_fit":outer,
        "selected_for_RGB_QC":selected_for_qc,
        "interpretation":(
            "Both C3 rings are hypotheses traced from image gradients, "
            "not proof of true polished facets. Camera transform is similarity "
            "normalization and frame-gauge inversion; no 3D rectification."
        ),
    })
    (output/"hypotheses.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n"
    )
    return summary


def run_source_benchmark(source_root, output, bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    validation.assert_frozen_method(validation.WINDOW_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    provenance=validation.assert_frozen_benchmark_manifest(manifest)
    source_root=Path(source_root).resolve()
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    stones=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-c3-RGB-QC-") as tmp:
        for item in manifest["bundles"]:
            certificate=item["certificate"]
            processed=Path(tmp)/certificate/"processed"
            pose_dir=Path(tmp)/certificate/"pose"
            source_manifest=Path(item["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest=Path.cwd()/source_manifest
            pipeline.run(
                source_root/certificate,processed,source_manifest,
                gain=1.0,accept_review=True,
            )
            analyse_processed_sequence(
                processed,pose_dir,persist_canonical=True
            )
            stones.append(run_stone(
                pose_dir,processed,output/"per-stone"/certificate,
                certificate=certificate
            ))
    result={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "benchmark_inputs":provenance,
        "stone_count":len(stones),
        "stones":[{
            "certificate":r["certificate"],
            "status":r["status"],
            "selected_source_indices":r["selected_source_indices"],
            "v3_primary_status":r["v3_primary_status"],
            "v3_primary_reason":r["v3_primary_reason"],
            "selected_for_RGB_QC":r.get("selected_for_RGB_QC",[]),
            "cases":[{
                "case_id":c["case_id"],
                "status":c["status"],
                "hypothesis_u":[h["u"] for h in c["hypotheses"]],
                "v3_selected_c3_u":c["v3_selected_c3_u"],
                "delta_from_full":c.get("absolute_selected_C3_change_from_full"),
                "camera_RGB_QC_path":(
                    f"per-stone/{r['certificate']}/{c['case_id']}/"
                    f"{c['camera_RGB_QC']['contact_sheet']}"
                    if c.get("camera_RGB_QC",{}).get("contact_sheet")
                    else None),
            } for c in r["cases"]],
        } for r in stones],
        "no_estimator_change":True,
        "physical_facet_identity_claim":False,
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n"
    )
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--bundle-manifest",type=Path,
                   default=Path("docs/360/benchmark/source-bundles.json"))
    args=p.parse_args()
    result=run_source_benchmark(
        args.source_root,args.output,args.bundle_manifest
    )
    for row in result["stones"]:
        print(row["certificate"],row["status"],
              "candidate hypothesis count",
              [len(c["hypothesis_u"]) for c in row["cases"]])
        for case in row["cases"]:
            print(" ",case["case_id"],
                  case["hypothesis_u"],"render",case["camera_RGB_QC_path"])


if __name__=="__main__":
    main()
