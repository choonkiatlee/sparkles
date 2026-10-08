"""Frozen validation contract for Asscher semantic geometry.

This module validates already-produced #75 wireframe outputs. It deliberately
contains no image loader, fitter entry point, or external target loader. The
validation stage measures stability and contract failures without changing the
geometry estimator it is meant to test.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import numpy as np

from . import asscher_sequence_gauge as sequence_gauge
from . import asscher_topology as topology
from . import asscher_wireframe as wireframe

SCHEMA = "diamond360-asscher-geometry-validation/1"
CONTRACT_SCHEMA = "diamond360-asscher-geometry-validation-contract/1"
FROZEN_WIREFRAME_REVISION = "8bbbbf64754f2bcbb48ab435b731bdf95f7722bc"
FROZEN_WIREFRAME_SPEC_SHA256 = (
    "5805a26f468a8b25664556747576075901e36d46401a41182c9d1469f1f68065"
)
BENCHMARK_MANIFEST_PATH = "docs/360/benchmark/source-bundles.json"
BENCHMARK_MANIFEST_CANONICAL_SHA256 = (
    "4e9fb4b51d8b2f628ca678ee309bc04e5fc3b0ca22ee0b1a1d35489685cb88f1"
)

FROZEN_WIREFRAME_SPECIFICATION = {
    "schema_version": "diamond360-asscher-wireframe-fit/1",
    "minimum_geometry_frames": 3,
    "maximum_geometry_frames": 7,
    "step_evidence_schema": "diamond360-asscher-steps/1",
    "topology_schema": "diamond360-asscher-semantic-scaffold/1",
    "crown_control_map": {"C1_C2": 2, "C2_C3": 1, "C3_TABLE": 0},
    "pavilion_loci": {
        "P1": {"window": [0.55, 0.92], "prior": 0.72, "half_width": 0.12},
        "P2": {"window": [0.35, 0.72], "prior": 0.54, "half_width": 0.11},
        "P3": {"window": [0.15, 0.52], "prior": 0.34, "half_width": 0.10},
    },
    "symmetry_policy": (
        "weak counterpart support inherited from persistent multi-sector "
        "evidence; no equality constraint is imposed"
    ),
    "geometry_policy": (
        "one stone-level scaffold is fitted from multiple compatible geometry "
        "views; per-frame edge matches are residual evidence only"
    ),
    "representation_policy": (
        "image-plane semantic support only; no direct polished-facet projection "
        "or exclusive pixel partition is claimed"
    ),
}


# Keep #88's original snapshot intact as an audit baseline.  #96 is a
# separate, explicitly frozen method revision, *not* a rewritten #75 result.
LEGACY_METHOD = "initial_v1"
OUTER_METHOD = "outer_octagon_v2"
FROZEN_OUTER_WIREFRAME_REVISION = "6334cc9d0c7e2c9a26854bfaeec7a8ebbb6fc668"
FROZEN_OUTER_WIREFRAME_SPEC_SHA256 = (
    "aaf8a885efe039b203330f9592dcccdb41ba11f3a731eb31143fa6de06b4e42e"
)
FROZEN_OUTER_WIREFRAME_SPECIFICATION = deepcopy(FROZEN_WIREFRAME_SPECIFICATION)
FROZEN_OUTER_WIREFRAME_SPECIFICATION.update({
    "outer_octagon_schema": "diamond360-asscher-outer-octagon/1",
    "outer_octagon": {
        "schema_version": "diamond360-asscher-outer-octagon/1",
        "purpose": (
            "fit and validate the physical silhouette before using any "
            "interior optical edge as semantic geometry"
        ),
        "selection_thresholds": {
            "minimum_edge_visibility_score": 0.72,
            "maximum_normalized_q90_boundary_residual": 0.040,
            "maximum_cardinal_parallelism_error_deg": 6.0,
            "maximum_abs_log_aspect": 0.10,
            "face_on_aspect_scale": 0.050,
            "face_on_parallelism_scale_deg": 3.0,
            "preferred_face_on_core_frames": 5,
        },
        "consensus_policy": (
            "outline residual, edge visibility, aspect and cardinal "
            "parallelism are absolute reliability gates; among reliable "
            "silhouettes the full outer-octagon projection-consistency score "
            "is used only as a within-stone ranking signal, never as a "
            "cross-stone rejection threshold; a robust medoid/MAD gate "
            "separately removes shape outliers"
        ),
        "stone_outline_policy": (
            "the stone-level GIRDLE_OUTLINE is the coordinate-wise median of "
            "the selected per-frame fitted octagons after centre/scale "
            "normalization in the stable sequence gauge"
        ),
        "physical_geometry_claim": (
            "2-D observed silhouette only; no physical camera angle or "
            "projective rectification is inferred"
        ),
    },
    "geometry_policy": (
        "fit the observed outer octagon first; use it to reject projection/"
        "silhouette outliers and define one stone-level coordinate anchor; "
        "only then infer inward crown/table support from persistent edges"
    ),
})


def _method_profile(method):
    if method == LEGACY_METHOD:
        return (
            FROZEN_WIREFRAME_REVISION,
            FROZEN_WIREFRAME_SPEC_SHA256,
            FROZEN_WIREFRAME_SPECIFICATION,
        )
    if method == OUTER_METHOD:
        return (
            FROZEN_OUTER_WIREFRAME_REVISION,
            FROZEN_OUTER_WIREFRAME_SPEC_SHA256,
            FROZEN_OUTER_WIREFRAME_SPECIFICATION,
        )
    raise ValueError(f"unknown frozen validation method: {method}")

STATUS_VALUES = ("ok", "review", "unavailable")
PROVENANCE_RANK = {
    "observed": 3,
    "model_inferred": 2,
    "symmetry_inferred": 1,
    "unavailable": 0,
}
OBSERVATION_STATE_RANK = {"complete": 2, "partial": 1, "unavailable": 0}
VALIDITY_RANK = {"ok": 2, "review": 1, "unavailable": 0}


def _jsonable(value):
    """Normalize tuples/numpy-ish values through JSON-compatible containers."""
    return json.loads(json.dumps(value))


def canonical_sha256(value):
    payload = json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_frozen_method(method=OUTER_METHOD):
    """Fail closed unless the declared method matches the running estimator."""
    _, expected_sha, expected_spec = _method_profile(method)
    if wireframe.SCHEMA != expected_spec["schema_version"]:
        raise RuntimeError("wireframe schema differs from frozen method contract")
    current = _jsonable(wireframe.specification())
    if canonical_sha256(current) != expected_sha or current != expected_spec:
        raise RuntimeError(
            "wireframe specification differs from declared frozen method; "
            "run the historical checkout or declare a new method revision"
        )
    if topology.SCAFFOLD_SCHEMA != current["topology_schema"]:
        raise RuntimeError("semantic scaffold schema differs from frozen contract")
    if sequence_gauge.SCHEMA != "diamond360-asscher-sequence-gauge/1":
        raise RuntimeError("sequence gauge contract differs from frozen #80 contract")
    return True

def metric_policy():
    return {
        "coordinate_space": "canonical_image_xy_normalized",
        "boundary_displacement": (
            "Euclidean displacement of corresponding boundary vertices in "
            "canonical coordinates; raw per-vertex values are preserved."
        ),
        "local_tier_normalization": (
            "For crown boundaries, divide each vertex displacement by the "
            "smallest radial separation to an adjacent crown boundary at the "
            "same orientation index. This is a dimensionless fraction of local "
            "tier spacing, not a quality threshold."
        ),
        "entity_displacement": (
            "Euclidean displacement of the centroid of the semantic support "
            "referenced by each entity observation. Crown entities additionally "
            "receive a family-local tier-spacing normalization where defined."
        ),
        "identity_consistency": (
            "Semantic observation IDs, support-to-semantic associations and the "
            "sequence gauge must remain stable."
        ),
        "confidence_change": "candidate confidence minus reference confidence",
        "status_threshold_policy": (
            "Version 1 defines no numeric pass/fail threshold for measured "
            "displacement. Structural, gauge and semantic identity failures are "
            "unavailable; evidence/provenance degradation is review; otherwise ok."
        ),
    }


def status_policy():
    return {
        "ok": "contracts remain valid with no semantic/gauge or evidence regression",
        "review": (
            "topology is valid and identity is stable, but source validity or "
            "observation provenance/availability degraded"
        ),
        "unavailable": (
            "a compared scaffold is missing/invalid, or semantic identity/gauge "
            "cannot be compared without changing the ruler"
        ),
        "numeric_displacement_thresholds": None,
    }


def frozen_method_record(method=OUTER_METHOD):
    revision, specification_sha, specification = _method_profile(method)
    return {
        "method_revision": method,
        "wireframe_revision": revision,
        "wireframe_schema": wireframe.SCHEMA,
        "wireframe_specification": deepcopy(specification),
        "wireframe_specification_sha256": specification_sha,
        "topology_contract_schema": topology.CONTRACT_SCHEMA,
        "topology_scaffold_schema": topology.SCAFFOLD_SCHEMA,
        "sequence_gauge_schema": sequence_gauge.SCHEMA,
    }

def benchmark_snapshot(manifest):
    """Return the source identity fields needed to reproduce a validation run."""
    manifest = _jsonable(manifest)
    if manifest.get("schema_version") != "sparkles-benchmark-sources/2":
        raise ValueError("unsupported benchmark source manifest schema")
    bundles = []
    for row in manifest.get("bundles", []):
        sha = row.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("benchmark bundle is missing a SHA-256")
        bundles.append({
            key: row.get(key)
            for key in (
                "certificate",
                "sha256",
                "bytes",
                "frame_count",
                "source_manifest",
                "filename",
                "download_url",
            )
        })
    if not bundles:
        raise ValueError("benchmark source manifest has no bundles")
    manifest_hash = canonical_sha256(manifest)
    return {
        "manifest_path": BENCHMARK_MANIFEST_PATH,
        "manifest_schema_version": manifest["schema_version"],
        "manifest_canonical_sha256": manifest_hash,
        "expected_manifest_canonical_sha256": BENCHMARK_MANIFEST_CANONICAL_SHA256,
        "manifest_matches_frozen_snapshot": (
            manifest_hash == BENCHMARK_MANIFEST_CANONICAL_SHA256
        ),
        "release_tag": manifest.get("release_tag"),
        "sequence_complete": manifest.get("sequence_complete"),
        "core_indices": manifest.get("core_indices"),
        "bundles": bundles,
    }


def assert_frozen_benchmark_manifest(manifest):
    """Fail closed if benchmark provenance differs from the predeclared set."""
    snapshot = benchmark_snapshot(manifest)
    if not snapshot["manifest_matches_frozen_snapshot"]:
        raise RuntimeError(
            "benchmark source manifest differs from frozen #88 snapshot; "
            "declare a new validation campaign before continuing"
        )
    return snapshot


def contract_document(method=OUTER_METHOD):
    _method_profile(method)
    return {
        "schema_version": CONTRACT_SCHEMA,
        "result_schema": SCHEMA,
        "frozen_method": frozen_method_record(method),
        "benchmark_manifest": {
            "path": BENCHMARK_MANIFEST_PATH,
            "canonical_sha256": BENCHMARK_MANIFEST_CANONICAL_SHA256,
        },
        "metric_policy": metric_policy(),
        "status_policy": status_policy(),
        "anti_leakage": {
            "validation_input": "already-produced wireframe/scaffold dictionaries",
            "image_fitting_available_in_this_module": False,
            "external_target_loading_available_in_this_module": False,
            "rule": (
                "Independent target values are compared only in a separate "
                "post-extraction stage; they are never inputs to geometry fitting "
                "or validation metric definitions."
            ),
        },
    }


def _boundary_map(scaffold):
    return {row["boundary_id"]: row for row in scaffold.get("boundaries", [])}


def _support_map(scaffold):
    return {row["support_id"]: row for row in scaffold.get("semantic_supports", [])}


def _point(scaffold, vertex_id):
    value = scaffold["vertices"][vertex_id]
    point = np.asarray(value, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all():
        raise ValueError(f"invalid vertex coordinates: {vertex_id}")
    return point


def _ring_radius_by_position(scaffold, boundary_id):
    boundary = _boundary_map(scaffold)[boundary_id]
    return {
        index: float(np.linalg.norm(_point(scaffold, vertex_id)))
        for index, vertex_id in enumerate(boundary["vertex_ids"])
    }


def _adjacent_crown_boundaries(boundary_id):
    order = list(topology.CROWN_BOUNDARY_ORDER)
    if boundary_id not in order:
        return []
    index = order.index(boundary_id)
    neighbors = []
    if index:
        neighbors.append(order[index - 1])
    if index + 1 < len(order):
        neighbors.append(order[index + 1])
    return neighbors


def _local_tier_spacing(reference, boundary_id):
    neighbors = _adjacent_crown_boundaries(boundary_id)
    if not neighbors:
        return {}
    current = _ring_radius_by_position(reference, boundary_id)
    neighbor_radii = [
        _ring_radius_by_position(reference, other) for other in neighbors
    ]
    result = {}
    for index, radius in current.items():
        distances = [
            abs(radius - row[index])
            for row in neighbor_radii
            if index in row
        ]
        positive = [value for value in distances if value > 1e-12]
        result[index] = min(positive) if positive else None
    return result


def boundary_displacement(reference, candidate):
    """Raw and locally normalized displacement for matching semantic boundaries."""
    ref_map = _boundary_map(reference)
    cand_map = _boundary_map(candidate)
    rows = {}
    all_ids = sorted(set(ref_map) | set(cand_map))
    for boundary_id in all_ids:
        if boundary_id not in ref_map or boundary_id not in cand_map:
            rows[boundary_id] = {
                "comparable": False,
                "reason": "boundary_missing_from_one_scaffold",
                "per_vertex": [],
            }
            continue
        ref_ids = list(ref_map[boundary_id].get("vertex_ids", []))
        cand_ids = list(cand_map[boundary_id].get("vertex_ids", []))
        if ref_ids != cand_ids:
            rows[boundary_id] = {
                "comparable": False,
                "reason": "boundary_vertex_identity_changed",
                "reference_vertex_ids": ref_ids,
                "candidate_vertex_ids": cand_ids,
                "per_vertex": [],
            }
            continue
        spacing = _local_tier_spacing(reference, boundary_id)
        per_vertex = []
        for index, vertex_id in enumerate(ref_ids):
            displacement = float(np.linalg.norm(
                _point(candidate, vertex_id) - _point(reference, vertex_id)
            ))
            local_spacing = spacing.get(index)
            per_vertex.append({
                "vertex_id": vertex_id,
                "displacement_u": displacement,
                "local_tier_spacing_u": local_spacing,
                "displacement_tier_fraction": (
                    None
                    if local_spacing is None or local_spacing <= 0
                    else float(displacement / local_spacing)
                ),
            })
        values = [row["displacement_u"] for row in per_vertex]
        normalized = [
            row["displacement_tier_fraction"] for row in per_vertex
            if row["displacement_tier_fraction"] is not None
        ]
        rows[boundary_id] = {
            "comparable": True,
            "per_vertex": per_vertex,
            "mean_displacement_u": float(np.mean(values)) if values else None,
            "median_displacement_u": float(np.median(values)) if values else None,
            "max_displacement_u": float(np.max(values)) if values else None,
            "mean_displacement_tier_fraction": (
                float(np.mean(normalized)) if normalized else None
            ),
            "max_displacement_tier_fraction": (
                float(np.max(normalized)) if normalized else None
            ),
        }
    return rows


def _entity_centroid(scaffold, semantic_id):
    observation = scaffold.get("entity_observations", {}).get(semantic_id)
    if not observation:
        return None
    supports = _support_map(scaffold)
    points = []
    for support_id in observation.get("support_ids", []):
        support = supports.get(support_id)
        if not support:
            continue
        points.extend(
            _point(scaffold, vertex_id)
            for vertex_id in support.get("vertex_ids", [])
        )
    if not points:
        return None
    return np.mean(np.asarray(points, dtype=float), axis=0)


def _family_spacing(reference, semantic_id):
    entity = topology.get_entity(
        topology.canonical_physical_topology(), semantic_id
    )
    family = entity.get("family")
    pair = {
        "C1": ("GIRDLE_OUTLINE", "C1_C2"),
        "C2": ("C1_C2", "C2_C3"),
        "C3": ("C2_C3", "C3_TABLE"),
        "table": ("C2_C3", "C3_TABLE"),
        "girdle": ("GIRDLE_OUTLINE", "C1_C2"),
    }.get(family)
    if pair is None:
        return None
    a = _ring_radius_by_position(reference, pair[0])
    b = _ring_radius_by_position(reference, pair[1])
    values = [abs(a[i] - b[i]) for i in sorted(set(a) & set(b))]
    values = [value for value in values if value > 1e-12]
    return float(np.median(values)) if values else None


def entity_displacement(reference, candidate):
    ref_obs = reference.get("entity_observations", {})
    cand_obs = candidate.get("entity_observations", {})
    rows = {}
    for semantic_id in sorted(set(ref_obs) | set(cand_obs)):
        ref_centroid = _entity_centroid(reference, semantic_id)
        cand_centroid = _entity_centroid(candidate, semantic_id)
        if ref_centroid is None or cand_centroid is None:
            rows[semantic_id] = {
                "comparable": False,
                "reason": "semantic_support_centroid_unavailable",
                "displacement_u": None,
                "local_tier_spacing_u": _family_spacing(reference, semantic_id),
                "displacement_tier_fraction": None,
            }
            continue
        displacement = float(np.linalg.norm(cand_centroid - ref_centroid))
        spacing = _family_spacing(reference, semantic_id)
        rows[semantic_id] = {
            "comparable": True,
            "reference_centroid_xy": ref_centroid.tolist(),
            "candidate_centroid_xy": cand_centroid.tolist(),
            "displacement_u": displacement,
            "local_tier_spacing_u": spacing,
            "displacement_tier_fraction": (
                None
                if spacing is None or spacing <= 0
                else float(displacement / spacing)
            ),
        }
    return rows


def semantic_identity_consistency(reference, candidate):
    ref_ids = set(reference.get("entity_observations", {}))
    cand_ids = set(candidate.get("entity_observations", {}))
    ref_supports = {
        key: tuple(row.get("semantic_ids", []))
        for key, row in _support_map(reference).items()
    }
    cand_supports = {
        key: tuple(row.get("semantic_ids", []))
        for key, row in _support_map(candidate).items()
    }
    shared_supports = sorted(set(ref_supports) & set(cand_supports))
    reassignments = [
        {
            "support_id": support_id,
            "reference_semantic_ids": list(ref_supports[support_id]),
            "candidate_semantic_ids": list(cand_supports[support_id]),
        }
        for support_id in shared_supports
        if ref_supports[support_id] != cand_supports[support_id]
    ]
    ref_gauge = reference.get("semantic_gauge", {}).get("gauge_id")
    cand_gauge = candidate.get("semantic_gauge", {}).get("gauge_id")
    return {
        "consistent": bool(
            ref_ids == cand_ids
            and set(ref_supports) == set(cand_supports)
            and not reassignments
            and ref_gauge == cand_gauge
        ),
        "missing_semantic_ids": sorted(ref_ids - cand_ids),
        "extra_semantic_ids": sorted(cand_ids - ref_ids),
        "missing_support_ids": sorted(set(ref_supports) - set(cand_supports)),
        "extra_support_ids": sorted(set(cand_supports) - set(ref_supports)),
        "support_semantic_reassignments": reassignments,
        "reference_gauge_id": ref_gauge,
        "candidate_gauge_id": cand_gauge,
        "gauge_consistent": ref_gauge == cand_gauge,
    }


def observation_changes(reference, candidate):
    ref_obs = reference.get("entity_observations", {})
    cand_obs = candidate.get("entity_observations", {})
    rows = {}
    for semantic_id in sorted(set(ref_obs) & set(cand_obs)):
        a, b = ref_obs[semantic_id], cand_obs[semantic_id]
        rows[semantic_id] = {
            "reference_provenance": a.get("provenance"),
            "candidate_provenance": b.get("provenance"),
            "provenance_changed": a.get("provenance") != b.get("provenance"),
            "provenance_regressed": (
                PROVENANCE_RANK.get(b.get("provenance"), -1)
                < PROVENANCE_RANK.get(a.get("provenance"), -1)
            ),
            "reference_observation_state": a.get("observation_state"),
            "candidate_observation_state": b.get("observation_state"),
            "observation_state_regressed": (
                OBSERVATION_STATE_RANK.get(b.get("observation_state"), -1)
                < OBSERVATION_STATE_RANK.get(a.get("observation_state"), -1)
            ),
            "reference_validity": a.get("validity"),
            "candidate_validity": b.get("validity"),
            "validity_regressed": (
                VALIDITY_RANK.get(b.get("validity"), -1)
                < VALIDITY_RANK.get(a.get("validity"), -1)
            ),
            "reference_confidence": a.get("confidence"),
            "candidate_confidence": b.get("confidence"),
            "confidence_delta": (
                None
                if a.get("confidence") is None or b.get("confidence") is None
                else float(b["confidence"] - a["confidence"])
            ),
        }
    return rows


def compare_scaffolds(reference_scaffold, candidate_scaffold):
    """Compare two fixed scaffolds without refitting or mutating either input."""
    if reference_scaffold is None or candidate_scaffold is None:
        return {
            "status": "unavailable",
            "reasons": ["missing_scaffold"],
            "topology_failures": [],
            "identity": None,
            "boundary_displacement": {},
            "entity_displacement": {},
            "observation_changes": {},
        }

    reference = deepcopy(reference_scaffold)
    candidate = deepcopy(candidate_scaffold)
    topology_failures = []
    for label, scaffold in (("reference", reference), ("candidate", candidate)):
        try:
            topology.validate_scaffold(scaffold)
        except (
            topology.ScaffoldValidationError,
            topology.TopologyValidationError,
            ValueError,
        ) as exc:
            topology_failures.append({"scaffold": label, "error": str(exc)})
    if topology_failures:
        return {
            "status": "unavailable",
            "reasons": ["topology_validation_failed"],
            "topology_failures": topology_failures,
            "identity": None,
            "boundary_displacement": {},
            "entity_displacement": {},
            "observation_changes": {},
        }

    identity = semantic_identity_consistency(reference, candidate)
    if not identity["consistent"]:
        return {
            "status": "unavailable",
            "reasons": ["semantic_identity_or_gauge_changed"],
            "topology_failures": [],
            "identity": identity,
            "boundary_displacement": boundary_displacement(reference, candidate),
            "entity_displacement": entity_displacement(reference, candidate),
            "observation_changes": observation_changes(reference, candidate),
        }

    changes = observation_changes(reference, candidate)
    review_reasons = []
    if (
        VALIDITY_RANK.get(candidate.get("validity"), -1)
        < VALIDITY_RANK.get(reference.get("validity"), -1)
    ):
        review_reasons.append("scaffold_validity_regressed")
    if any(row["provenance_regressed"] for row in changes.values()):
        review_reasons.append("observation_provenance_regressed")
    if any(row["observation_state_regressed"] for row in changes.values()):
        review_reasons.append("observation_state_regressed")
    if any(row["validity_regressed"] for row in changes.values()):
        review_reasons.append("entity_validity_regressed")

    return {
        "status": "review" if review_reasons else "ok",
        "reasons": review_reasons,
        "topology_failures": [],
        "identity": identity,
        "boundary_displacement": boundary_displacement(reference, candidate),
        "entity_displacement": entity_displacement(reference, candidate),
        "observation_changes": changes,
    }


def build_validation_record(
    reference_result,
    candidate_result,
    benchmark_manifest,
    *,
    case_id,
    comparison_kind,
    run_metadata=None,
    method=OUTER_METHOD,
):
    """Wrap a scaffold comparison in the frozen #88 provenance contract.

    Inputs are already-produced #75 result dictionaries. There is intentionally
    no image path, fitting callback, or external target argument.
    """
    assert_frozen_method(method)
    reference_result = deepcopy(reference_result)
    candidate_result = deepcopy(candidate_result)
    sources = assert_frozen_benchmark_manifest(benchmark_manifest)

    result_reasons = []
    for label, result in (
        ("reference", reference_result),
        ("candidate", candidate_result),
    ):
        if result.get("schema_version") != wireframe.SCHEMA:
            result_reasons.append(f"{label}_wireframe_schema_mismatch")
        if result.get("status") == "unavailable" or result.get("scaffold") is None:
            result_reasons.append(f"{label}_wireframe_unavailable")

    if result_reasons:
        comparison = {
            "status": "unavailable",
            "reasons": result_reasons,
            "topology_failures": [],
            "identity": None,
            "boundary_displacement": {},
            "entity_displacement": {},
            "observation_changes": {},
        }
    else:
        comparison = compare_scaffolds(
            reference_result["scaffold"], candidate_result["scaffold"]
        )

    return {
        "schema_version": SCHEMA,
        "case_id": str(case_id),
        "comparison_kind": str(comparison_kind),
        "status": comparison["status"],
        "reasons": comparison["reasons"],
        "frozen_method": frozen_method_record(method),
        "benchmark_inputs": sources,
        "metric_policy": metric_policy(),
        "status_policy": status_policy(),
        "run_metadata": _jsonable(run_metadata or {}),
        "reference_result_status": reference_result.get("status"),
        "candidate_result_status": candidate_result.get("status"),
        "measurements": {
            "topology_failures": comparison["topology_failures"],
            "semantic_identity": comparison["identity"],
            "boundary_displacement": comparison["boundary_displacement"],
            "entity_displacement": comparison["entity_displacement"],
            "observation_changes": comparison["observation_changes"],
        },
        "interpretation": (
            "Geometry validation only. Raw displacement is reported without a "
            "quality meaning or post-hoc numeric pass threshold."
        ),
    }
