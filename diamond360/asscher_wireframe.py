"""Stone-level constrained semantic Asscher wireframe fitting.

The fitter consumes #73 canonical pose, #80's stable sequence gauge, #74's
semantic topology, and the persistent radial evidence from asscher_steps.  Its
primary product is one fixed stone-level image-plane semantic scaffold.  Local
per-frame edge matches are retained only as support/residual evidence and never
move that scaffold.

Physical semantic identity, image-plane semantic support, and later optical
appearance regions remain distinct.  In particular pavilion supports visible
through the table are deliberately non-exclusive and are not direct polished-
facet projection claims.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from . import asscher_outer_octagon as outer_octagon
from . import asscher_steps as steps
from . import asscher_topology as topology

SCHEMA = "diamond360-asscher-wireframe-fit/1"
MIN_GEOMETRY_FRAMES = 3
MAX_GEOMETRY_FRAMES = 7
LOCAL_RESIDUAL_RADIUS_U = 0.035

# asscher_steps radial-sector order -> topology semantic orientation order.
STEP_TO_TOPOLOGY = (6, 7, 0, 1, 2, 3, 4, 5)
TOPOLOGY_TO_STEP = tuple(STEP_TO_TOPOLOGY.index(i) for i in range(8))

# The three persistent #19 step anchors are reused in outer-to-inner order.
# These are image-plane semantic hypotheses, not physical facet lengths.
CROWN_CONTROL_MAP = {
    "C1_C2": 2,   # middle_outer
    "C2_C3": 1,   # inner_middle
    "C3_TABLE": 0,  # centre_inner
}

# Pavilion loci are weaker non-exclusive semantic supports within the fitted
# table. Fractions are relative to each sector's table radius.
PAVILION_LOCI = {
    "P1": {"window": (0.55, 0.92), "prior": 0.72, "half_width": 0.12},
    "P2": {"window": (0.35, 0.72), "prior": 0.54, "half_width": 0.11},
    "P3": {"window": (0.15, 0.52), "prior": 0.34, "half_width": 0.10},
}


def specification():
    return {
        "schema_version": SCHEMA,
        "minimum_geometry_frames": MIN_GEOMETRY_FRAMES,
        "maximum_geometry_frames": MAX_GEOMETRY_FRAMES,
        "outer_octagon_schema": outer_octagon.SCHEMA,
        "outer_octagon": outer_octagon.specification(),
        "step_evidence_schema": steps.SCHEMA,
        "topology_schema": topology.SCAFFOLD_SCHEMA,
        "crown_control_map": dict(CROWN_CONTROL_MAP),
        "pavilion_loci": PAVILION_LOCI,
        "symmetry_policy": (
            "weak counterpart support inherited from persistent multi-sector "
            "evidence; no equality constraint is imposed"
        ),
        "geometry_policy": (
            "fit the observed outer octagon first; use it to reject projection/"
            "silhouette outliers and define one stone-level coordinate anchor; "
            "only then infer inward crown/table support from persistent edges"
        ),
        "representation_policy": (
            "image-plane semantic support only; no direct polished-facet "
            "projection or exclusive pixel partition is claimed"
        ),
    }


def _clip01(value):
    return float(np.clip(float(value), 0.0, 1.0))


def _topology_order(values):
    values = np.asarray(values, float)
    if values.shape != (8,):
        raise ValueError("expected eight radial sector values")
    return values[list(STEP_TO_TOPOLOGY)]


def _step_order(values):
    values = np.asarray(values, float)
    if values.shape != (8,):
        raise ValueError("expected eight semantic orientation values")
    return values[list(TOPOLOGY_TO_STEP)]


def _ideal_outer_vertices(cut=0.28):
    points = np.asarray([
        [-1 + cut, -1], [1 - cut, -1], [1, -1 + cut], [1, 1 - cut],
        [1 - cut, 1], [-1 + cut, 1], [-1, 1 - cut], [-1, -1 + cut],
    ], dtype=float)
    return points


def _ring_vertices(outer_vertices, sector_controls):
    """Scale outline vertices using the two semantic edge sectors they join."""
    outer = np.asarray(outer_vertices, float)
    controls = np.asarray(sector_controls, float)
    if outer.shape != (8, 2) or controls.shape != (8,):
        raise ValueError("outer_vertices must be 8x2 and controls length eight")
    if not np.isfinite(outer).all() or not np.isfinite(controls).all():
        raise ValueError("ring geometry must be finite")
    if np.any(controls <= 0) or np.any(controls > 1.001):
        raise ValueError("ring controls must lie in (0, 1]")
    vertex_scale = np.array([
        0.5 * (controls[(i - 1) % 8] + controls[i])
        for i in range(8)
    ])
    return outer * vertex_scale[:, None]


def _set_ring(scaffold, prefix, points):
    points = np.asarray(points, float)
    if points.shape != (8, 2):
        raise ValueError("ring points must be 8x2")
    for i, point in enumerate(points):
        scaffold["vertices"][f"{prefix}_V{i}"] = [
            float(point[0]), float(point[1])
        ]


def _boundary_confidence(control):
    support = float(control.get("sector_support", 0.0))
    margin = float(control.get("window_margin", 0.0))
    # Window margin is QC rather than another learned score.  Saturate quickly
    # so confidence is dominated by cross-sector evidence.
    margin_score = min(1.0, margin / 0.035)
    return _clip01(0.82 * support + 0.18 * margin_score)


def _control_sector_confidence(control):
    observed = np.asarray(control.get("observed", np.zeros(8)), bool)
    zscores = np.asarray(control.get("zscores", np.full(8, np.nan)), float)
    values = np.full(8, 0.20, float)
    good = observed & np.isfinite(zscores)
    values[good] = np.clip(0.45 + 0.18 * zscores[good], 0.0, 1.0)
    return _topology_order(values)


def _compact_control(control):
    return {
        "global_u": float(control["global_u"]),
        "sector_u_step_order": [
            float(x) for x in np.asarray(control["sector_u"], float)
        ],
        "sector_u_topology_order": [
            float(x) for x in _topology_order(control["sector_u"])
        ],
        "sector_support": float(control.get("sector_support", 0.0)),
        "confidence": _boundary_confidence(control),
        "semantic_window": [
            float(x) for x in control.get("semantic_window", ())
        ],
        "window_margin": float(control.get("window_margin", 0.0)),
        "near_window_edge": bool(control.get("near_window_edge", False)),
    }


def extract_sector_evidence(brightness, mask, valid_mask):
    """Reuse #19's normalized radial evidence without assigning facet identity."""
    profiles = steps.polar_profiles(brightness, mask, valid_mask)
    edge = steps.edge_evidence(profiles["profiles"], profiles["support"])
    sectors = steps.sector_evidence(edge, profiles["angles"])
    return np.asarray(profiles["u"], float), np.asarray(sectors, float)


