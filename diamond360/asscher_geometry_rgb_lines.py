"""Independent original-camera RGB line/corner diagnostic for Asscher #124.

Research only: no radial brightness peak location is used to detect these lines.
Outer silhouette supplies side orientation and the #80 source-camera map;
each *interior* line needs independent extended RGB evidence, and corners
are intersections of measured lines rather than scaled outer vertices.
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
from scipy.signal import find_peaks

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_outer_octagon as outer_octagon
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-camera-RGB-facet-lines/1"
POLICY = {
    "schema_version": SCHEMA,
    "image_source": "original_camera_RGB_warped_into_sequence_gauge_for_measurement",
    "frame_selection": "frozen_96_outer_octagon_selected_crown_views",
    "line_families": "eight_physical_silhouette_side_directions",
    "edge_provenance": "oriented_original_RGB_gradient_and_along_line_continuity",
    "interior_silhouette_fraction_search": [0.34, 0.78],
    "candidate_offsets_per_side": 69,
    "line_samples": 91,
    "minimum_coverage": 0.50,
    "minimum_longest_contiguous": 0.30,
    "minimum_valid_fraction": 0.80,
    "maximum_side_fraction_spread_for_polygon": 0.18,
    "minimum_detected_sides_for_polygon": 8,
    "vertices": "intersections_of_measured_neighbor_line_equations",
    "no_unobserved_side_infill": True,
    "no_radial_peak_selection": True,
    "no_production_estimator_change": True,
    "physical_facet_identity_claim": False,
}
FRACTIONS = np.linspace(*POLICY["interior_silhouette_fraction_search"],
                        POLICY["candidate_offsets_per_side"])
COLORS = [(238, 76, 113), (25, 216, 247), (251, 197, 63),
          (148, 229, 100), (238, 131, 239), (255, 164, 84),
          (118, 174, 252), (181, 141, 255)]


def outer_side_families(outer):
    """Eight exact independent line normals from measured outer polygon."""
    outer = np.asarray(outer, float)
    if outer.shape != (8, 2) or not np.isfinite(outer).all():
        raise ValueError("need finite ordered outer octagon")
    center = np.mean(outer, axis=0)
    sides = []
    for i in range(8):
        a, b = outer[i], outer[(i + 1) % 8]
        direction = b - a
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-9:
            raise ValueError("degenerate outer side")
        tangent = direction / norm
        normal = np.array([-tangent[1], tangent[0]])
        midpoint = (a + b) * 0.5
        if np.dot(normal, midpoint - center) < 0:
            normal *= -1
        dist = float(np.dot(normal, midpoint - center))
        if dist <= 0:
            raise ValueError("outer side does not face away from center")
        sides.append({
            "index": i,
            "normal": normal,
            "tangent": tangent,
            "center": center,
            "outer_distance": dist,
            "outer_side_length": norm,
        })
    return sides


def normalized_gauge(mask):
    """Exactly match #75's fitted-scaffold-to-#80-pixels scale."""
    yy, xx = np.nonzero(np.asarray(mask, bool))
    if len(xx) == 0:
        raise ValueError("gauge silhouette unavailable")
    cx, cy = float(xx.mean()), float(yy.mean())
    scale = max(float(np.max(abs(xx-cx))),float(np.max(abs(yy-cy))),1.)
    return np.array([cx, cy],float), scale


def image_to_gauge(source_rgb, gauge_mask, gauge_to_camera):
    """Resample untouched camera RGB through the *existing* exact gauge map."""
    rgb=np.asarray(source_rgb.convert("RGB"),float)/255.
    gray=rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
    m=np.asarray(gauge_to_camera,float)
    if m.shape != (3,3) or not np.isfinite(m).all():
        raise ValueError("missing valid camera map")
    h,w=gauge_mask.shape
    y,x=np.indices((h,w),dtype=float)
    xy=np.stack([x.ravel(),y.ravel(),np.ones(h*w)],axis=0)
    camera=m@xy
    valid_homog=abs(camera[2])>1e-12
    denom=np.where(valid_homog,camera[2],1.)
    sx=(camera[0]/denom).reshape(h,w)
    sy=(camera[1]/denom).reshape(h,w)
    valid=(valid_homog.reshape(h,w)
           &(sx>=0)&(sy>=0)&(sx<=source_rgb.width-1)
           &(sy<=source_rgb.height-1)
           &np.asarray(gauge_mask,bool))
    sampled=ndi.map_coordinates(gray,[sy,sx],order=1,
                                mode="constant",cval=0.)
    return sampled,valid


