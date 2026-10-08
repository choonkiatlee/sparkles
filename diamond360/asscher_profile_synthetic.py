"""Deterministic synthetic projected Asscher pavilion silhouette scenes.

This is a 2D profile-envelope renderer, not a 3D faceting, camera calibration,
ray-tracing, or physical-angle generator. It retains known image-plane knot
truth in a DIFFERENT object from the estimator's observations.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

from .asscher_profile_projected_fit import OBSERVATION_SCHEMA

SCHEMA = "sparkles-pavilion-synthetic-scene/1"


@dataclass(frozen=True)
class Side:
    """Positive radial x-per-y slopes, with ordered knots from pointed tip."""
    knots: tuple[float, ...]
    slopes: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.slopes) != len(self.knots) + 1 or not 1 <= len(self.slopes) <= 3:
            raise ValueError("each side requires 1–3 projected straight stretches")
        if any(not (0.1 < v < 3.0) for v in self.slopes):
            raise ValueError("visible projected radial slopes must be positive")
        if any(not (0.12 <= k <= 0.88) for k in self.knots):
            raise ValueError("projected break must be away from tips")
        if any(b - a < 0.13 for a, b in zip((0,) + self.knots, self.knots + (1,))):
            raise ValueError("short synthetic pavilion segment")
        if tuple(sorted(self.knots)) != self.knots or len(set(self.knots)) != len(self.knots):
            raise ValueError("breaks must be strictly increasing")

    def radius(self, fractional_y: float) -> float:
        t = max(0.0, min(1.0, float(fractional_y)))
        borders = (0.0,) + self.knots + (1.0,)
        return sum(self.slopes[i] * max(0.0, min(t, b) - a)
                   for i, (a, b) in enumerate(zip(borders[:-1], borders[1:])))


@dataclass(frozen=True)
class Scene:
    left: Side
    right: Side
    seed: int
    tip_x: float = 205.0
    tip_y: float = 52.0
    pavilion_height_px: int = 145
    shear_dx_per_dy: float = 0.0
    noise_std_px: float = 0.7
    blur_std_rows: float = 0.0
    dropout: float = 0.0
    left_occlusion: tuple[float, float] = (0.0, 0.0)
    right_occlusion: tuple[float, float] = (0.0, 0.0)
    right_shadow_from_fraction: float = 1.0
    outlier_probability: float = 0.0
    inner_distractors: bool = False

    def __post_init__(self) -> None:
        if not 60 <= self.pavilion_height_px <= 190:
            raise ValueError("unreasonable synthetic image height")
        if not 0 <= self.dropout <= 0.95 or not 0 <= self.outlier_probability <= 0.2:
            raise ValueError("invalid synthetic noise")
        if not 0 <= self.noise_std_px <= 4 or not 0 <= self.blur_std_rows <= 4:
            raise ValueError("invalid pixel-like noise or blur")
        for start, end in (self.left_occlusion, self.right_occlusion):
            if not (0 <= start <= end <= 1):
                raise ValueError("occlusion fractions must be ordered")
        if not 0 < self.right_shadow_from_fraction <= 1:
            raise ValueError("shadow start must lie inside pavilion")


def projected_x(scene: Scene, side: str, t: float) -> float:
    shape = scene.left if side == "left" else scene.right
    sign = -1 if side == "left" else 1
    h = scene.pavilion_height_px
    return scene.tip_x + scene.shear_dx_per_dy*h*t + sign*h*shape.radius(t)


def sample_scene(scene: Scene) -> dict:
    """Return disjoint observations, ground-truth knots, and optical distractors."""
    rng = np.random.default_rng(scene.seed)
    t_values = np.linspace(0, 1, scene.pavilion_height_px + 1)
    true_x = {
        side: np.array([projected_x(scene, side, t) for t in t_values])
        for side in ("left", "right")
    }
    obs, distractors = {}, {}
    for side in ("left", "right"):
        x_values = true_x[side].copy()
        if scene.blur_std_rows:
            from scipy.ndimage import gaussian_filter1d
            x_values = gaussian_filter1d(x_values, scene.blur_std_rows, mode="nearest")
        x_values += rng.normal(0.0, scene.noise_std_px, len(x_values))
        mask = rng.random(len(x_values)) >= scene.dropout
        start, end = scene.left_occlusion if side == "left" else scene.right_occlusion
        mask &= ~((t_values >= start) & (t_values <= end) & (end > start))
        if side == "right":
            mask &= t_values < scene.right_shadow_from_fraction
        outliers = (rng.random(len(x_values)) < scene.outlier_probability) & mask
        x_values[outliers] += rng.normal(0, 9, np.count_nonzero(outliers))
        obs[side] = [
            {"y_px": float(scene.tip_y + yi),
             "x_px": round(float(x_values[yi]), 5) if mask[yi] else None}
            for yi in range(2, len(t_values) - 1, 2)
        ]
        distractors[side] = [
            {
                "y_px": float(scene.tip_y + t*scene.pavilion_height_px),
                "internal_virtual_edge_x_px": round(
                    projected_x(scene,side,t) + (34 if side=="left" else -34), 3)
            } for t in (0.26,0.48,0.67)
        ] if scene.inner_distractors else []
    return {
        "schema_version": SCHEMA,
        "observations": {
            "schema_version": OBSERVATION_SCHEMA,
            "source_kind": "synthetic_profile",
            "pavilion_roi_y_px": [
                float(scene.tip_y), float(scene.tip_y+scene.pavilion_height_px)
            ],
            "contours": obs,
        },
        "truth": {
            "type": "KNOWN_IMAGE_PLANE_PROJECTED_BREAKS_NOT_PHYSICAL_FACETS",
            "left_break_y_px": [round(scene.tip_y+k*scene.pavilion_height_px,4)
                                for k in scene.left.knots],
            "right_break_y_px": [round(scene.tip_y+k*scene.pavilion_height_px,4)
                                 for k in scene.right.knots],
            "left_segment_count": len(scene.left.slopes),
            "right_segment_count": len(scene.right.slopes),
            "shear_dx_per_dy": scene.shear_dx_per_dy,
        },
        "optical_distractors_never_fit_inputs": distractors,
        "rendering_only": {
            "tip_x": scene.tip_x, "tip_y": scene.tip_y,
            "height_px": scene.pavilion_height_px,
            "inner_distractors": scene.inner_distractors,
        },
        "source_kind": "purely_synthetic_no_photographic_reference",
    }


def render_scene(scene: Scene, fitted: Optional[dict] = None) -> Image.Image:
    """Draw profile and truth/fitted changes as a technical diagnostic."""
    image = Image.new("RGB",(410,270),(211,212,215))
    draw = ImageDraw.Draw(image)
    y0,h=scene.tip_y,scene.pavilion_height_px
    left=[(projected_x(scene,"left",t),y0+h*t) for t in np.linspace(0,1,180)]
    right=[(projected_x(scene,"right",t),y0+h*t) for t in np.linspace(0,1,180)]
    draw.polygon(left+list(reversed(right)),fill=(247,246,249))
    draw.line(left,fill=(38,108,162),width=2)
    draw.line(right,fill=(38,108,162),width=2)
    if scene.inner_distractors:
        for t in (0.27,0.41,0.56,0.70):
            y=y0+h*t
            lx=projected_x(scene,"left",t)+28
            rx=projected_x(scene,"right",t)-28
            if lx<rx:
                draw.line((lx,y,rx,y),fill=(113,100,135),width=3)
    for side,interval in (("left",scene.left_occlusion),
                          ("right",scene.right_occlusion)):
        a,b=interval
        if b>a:
            for y in range(int(y0+h*a),int(y0+h*b)+1,2):
                t=(y-y0)/h
                x=projected_x(scene,side,t)
                draw.ellipse((x-4,y-4,x+4,y+4),fill=(211,212,215))
    for side,spec in (("left",scene.left),("right",scene.right)):
        for frac in spec.knots:
            yy=y0+frac*h
            xx=projected_x(scene,side,frac)
            draw.ellipse((xx-5,yy-5,xx+5,yy+5),
                         fill=(19,26,39),outline=(255,255,255),width=2)
        if fitted is not None:
            for yy in fitted.get("sides",{}).get(side,{}).get("candidate_break_y_px",[]):
                t=(yy-y0)/h
                xx=projected_x(scene,side,t)
                draw.ellipse((xx-8,yy-8,xx+8,yy+8),
                             outline=(238,123,10),width=3)
    return image