def _pavilion_loci(frame_sector_evidence, u, table_step_controls):
    """Fit weak, non-exclusive pavilion support loci inside the table."""
    data = np.asarray(frame_sector_evidence, float)
    u = np.asarray(u, float)
    table = np.asarray(table_step_controls, float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sectors = np.nanmedian(data, axis=0)
        consensus = np.nanmedian(sectors, axis=0)
    consensus = ndi.gaussian_filter1d(
        np.nan_to_num(consensus, nan=0.0), 1.0, mode="nearest"
    )
    table_global = float(np.median(table))
    results = {}

    for family, spec in PAVILION_LOCI.items():
        lo_frac, hi_frac = spec["window"]
        lo, hi = lo_frac * table_global, hi_frac * table_global
        zone = (u >= lo) & (u <= hi)
        ids = np.flatnonzero(zone)
        if not len(ids):
            global_u = float(spec["prior"] * table_global)
        else:
            global_u = float(u[ids[int(np.argmax(consensus[ids]))]])

        values = np.full(8, global_u, float)
        observed = np.zeros(8, bool)
        zscores = np.full(8, np.nan, float)
        radius = max(0.018, 0.10 * table_global)
        for sector in range(8):
            peak = steps._local_peak(
                sectors[sector], u, global_u, radius=radius
            )
            if (
                peak is not None
                and peak.get("z") is not None
                and peak["z"] >= 0.8
                and lo <= peak["u"] <= hi
            ):
                values[sector] = float(peak["u"])
                observed[sector] = True
                zscores[sector] = float(peak["z"])

        if float(observed.mean()) < 0.25:
            values = table * float(spec["prior"])
            observed[:] = False
            zscores[:] = np.nan
            provenance = "model_inferred"
        else:
            provenance = "observed"

        results[family] = {
            "global_u": float(np.median(values)),
            "sector_u": values,
            "observed": observed,
            "zscores": zscores,
            "sector_support": float(observed.mean()),
            "provenance": provenance,
            "table_fraction_window": [float(lo_frac), float(hi_frac)],
        }

    # Preserve P3 < P2 < P1 < table separately in every sector.  A conflict
    # drops that sector back to the declared model prior instead of forcing an
    # edge to masquerade as a different semantic family.
    for sector in range(8):
        ordered = [
            results["P3"]["sector_u"][sector],
            results["P2"]["sector_u"][sector],
            results["P1"]["sector_u"][sector],
            table[sector],
        ]
        if np.min(np.diff(ordered)) <= 0.025:
            for family in ("P1", "P2", "P3"):
                spec = PAVILION_LOCI[family]
                results[family]["sector_u"][sector] = (
                    table[sector] * float(spec["prior"])
                )
                results[family]["observed"][sector] = False
                results[family]["zscores"][sector] = np.nan
                results[family]["provenance"] = "model_inferred"

    for family in results:
        row = results[family]
        row["sector_support"] = float(np.mean(row["observed"]))
        row["global_u"] = float(np.median(row["sector_u"]))
        row["confidence"] = _clip01(
            0.18 + 0.72 * row["sector_support"]
            if row["sector_support"] > 0
            else 0.20
        )
    return results


def _frame_target_diagnostic(profile, u, target):
    peak = steps._local_peak(
        profile, u, float(target), radius=LOCAL_RESIDUAL_RADIUS_U
    )
    if peak is None or peak.get("z") is None:
        return {"supported": False, "residual_u": None, "z": None}
    supported = bool(peak["z"] >= 0.8)
    return {
        "supported": supported,
        "residual_u": (
            float(abs(peak["u"] - float(target))) if supported else None
        ),
        "z": float(peak["z"]),
    }


def _frame_evidence_rows(
    data, u, crown_controls, pavilion, frame_metadata
):
    rows = []
    for frame_index, frame in enumerate(np.asarray(data, float)):
        meta = (
            frame_metadata[frame_index]
            if frame_metadata is not None
            else {"source_index": frame_index, "position": frame_index}
        )
        row = {
            "source_index": meta.get("source_index"),
            "position": meta.get("position"),
            "rotation_phase_deg": meta.get("rotation_phase_deg"),
            "boundaries": {},
            "pavilion_support_loci": {},
        }
        for boundary_id, control in crown_controls.items():
            targets = np.asarray(control["sector_u"], float)
            diagnostics = [
                _frame_target_diagnostic(frame[s], u, targets[s])
                for s in range(8)
            ]
            supported = [d["supported"] for d in diagnostics]
            residuals = [
                d["residual_u"] for d in diagnostics
                if d["residual_u"] is not None
            ]
            row["boundaries"][boundary_id] = {
                "sector_supported_step_order": supported,
                "support_fraction": float(np.mean(supported)),
                "median_residual_u": (
                    None if not residuals else float(np.median(residuals))
                ),
            }
        for family, fit in pavilion.items():
            targets = np.asarray(fit["sector_u"], float)
            diagnostics = [
                _frame_target_diagnostic(frame[s], u, targets[s])
                for s in range(8)
            ]
            supported = [d["supported"] for d in diagnostics]
            residuals = [
                d["residual_u"] for d in diagnostics
                if d["residual_u"] is not None
            ]
            row["pavilion_support_loci"][family] = {
                "sector_supported_step_order": supported,
                "support_fraction": float(np.mean(supported)),
                "median_residual_u": (
                    None if not residuals else float(np.median(residuals))
                ),
            }
        rows.append(row)
    return rows


def _supporting_sources(
    frame_rows, kind, semantic_key, topology_sector=None, threshold=0.8
):
    sources, positions = [], []
    raw_sector = (
        None
        if topology_sector is None
        else TOPOLOGY_TO_STEP[int(topology_sector)]
    )
    for row in frame_rows:
        record = row[kind][semantic_key]
        if raw_sector is None:
            supported = record["support_fraction"] >= threshold
        else:
            supported = record["sector_supported_step_order"][raw_sector]
        if supported:
            sources.append(row.get("source_index"))
            positions.append(row.get("position"))
    return sources, positions


def _add_support(
    scaffold, support_id, semantic_ids, vertex_ids, confidence, provenance
):
    record = {
        "support_id": support_id,
        "support_type": "polygon",
        "semantic_ids": list(semantic_ids),
        "vertex_ids": list(vertex_ids),
        "attribution_mode": "nonexclusive_semantic_support",
        "direct_projection_claim": False,
        "confidence": _clip01(confidence),
        "provenance": provenance,
        "observation_state": (
            "complete" if confidence >= 0.65 else "partial"
        ),
    }
    scaffold["semantic_supports"].append(record)
    return record


def _update_entity_observations(scaffold, frame_rows):
    supports = {
        row["support_id"]: row for row in scaffold["semantic_supports"]
    }
    by_semantic = {}
    for support in supports.values():
        for semantic_id in support["semantic_ids"]:
            by_semantic.setdefault(semantic_id, []).append(support)

    for semantic_id, observation in scaffold["entity_observations"].items():
        refs = by_semantic.get(semantic_id, [])
        observation["support_ids"] = [row["support_id"] for row in refs]
        if refs:
            confidence = max(float(row["confidence"]) for row in refs)
            provenance = (
                "observed"
                if any(row["provenance"] == "observed" for row in refs)
                else "model_inferred"
            )
            observation.update(
                confidence=confidence,
                provenance=provenance,
                observation_state=(
                    "complete" if confidence >= 0.65 else "partial"
                ),
                validity="ok" if confidence >= 0.40 else "review",
            )

        entity = topology.get_entity(
            topology.canonical_physical_topology(), semantic_id
        )
        family = entity.get("family")
        orientation_index = entity.get("orientation_index")
        sources, positions = [], []
        if family in ("C1", "C2", "C3") and orientation_index is not None:
            inner_boundary = {
                "C1": "C1_C2", "C2": "C2_C3", "C3": "C3_TABLE"
            }[family]
            sources, positions = _supporting_sources(
                frame_rows, "boundaries", inner_boundary,
                topology_sector=orientation_index,
            )
        elif family in ("P1", "P2", "P3") and orientation_index is not None:
            sources, positions = _supporting_sources(
                frame_rows, "pavilion_support_loci", family,
                topology_sector=orientation_index,
            )
        elif semantic_id == "TABLE":
            sources, positions = _supporting_sources(
                frame_rows, "boundaries", "C3_TABLE", threshold=0.50
            )
        elif semantic_id == "GIRDLE":
            sources = [row.get("source_index") for row in frame_rows]
            positions = [row.get("position") for row in frame_rows]
            observation.update(
                confidence=0.95,
                provenance="observed",
                observation_state="complete",
                validity="ok",
            )
        elif semantic_id == "CULET_REGION":
            sources, positions = _supporting_sources(
                frame_rows, "pavilion_support_loci", "P3", threshold=0.50
            )

        observation["supporting_source_indices"] = [
            value for value in sources if value is not None
        ]
        observation["supporting_positions"] = [
            value for value in positions if value is not None
        ]


def fit_from_sector_evidence(
    frame_sector_evidence,
    u,
    *,
    gauge_id,
    frame_metadata=None,
    outer_vertices=None,
    outer_confidence=0.95,
    step_peak_policy=steps.GLOBAL_PEAK_POLICY,
    step_rank_policy=steps.LEGACY_RANK_POLICY,
):
    """Fit one fixed scaffold from already-gauged multi-frame edge evidence."""
    data = np.asarray(frame_sector_evidence, float)
    u = np.asarray(u, float)
    if data.ndim != 3 or data.shape[1] != 8 or data.shape[2] != len(u):
        raise ValueError("evidence must be frame x 8-sector x radial-sample")
    if data.shape[0] < MIN_GEOMETRY_FRAMES:
        return {
            "schema_version": SCHEMA,
            "status": "unavailable",
            "reason": "fewer_than_three_compatible_geometry_views",
            "scaffold": None,
        }
    if not gauge_id:
        raise ValueError("stable sequence gauge_id is required")

    # Original #75/#96 path is unchanged; experimental selection is opt-in.
    template = (
        steps.discover_template(data, u)
        if (step_peak_policy == steps.GLOBAL_PEAK_POLICY
            and step_rank_policy == steps.LEGACY_RANK_POLICY)
        else steps.discover_template(
            data, u, peak_policy=step_peak_policy,
            rank_policy=step_rank_policy,
        )
    )
    if template["status"] == "unavailable":
        return {
            "schema_version": SCHEMA,
            "status": "unavailable",
            "reason": template.get("reason"),
            "fit_specification": specification(),
            "scaffold": None,
            "partial_step_controls": {
                key: _compact_control(value)
                for key, value in template.get("partial_controls", {}).items()
            },
        }

    controls = template["controls"]
    crown_controls = {
        boundary_id: controls[index]
        for boundary_id, index in CROWN_CONTROL_MAP.items()
    }
    table_step = np.asarray(
        crown_controls["C3_TABLE"]["sector_u"], float
    )
    pavilion = _pavilion_loci(data, u, table_step)
    frame_rows = _frame_evidence_rows(
        data, u, crown_controls, pavilion, frame_metadata
    )

    scaffold = topology.canonical_synthetic_scaffold(
        gauge_id=str(gauge_id)
    )
    outer = (
        _ideal_outer_vertices()
        if outer_vertices is None
        else np.asarray(outer_vertices, float)
    )
    if outer.shape != (8, 2):
        raise ValueError("outer_vertices must be 8x2")

    _set_ring(scaffold, "GIRDLE_OUTLINE", outer)
    boundary_controls_topology = {
        "GIRDLE_OUTLINE": np.ones(8, float),
    }
    for boundary_id, control in crown_controls.items():
        semantic_controls = _topology_order(control["sector_u"])
        boundary_controls_topology[boundary_id] = semantic_controls
        _set_ring(
            scaffold,
            boundary_id,
            _ring_vertices(outer, semantic_controls),
        )

    # Update boundary evidence/provenance on the #74 scaffold.
    boundaries = {
        row["boundary_id"]: row for row in scaffold["boundaries"]
    }
    outer_confidence = _clip01(outer_confidence)
    boundaries["GIRDLE_OUTLINE"].update(
        confidence=outer_confidence,
        provenance="observed",
        observation_state="complete",
    )
    for boundary_id, control in crown_controls.items():
        confidence = _boundary_confidence(control)
        boundaries[boundary_id].update(
            confidence=confidence,
            provenance=(
                "observed" if control["sector_support"] >= 0.50
                else "model_inferred"
            ),
            observation_state=(
                "complete" if control["sector_support"] >= 0.75
                else "partial"
            ),
        )

    # Crown family supports inherit the two bounding semantic controls, but
    # remain non-exclusive image-plane supports under #74.
    support_index = {
        row["support_id"]: row for row in scaffold["semantic_supports"]
    }
    crown_bounds = {
        "C1": ("GIRDLE_OUTLINE", "C1_C2"),
        "C2": ("C1_C2", "C2_C3"),
        "C3": ("C2_C3", "C3_TABLE"),
    }
    boundary_sector_conf = {
        "GIRDLE_OUTLINE": np.full(8, outer_confidence, float),
        **{
            boundary_id: _control_sector_confidence(control)
            for boundary_id, control in crown_controls.items()
        },
    }
    for family, (outer_id, inner_id) in crown_bounds.items():
        for sector, orientation in enumerate(topology.ORIENTATIONS):
            support = support_index[f"SUPPORT_{family}_{orientation}"]
            confidence = float(min(
                boundary_sector_conf[outer_id][sector],
                boundary_sector_conf[inner_id][sector],
            ))
            support.update(
                confidence=_clip01(confidence),
                provenance=(
                    "observed" if confidence >= 0.45
                    else "model_inferred"
                ),
                observation_state=(
                    "complete" if confidence >= 0.65 else "partial"
                ),
            )

    # Pavilion supports are deliberately overlapping image-plane loci.  They
    # are not interpreted as direct polished-facet projections.
    for family, fit in pavilion.items():
        topo_controls = _topology_order(fit["sector_u"])
        table_topo = boundary_controls_topology["C3_TABLE"]
        half = float(PAVILION_LOCI[family]["half_width"])
        outer_controls = np.minimum(
            table_topo * 0.98,
            topo_controls + half * table_topo,
        )
        inner_controls = np.maximum(
            0.025,
            topo_controls - half * table_topo,
        )
        _set_ring(
            scaffold,
            f"{family}_HINT_OUTER",
            _ring_vertices(outer, outer_controls),
        )
        _set_ring(
            scaffold,
            f"{family}_HINT_INNER",
            _ring_vertices(outer, inner_controls),
        )
        sector_conf = np.full(8, 0.20, float)
        observed = _topology_order(fit["observed"].astype(float)) > 0.5
        zscores = _topology_order(
            np.nan_to_num(fit["zscores"], nan=0.0)
        )
        sector_conf[observed] = np.clip(
            0.42 + 0.16 * zscores[observed], 0.0, 1.0
        )
        for sector, orientation in enumerate(topology.ORIENTATIONS):
            support = support_index[f"SUPPORT_{family}_{orientation}"]
            confidence = float(sector_conf[sector])
            support.update(
                confidence=_clip01(confidence),
                provenance=(
                    "observed" if observed[sector] else "model_inferred"
                ),
                observation_state=(
                    "complete" if confidence >= 0.65 else "partial"
                ),
            )

    table_vertices = boundaries["C3_TABLE"]["vertex_ids"]
    table_confidence = float(boundaries["C3_TABLE"]["confidence"])
    table_support = _add_support(
        scaffold,
        "SUPPORT_TABLE",
        ["TABLE"],
        table_vertices,
        table_confidence,
        boundaries["C3_TABLE"]["provenance"],
    )
    scaffold["entity_observations"]["TABLE"]["support_ids"] = [
        table_support["support_id"]
    ]

    culet_vertices = [
        f"P3_HINT_INNER_V{i}" for i in range(8)
    ]
    culet_support = _add_support(
        scaffold,
        "SUPPORT_CULET_REGION",
        ["CULET_REGION"],
        culet_vertices,
        pavilion["P3"]["confidence"],
        pavilion["P3"]["provenance"],
    )
    scaffold["entity_observations"]["CULET_REGION"]["support_ids"] = [
        culet_support["support_id"]
    ]

    # Windmill/junction identity exists, but v1 does not force a visible edge
    # to become a directly observed polished junction.
    for orientation in ("NE", "SE", "SW", "NW"):
        scaffold["entity_observations"][f"WINDMILL_{orientation}"].update(
            confidence=0.25,
            provenance="model_inferred",
            observation_state="partial",
            validity="review",
            supporting_source_indices=[],
            supporting_positions=[],
        )

    _update_entity_observations(scaffold, frame_rows)

    review_reasons = []
    if template["status"] == "review":
        review_reasons.append(template.get("reason") or "step_template_review")
    weak_pavilion = [
        family for family, row in pavilion.items()
        if row["sector_support"] < 0.25
    ]
    if weak_pavilion:
        review_reasons.append(
            "weak_pavilion_support:" + ",".join(weak_pavilion)
        )
    scaffold["validity"] = "review" if review_reasons else "ok"
    scaffold["review_reasons"] = review_reasons
    scaffold["coordinate_metadata"] = {
        "outer_outline_source": (
            "multi_frame_median_outline"
            if outer_vertices is not None
            else "canonical_model_outline"
        ),
        "radial_coordinate": "silhouette_normalized_u",
        "physical_length_claim": False,
    }
    topology.validate_scaffold(scaffold)

    selected_candidate_u = [
        float(control["global_u"]) for control in controls
    ]
    rejected = [
        {
            "u": float(candidate["u"]),
            "prominence": float(candidate["prominence"]),
            "sector_support": float(candidate["sector_support"]),
        }
        for candidate in template.get("candidates", [])
        if all(
            abs(float(candidate["u"]) - chosen_u) > 1e-12
            for chosen_u in selected_candidate_u
        )
    ]

    boundary_evidence = {
        boundary_id: _compact_control(control)
        for boundary_id, control in crown_controls.items()
    }
    pavilion_evidence = {
        family: {
            "global_u": float(row["global_u"]),
            "sector_u_step_order": [
                float(x) for x in row["sector_u"]
            ],
            "sector_u_topology_order": [
                float(x) for x in _topology_order(row["sector_u"])
            ],
            "sector_support": float(row["sector_support"]),
            "confidence": float(row["confidence"]),
            "provenance": row["provenance"],
            "table_fraction_window": row["table_fraction_window"],
        }
        for family, row in pavilion.items()
    }

    return {
        "schema_version": SCHEMA,
        "status": scaffold["validity"],
        "reason": None,
        "fit_specification": specification(),
        "topology_id": topology.TOPOLOGY_ID,
        "semantic_gauge_id": str(gauge_id),
        "scaffold": scaffold,
        "boundary_evidence": boundary_evidence,
        "pavilion_evidence": pavilion_evidence,
        "frame_evidence": frame_rows,
        "rejected_candidates": rejected,
        **({"c3_ranking_audit": template["c3_ranking_audit"]}
           if "c3_ranking_audit" in template else {}),
        "interpretation": (
            "One fixed stone-level image-plane semantic scaffold inferred from "
            "multiple compatible geometry views. Per-frame edge matches are "
            "support/residual evidence only and do not redefine geometry. "
            "Pavilion supports are non-exclusive through-table semantic loci, "
            "not direct polished-facet projections or optical regions."
        ),
    }


def _select_geometry_records(payload, max_frames=MAX_GEOMETRY_FRAMES):
    records = list(payload.get("frames", []))
    resolved = payload.get("face_selection", {}).get("status") == "resolved"
    candidates = []
    for record in records:
        status = record.get("assessment", {}).get("status")
        canonical = record.get("canonical") or {}
        coordinate = record.get("sequence_coordinate") or {}
        if status not in ("ok", "review") or not canonical.get("path"):
            continue
        if coordinate.get("gauge_status") not in ("available", "review"):
            continue
        if resolved and record.get("face_role") != "likely_crown_lobe":
            continue
        candidates.append(record)
    candidates.sort(
        key=lambda row: (
            int(row.get("rank", 10**9)),
            int(row.get("position", 10**9)),
        )
    )
    if max_frames is None:
        return candidates
    return candidates[: int(max_frames)]


def _gauge_id(payload):
    gauge = (payload.get("sequence_gauge") or {}).get(
        "orientation_gauge"
    ) or {}
    if gauge.get("status") not in ("available", "review"):
        return None
    return (
        f"asscher-sequence-gauge-v1:"
        f"{gauge.get('reference_source_index')}:"
        f"{gauge.get('selected_reference_quarter_turn')}"
    )


def _rotate_to_gauge(array, record):
    branch = record.get("sequence_coordinate", {}).get(
        "gauge_quarter_turn"
    )
    if branch not in (0, 1, 2, 3):
        raise ValueError("selected frame has no stable quarter-turn gauge")
    return np.rot90(np.asarray(array), k=int(branch))


def _median_outer_vertices(masks):
    masks = [np.asarray(mask, bool) for mask in masks]
    base = _ideal_outer_vertices()
    angles = np.arctan2(base[:, 1], base[:, 0])
    radial = []
    for mask in masks:
        _, outlines, _, _ = steps._ray_geometry(
            mask, angles, radial_samples=32
        )
        radial.append(outlines)
    radius = np.median(np.asarray(radial, float), axis=0)
    points = np.column_stack([
        np.cos(angles) * radius,
        np.sin(angles) * radius,
    ])
    scale = float(np.max(np.abs(points)))
    if not np.isfinite(scale) or scale <= 0:
        return _ideal_outer_vertices()
    return points / scale


def _scaffold_points_in_gauge(mask, scaffold):
    """Map normalized scaffold vertices into the #80 sequence-gauge canvas."""
    yy, xx = np.nonzero(mask)
    if not len(xx):
        raise ValueError("cannot render scaffold without gauge mask support")
    cx, cy = float(np.mean(xx)), float(np.mean(yy))
    scale = max(
        float(np.max(np.abs(xx - cx))),
        float(np.max(np.abs(yy - cy))),
        1.0,
    )
    return {
        vertex_id: (
            cx + float(point[0]) * scale,
            cy + float(point[1]) * scale,
        )
        for vertex_id, point in scaffold["vertices"].items()
    }


def _draw_scaffold_on_frame(brightness, mask, scaffold):
    """Fallback measurement-view QC; intentionally not the preferred display."""
    grey = np.rint(np.clip(brightness, 0.0, 1.0) * 255).astype(np.uint8)
    rgb = np.repeat(grey[:, :, None], 3, axis=2)
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    points_by_id = _scaffold_points_in_gauge(mask, scaffold)

    for support in scaffold["semantic_supports"]:
        if not support["semantic_ids"][0].startswith("P"):
            continue
        points = [points_by_id[v] for v in support["vertex_ids"]]
        draw.line(points + [points[0]], fill=(150, 150, 150), width=1)
    for boundary in scaffold["boundaries"]:
        points = [points_by_id[v] for v in boundary["vertex_ids"]]
        if boundary.get("closed"):
            points += [points[0]]
        draw.line(points, fill=(255, 255, 255), width=2)
    return image


def _draw_scaffold_on_source(processed, record, gauge_mask, scaffold):
    """Render human-facing QC on the untouched camera RGB using exact #80 map."""
    source_path = record.get("source_camera_path")
    transform = (record.get("sequence_coordinate") or {}).get(
        "sequence_gauge_to_camera_xy"
    )
    if not source_path or transform is None:
        return None

    source = Image.open(Path(processed) / source_path).convert("RGB")
    matrix = np.asarray(transform, float)
    if matrix.shape != (3, 3):
        return None

    gauge_points = _scaffold_points_in_gauge(gauge_mask, scaffold)

    def camera_point(vertex_id):
        x, y = gauge_points[vertex_id]
        mapped = matrix @ np.array([x, y, 1.0], dtype=float)
        return float(mapped[0] / mapped[2]), float(mapped[1] / mapped[2])

    draw = ImageDraw.Draw(source)
    width = max(2, int(round(max(source.size) / 280.0)))
    faint_width = max(1, width - 1)
    for support in scaffold["semantic_supports"]:
        if not support["semantic_ids"][0].startswith("P"):
            continue
        points = [camera_point(v) for v in support["vertex_ids"]]
        draw.line(
            points + [points[0]],
            fill=(170, 170, 170),
            width=faint_width,
        )
    for boundary in scaffold["boundaries"]:
        points = [camera_point(v) for v in boundary["vertex_ids"]]
        if boundary.get("closed"):
            points += [points[0]]
        draw.line(points, fill=(255, 255, 255), width=width)

    # Crop using the gauge-mask footprint transformed back to camera space so
    # the QC preserves native source detail without wasting space on background.
    yy, xx = np.nonzero(gauge_mask)
    if not len(xx):
        return source
    xmin, xmax = float(xx.min()), float(xx.max())
    ymin, ymax = float(yy.min()), float(yy.max())
    corners = np.array(
        [
            [xmin, ymin, 1.0],
            [xmax, ymin, 1.0],
            [xmax, ymax, 1.0],
            [xmin, ymax, 1.0],
        ],
        dtype=float,
    ).T
    camera = matrix @ corners
    camera = camera[:2] / camera[2:3]
    left, top = camera.min(axis=1)
    right, bottom = camera.max(axis=1)
    pad = 0.08 * max(right - left, bottom - top)
    box = (
        max(0, int(math.floor(left - pad))),
        max(0, int(math.floor(top - pad))),
        min(source.width, int(math.ceil(right + pad))),
        min(source.height, int(math.ceil(bottom + pad))),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return source
    return source.crop(box)


def _contact_sheet(items, destination, columns=4):
    if not items:
        return None
    width = max(image.width for image in items)
    height = max(image.height for image in items)
    columns = min(columns, len(items))
    rows = int(math.ceil(len(items) / columns))
    sheet = Image.new("RGB", (columns * width, rows * height), "white")
    for i, image in enumerate(items):
        sheet.paste(image, ((i % columns) * width, (i // columns) * height))
    sheet.save(destination, quality=90)
    return Path(destination).name


def fit_pose_sequence(
    pose_output,
    output,
    *,
    max_frames=MAX_GEOMETRY_FRAMES,
    processed=None,
):
    """Fit and persist one stone-level scaffold from a #73/#80 pose output."""
    pose_output = Path(pose_output).resolve()
    output = Path(output).resolve()
    processed = None if processed is None else Path(processed).resolve()
    payload_path = pose_output / "asscher-pose.json"
    if not payload_path.is_file():
        raise ValueError("pose_output must contain asscher-pose.json")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("wireframe output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)

    payload = json.loads(payload_path.read_text())
    gauge_id = _gauge_id(payload)
    if gauge_id is None:
        result = {
            "schema_version": SCHEMA,
            "status": "unavailable",
            "reason": "stable_sequence_gauge_unavailable",
            "scaffold": None,
        }
        (output / "wireframe.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
        return result

    coarse_candidates = _select_geometry_records(payload, max_frames=None)
    selected, outer_selection = outer_octagon.select_records(
        coarse_candidates,
        max_frames=max_frames,
        min_frames=MIN_GEOMETRY_FRAMES,
    )
    if len(selected) < MIN_GEOMETRY_FRAMES:
        result = {
            "schema_version": SCHEMA,
            "status": "unavailable",
            "reason": "fewer_than_three_outer_octagon_views",
            "semantic_gauge_id": gauge_id,
            "selected_source_indices": [
                row.get("source_index") for row in selected
            ],
            "outer_selection": outer_selection,
            "scaffold": None,
        }
        (output / "wireframe.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
        return result

    selection_by_source = {
        row.get("source_index"): row
        for row in outer_selection.get("frames", [])
    }
    evidence, masks, brightness_frames, metadata = [], [], [], []
    u_reference = None
    for record in selected:
        with np.load(pose_output / record["canonical"]["path"]) as data:
            brightness = _rotate_to_gauge(
                np.asarray(data["brightness"], float), record
            )
            mask = _rotate_to_gauge(
                np.asarray(data["mask"], bool), record
            )
            valid = _rotate_to_gauge(
                np.asarray(data["valid_mask"], bool), record
            )
        u, sectors = extract_sector_evidence(brightness, mask, valid)
        if u_reference is None:
            u_reference = u
        elif not np.allclose(u_reference, u):
            raise ValueError("selected canonical frames use incompatible radial grids")
        evidence.append(sectors)
        masks.append(mask)
        brightness_frames.append(brightness)
        coordinate = record.get("sequence_coordinate") or {}
        metadata.append({
            "source_index": record.get("source_index"),
            "position": record.get("position"),
            "rank": record.get("rank"),
            "face_role": record.get("face_role"),
            "rotation_phase_deg": coordinate.get("rotation_phase_deg"),
            "gauge_quarter_turn": coordinate.get("gauge_quarter_turn"),
            "outer_octagon": selection_by_source.get(
                record.get("source_index")
            ),
        })

    outer_fit = outer_octagon.fit_consensus(
        masks,
        frame_metadata=metadata,
    )
    outer = np.asarray(
        outer_fit["vertices_topology_order"],
        float,
    )
    result = fit_from_sector_evidence(
        np.asarray(evidence),
        u_reference,
        gauge_id=gauge_id,
        frame_metadata=metadata,
        outer_vertices=outer,
        outer_confidence=outer_fit["confidence"],
    )
    result["outer_selection"] = outer_selection
    result["outer_evidence"] = outer_fit
    result["selected_frames"] = metadata
    result["sequence_gauge"] = payload.get("sequence_gauge")
    if result.get("scaffold") is not None:
        items = []
        display_source = "normalized_lowpass_measurement_fallback"
        for record, brightness, mask in zip(
            selected, brightness_frames, masks
        ):
            image = None
            if processed is not None:
                image = _draw_scaffold_on_source(
                    processed, record, mask, result["scaffold"]
                )
            if image is None:
                image = _draw_scaffold_on_frame(
                    brightness, mask, result["scaffold"]
                )
            else:
                display_source = "original_camera_rgb_exact_sequence_gauge_map"
            items.append(image)
        reference = topology.render_scaffold(
            result["scaffold"], size=max(items[0].size)
        )
        items.append(reference)
        result["qc_path"] = _contact_sheet(
            items, output / "wireframe-qc.jpg", columns=4
        )
        result["qc_display_source"] = display_source
        result["qc_interpretation"] = (
            "Human-facing QC uses original camera RGB when processed input is "
            "available. The fitter still uses the frozen normalized low-pass "
            "measurement representation; display sharpening does not alter "
            "geometry."
        )
    else:
        result["qc_path"] = None
        result["qc_display_source"] = None

    (output / "wireframe.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fit one fixed semantic Asscher scaffold from #73/#80 pose output"
    )
    parser.add_argument("pose_output", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--max-frames", type=int, default=MAX_GEOMETRY_FRAMES
    )
    parser.add_argument(
        "--processed",
        type=Path,
        default=None,
        help="Optional processed sequence root for sharp native-RGB QC",
    )
    args = parser.parse_args()
    result = fit_pose_sequence(
        args.pose_output,
        args.output,
        max_frames=args.max_frames,
        processed=args.processed,
    )
    print(
        result["status"],
        result.get("reason"),
        result.get("selected_source_indices")
        or [
            row.get("source_index")
            for row in result.get("selected_frames", [])
        ],
    )


if __name__ == "__main__":
    main()