def longest_true_run(row):
    row=np.asarray(row,bool)
    padded=np.r_[False,row,False]
    changes=np.diff(padded.astype(np.int8))
    begins=np.flatnonzero(changes==1)
    ends=np.flatnonzero(changes==-1)
    return int(np.max(ends-begins)) if len(begins) else 0


def _line_sample(side, fraction):
    n, tangent = side["normal"],side["tangent"]
    # A free straight line, not a radial octagon formed by scaling vertices.
    # Probe a long strip around the expected side direction.
    center=side["center"] + n*side["outer_distance"]*fraction
    extent=max(.09, side["outer_side_length"]*fraction*.68)
    along=np.linspace(-extent,extent,POLICY["line_samples"])
    return center[None,:]+along[:,None]*tangent[None,:]


def _extract_line_score(gx, gy, valid, center_px, scale, side, fraction, base):
    points=_line_sample(side,float(fraction))
    px=center_px[None,:]+points*scale
    coords=[px[:,1],px[:,0]]
    is_valid=ndi.map_coordinates(valid.astype(float),coords,order=0,
                                 mode="constant",cval=0)>0.5
    if is_valid.mean()<POLICY["minimum_valid_fraction"]:
        return None
    normal=side["normal"]
    directional=np.abs(
        ndi.map_coordinates(gx,coords,order=1,mode="constant",cval=0)*normal[0]
        +ndi.map_coordinates(gy,coords,order=1,mode="constant",cval=0)*normal[1]
    )
    high=(directional>=base)&is_valid
    coverage=float(np.mean(high))
    contiguous=float(longest_true_run(high)/len(high))
    # Favor *extended* straight gradients; isolated hot pixels must not vote.
    strength=float(np.mean(np.minimum(directional/(base+1e-9),3.))*1/3)
    return {
        "fraction":float(fraction),
        "coverage":coverage,
        "longest_contiguous_fraction":contiguous,
        "strength":strength,
        "valid_fraction":float(np.mean(is_valid)),
        "score":float((coverage*.50+contiguous*.40+strength*.10)),
        "sample_start":points[0].tolist(),
        "sample_end":points[-1].tolist(),
    }


