"""Target-blind 3-D Asscher-like pavilion simulator and held-out contour benchmark.

This is a *synthetic generative model*, not an inverse physical-angle
estimator and not proof that every projected silhouette bend is a P1/P2/P3
facet junction. Four concentric bevelled-square rings make three physical
pavilion bands (tip→P3→P2→P1→girdle), then orthographic camera projection
and projected-triangle scanlines produce the **union's exterior**.

No archived DiaGem image, physical photo-angle targets, PriceScope expert
readings, interior optical features, or manually corrected points are read.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_profile_pavilion_refinement as existing_fit

SCHEMA = "diamond360-asscher-synthetic-pavilion-observability/1"
GENERATOR_POLICY = {
    "surface": "three_facet_bands_between_four_bevelled_square_rings",
    "tier_order_top_to_bottom": ["tip_to_P3", "P3_to_P2", "P2_to_P1_girdle"],
    "mesh": "8_corresponding_vertices_per_ring_two_triangles_per_panel_plus_caps",
    "projection": "orthographic_yaw_tilt_roll_no_perspective",
    "silhouette": "projected_triangle_union_scanline_NOT_convex_hull",
    "sample": "integer_source_image_y_center",
    "support": "independent_seeded_missing_rows_no_interpolation",
    "baseline": "preexisting_unmodified_source_outline_hinge_fit",
    "baseline_penalty": existing_fit.POLICY["default_penalty_px2"],
    "max_visible_stretches": existing_fit.POLICY["maximum_apparent_stretches_per_side"],
    "holdout": "every_fifth_supported_row_with_index_modulo_5_eq_0",
    "no_external_photo_or_expert_target_access": True,
    "physical_facet_angle_status": "not_measured_from_image",
}


@dataclass(frozen=True)
class Shape:
    """Heights from upper pavilion tip (0) toward widest girdle region (1)."""
    levels_y: tuple[float, float, float, float]
    radii: tuple[float, float, float, float]
    corner_cut: float = 0.20
    left_width: float = 1.0
    right_width: float = 1.0

    def validate(self):
        if len(self.levels_y) != 4 or len(self.radii) != 4:
            raise ValueError("exactly four ring levels needed for three physical bands")
        v = list(self.levels_y) + list(self.radii) + [
            self.corner_cut, self.left_width, self.right_width
        ]
        if not all(math.isfinite(x) for x in v):
            raise ValueError("all geometry parameters must be finite")
        if self.levels_y[0] != 0 or self.levels_y[-1] != 1:
            raise ValueError("axial coordinates must start at tip 0 and end at girdle 1")
        if self.radii[-1] != 1 or not 0 <= self.radii[0] <= 0.06:
            raise ValueError("girdle radius normalized to 1; culet-region tip small")
        if min(np.diff(self.levels_y)) < 0.12 or min(np.diff(self.radii)) < 0.04:
            raise ValueError("ring heights/radii must increase with positive finite bands")
        if not 0.08 <= self.corner_cut <= 0.35:
            raise ValueError("invalid Asscher corner truncation")
        if not 0.85 <= self.left_width <= 1.15 or not 0.85 <= self.right_width <= 1.15:
            raise ValueError("unsupported lateral asymmetry")
        return self


@dataclass(frozen=True)
class Camera:
    """Projection is deliberately independent of image-source assumptions."""
    yaw_deg: float = 0.0
    tilt_deg: float = 0.0
    roll_deg: float = 0.0
    scale_px: float = 120.0
    center_x_px: float = 205.0
    tip_y_px: float = 53.0

    def validate(self):
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise ValueError("non-finite camera parameter")
        if abs(self.yaw_deg) > 45 or abs(self.tilt_deg) > 20 or abs(self.roll_deg) > 15:
            raise ValueError("this benchmark only models near-profile views")
        if not 40 <= self.scale_px <= 200:
            raise ValueError("camera image scale outside benchmark range")
        return self


def mesh(shape: Shape):
    """Return vertices N×3 in (x, down-axis-y, transverse-z), triangles M×3."""
    shape.validate()
    vertices = []
    for y, radius in zip(shape.levels_y, shape.radii):
        cut = radius * (1 - shape.corner_cut)
        # 8 corners in circumference order, independent of mesh orientation.
        outline = [(-cut, -radius), (cut, -radius), (radius, -cut),
                   (radius, cut), (cut, radius), (-cut, radius),
                   (-radius, cut), (-radius, -cut)]
        for x, z in outline:
            x *= shape.left_width if x < 0 else shape.right_width
            vertices.append((x, y, z))
    triangles = []
    for tier in range(3):
        a, b = 8*tier, 8*(tier+1)
        for k in range(8):
            j = (k+1) % 8
            triangles.extend([(a+k, b+k, b+j), (a+k, b+j, a+j)])
    # Tip and girdle caps close the synthetic solid. They are not visible
    # polished "culet facets" or a physical crown/table model.
    for start in (0, 24):
        for k in range(1, 7):
            triangles.append((start, start+k, start+k+1))
    return np.asarray(vertices, float), np.asarray(triangles, int)


def project(vertices, camera: Camera):
    """Orthographic projected image coordinates (x right, y down)."""
    camera.validate()
    yaw, tilt, roll = (math.radians(v) for v in
                       (camera.yaw_deg, camera.tilt_deg, camera.roll_deg))
    x, y, z = vertices.T
    u = math.cos(yaw)*x + math.sin(yaw)*z
    depth = -math.sin(yaw)*x + math.cos(yaw)*z
    v = math.cos(tilt)*y + math.sin(tilt)*depth
    xx = math.cos(roll)*u - math.sin(roll)*v
    yy = math.sin(roll)*u + math.cos(roll)*v
    return np.column_stack([
        camera.center_x_px + camera.scale_px*xx,
        camera.tip_y_px + camera.scale_px*yy,
    ])


def _triangle_row_intersections(poly, y):
    """Return intersections with one projected filled triangle scanline."""
    xs = []
    for p, q in ((poly[0], poly[1]), (poly[1], poly[2]), (poly[2], poly[0])):
        a, b = float(p[1]), float(q[1])
        if (min(a,b) <= y <= max(a,b)):
            if abs(b-a) < 1e-10:
                xs.extend([float(p[0]), float(q[0])])
            else:
                t = (y-a)/(b-a)
                if -1e-9 <= t <= 1+1e-9:
                    xs.append(float(p[0] + t*(q[0]-p[0])))
    return xs


def silhouette(shape: Shape, camera: Camera):
    """Image-plane envelope of UNION of projected filled mesh triangles.

    Crucially this is *not* the convex hull of projected vertices. A pavilion
    silhouette may have inward kinks at tier transitions which hulls erase.
    """
    vertices, triangles = mesh(shape)
    xy = project(vertices, camera)
    faces = xy[triangles]
    ys = np.arange(math.ceil(float(xy[:, 1].min())),
                   math.floor(float(xy[:, 1].max()))+1, dtype=int)
    envelope = []
    for y in ys:
        left, right = math.inf, -math.inf
        for tri in faces:
            if y < float(tri[:,1].min()) or y > float(tri[:,1].max()):
                continue
            cross = _triangle_row_intersections(tri, float(y))
            if cross:
                left = min(left, min(cross))
                right = max(right, max(cross))
        if math.isfinite(left) and math.isfinite(right) and right >= left:
            envelope.append([round(float(left), 5), int(y), round(float(right), 5)])
    return np.asarray(envelope, dtype=float).reshape(-1, 3)


def projected_tier_visibility(shape: Shape, camera: Camera, min_slope_jump=0.22):
    """Synthetic-only observability oracle with precise scope.

    For an untilted orthographic *profile*, three physical bands can map to
    one, two, or three distinguishable line stretches in the external
    envelope. For tilt/roll we deliberately decline any 1:1 ring/break
    correspondence: different mesh generators may enter/leave silhouette.
    This oracle NEVER runs on or labels a real photograph.
    """
    shape.validate()
    camera.validate()
    if abs(camera.tilt_deg) > 1e-10 or abs(camera.roll_deg) > 1e-10:
        return {
            "status": "not_identifiable_by_single_ring_rows_under_oblique_pose",
            "physical_band_count": 3,
            "observable_stretch_count": None,
            "projected_ring_break_correspondence": "unknown",
        }
    radius_scale = max(
        float(project(np.array([[1.,0.,0.],[0.,0.,0.]]),camera)[0,0] -
              project(np.array([[1.,0.,0.],[0.,0.,0.]]),camera)[1,0]),
        0.01,
    ) / camera.scale_px
    # Using the ring generator's actual synthetic radii is legitimate as an
    # oracle; the estimator never sees these synthetic truth parameters.
    slopes = np.diff(shape.radii) / np.diff(shape.levels_y) * radius_scale
    if not all(np.isfinite(slopes)):
        return {"status":"unavailable","physical_band_count":3}
    jumps = np.abs(np.diff(slopes))
    observable = [bool(v >= min_slope_jump) for v in jumps]
    return {
        "status": "synthetic_untilted_profile_oracle_only",
        "physical_band_count": 3,
        "observable_stretch_count": 1 + sum(observable),
        "per_ring_junction_visible": observable,
        "projected_relative_slopes": [round(float(x),5) for x in slopes],
        "minimum_detectable_projected_slope_jump": min_slope_jump,
        "projected_ring_break_correspondence":
            "synthetic_truth_only_not_inferred_for_real_images",
    }


def observe(envelope, seed: int, missing_intervals=(), noise_px=0.0,
            x_bias_px=(0.0, 0.0), synthetic_internal_stripes=False):
    """Simulate *exterior observations*; stripes are negative controls only."""
    if not isinstance(seed, int) or not 0 <= noise_px <= 3.0:
        raise ValueError("seed must be int and source-position noise within [0,3]")
    random = np.random.default_rng(seed)
    out = {"left": [], "right": []}
    for left, y, right in envelope:
        yy = int(y)
        if any(a <= yy <= b for a, b in missing_intervals):
            continue
        for side, x, bias in (("left",left,x_bias_px[0]),
                              ("right",right,x_bias_px[1])):
            source_x = float(x + bias + random.normal(0, noise_px))
            out[side].append({
                "xy_px": [round(source_x, 4), yy],
                "weight": 1.0,
                "provenance": "synthetic_projected_external_silhouette",
            })
    # By construction, synthetic virtual stripes exist only in the rendered
    # image, NEVER in contour observations fed into geometry fitting.
    return out


def synthetic_scene(shape, camera, seed, missing_intervals=(),
                    noise_px=0.0, stripes=False):
    edges = silhouette(shape, camera)
    observed = observe(edges, seed, missing_intervals, noise_px,
                       synthetic_internal_stripes=stripes)
    return {
        "shape": asdict(shape), "camera": asdict(camera),
        "three_physical_bands": GENERATOR_POLICY["tier_order_top_to_bottom"],
        "physical_boundary_vertices": [0, 8, 16, 24],
        "physical_plane_angles_from_image": None,
        "source_observations": observed,
        "ideal_exterior_silhouette_xy": edges.tolist(),
        "unobserved_intervals_y_px": [list(v) for v in missing_intervals],
        "internal_optical_stripes_present_but_excluded": stripes,
        "geometry_provenance": "fully_synthetic_and_expert_target_blind",
    }


def _estimated_x(model, y):
    beta=model["beta"]
    return float(beta[0] + beta[1]*y + sum(
        c*max(0,y-b) for c,b in zip(beta[2:],model["break_y_px"])))


def evaluate_scene(scene):
    """Frozen, predeclared fit to train-only rows; test on unseen image rows."""
    answer={}
    for side in ("left","right"):
        rows=scene["source_observations"][side]
        train=[p for i,p in enumerate(rows) if i%5!=0]
        heldout=[p for i,p in enumerate(rows) if i%5==0]
        fit=existing_fit._fit(train,existing_fit.POLICY["default_penalty_px2"])
        if fit is None or not heldout:
            answer[side]={"status":"unavailable","reason":"insufficient_observed_external_support",
                          "training_rows":len(train),"heldout_rows":len(heldout)}
            continue
        sq=[(_estimated_x(fit,p["xy_px"][1])-p["xy_px"][0])**2 for p in heldout]
        answer[side]={
            "status":"synthetic_image_plane_evaluation",
            "selected_projected_stretches":fit["segment_count"],
            "predicted_image_break_y_px":fit["break_y_px"],
            "heldout_outer_edge_rmse_px":round(float(np.sqrt(np.mean(sq))),4),
            "training_rows":len(train),"heldout_rows":len(heldout),
            "provenance":"image_plane_fit_not_P1_P2_P3_physical_correspondence",
        }
    return answer


# Fixed synthetic-only dev/holdout programs. Heldout shapes and poses must NOT
# be used to select complexity penalties or tune the source silhouette fitter.
CASES = (
    ("dev", "level_three_tiers", Shape((0,.26,.60,1),(.02,.16,.48,1),.20),Camera(),11,(),.15,False),
    ("dev", "near_collinear_three_physical_tiers",Shape((0,.33,.66,1),(.02,.345,.667,1),.16),Camera(),12,(),.2,True),
    ("dev", "one_missing_early_tier",Shape((0,.25,.60,1),(.02,.18,.55,1),.30),Camera(),13,((72,88),),.4,False),
    ("holdout", "heldout_step_proportions",Shape((0,.18,.53,1),(.01,.14,.43,1),.27),Camera(yaw_deg=14),101,(),.6,True),
    ("holdout", "heldout_oblique_pose",Shape((0,.37,.70,1),(.02,.32,.64,1),.11),Camera(yaw_deg=-26,tilt_deg=11),102,(),.55,False),
    ("holdout", "heldout_asymmetric_pavilion",Shape((0,.24,.63,1),(.015,.18,.52,1),.33,left_width=.90,right_width=1.10),Camera(roll_deg=3),103,(),.45,False),
    ("holdout", "heldout_shadowed_intermediate",Shape((0,.28,.61,1),(.01,.22,.57,1),.23),Camera(yaw_deg=31,tilt_deg=-8),104,((101,117),),.8,True),
    ("holdout", "heldout_high_noise_partial",Shape((0,.30,.74,1),(.04,.19,.62,1),.17),Camera(roll_deg=-5),105,((88,109),(144,154)),1.5,False),
)


def benchmark():
    cases=[]
    for group,name,shape,camera,seed,missing,noise,stripes in CASES:
        scene=synthetic_scene(shape,camera,seed,missing,noise,stripes)
        metrics=evaluate_scene(scene)
        cases.append({
            "split":group,"name":name,"seed":seed,
            "physical_tier_band_count":3,
            "tip_to_girdle_ring_levels":list(shape.levels_y),
            "shape":{**asdict(shape),
                     "levels_y":list(shape.levels_y),
                     "radii":list(shape.radii)},
            "camera":asdict(camera),
            "synthetic_oracle_visibility":projected_tier_visibility(shape,camera),
            "missing_y_intervals_px":[list(v) for v in missing],
            "noise_px":noise,"internal_stripes_control":stripes,
            "projected_transition_identity":
                "UNKNOWN_under_pose_and_envelope_switching_never_assume_ring_equals_break",
            "external_source_only_baseline":metrics,
        })
    return {
        "schema_version":SCHEMA,
        "policy":GENERATOR_POLICY,
        "status":"synthetic_benchmark_not_real_photo_validation",
        "physical_tier_identity_from_source_image":"unavailable",
        "expert_targets_loaded":False,
        "real_diamond_photo_used":False,
        "cases":cases,
    }


def render_case(shape, camera, obs, stripes=False, width=420, height=235):
    """Synthetic profile preview only. Interior stripes are decorative negatives."""
    scan=silhouette(shape,camera)
    image=Image.new("RGB",(width,height),(225,226,229))
    d=ImageDraw.Draw(image)
    if len(scan)>1:
        polygon=[(float(x),float(y)) for x,y,_ in scan]
        polygon += [(float(r),float(y)) for _,y,r in scan[::-1]]
        d.polygon(polygon, fill=(240,242,246))
        if stripes:
            for y in range(80,180,18):
                d.line((175,y,245,y),fill=(45,43,53),width=3)
    for side,fill in (("left",(16,150,74)),("right",(31,112,224))):
        for row in obs[side]:
            x,y=row["xy_px"]
            d.ellipse((x-1.5,y-1.5,x+1.5,y+1.5),fill=fill)
    return image


def write_benchmark(path):
    root=Path(path)
    root.mkdir(parents=True,exist_ok=True)
    report=benchmark()
    (root/"synthetic-pavilion-benchmark.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    # One held-out composite, with fixed scene metadata, *no* DiaGem JPEG.
    names=("level_three_tiers","near_collinear_three_physical_tiers",
           "heldout_asymmetric_pavilion","heldout_oblique_pose")
    panels=[]
    for group,name,shape,camera,seed,missing,noise,stripes in CASES:
        if name in names:
            s=synthetic_scene(shape,camera,seed,missing,noise,stripes)
            img=render_case(shape,camera,s["source_observations"],stripes)
            panels.append((name,img))
    canvas=Image.new("RGB",(840,2*275),(248,249,251))
    d=ImageDraw.Draw(canvas)
    for idx,(name,img) in enumerate(panels):
        x=420*(idx%2);y=275*(idx//2)
        canvas.paste(img,(x,y+24))
        d.text((x+10,y+7),name,fill=(24,31,44))
    canvas.save(root/"synthetic-pavilion-cases.png")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=write_benchmark(args.output)
    print(json.dumps({"cases":len(report["cases"]),"splits":{
        split:sum(1 for v in report["cases"] if v["split"]==split)
        for split in ("dev","holdout")},"real_photo_used":False,
        "physical_angle_inferred":False},sort_keys=True))


if __name__=="__main__":
    main()
