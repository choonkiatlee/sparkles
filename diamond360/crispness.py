"""Static tier-boundary crispness primitives for Asscher 360 imagery.

The descriptor deliberately reuses #19 geometry. It scores held-out radial edge
profiles around #19-style expected boundary locations; it does not discover a
second set of semantic bands and it does not infer cut quality or light return.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import asscher_steps as steps

SCHEMA = "diamond360-static-crispness/1"
BOUNDARIES = steps.BOUNDARIES
DEFAULT_SEARCH_RADIUS = 0.04
DEFAULT_Z_THRESHOLD = 0.8  # Reuse #19's local-support convention.
PERTURBATIONS = ("blur", "downsample", "jpeg", "sharpen")


def _finite(values):
    return np.asarray(
        [float(v) for v in values if v is not None and math.isfinite(float(v))],
        float,
    )


def _median(values):
    data = _finite(values)
    return float(np.median(data)) if data.size else None


def _quantile(values, q):
    data = _finite(values)
    return float(np.quantile(data, q)) if data.size else None


def longest_circular_gap_fraction(supported):
    """Fraction of the angular circumference in the longest unsupported run."""
    supported = np.asarray(supported, bool)
    if supported.ndim != 1 or supported.size == 0:
        raise ValueError("supported must be a non-empty 1-D boolean array")
    missing = ~supported
    if not missing.any():
        return 0.0
    if missing.all():
        return 1.0
    doubled = np.r_[missing, missing]
    best = run = 0
    for flag in doubled:
        run = run + 1 if flag else 0
        best = max(best, run)
    return float(min(best, supported.size) / supported.size)


def _local_peak(profile, support, u, target, search_radius):
    profile = np.asarray(profile, float)
    support = np.asarray(support, bool)
    if profile.shape != support.shape or profile.shape != np.asarray(u).shape:
        raise ValueError("profile, support and u must have matching shapes")
    eligible = (
        support
        & np.isfinite(profile)
        & (np.abs(np.asarray(u) - float(target)) <= search_radius)
    )
    if eligible.sum() < 2:
        return None
    indices = np.flatnonzero(eligible)
    idx = int(indices[int(np.nanargmax(profile[indices]))])
    masked = np.where(support & np.isfinite(profile), profile, np.nan)
    z = steps._robust_z(masked)
    peak_z = float(z[idx]) if np.isfinite(z[idx]) else None
    return {
        "index": idx,
        "u": float(u[idx]),
        "edge": float(profile[idx]),
        "z": peak_z,
        "offset_u": float(u[idx] - target),
    }


def measure_boundary_frame(
    ray_edge,
    ray_support,
    u,
    angles,
    control,
    *,
    search_radius=DEFAULT_SEARCH_RADIUS,
    z_threshold=DEFAULT_Z_THRESHOLD,
    include_ray_evidence=True,
):
    """Score one expected #19 boundary in one frame across all radial rays."""
    ray_edge = np.asarray(ray_edge, float)
    ray_support = np.asarray(ray_support, bool)
    u = np.asarray(u, float)
    angles = np.asarray(angles, float)
    if ray_edge.ndim != 2 or ray_edge.shape != ray_support.shape:
        raise ValueError(
            "ray_edge and ray_support must be matching ray x radius arrays"
        )
    if ray_edge.shape[0] != angles.size or ray_edge.shape[1] != u.size:
        raise ValueError("angles/u must match ray_edge dimensions")
    if len(control.get("sector_u", [])) != 8:
        raise ValueError("control must contain eight #19 sector_u locations")

    targets = steps._periodic_boundary(angles, control["sector_u"])
    peaks = [
        _local_peak(
            ray_edge[i],
            ray_support[i],
            u,
            targets[i],
            search_radius,
        )
        for i in range(len(angles))
    ]
    finite = [p for p in peaks if p is not None and p["z"] is not None]
    supported = np.asarray(
        [
            p is not None
            and p["z"] is not None
            and p["z"] >= z_threshold
            for p in peaks
        ],
        bool,
    )
    peak_z = [p["z"] for p in finite]
    offsets = [p["offset_u"] for p in finite]
    offset_median = _median(offsets)
    offset_mad = None
    if offsets:
        values = np.asarray(offsets, float)
        med = float(np.median(values))
        offset_mad = float(1.4826 * np.median(np.abs(values - med)))

    result = {
        "status": (
            "ok"
            if len(finite) >= max(8, int(round(.5 * len(angles))))
            else "review"
            if len(finite) >= max(4, int(round(.25 * len(angles))))
            else "unavailable"
        ),
        "ray_count": int(len(angles)),
        "finite_peak_count": int(len(finite)),
        "supported_ray_count": int(supported.sum()),
        "supported_fraction": float(supported.mean()),
        "longest_gap_fraction": longest_circular_gap_fraction(supported),
        "median_peak_z": _median(peak_z),
        "q10_peak_z": _quantile(peak_z, .1),
        "median_abs_offset_u": _median([abs(v) for v in offsets]),
        "offset_mad_u": offset_mad,
        "median_signed_offset_u": offset_median,
    }
    if include_ray_evidence:
        result["rays"] = [
            None
            if p is None
            else {
                "target_u": float(targets[i]),
                "peak_u": p["u"],
                "peak_z": p["z"],
                "supported": bool(supported[i]),
            }
            for i, p in enumerate(peaks)
        ]
    return result