def extract_frame_lines(gray, valid, mask, outer):
    """Find scored real line segments, not prechosen radial facet boundaries."""
    gray=np.asarray(gray,float)
    valid=np.asarray(valid,bool)
    mask=np.asarray(mask,bool)
    if gray.shape!=mask.shape or valid.shape!=mask.shape:
        raise ValueError("gauge RGB and masks incompatible")
    interior=ndi.binary_erosion(mask,iterations=3)&valid
    if np.count_nonzero(interior)<256:
        return {"status":"unavailable","reason":"insufficient_RGB_support",
                "sides":[],"polygon":None}
    smooth=ndi.gaussian_filter(gray,1.0)
    gx=ndi.sobel(smooth,axis=1)/8.
    gy=ndi.sobel(smooth,axis=0)/8.
    gradient=np.hypot(gx,gy)
    base=float(np.percentile(gradient[interior],78))
    if base<1e-5:
        base=float(np.percentile(gradient[interior],99))*.65
    if base<1e-5:
        return {"status":"unavailable","reason":"no_detectable_RGB_gradients",
                "sides":[],"polygon":None}
    center,scale=normalized_gauge(mask)
    side_families=outer_side_families(outer)
    result=[]
    for side in side_families:
        responses=[
            _extract_line_score(gx,gy,interior,center,scale,side,f,base)
            for f in FRACTIONS
        ]
        scores=np.asarray([r["score"] if r is not None else 0.
                           for r in responses],float)
        maxima,_=find_peaks(scores,distance=4)
        if len(maxima)==0 and len(scores):
            maxima=np.array([int(np.argmax(scores))])
        selected=sorted(
            (responses[i] for i in maxima if responses[i] is not None
             and responses[i]["coverage"]>=POLICY["minimum_coverage"]
             and responses[i]["longest_contiguous_fraction"]>=
                 POLICY["minimum_longest_contiguous"]),
            key=lambda r:-r["score"]
        )[:3]
        result.append({
            "side":side["index"],
            "outer_normal_xy":side["normal"].tolist(),
            "outer_distance":side["outer_distance"],
            "detected_candidates":selected,
            "selected_line":selected[0] if selected else None,
            "reason":None if selected else "no_long_coherent_RGB_line",
        })
    polygon=intersect_measured_sides(outer,result)
    return {
        "status":"polygon_candidate" if polygon is not None
                 else ("partial_line_evidence" if any(
                     side["selected_line"] is not None for side in result)
                       else "unavailable"),
        "gradient_reference":base,
        "detected_side_count":sum(row["selected_line"] is not None
                                  for row in result),
        "sides":result,
        "polygon":polygon,
        "interpretation":(
            "All lines originate from oriented native camera-RGB gradient "
            "support. A closed contour is only a tentative image-plane "
            "hypothesis, never a proven physical facet boundary."
        ),
    }


def intersect_measured_sides(outer, sides):
    """No missing-side interpolation. Eight independently measured lines required."""
    if len(sides)!=8 or any(x["selected_line"] is None for x in sides):
        return None
    fractions=np.asarray([x["selected_line"]["fraction"] for x in sides])
    if np.ptp(fractions)>POLICY["maximum_side_fraction_spread_for_polygon"]:
        return None
    families=outer_side_families(outer)
    center=families[0]["center"]
    vertices=[]
    for i in range(8):
        previous=families[(i-1)%8]
        current=families[i]
        matrix=np.vstack([previous["normal"],current["normal"]])
        if abs(np.linalg.det(matrix))<.15:
            return None
        offset=np.array([
            previous["outer_distance"]*fractions[(i-1)%8],
            current["outer_distance"]*fractions[i],
        ])
        try:
            corner=center+np.linalg.solve(matrix,offset)
        except np.linalg.LinAlgError:
            return None
        vertices.append(corner)
    vertices=np.asarray(vertices,float)
    cross=np.cross(np.roll(vertices,-1,axis=0)-vertices,
                   np.roll(vertices,-2,axis=0)-np.roll(vertices,-1,axis=0))
    if not (np.all(cross>1e-5) or np.all(cross< -1e-5)):
        return None
    if any(np.max((vertices-center)@family["normal"]-
                  family["outer_distance"])>1e-6 for family in families):
        return None
    area=.5*abs(float(np.sum(vertices[:,0]*np.roll(vertices[:,1],-1)
                             -vertices[:,1]*np.roll(vertices[:,0],-1))))
    if area<1e-4:
        return None
    return {
        "vertices_topology_order":vertices.tolist(),
        "intersection_policy":"adjacent_original_RGB_supported_lines",
        "area":area,
        "side_fraction_range":[float(fractions.min()),float(fractions.max())],
        "all_sides_directly_supported":True,
        "physical_facet_identity_verified":False,
    }


def _points_to_camera(points,mask,matrix):
    center,scale=normalized_gauge(mask)
    xy=np.asarray(points,float)*scale+center
    src=np.c_[xy,np.ones(len(xy))]@np.asarray(matrix,float).T
    if np.any(abs(src[:,2])<1e-10):
        raise ValueError("invalid projected RGB line")
    return src[:,:2]/src[:,2,None]


