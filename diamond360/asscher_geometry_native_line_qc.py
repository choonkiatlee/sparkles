"""#124: independent image-line and observed-corner diagnostic, NOT a fitter.

LSD line segments are observed in original camera RGB warped only by the
existing #80 sequence-gauge transform. No radius u is preselected and no
closed facet polygon is inferred from eight independently guessed radii.
An intersection exists only when the *observed finite segments* reach it.
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
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-native-facet-line-diagnostic/1"
POLICY = {
    "schema_version": SCHEMA,
    "representation": "observed finite line segments and observed adjacent-family intersections",
    "detector": "OpenCV LSD standard, candidate spans measured on original camera RGB in #80 gauge",
    "roi_fraction_of_outer_normal_distance": [0.25, 0.90],
    "max_orientation_difference_degrees": 13.0,
    "minimum_length_fraction_of_outer_side": 0.12,
    "max_intersection_extrapolation_fraction_of_diameter": 0.022,
    "minimum_intersection_angle_degrees": 18.0,
    "max_segments_per_direction_family": 18,
    "no_fixed_C3_radius_or_ring_fit": True,
    "unavailable_if_no_supported_polygon": True,
    "physical_facet_identity_claim": False,
    "held_out_views_do_not_vote": True,
    "manual_source_stress_only": True,
}


def _unit(vec):
    v = np.asarray(vec, float)
    norm = float(np.linalg.norm(v))
    if not np.isfinite(norm) or norm <= 1e-9:
        raise ValueError("zero-length edge")
    return v / norm


def outline_families(outer_vertices):
    """Return observed outer side directions and outward normals; no ideal angle."""
    points = np.asarray(outer_vertices, float)
    if points.shape != (8, 2) or not np.isfinite(points).all():
        raise ValueError("expected eight finite outer vertices")
    center = np.mean(points, axis=0)
    rows = []
    for i, start in enumerate(points):
        finish = points[(i + 1) % 8]
        tangent = _unit(finish - start)
        midpoint = (start + finish) / 2.0
        normal = np.array([-tangent[1], tangent[0]])
        if float(normal @ (midpoint - center)) < 0:
            normal = -normal
        offset = float(normal @ (midpoint - center))
        rows.append({
            "family": i,
            "tangent": tangent.tolist(),
            "normal": normal.tolist(),
            "outer_offset": offset,
            "outer_side_length": float(np.linalg.norm(finish - start)),
        })
    return rows


def _wrapped_line_angle(tangent1, tangent2):
    return float(math.degrees(math.acos(
        min(1.0, abs(float(np.dot(_unit(tangent1), _unit(tangent2)))))
    )))


def _segment_projection(segment, families, centre, *, diameter):
    a = np.asarray(segment[:2], float)
    b = np.asarray(segment[2:4], float)
    length = float(np.linalg.norm(b - a))
    if length < 5:
        return None
    tangent = (b - a) / length
    midpoint = (a + b) / 2.0
    rows = []
    for family in families:
        normal = np.asarray(family["normal"], float)
        offset = family["outer_offset"]
        ratio = float(np.dot(midpoint - centre, normal)) / max(offset, 1e-9)
        orientation = _wrapped_line_angle(tangent, family["tangent"])
        if not (0.25 <= ratio <= 0.90):
            continue
        if orientation > POLICY["max_orientation_difference_degrees"]:
            continue
        if length < max(5.0, family["outer_side_length"] * 0.12):
            continue
        # Segment is meaningful only if its sampled normal offsets are
        # reasonably constant along the *observed finite* segment.
        u_start = float(np.dot(a - centre, normal)) / offset
        u_finish = float(np.dot(b - centre, normal)) / offset
        if abs(u_start - u_finish) > 0.045:
            continue
        rows.append((orientation, abs(ratio - 0.55), family["family"], ratio))
    if not rows:
        return None
    _, _, fam, ratio = min(rows)
    return {
        "family": int(fam),
        "p0": [float(x) for x in a],
        "p1": [float(x) for x in b],
        "length_px": length,
        "normal_fraction_of_outer": ratio,
        "angular_error_degrees": float(
            _wrapped_line_angle(tangent, families[fam]["tangent"])
        ),
    }


def segment_intersection(first, second, *, max_extension_px):
    """Intersect finite observed segments; do not extrapolate distant lines."""
    p = np.asarray(first["p0"], float)
    a = np.asarray(first["p1"], float) - p
    q = np.asarray(second["p0"], float)
    b = np.asarray(second["p1"], float) - q
    cross = float(a[0] * b[1] - a[1] * b[0])
    if abs(cross) < 1e-7:
        return None
    d = q - p
    t = float((d[0] * b[1] - d[1] * b[0]) / cross)
    v = float((d[0] * a[1] - d[1] * a[0]) / cross)
    a_length = float(np.linalg.norm(a))
    b_length = float(np.linalg.norm(b))
    if not (-max_extension_px/a_length <= t <= 1+max_extension_px/a_length
            and -max_extension_px/b_length <= v <= 1+max_extension_px/b_length):
        return None
    xy = p + t*a
    return [float(x) for x in xy]


def _in_mask(mask, x, y):
    h, w = mask.shape
    ix, iy = int(round(x)), int(round(y))
    return 0 <= ix < w and 0 <= iy < h and bool(mask[iy, ix])


def observed_junctions(segments, mask, *, diameter):
    """Propose corners only at finite LSD segment intersections.

    Adjacent direction *families* are a topological prior, not evidence
    that the two meeting lines delimit a physical polished facet.
    """
    rows = []
    per_family = [
        sorted((s for s in segments if s["family"] == i),
               key=lambda s: -s["length_px"])[:18]
        for i in range(8)
    ]
    max_extension = 0.022*float(diameter)
    for family in range(8):
        for a in per_family[family]:
            for b in per_family[(family+1) % 8]:
                angle = _wrapped_line_angle(
                    np.asarray(a["p1"])-a["p0"],
                    np.asarray(b["p1"])-b["p0"],
                )
                if angle < 18:
                    continue
                pt = segment_intersection(a, b, max_extension_px=max_extension)
                if pt is None or not _in_mask(mask, *pt):
                    continue
                if any(r["family_pair"] == [family, (family+1) % 8] and
                       np.linalg.norm(np.asarray(r["point_gauge_xy"])-pt)
                       < diameter*0.022 for r in rows):
                    continue
                rows.append({
                    "family_pair": [family, (family+1) % 8],
                    "point_gauge_xy": pt,
                    "crossing_angle_degrees": angle,
                    "supporting_lengths_px": [a["length_px"], b["length_px"]],
                })
    return rows


def _gauge_rgb(source, record, size):
    """Sample native RGB into the fixed gauge using the exact inverse map."""
    m = np.asarray(
        (record.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy"
        ), float
    )
    if m.shape != (3, 3) or not np.isfinite(m).all():
        raise ValueError("missing exact gauge-to-camera transform")
    if abs(m[2, 0]) > 1e-8 or abs(m[2, 1]) > 1e-8:
        raise ValueError("non-affine camera-to-gauge map unsupported")
    if abs(m[2,2]) < 1e-12:
        raise ValueError("invalid camera-to-gauge projection")
    m = m / m[2,2]
    rgb = source.transform(
        size, Image.Transform.AFFINE,
        tuple(float(x) for x in m[:2].reshape(-1)),
        resample=Image.Resampling.BILINEAR,
    )
    return np.asarray(rgb, np.uint8), m


def _detect_lsd_segments(rgb):
    # Research tool: optional dependency; do not alter production runtime.
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "Install opencv-python-headless to run research line diagnostics"
        ) from exc
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8,8))
    enhanced = clahe.apply(grey)
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = detector.detect(enhanced)[0]
    if lines is None:
        return []
    return [list(map(float, row)) for row in lines.reshape(-1,4)]


def _camera_points(points, matrix):
    points = np.asarray(points, float)
    ones = np.ones((len(points),1),float)
    out = (matrix @ np.column_stack((points,ones)).T).T
    if np.any(abs(out[:,2]) < 1e-9):
        raise ValueError("line projection singular")
    return out[:,:2]/out[:,2,None]


def _original_rgb_qc(source, record, mask, segments, junctions, outer_vertices,
                     matrix, destination, *, max_lines=160):
    """Draw *detected lines*, never a reconstructed ring, in camera pixels."""
    from PIL import ImageFont
    image=source.copy()
    draw=ImageDraw.Draw(image)
    palette=[(255,100,84),(255,184,68),(236,236,92),(92,238,143),
             (73,214,255),(99,139,255),(193,99,242),(250,107,205)]
    for row in sorted(segments,key=lambda s:-s["length_px"])[:max_lines]:
        xy=_camera_points([row["p0"], row["p1"]],matrix)
        draw.line([tuple(xy[0]),tuple(xy[1])],
                  fill=palette[row["family"]],width=max(2,source.width//380))
    for row in junctions:
        xy=_camera_points([row["point_gauge_xy"]],matrix)[0]
        x,y=map(float,xy)
        rr=max(3,int(source.width/180))
        draw.ellipse((x-rr,y-rr,x+rr,y+rr),
                     outline=(255,255,255),width=max(2,rr//2))
    # Crop by the untouched silhouette footprint projected into camera.
    yy,xx=np.nonzero(mask)
    if len(xx):
        corners=_camera_points([
            (xx.min(),yy.min()), (xx.max(),yy.min()),
            (xx.max(),yy.max()), (xx.min(),yy.max()),
        ],matrix)
        left,top=corners.min(axis=0)
        right,bottom=corners.max(axis=0)
        pad=.07*max(right-left,bottom-top)
        box=(max(0,int(left-pad)),max(0,int(top-pad)),
             min(image.width,int(right+pad+1)),min(image.height,int(bottom+pad+1)))
        if box[2]>box[0] and box[3]>box[1]:
            image=image.crop(box)
            clean=source.crop(box)
        else:
            clean=source
    else:
        clean=source
    new=Image.new("RGB",(clean.width+image.width+8,max(clean.height,image.height)+33),
                  (12,12,12))
    new.paste(clean,(0,33))
    new.paste(image,(clean.width+8,33))
    label=f"src {record.get('source_index')} pos {record.get('position')} {record.get('face_role')} | native RGB / observed segments + candidate intersections"
    ImageDraw.Draw(new).text((7,9),label,fill="white")
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    new.save(destination,quality=90)
    return destination.name


def inspect_frame(source, record, mask, outer_vertices, *, destination):
    image=Image.open(source).convert("RGB")
    h,w=mask.shape
    gauge,matrix=_gauge_rgb(image,record,(w,h))
    pts=wireframe._scaffold_points_in_gauge(
        mask,{"vertices":{f"v{i}":p for i,p in enumerate(outer_vertices)}}
    )
    polygon=np.asarray([pts[f"v{i}"] for i in range(8)],float)
    centre=np.mean(polygon,axis=0)
    families=outline_families(polygon)
    diameter=2*max(np.linalg.norm(polygon-centre,axis=1))
    detected=_detect_lsd_segments(gauge)
    matched=[]
    for line in detected:
        s=_segment_projection(line,families,centre,diameter=diameter)
        if s is not None and all(_in_mask(mask,*q) for q in (s["p0"],s["p1"])):
            matched.append(s)
    junctions=observed_junctions(matched,mask,diameter=diameter)
    family_coverage=sorted({s["family"] for s in matched})
    corner_coverage=sorted({r["family_pair"][0] for r in junctions})
    saved=_original_rgb_qc(
        image,record,mask,matched,junctions,polygon,matrix,destination
    )
    return {
        "source_index":record.get("source_index"),
        "position":record.get("position"),
        "face_role":record.get("face_role"),
        "pose_status":(record.get("assessment") or {}).get("status"),
        "source_original_rgb":str(record.get("source_camera_path")),
        "original_rgb_qc":saved,
        "raw_detected_segment_count":len(detected),
        "candidate_segment_count":len(matched),
        "covered_side_families":family_coverage,
        "observed_corner_families":corner_coverage,
        "candidate_junction_count":len(junctions),
        "segments":matched,
        "junctions":junctions,
        "polygon_fit_status":"unavailable_not_attempted_without_tracked_junction_cycle",
        "physical_facet_identity_claim":False,
    }


def run_stone(processed, pose_dir, out, *, certificate):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    payload=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    primary, selected, _, _=stability._primary_fit(
        pose_dir,payload,method=validation.OUTER_METHOD
    )
    result={
        "schema_version":SCHEMA,"certificate":certificate,
        "selected_source_indices":[r["source_index"] for r in selected],
        "face_selection":payload.get("face_selection"),
        "primary_frozen_geometry_status":primary.get("status"),
        "status":"unavailable",
        "frames":[],
        "physical_facet_identity_claim":False,
    }
    if len(selected)<3 or primary.get("scaffold") is None:
        result["reason"]="no_frozen_outer_scaffold"
    else:
        outer=np.asarray([
            primary["scaffold"]["vertices"][f"GIRDLE_OUTLINE_V{i}"]
            for i in range(8)
        ],float)
        thumbs=[]
        for record in selected:
            _,mask,_=stability._load_gauged_arrays(pose_dir,record)
            src=Path(processed)/record["source_camera_path"]
            if not src.is_file():
                result["frames"].append({"source_index":record["source_index"],
                    "status":"unavailable_missing_original_RGB"})
                continue
            frame=inspect_frame(
                src,record,mask,outer,
                destination=out/f"source-{int(record['source_index']):04d}-lines.jpg",
            )
            result["frames"].append(frame)
            img=Image.open(out/frame["original_rgb_qc"]).convert("RGB")
            img.thumbnail((1000,400))
            thumbs.append(img)
        sheet=wireframe._contact_sheet(
            thumbs,out/"camera-RGB-line-intersections.jpg",columns=1
        )
        result.update({
            "status":"diagnostic_only",
            "camera_RGB_contact_sheet":sheet,
            "frozen_outer_vertices_topology_order":outer.tolist(),
            "reason":"physical_C3_facet_boundary_not_established",
        })
    (out/"diagnostic.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n"
    )
    return result


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    stones=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-native-line-qc-") as temp:
        for item in manifest["bundles"]:
            cert=item["certificate"]
            processed=Path(temp)/cert/"processed"
            pose_dir=Path(temp)/cert/"pose"
            source_manifest=Path(item["source_manifest"])
            if not source_manifest.is_absolute():
                source_manifest=Path.cwd()/source_manifest
            pipeline.run(
                Path(source_root)/cert,processed,source_manifest,
                gain=1.0,accept_review=True
            )
            analyse_processed_sequence(processed,pose_dir,persist_canonical=True)
            stones.append(run_stone(
                processed,pose_dir,output/"per-stone"/cert,certificate=cert
            ))
    summary={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "stones":[{
            "certificate":r["certificate"],
            "status":r["status"],
            "selected_source_indices":r["selected_source_indices"],
            "face_selection":r.get("face_selection"),
            "camera_RGB_contact_sheet":(
                f"per-stone/{r['certificate']}/{r.get('camera_RGB_contact_sheet')}"
                if r.get("camera_RGB_contact_sheet") else None),
            "frames":[{
                "source_index":f["source_index"],
                "family_coverage":len(f.get("covered_side_families",[])),
                "junction_family_coverage":len(f.get("observed_corner_families",[])),
                "polygon_fit_status":f.get("polygon_fit_status"),
            } for f in r["frames"]],
        } for r in stones],
        "estimator_unchanged":True,
        "physical_facet_identity_claim":False,
    }
    (output/"summary.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n"
    )
    return summary


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--bundle-manifest",type=Path,default=Path(
        "docs/360/benchmark/source-bundles.json"))
    args=ap.parse_args()
    result=run_source_benchmark(
        args.source_root,args.output,args.bundle_manifest)
    for s in result["stones"]:
        print(s["certificate"],s["status"],
              [(r["source_index"],r["family_coverage"],r["junction_family_coverage"])
               for r in s["frames"]])


if __name__=="__main__":
    main()
