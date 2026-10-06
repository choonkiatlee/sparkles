"""Asscher-aware nested step-band correspondence from registered 360 frames.

This stage intentionally does not claim individual-facet identity. It discovers a
sequence-level template from persistent radial edge evidence, then maps that
ordered template through each frame's silhouette. Per-frame local edge matches
are retained as confidence/QC only and never force a moving correspondence.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.signal import find_peaks, peak_prominences

from .region_traces import validate_interval

SCHEMA = "diamond360-asscher-steps/1"
BANDS = ("centre", "inner_step", "middle_step", "outer_step")
BOUNDARIES = ("centre_inner", "inner_middle", "middle_outer")
# Broad silhouette-normalised zones keep ordinal labels semantically comparable.
# A strong reflection edge outside its zone is not allowed to substitute for a
# missing Asscher step boundary.
BOUNDARY_WINDOWS = ((.42, .60), (.64, .82), (.82, .92))
SECTOR_NAMES = ("side_E", "corner_SE", "side_S", "corner_SW",
                "side_W", "corner_NW", "side_N", "corner_NE")


def _robust_z(values):
    values = np.asarray(values, float)
    finite = np.isfinite(values)
    result = np.full(values.shape, np.nan, float)
    if not finite.any():
        return result
    v = values[finite]
    med = np.median(v)
    mad = np.median(np.abs(v - med))
    scale = max(1.4826 * mad, np.std(v) * .2, 1e-6)
    result[finite] = (values[finite] - med) / scale
    return result


def _sector_ids(angles):
    return (np.floor((np.asarray(angles) + np.pi / 8) / (np.pi / 4)).astype(int)) % 8


def _ray_geometry(mask, angles, radial_samples=160):
    mask = np.asarray(mask, bool)
    if mask.ndim != 2 or min(mask.shape) < 32:
        raise ValueError("Step correspondence requires a 2-D registered mask at least 32 px across")
    h, w = mask.shape
    cy, cx = (h - 1) / 2, (w - 1) / 2
    max_r = float(np.hypot(max(cx, w - 1 - cx), max(cy, h - 1 - cy)))
    probe_r = np.linspace(0, max_r, max(256, int(np.ceil(max_r * 2)) + 1))
    yy = cy + np.sin(angles)[:, None] * probe_r[None, :]
    xx = cx + np.cos(angles)[:, None] * probe_r[None, :]
    inside = ndi.map_coordinates(mask.astype(np.uint8), [yy, xx], order=0,
                                 mode="constant", cval=0) > 0
    outlines = np.zeros(len(angles), float)
    for i, row in enumerate(inside):
        hits = np.flatnonzero(row)
        if not len(hits):
            continue
        outlines[i] = probe_r[hits[-1]]
    if np.count_nonzero(outlines > 8) < len(angles) * .9:
        raise ValueError("Registered silhouette does not surround the canonical centre reliably")
    bad = outlines <= 8
    if bad.any():
        good = np.flatnonzero(~bad)
        extended_x = np.r_[good - len(angles), good, good + len(angles)]
        extended_y = np.r_[outlines[good], outlines[good], outlines[good]]
        outlines[bad] = np.interp(np.flatnonzero(bad), extended_x, extended_y)
    u = np.linspace(0, 1, radial_samples)
    radius = outlines[:, None] * u[None, :]
    yy = cy + np.sin(angles)[:, None] * radius
    xx = cx + np.cos(angles)[:, None] * radius
    return u, outlines, yy, xx


def polar_profiles(brightness, mask, valid_mask, angle_count=96, radial_samples=160):
    """Sample silhouette-normalised radial brightness profiles."""
    brightness = np.asarray(brightness, float)
    mask = np.asarray(mask, bool)
    valid_mask = np.asarray(valid_mask, bool)
    if brightness.shape != mask.shape or mask.shape != valid_mask.shape:
        raise ValueError("Brightness, silhouette and valid support must have matching shapes")
    angles = np.linspace(0, 2 * np.pi, angle_count, endpoint=False)
    u, outlines, yy, xx = _ray_geometry(mask, angles, radial_samples)
    values = ndi.map_coordinates(brightness, [yy, xx], order=1, mode="constant", cval=np.nan)
    support = ndi.map_coordinates(valid_mask.astype(np.uint8), [yy, xx], order=0,
                                  mode="constant", cval=0) > 0
    support &= (u[None, :] >= .08) & (u[None, :] <= .92)
    norm = values.copy()
    for i in range(len(angles)):
        sample = values[i, support[i]]
        scale = np.median(sample) if len(sample) else np.nan
        if not np.isfinite(scale) or scale < .05:
            support[i] = False
        else:
            norm[i] = values[i] / scale
    return dict(u=u, angles=angles, outlines=outlines, profiles=norm, support=support)


def edge_evidence(profiles, support):
    profiles = np.asarray(profiles, float)
    support = np.asarray(support, bool)
    if profiles.shape != support.shape or profiles.ndim != 2:
        raise ValueError("Polar profiles and support must be matching 2-D arrays")
    filled = profiles.copy()
    for i in range(len(filled)):
        ok = support[i] & np.isfinite(filled[i])
        if ok.sum() < 8:
            filled[i] = 0
            continue
        x = np.arange(filled.shape[1])
        filled[i, ~ok] = np.interp(x[~ok], x[ok], filled[i, ok])
    smooth = ndi.gaussian_filter1d(filled, 1.25, axis=1, mode="nearest")
    edge = np.abs(np.gradient(smooth, axis=1))
    edge[~support] = np.nan
    return edge


def sector_evidence(edge, angles):
    edge = np.asarray(edge, float)
    ids = _sector_ids(angles)
    out = np.full((8, edge.shape[1]), np.nan, float)
    for sector in range(8):
        rows = edge[ids == sector]
        if len(rows):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out[sector] = np.nanmedian(rows, axis=0)
    return out


def _local_peak(profile, u, centre, radius=.055):
    profile = np.asarray(profile, float)
    window = np.isfinite(profile) & (np.abs(u - centre) <= radius)
    if window.sum() < 3:
        return None
    indices = np.flatnonzero(window)
    local = profile[indices]
    j = int(np.nanargmax(local))
    idx = int(indices[j])
    z = _robust_z(profile)
    return dict(index=idx, u=float(u[idx]), evidence=float(profile[idx]),
                z=float(z[idx]) if np.isfinite(z[idx]) else None)


def _control_from_candidate(boundary, window, u):
    """Convert one supported semantic-boundary candidate into sector controls."""
    global_u = boundary["u"]
    radial_spacing = float(np.median(np.diff(u)))
    margin = float(min(global_u - window[0], window[1] - global_u))
    vals = np.full(8, global_u, float)
    observed = np.zeros(8, bool)
    zscores = np.full(8, np.nan)
    for s, peak in enumerate(boundary["sector_peaks"]):
        if peak is not None and peak["z"] is not None and peak["z"] >= .8:
            vals[s] = peak["u"]
            observed[s] = True
            zscores[s] = peak["z"]
    for s in range(4):
        t = s + 4
        if observed[s] and observed[t]:
            mean = (vals[s] + vals[t]) / 2
            vals[s] = .8 * vals[s] + .2 * mean
            vals[t] = .8 * vals[t] + .2 * mean
    return dict(
        global_u=global_u, sector_u=vals, observed=observed, zscores=zscores,
        sector_support=float(observed.mean()), prominence=boundary["prominence"],
        semantic_window=window, window_margin=margin,
        window_margin_samples=margin / radial_spacing,
        near_window_edge=bool(margin <= radial_spacing),
    )

def discover_template(frame_sector_evidence, u):
    """Discover three ordered persistent boundaries and 8-sector control points."""
    data = np.asarray(frame_sector_evidence, float)
    if data.ndim != 3 or data.shape[1] != 8 or data.shape[2] != len(u):
        raise ValueError("Expected frame × 8-sector × radial-sample evidence")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sectors = np.nanmedian(data, axis=0)
        consensus = np.nanmedian(sectors, axis=0)
    consensus = ndi.gaussian_filter1d(np.nan_to_num(consensus, nan=0.0), 1.2)
    interior = (u >= .16) & (u <= .92)
    distance = max(3, int(round(.095 * (len(u) - 1))))
    raw_peaks, _ = find_peaks(consensus, distance=distance)
    raw_peaks = raw_peaks[interior[raw_peaks]]
    prominence = peak_prominences(consensus, raw_peaks)[0] if len(raw_peaks) else np.array([], float)
    candidates = []
    for idx, prom in zip(raw_peaks, prominence):
        per_sector = [_local_peak(sectors[s], u, float(u[idx]), radius=.045) for s in range(8)]
        supported = sum(p is not None and p["z"] is not None and p["z"] >= .8 for p in per_sector)
        candidates.append(dict(index=int(idx), u=float(u[idx]), prominence=float(prom),
                               sector_support=supported / 8, sector_peaks=per_sector))
    if len(candidates) < 3:
        ranked = np.argsort(consensus[interior])[::-1]
        interior_idx = np.flatnonzero(interior)
        chosen = [c["index"] for c in candidates]
        for r in ranked:
            idx = int(interior_idx[r])
            if any(abs(idx - other) < distance for other in chosen):
                continue
            per_sector = [_local_peak(sectors[s], u, float(u[idx]), radius=.045) for s in range(8)]
            supported = sum(p is not None and p["z"] is not None and p["z"] >= .8 for p in per_sector)
            candidates.append(dict(index=idx, u=float(u[idx]), prominence=0.0,
                                   sector_support=supported / 8, sector_peaks=per_sector))
            chosen.append(idx)
            if len(candidates) >= 6:
                break
    if len(candidates) < 3:
        return dict(status="unavailable", reason="fewer_than_three_persistent_radial_edges",
                    consensus=consensus, sectors=sectors, candidates=candidates)

    prom_values = np.array([c["prominence"] for c in candidates])
    prom_scale = max(float(np.median(prom_values[prom_values > 0])) if np.any(prom_values > 0) else 0.0, 1e-6)
    selected = []
    missing = []
    for name, (lo, hi) in zip(BOUNDARIES, BOUNDARY_WINDOWS):
        options = [c for c in candidates
                   if lo <= c["u"] <= hi and c["sector_support"] >= .25]
        if not options:
            selected.append(None)
            missing.append(name)
            continue
        selected.append(max(
            options,
            key=lambda c: np.log1p(c["prominence"] / prom_scale) + 1.25 * c["sector_support"],
        ))
    partial_controls = {
        name: _control_from_candidate(boundary, window, u)
        for name, boundary, window in zip(BOUNDARIES, selected, BOUNDARY_WINDOWS)
        if boundary is not None
    }
    if missing:
        return dict(
            status="unavailable",
            reason=f"no_supported_{missing[0]}_edge",
            consensus=consensus,
            sectors=sectors,
            candidates=candidates,
            partial_controls=partial_controls,
        )
    if np.min(np.diff([c["u"] for c in selected])) < .075:
        return dict(status="unavailable", reason="semantic_boundaries_not_separable",
                    consensus=consensus, sectors=sectors, candidates=candidates,
                    partial_controls=partial_controls)
    controls = [
        _control_from_candidate(boundary, window, u)
        for boundary, window in zip(selected, BOUNDARY_WINDOWS)
    ]

    global_u = np.array([c["global_u"] for c in controls])
    for s in range(8):
        vals = np.array([c["sector_u"][s] for c in controls])
        if np.min(np.diff(vals)) < .075:
            for j, c in enumerate(controls):
                c["sector_u"][s] = global_u[j]
                c["observed"][s] = False
                c["zscores"][s] = np.nan
    supports = [float(c["observed"].mean()) for c in controls]
    for c, support in zip(controls, supports):
        c["sector_support"] = support
    status = "ok" if min(supports) >= .5 else "review" if min(supports) >= .25 else "unavailable"
    reason = None if status != "unavailable" else "insufficient_cross_sector_support"
    if status != "unavailable" and any(c["near_window_edge"] for c in controls):
        status = "review"
        reason = "semantic_window_edge"
    return dict(status=status, reason=reason, consensus=consensus, sectors=sectors,
                candidates=candidates, controls=controls)


def boundary_alignment(frame_sector_evidence, u, controls):
    """Compare edge evidence at detected boundaries with legacy fixed radii."""
    data = np.asarray(frame_sector_evidence, float)
    coarse = (.20, .45, .70)
    rows = []
    for j, control in enumerate(controls):
        step_values = []
        coarse_values = []
        for frame in range(data.shape[0]):
            for sector in range(8):
                profile = data[frame, sector]
                for target, store in ((float(control["sector_u"][sector]), step_values), (coarse[j], coarse_values)):
                    window = np.isfinite(profile) & (np.abs(u - target) <= .018)
                    if window.any():
                        store.append(float(np.nanmax(profile[window])))
        step = float(np.median(step_values)) if step_values else None
        old = float(np.median(coarse_values)) if coarse_values else None
        rows.append(dict(boundary=BOUNDARIES[j], step_edge_median=step, coarse_edge_median=old,
                         edge_ratio=(step / old if step is not None and old not in (None, 0) else None)))
    return rows


def _periodic_boundary(theta, sector_values):
    theta = np.mod(theta, 2 * np.pi)
    centres = np.arange(8) * (np.pi / 4)
    values = np.asarray(sector_values, float)
    xp = np.r_[centres[-1] - 2 * np.pi, centres, centres[0] + 2 * np.pi]
    fp = np.r_[values[-1], values, values[0]]
    return np.interp(theta, xp, fp)


def normalised_radius_map(mask, angle_count=192):
    mask = np.asarray(mask, bool)
    h, w = mask.shape
    angles = np.linspace(0, 2 * np.pi, angle_count, endpoint=False)
    _, outlines, _, _ = _ray_geometry(mask, angles, radial_samples=32)
    cy, cx = (h - 1) / 2, (w - 1) / 2
    y, x = np.indices(mask.shape)
    dy, dx = y - cy, x - cx
    theta = np.mod(np.arctan2(dy, dx), 2 * np.pi)
    xp = np.r_[angles[-1] - 2 * np.pi, angles, angles[0] + 2 * np.pi]
    fp = np.r_[outlines[-1], outlines, outlines[0]]
    outline = np.interp(theta.ravel(), xp, fp).reshape(mask.shape)
    radius = np.hypot(dx, dy)
    u = np.full(mask.shape, np.inf, float)
    good = mask & (outline > 0)
    u[good] = radius[good] / outline[good]
    return u, theta


def boundary_strip_masks(mask, sector_u, width, guard=.01, sector_mask=None):
    """Build fixed strips just inside/outside an existing radial boundary.

    ``sector_u`` is the existing eight-sector boundary control in the same
    silhouette-normalised radial coordinate used by #19. The boundary is not
    re-estimated per frame. ``guard`` deliberately excludes the immediate edge
    so downstream tonal contrast is less sensitive to sharpening/edge pixels.
    """
    mask = np.asarray(mask, bool)
    controls = np.asarray(sector_u, float)
    if controls.shape != (8,) or not np.all(np.isfinite(controls)):
        raise ValueError("sector_u must contain eight finite boundary controls")
    if np.any((controls <= 0) | (controls >= 1)):
        raise ValueError("boundary controls must lie strictly inside the silhouette")
    width = float(width)
    guard = float(guard)
    if not np.isfinite(width) or width <= 0:
        raise ValueError("strip width must be finite and positive")
    if not np.isfinite(guard) or guard < 0:
        raise ValueError("strip guard must be finite and nonnegative")

    u, theta = normalised_radius_map(mask)
    boundary = _periodic_boundary(theta, controls)
    support = mask.copy()
    if sector_mask is not None:
        sector_mask = np.asarray(sector_mask, bool)
        if sector_mask.shape != mask.shape:
            raise ValueError("sector mask must match the silhouette shape")
        support &= sector_mask

    inner_hi = boundary - guard
    inner_lo = inner_hi - width
    outer_lo = boundary + guard
    outer_hi = outer_lo + width
    inside = support & (u >= inner_lo) & (u < inner_hi)
    outside = support & (u > outer_lo) & (u <= outer_hi)
    return {"inside": inside, "outside": outside}

def build_masks(mask, controls):
    if len(controls) != 3:
        raise ValueError("Exactly three nested boundaries are required for four step bands")
    u, theta = normalised_radius_map(mask)
    boundaries = [_periodic_boundary(theta, c["sector_u"]) for c in controls]
    if np.any((boundaries[1] - boundaries[0])[mask] < .04) or np.any((boundaries[2] - boundaries[1])[mask] < .04):
        raise ValueError("Step boundaries cross after interpolation")
    result = {
        "centre": mask & (u < boundaries[0]),
        "inner_step": mask & (u >= boundaries[0]) & (u < boundaries[1]),
        "middle_step": mask & (u >= boundaries[1]) & (u < boundaries[2]),
        "outer_step": mask & (u >= boundaries[2]),
    }
    coverage = sum(v.astype(np.uint8) for v in result.values())
    if not np.array_equal(coverage[mask], np.ones(mask.sum(), np.uint8)):
        raise ValueError("Step masks must partition the silhouette exactly once")
    return result


def frame_support(frame_sector, u, controls, radius=.04):
    result = []
    for control in controls:
        matches = []
        for s in range(8):
            peak = _local_peak(frame_sector[s], u, float(control["sector_u"][s]), radius)
            if peak is None or peak["z"] is None or peak["z"] < .8:
                matches.append(None)
            else:
                matches.append(peak)
        observed = [m for m in matches if m is not None]
        result.append(dict(
            supported_sectors=len(observed),
            support_fraction=len(observed) / 8,
            median_abs_offset=(float(np.median([abs(m["u"] - control["sector_u"][s])
                                               for s, m in enumerate(matches) if m is not None]))
                               if observed else None),
            sector_matches=matches,
        ))
    minimum = min((r["support_fraction"] for r in result), default=0)
    status = "ok" if minimum >= .5 else "review" if minimum >= .25 else "unavailable"
    return status, result


def _overlay(rgb, masks):
    rgb = np.asarray(rgb).copy()
    colours = np.array([[235, 85, 65], [65, 190, 105], [65, 125, 235], [235, 190, 55]])
    for i, name in enumerate(BANDS):
        m = masks[name]
        rgb[m] = (.78 * rgb[m] + .22 * colours[i]).astype(np.uint8)
    for name in BANDS[:-1]:
        m = masks[name]
        boundary = m & ~ndi.binary_erosion(m)
        rgb[boundary] = [255, 255, 255]
    return Image.fromarray(rgb)


def _contact_sheet(items, destination, columns=4, cell=(260, 280)):
    cw, ch = cell
    rows = max(1, int(np.ceil(len(items) / columns)))
    sheet = Image.new("RGB", (cw * columns, ch * rows), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for i, (label, image) in enumerate(items):
        x, y = (i % columns) * cw, (i // columns) * ch
        thumb = image.copy()
        thumb.thumbnail((cw - 10, ch - 34))
        sheet.paste(thumb, (x + (cw - thumb.width) // 2, y + 28))
        draw.text((x + 5, y + 5), label, fill="black")
    sheet.save(destination)


def _profile_plot(u, template, destination):
    im = Image.new("RGB", (1000, 520), "white")
    d = ImageDraw.Draw(im)
    left, top, right, bottom = 70, 55, 970, 455
    profile = template["consensus"]
    hi = max(float(np.max(profile)), 1e-6)
    d.text((15, 15), "Sequence-median radial edge evidence; lines = selected ordered boundaries", fill="black")
    d.line((left, bottom, right, bottom), fill="grey")
    d.line((left, top, left, bottom), fill="grey")
    points = []
    for uu, value in zip(u, profile):
        x = left + float(uu) * (right - left)
        y = bottom - float(value) / hi * (bottom - top)
        points.append((x, y))
    if len(points) > 1:
        d.line(points, fill="#333333", width=2)
    for old in (.20, .45, .70):
        x = left + old * (right - left)
        d.line((x, top, x, bottom), fill="#bbbbbb", width=1)
    if template.get("controls"):
        for i, c in enumerate(template["controls"]):
            x = left + c["global_u"] * (right - left)
            d.line((x, top, x, bottom), fill=["#c53b2c", "#26884a", "#245dc0"][i], width=3)
            d.text((x + 4, top + 8), f"{BOUNDARIES[i]} {c['global_u']:.3f}", fill="black")
    for tick in np.linspace(0, 1, 6):
        x = left + tick * (right - left)
        d.text((x - 8, bottom + 8), f"{tick:.1f}", fill="black")
    d.text((15, 485), "u = radial distance / silhouette radius in the same direction; geometry/QC, not a cut grade", fill="black")
    im.save(destination)


def _json_control(control):
    return dict(global_u=float(control["global_u"]),
                sector_u=[float(x) for x in control["sector_u"]],
                observed=[bool(x) for x in control["observed"]],
                zscores=[float(x) if np.isfinite(x) else None for x in control["zscores"]],
                sector_support=float(control["sector_support"]),
                prominence=float(control["prominence"]),
                semantic_window=list(control["semantic_window"]),
                window_margin=float(control["window_margin"]),
                window_margin_samples=float(control["window_margin_samples"]),
                near_window_edge=bool(control["near_window_edge"]))


def run(processed, output, indices, wrap=False, angle_count=96, radial_samples=160):
    processed, output = Path(processed).resolve(), Path(output).resolve()
    if processed == output or processed in output.parents or output in processed.parents:
        raise ValueError("Step input/output must be disjoint")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose a fresh step output directory")
    sequence_path = processed / "sequence.json"
    metadata = json.loads(sequence_path.read_text())
    validate_interval(indices, metadata.get("source_frame_count"), wrap)
    lookup = {}
    for record in metadata.get("frames", []):
        lookup.setdefault(record.get("source_index"), []).append(record)
    selected = []
    excluded = []
    seen = set()
    for index in indices:
        records = lookup.get(index, [])
        if len(records) > 1:
            raise ValueError(f"Ambiguous source index {index}")
        record = records[0] if records else None
        digest = record.get("pixel_sha256", record.get("sha256")) if record else None
        reason = ("missing_frame" if record is None else
                  "unaccepted_outline" if "registration" not in record else
                  "duplicate_frame" if digest in seen else None)
        if reason:
            excluded.append(dict(source_index=index, reason=reason))
            selected.append(None)
        else:
            seen.add(digest)
            selected.append(record)
    accepted = [r for r in selected if r is not None]
    if len(accepted) < 3:
        raise ValueError("Need at least three accepted unique registered frames for a step template")

    frames = []
    for record in accepted:
        with np.load(processed / record["photometry_path"]) as data:
            brightness = data["encoded_brightness"].copy()
            valid = data["valid_mask"].copy()
        reg = record["registration"]
        mask = np.asarray(Image.open(processed / reg["mask_path"]).convert("L")) > 0
        rgb = np.asarray(Image.open(processed / reg["rgb_path"]).convert("RGB"))
        polar = polar_profiles(brightness, mask, valid, angle_count, radial_samples)
        edge = edge_evidence(polar["profiles"], polar["support"])
        sectors = sector_evidence(edge, polar["angles"])
        frames.append(dict(record=record, mask=mask, rgb=rgb, polar=polar, sectors=sectors))
    u = frames[0]["polar"]["u"]
    stacked = np.stack([f["sectors"] for f in frames])
    template = discover_template(stacked, u)

    output.mkdir(parents=True, exist_ok=True)
    _profile_plot(u, template, output / "edge-profile.png")
    result = dict(
        schema_version=SCHEMA,
        requested_indices=list(indices),
        accepted_indices=[r["source_index"] for r in accepted],
        excluded=excluded,
        wrap_explicit=bool(wrap),
        representation="three ordered sequence-level nested boundaries with eight Asscher side/corner sector controls",
        radial_coordinate="distance from registered canvas centre divided by silhouette radius in the same direction",
        correspondence="sequence template; per-frame local edge matches are QC only and never establish individual-facet identity",
        edge_definition="absolute radial derivative of lightly smoothed ray-local median-normalised encoded brightness",
        bands=list(BANDS),
        boundary_names=list(BOUNDARIES),
        sector_names=list(SECTOR_NAMES),
        template_status=template["status"],
        template_reason=template.get("reason"),
        limitation="recorded-image step-band approximation, not crown/pavilion separation, windmill identity, 3-D reconstruction, leakage or cut grading",
        partial_boundaries={
            name: _json_control(control)
            for name, control in (template.get("partial_controls") or {}).items()
        },
        frames=[],
    )
    if template.get("controls"):
        result["boundaries"] = {name: _json_control(c) for name, c in zip(BOUNDARIES, template["controls"])}
        result["coarse_comparison"] = {
            "legacy_radii": [.20, .45, .70],
            "edge_alignment": boundary_alignment(stacked, u, template["controls"]),
            "interpretation": "diagnostic only: ratio > 1 means the detected boundary sits on stronger persistent radial edge evidence than the corresponding legacy fixed radius",
        }
    else:
        result["boundaries"] = {}
        result["coarse_comparison"] = None

    overlays = []
    region_dir = output / "regions"
    if template["status"] != "unavailable":
        region_dir.mkdir(exist_ok=True)
        stride = max(1, int(np.ceil(len(frames) / 12)))
        for j, frame in enumerate(frames):
            masks = build_masks(frame["mask"], template["controls"])
            status, support = frame_support(frame["sectors"], u, template["controls"])
            stem = f"{frame['record']['position']:04d}"
            path = f"regions/{stem}.npz"
            np.savez_compressed(output / path, **masks)
            fractions = {name: float(m.sum() / max(1, frame["mask"].sum())) for name, m in masks.items()}
            result["frames"].append(dict(
                source_index=frame["record"]["source_index"],
                position=frame["record"]["position"],
                status=status,
                region_path=path,
                silhouette_fraction=fractions,
                boundary_support=support,
            ))
            if j % stride == 0 or j == len(frames) - 1:
                overlays.append((f"source {frame['record']['source_index']} · {status}",
                                 _overlay(frame["rgb"], masks)))
        _contact_sheet(overlays[:12], output / "overlays.jpg")
    else:
        for frame in frames:
            result["frames"].append(dict(source_index=frame["record"]["source_index"],
                                         position=frame["record"]["position"],
                                         status="unavailable",
                                         boundary_support=[]))
    (output / "steps.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("processed", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--indices", required=True, help="ordered consecutive source indices")
    p.add_argument("--wrap", action="store_true")
    a = p.parse_args()
    try:
        result = run(a.processed, a.output, [int(i) for i in a.indices.split(",")], a.wrap)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        p.error(str(e))
    print(f"{result['template_status']}: {len(result['accepted_indices'])}/{len(result['requested_indices'])} frames -> {a.output}")


if __name__ == "__main__":
    main()