def draw_frame(source,mask,matrix,outer,detection,*,source_index):
    """Native RGB (left) + observed segments (middle) + corners (right)."""
    source=source.convert("RGB")
    bbox=_points_to_camera(np.asarray(outer,float),mask,matrix)
    left,top=bbox.min(axis=0)
    right,bottom=bbox.max(axis=0)
    pad=.11*max(right-left,bottom-top)
    crop=(max(0,int(left-pad)),max(0,int(top-pad)),
          min(source.width,int(right+pad)),min(source.height,int(bottom+pad)))
    if crop[2]<=crop[0] or crop[3]<=crop[1]:
        raise ValueError("invalid source camera crop")
    panels=[source.copy() for _ in range(3)]
    width=max(2,int(max(source.size)/260))
    for j in (1,2):
        draw=ImageDraw.Draw(panels[j])
        outside=[tuple(x) for x in bbox]
        draw.line(outside+outside[:1],fill=(245,245,245),width=width)
        for row in detection["sides"]:
            line=row["selected_line"]
            if line is None:
                continue
            camera=_points_to_camera(
                [line["sample_start"],line["sample_end"]],mask,matrix
            )
            draw.line([tuple(v) for v in camera],
                      fill=COLORS[row["side"]],width=width+1)
        if j==2 and detection["polygon"] is not None:
            points=_points_to_camera(
                detection["polygon"]["vertices_topology_order"],mask,matrix
            )
            for x,y in points:
                draw.ellipse((x-3*width,y-3*width,x+3*width,y+3*width),
                             outline=(255,255,255),width=width)
    labels=["Original camera RGB",
            "Observed straight-line candidates",
            "Actual intersections (only if all 8 pass)"]
    cropped=[]
    for panel,label in zip(panels,labels):
        part=panel.crop(crop)
        with_header=Image.new("RGB",(part.width,part.height+50),(16,16,16))
        with_header.paste(part,(0,50))
        d=ImageDraw.Draw(with_header)
        d.text((7,6),f"src {source_index} | {label}",fill="white")
        d.text((7,25),f"evidence {detection['detected_side_count']}/8 | {detection['status']}",
               fill=(215,215,215))
        cropped.append(with_header)
    spacing=5
    output=Image.new("RGB",(
        sum(im.width for im in cropped)+spacing*2,
        max(im.height for im in cropped)),(20,20,20))
    x=0
    for im in cropped:
        output.paste(im,(x,0))
        x+=im.width+spacing
    return output