def measure_frame(ray_edge, ray_support, u, angles, controls, **kwargs):
    if len(controls) != len(BOUNDARIES):
        raise ValueError("exactly three #19 boundary controls are required")
    return {
        name: measure_boundary_frame(
            ray_edge,
            ray_support,
            u,
            angles,
            control,
            **kwargs,
        )
        for name, control in zip(BOUNDARIES, controls)
    }


def summarise_frames(frames):
    """Keep strength, continuity and positional consistency as separate primitives."""
    result = {}
    requested = len(frames)
    for name in BOUNDARIES:
        rows = [
            frame[name]
            for frame in frames
            if frame is not None and name in frame
        ]
        usable = [row for row in rows if row.get("status") != "unavailable"]

        def vals(key):
            return [row.get(key) for row in usable]

        strength = vals("median_peak_z")
        continuity = vals("supported_fraction")
        gaps = vals("longest_gap_fraction")
        offsets = vals("offset_mad_u")
        gap_values = _finite(gaps)
        result[name] = {
            "requested_frame_count": requested,
            "scored_frame_count": len(rows),
            "usable_frame_count": len(usable),
            "coverage_fraction": (
                float(len(rows) / requested) if requested else None
            ),
            "status": "ok" if len(usable) >= 3 else "unavailable",
            "reasons": [],
            "strength_median_peak_z": _median(strength),
            "strength_q10_peak_z": _quantile(strength, .1),
            "continuity_median_supported_fraction": _median(continuity),
            "continuity_worst_gap_fraction": (
                float(np.max(gap_values)) if gap_values.size else None
            ),
            "position_median_mad_u": _median(offsets),
            "position_q90_mad_u": _quantile(offsets, .9),
        }
    return result


def build_crossfit_templates(frame_sector_evidence, u):
    """Discover geometry on alternating training frames; score only the held-out half."""
    data = np.asarray(frame_sector_evidence, float)
    if data.ndim != 3 or data.shape[1] != 8 or data.shape[0] < 6:
        raise ValueError(
            "cross-fit needs at least six frame x 8-sector edge-evidence arrays"
        )
    templates = []
    positions = np.arange(data.shape[0])
    for fold in (0, 1):
        holdout = positions[positions % 2 == fold]
        train = positions[positions % 2 != fold]
        template = steps.discover_template(data[train], np.asarray(u, float))
        templates.append(
            {
                "fold": fold,
                "train_positions": train.tolist(),
                "holdout_positions": holdout.tolist(),
                "status": template["status"],
                "reason": template.get("reason"),
                "controls": template.get("controls"),
            }
        )
    return templates


def score_crossfit(
    frame_ray_edges,
    frame_ray_support,
    u,
    angles,
    templates,
    **kwargs,
):
    edge = np.asarray(frame_ray_edges, float)
    support = np.asarray(frame_ray_support, bool)
    if edge.ndim != 3 or support.shape != edge.shape:
        raise ValueError(
            "cross-fit ray evidence must be matching frame x ray x radius arrays"
        )
    frames = [None] * edge.shape[0]
    frame_status = ["unavailable"] * edge.shape[0]
    for template in templates:
        controls = template.get("controls")
        for pos in template["holdout_positions"]:
            if template.get("status") == "unavailable" or not controls:
                continue
            frames[pos] = measure_frame(
                edge[pos],
                support[pos],
                u,
                angles,
                controls,
                **kwargs,
            )
            frame_status[pos] = template.get("status", "unavailable")

    summary = summarise_frames(frames)
    template_statuses = [t.get("status", "unavailable") for t in templates]
    scored = sum(frame is not None for frame in frames)
    reasons = []
    if "unavailable" in template_statuses or scored < len(frames):
        reasons.append("crossfit_template_unavailable")
    if "review" in template_statuses:
        reasons.append("crossfit_template_review")
    crossfit_status = (
        "unavailable"
        if scored < 3
        else "review"
        if reasons
        else "ok"
    )
    for cell in summary.values():
        if cell["status"] == "unavailable":
            continue
        if crossfit_status == "review":
            cell["status"] = "review"
        cell["reasons"] = list(reasons)

    return {
        "frames": frames,
        "frame_template_status": frame_status,
        "crossfit_status": crossfit_status,
        "crossfit_reasons": reasons,
        "summary": summary,
    }