def run_stone(pose_dir,processed,output,*,certificate):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    payload=json.loads((Path(pose_dir)/"asscher-pose.json").read_text())
    primary,records,_,_=stability._primary_fit(
        pose_dir,payload,method=validation.OUTER_METHOD
    )
    summary={
        "certificate":certificate,
        "selected_source_indices":[r["source_index"] for r in records],
        "selected_face_roles":[r.get("face_role") for r in records],
        "pose_face_selection":payload.get("face_selection"),
        "frozen_outer_method":validation.OUTER_METHOD,
        "status":"unavailable",
        "frames":[],
        "cross_frame_support":[],
    }
    if len(records)<3:
        summary["reason"]="insufficient_frozen_crown_views"
        return summary
    evidence,u,masks,brightness,metadata=stability._load_evidence(
        pose_dir,records
    )
    outer=outer_octagon.fit_consensus(masks,frame_metadata=metadata)
    vertices=np.asarray(outer["vertices_topology_order"],float)
    summary["outer_vertices_topology_order"]=vertices.tolist()
    rows=[]
    for record,mask in zip(records,masks):
        source_path=record.get("source_camera_path")
        matrix=(record.get("sequence_coordinate") or {}).get(
            "sequence_gauge_to_camera_xy")
        if not source_path or matrix is None:
            rows.append({
                "source_index":record["source_index"],"status":"unavailable",
                "reason":"missing_original_camera_RGB_or_gauge_transform",
            })
            continue
        source=Image.open(Path(processed)/source_path).convert("RGB")
        image,valid=image_to_gauge(source,mask,matrix)
        detected=extract_frame_lines(image,valid,mask,vertices)
        qc=draw_frame(source,mask,matrix,vertices,detected,
                      source_index=record["source_index"])
        name=f"source-{int(record['source_index']):04d}-native-RGB.jpg"
        qc.save(output/name,quality=92)
        rows.append({
            "source_index":record["source_index"],
            "position":record.get("position"),
            "face_role":record.get("face_role"),
            "camera_RGB_QC":name,
            "gauge_transform_used":True,
            **detected,
        })
    summary["frames"]=rows
    for i in range(8):
        observed=[
            (row["source_index"],
             row["sides"][i]["selected_line"]["fraction"])
            for row in rows
            if len(row.get("sides",[]))==8
            and row["sides"][i]["selected_line"] is not None
        ]
        frac=np.asarray([x[1] for x in observed],float)
        summary["cross_frame_support"].append({
            "side":i,
            "observed_source_indices":[x[0] for x in observed],
            "observed_frame_count":len(observed),
            "fraction_median":float(np.median(frac)) if len(frac) else None,
            "fraction_range":[float(frac.min()),float(frac.max())]
                             if len(frac) else None,
        })
    summary["status"]="rendered" if any("camera_RGB_QC" in r for r in rows) else "unavailable"
    summary["polygon_candidate_frame_count"]=sum(
        r.get("polygon") is not None for r in rows)
    summary["original_outer_method_unchanged"]=True
    summary["physical_facet_claim"]=False
    summary["warning"]=(
        "Long contrast lines can still be virtual or reflected facets. "
        "No geometry should be selected from this diagnostic without "
        "manual original-camera RGB review."
    )
    (output/"line-evidence.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n"
    )
    images=[]
    for r in rows:
        if r.get("camera_RGB_QC"):
            pic=Image.open(output/r["camera_RGB_QC"]).convert("RGB")
            pic.thumbnail((1300,490),Image.Resampling.LANCZOS)
            images.append(pic.copy())
    if images:
        wireframe._contact_sheet(
            images,output/"native-RGB-line-contact-sheet.jpg",columns=1)
    return summary


def run_source_benchmark(source_root,output,bundle_manifest):
    validation.assert_frozen_method(validation.OUTER_METHOD)
    manifest=json.loads(Path(bundle_manifest).read_text())
    validation.assert_frozen_benchmark_manifest(manifest)
    source_root=Path(source_root).resolve()
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    overview=[]
    with tempfile.TemporaryDirectory(prefix="sparkles-rgb-lines-") as tmp:
        for bundle in manifest["bundles"]:
            cert=bundle["certificate"]
            processed=Path(tmp)/cert/"processed"
            pose=Path(tmp)/cert/"pose"
            m=Path(bundle["source_manifest"])
            if not m.is_absolute():
                m=Path.cwd()/m
            pipeline.run(source_root/cert,processed,m,gain=1.0,
                         accept_review=True)
            analyse_processed_sequence(processed,pose,persist_canonical=True)
            data=run_stone(pose,processed,output/"per-stone"/cert,
                           certificate=cert)
            overview.append({
                "certificate":cert,
                "status":data["status"],
                "selected_source_indices":data["selected_source_indices"],
                "selected_face_roles":data["selected_face_roles"],
                "polygon_candidate_frame_count":data.get("polygon_candidate_frame_count",0),
                "per_side":data["cross_frame_support"],
                "QC_contact_sheet":(
                    f"per-stone/{cert}/native-RGB-line-contact-sheet.jpg"
                    if data["status"]=="rendered" else None
                ),
            })
    report={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "benchmark_manifest_canonical_sha256":
            validation.BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "stones":overview,
        "method_change":False,
        "interpretation":"diagnostic line and corner evidence, not polished facet identity",
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
    for stone in report["stones"]:
        print(stone["certificate"],stone["status"],
              "octagon candidate frames",stone["polygon_candidate_frame_count"])
        for side in stone["per_side"]:
            print(" side",side["side"],"observed frames",
                  side["observed_frame_count"],"fraction",
                  side["fraction_median"])


if __name__=="__main__":
    main()