def crossfit_measure(
    frame_ray_edges,
    frame_ray_support,
    frame_sector_evidence,
    u,
    angles,
    **kwargs,
):
    templates = build_crossfit_templates(frame_sector_evidence, u)
    scored = score_crossfit(
        frame_ray_edges,
        frame_ray_support,
        u,
        angles,
        templates,
        **kwargs,
    )
    return {
        "schema_version": SCHEMA,
        "geometry_policy": (
            "interleaved two-fold: discover #19 boundary geometry on one parity, "
            "score the held-out parity, then swap"
        ),
        "templates": templates,
        **scored,
    }


def _restore_shape(array, shape):
    out = np.asarray(array, float)
    result = np.empty(shape, float)
    h = min(shape[0], out.shape[0])
    w = min(shape[1], out.shape[1])
    result[:h, :w] = out[:h, :w]
    if h < shape[0]:
        result[h:, :w] = out[h - 1:h, :w]
    if w < shape[1]:
        result[:, w:] = result[:, w - 1:w]
    return result


def apply_perturbation(brightness, kind):
    """Controlled image-space perturbations for source-pipeline sensitivity checks."""
    x = np.asarray(brightness, float)
    if x.ndim != 2:
        raise ValueError("brightness must be a 2-D array")
    finite = np.isfinite(x)
    if not finite.any():
        return x.copy()
    lo = float(np.nanmin(x[finite]))
    hi = float(np.nanmax(x[finite]))
    fill = float(np.nanmedian(x[finite]))
    work = np.where(finite, x, fill)

    if kind == "blur":
        out = ndi.gaussian_filter(work, .8, mode="nearest")
    elif kind == "downsample":
        small = ndi.zoom(work, .5, order=1, prefilter=False)
        zoom = (
            work.shape[0] / small.shape[0],
            work.shape[1] / small.shape[1],
        )
        out = _restore_shape(
            ndi.zoom(small, zoom, order=1, prefilter=False),
            work.shape,
        )
    elif kind == "sharpen":
        smooth = ndi.gaussian_filter(work, .8, mode="nearest")
        out = work + .75 * (work - smooth)
        out = np.clip(out, lo, hi)
    elif kind == "jpeg":
        if hi <= lo:
            out = work.copy()
        else:
            encoded = np.clip(
                np.rint((work - lo) / (hi - lo) * 255),
                0,
                255,
            ).astype(np.uint8)
            buffer = io.BytesIO()
            Image.fromarray(encoded, mode="L").save(
                buffer,
                format="JPEG",
                quality=70,
                optimize=False,
            )
            buffer.seek(0)
            decoded = (
                np.asarray(Image.open(buffer).convert("L"), float) / 255.0
            )
            out = lo + decoded * (hi - lo)
    else:
        raise ValueError(f"unknown perturbation: {kind}")

    out = np.asarray(out, float)
    out[~finite] = np.nan
    return out


def compare_summaries(baseline, candidate):
    """Perturbation deltas without collapsing the primitive families."""
    metrics = (
        "strength_median_peak_z",
        "continuity_median_supported_fraction",
        "continuity_worst_gap_fraction",
        "position_median_mad_u",
    )
    result = {}
    for boundary in BOUNDARIES:
        result[boundary] = {}
        for metric in metrics:
            base = baseline.get(boundary, {}).get(metric)
            test = candidate.get(boundary, {}).get(metric)
            if base is None or test is None:
                result[boundary][metric] = {
                    "baseline": base,
                    "candidate": test,
                    "absolute_delta": None,
                    "relative_delta": None,
                }
                continue
            delta = float(test - base)
            relative = (
                float(delta / abs(base)) if abs(base) > 1e-12 else None
            )
            result[boundary][metric] = {
                "baseline": float(base),
                "candidate": float(test),
                "absolute_delta": delta,
                "relative_delta": relative,
            }
    return result
