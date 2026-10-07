"""Geometry-only semantic topology for Asscher-like step cuts.

Physical semantic identity, image-plane semantic support, and future optical /
virtual-facet regions are deliberately separate representations. Image-plane
support is non-exclusive and is never asserted to be a direct polished-facet
projection, especially for pavilion structure seen through the table.
"""
from __future__ import annotations

from copy import deepcopy
import math
from PIL import Image, ImageDraw

TOPOLOGY_SCHEMA = "diamond360-asscher-physical-topology/1"
SCAFFOLD_SCHEMA = "diamond360-asscher-semantic-scaffold/1"
CONTRACT_SCHEMA = "diamond360-asscher-topology-contract/1"
TOPOLOGY_ID = "asscher-step-cut-semantic-v1"

ORIENTATIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
CROWN_FAMILIES = ("C1", "C2", "C3")
PAVILION_FAMILIES = ("P1", "P2", "P3")
FACET_FAMILIES = CROWN_FAMILIES + PAVILION_FAMILIES
PROVENANCE = ("observed", "model_inferred", "symmetry_inferred", "unavailable")
OBSERVATION_STATES = ("complete", "partial", "unavailable")
VALIDITY_STATES = ("ok", "review", "unavailable")
CROWN_BOUNDARY_ORDER = ("GIRDLE_OUTLINE", "C1_C2", "C2_C3", "C3_TABLE")


class TopologyValidationError(ValueError):
    pass


class ScaffoldValidationError(ValueError):
    pass


def _fid(family, orientation):
    return f"{family}_{orientation}"


def _rotation_relations(family, index):
    return {
        f"quarter_turn_{turns}": _fid(
            family, ORIENTATIONS[(index + 2 * turns) % 8]
        )
        for turns in (1, 2, 3)
    }


def canonical_physical_topology():
    """Stable physical semantic identities/relations; no image pixel ownership."""
    entities = []
    for layer, families in (("crown", CROWN_FAMILIES), ("pavilion", PAVILION_FAMILIES)):
        for family_index, family in enumerate(families):
            for i, orientation in enumerate(ORIENTATIONS):
                neighbours = [
                    _fid(family, ORIENTATIONS[(i - 1) % 8]),
                    _fid(family, ORIENTATIONS[(i + 1) % 8]),
                ]
                if family_index:
                    neighbours.append(_fid(families[family_index - 1], orientation))
                if family_index + 1 < len(families):
                    neighbours.append(_fid(families[family_index + 1], orientation))
                if family_index == 0:
                    neighbours.append("GIRDLE")
                if layer == "crown" and family == "C3":
                    neighbours.append("TABLE")
                if layer == "pavilion" and family == "P3":
                    neighbours.append("CULET_REGION")
                if orientation in ("NE", "SE", "SW", "NW"):
                    neighbours.append(f"WINDMILL_{orientation}")
                relations = _rotation_relations(family, i)
                entities.append({
                    "semantic_id": _fid(family, orientation),
                    "entity_type": "physical_facet",
                    "layer": layer,
                    "family": family,
                    "orientation": orientation,
                    "orientation_index": i,
                    "rotation_orbit_id": f"{family}_orbit",
                    "rotation_orbit_members": [_fid(family, o) for o in ORIENTATIONS],
                    "rotation_relations": relations,
                    "opposite_semantic_id": relations["quarter_turn_2"],
                    "structural_neighbors": neighbours,
                })

    corners = ("NE", "SE", "SW", "NW")
    for i, orientation in enumerate(corners):
        members = [f"WINDMILL_{o}" for o in corners]
        entities.append({
            "semantic_id": f"WINDMILL_{orientation}",
            "entity_type": "junction_structure",
            "layer": "shared",
            "family": "windmill_junction",
            "orientation": orientation,
            "orientation_index": ORIENTATIONS.index(orientation),
            "rotation_orbit_id": "WINDMILL_orbit",
            "rotation_orbit_members": members,
            "rotation_relations": {
                f"quarter_turn_{turns}": members[(i + turns) % 4]
                for turns in (1, 2, 3)
            },
            "opposite_semantic_id": members[(i + 2) % 4],
            "structural_neighbors": [_fid(f, orientation) for f in FACET_FAMILIES],
        })

    for semantic_id, layer, family, neighbours in (
        ("TABLE", "crown", "table", [_fid("C3", o) for o in ORIENTATIONS]),
        (
            "GIRDLE",
            "shared",
            "girdle",
            [_fid("C1", o) for o in ORIENTATIONS]
            + [_fid("P1", o) for o in ORIENTATIONS],
        ),
        (
            "CULET_REGION",
            "pavilion",
            "culet_region",
            [_fid("P3", o) for o in ORIENTATIONS],
        ),
    ):
        entities.append({
            "semantic_id": semantic_id,
            "entity_type": "physical_structure",
            "layer": layer,
            "family": family,
            "orientation": None,
            "orientation_index": None,
            "rotation_orbit_id": semantic_id,
            "rotation_orbit_members": [semantic_id],
            "rotation_relations": {
                "quarter_turn_1": semantic_id,
                "quarter_turn_2": semantic_id,
                "quarter_turn_3": semantic_id,
            },
            "opposite_semantic_id": semantic_id,
            "structural_neighbors": neighbours,
        })

    return {
        "schema_version": TOPOLOGY_SCHEMA,
        "topology_id": TOPOLOGY_ID,
        "interpretation": (
            "Physical semantic identity/topology only; not pixel ownership, "
            "not a flat image partition, and not a 3-D reconstruction."
        ),
        "facet_order": {
            "crown_outer_to_inner": list(CROWN_FAMILIES),
            "pavilion_girdle_to_culet": list(PAVILION_FAMILIES),
        },
        "orientation_gauge": {
            "orientations_clockwise": list(ORIENTATIONS),
            "orientation_period_deg": 90,
            "quarter_turn_equivalent": True,
            "sequence_policy": (
                "The absolute N/E/S/W gauge is arbitrary modulo 90 degrees, "
                "but once selected it must remain fixed for a stone/sequence."
            ),
        },
        "image_mapping_policy": {
            "physical_entity_owns_pixels": False,
            "exclusive_pixel_partition_required": False,
            "direct_projection_claim": False,
            "future_optical_association_cardinality": "many_to_many",
        },
        "entities": entities,
    }


def _index(topology):
    return {row["semantic_id"]: row for row in topology["entities"]}


def get_entity(topology, semantic_id):
    try:
        return _index(topology)[semantic_id]
    except KeyError as exc:
        raise KeyError(f"unknown semantic_id: {semantic_id}") from exc


def rotate_semantic_id(topology, semantic_id, quarter_turns=1):
    turns = int(quarter_turns) % 4
    if not turns:
        return semantic_id
    return get_entity(topology, semantic_id)["rotation_relations"][
        f"quarter_turn_{turns}"
    ]


def opposite_semantic_id(topology, semantic_id):
    return get_entity(topology, semantic_id)["opposite_semantic_id"]


def validate_topology(topology):
    if topology.get("schema_version") != TOPOLOGY_SCHEMA:
        raise TopologyValidationError("unsupported topology schema_version")
    if topology.get("topology_id") != TOPOLOGY_ID:
        raise TopologyValidationError("unexpected topology_id")
    ids = [row.get("semantic_id") for row in topology.get("entities", [])]
    if not ids or len(set(ids)) != len(ids) or any(not x for x in ids):
        raise TopologyValidationError("semantic_ids must be non-empty and unique")
    index = _index(topology)
    for row in topology["entities"]:
        semantic_id = row["semantic_id"]
        for other in row.get("structural_neighbors", []):
            if other not in index:
                raise TopologyValidationError(f"{semantic_id} references {other}")
            if semantic_id not in index[other].get("structural_neighbors", []):
                raise TopologyValidationError(
                    f"adjacency must be reciprocal: {semantic_id} -> {other}"
                )
        relation = row.get("rotation_relations", {})
        if any(relation.get(f"quarter_turn_{n}") not in index for n in (1, 2, 3)):
            raise TopologyValidationError(f"invalid rotation relation for {semantic_id}")
        if row.get("opposite_semantic_id") != relation["quarter_turn_2"]:
            raise TopologyValidationError(f"invalid opposite for {semantic_id}")
        q = semantic_id
        for _ in range(4):
            q = rotate_semantic_id(topology, q)
        if q != semantic_id:
            raise TopologyValidationError(f"rotation cycle does not close: {semantic_id}")
    mapping = topology.get("image_mapping_policy", {})
    if (
        mapping.get("exclusive_pixel_partition_required") is not False
        or mapping.get("direct_projection_claim") is not False
        or mapping.get("future_optical_association_cardinality") != "many_to_many"
    ):
        raise TopologyValidationError("image/optical extension policy was narrowed")
    return True


def _ring(radius, cut=0.28):
    r, c = float(radius), float(radius) * float(cut)
    return [
        [-r + c, -r], [r - c, -r], [r, -r + c], [r, r - c],
        [r - c, r], [-r + c, r], [-r, r - c], [-r, -r + c],
    ]


def _add_ring(vertices, prefix, points):
    ids = []
    for i, point in enumerate(points):
        key = f"{prefix}_V{i}"
        vertices[key] = [float(point[0]), float(point[1])]
        ids.append(key)
    return ids


def _supports_between(outer, inner, family):
    return [{
        "support_id": f"SUPPORT_{family}_{orientation}",
        "support_type": "polygon",
        "semantic_ids": [_fid(family, orientation)],
        "vertex_ids": [outer[i], outer[(i + 1) % 8], inner[(i + 1) % 8], inner[i]],
        "attribution_mode": "nonexclusive_semantic_support",
        "direct_projection_claim": False,
        "confidence": 1.0,
        "provenance": "model_inferred",
        "observation_state": "complete",
    } for i, orientation in enumerate(ORIENTATIONS)]


def canonical_synthetic_scaffold(
    *, gauge_id="synthetic-sequence-gauge", asymmetric=False,
    unavailable_semantic_ids=()
):
    """Source-free contract fixture; not an ideal cut or physical projection."""
    topology = canonical_physical_topology()
    vertices, rings = {}, {}
    radii = {
        "GIRDLE_OUTLINE": 1.0,
        "C1_C2": 0.76,
        "C2_C3": 0.56,
        "C3_TABLE": 0.34,
    }
    for role in CROWN_BOUNDARY_ORDER:
        points = _ring(radii[role])
        if asymmetric and role == "C3_TABLE":
            points[0][0] -= 0.025
            points[4][0] += 0.012
            points[2][1] -= 0.010
        rings[role] = _add_ring(vertices, role, points)

    boundaries = [{
        "boundary_id": role,
        "boundary_family": role,
        "nesting_group": "crown_faceup",
        "nesting_rank": rank,
        "closed": True,
        "vertex_ids": rings[role],
        "confidence": 1.0,
        "provenance": "model_inferred",
        "observation_state": "complete",
    } for rank, role in enumerate(CROWN_BOUNDARY_ORDER)]

    supports = []
    for family, outer, inner in (
        ("C1", rings["GIRDLE_OUTLINE"], rings["C1_C2"]),
        ("C2", rings["C1_C2"], rings["C2_C3"]),
        ("C3", rings["C2_C3"], rings["C3_TABLE"]),
    ):
        supports += _supports_between(outer, inner, family)

    # Pavilion support is deliberately overlapping image-plane evidence within
    # the table. It is not required to tile the table or directly project facets.
    table_r = radii["C3_TABLE"]
    for family, outer_scale, inner_scale in (
        ("P1", 0.96, 0.48), ("P2", 0.78, 0.30), ("P3", 0.58, 0.10)
    ):
        outer = _add_ring(vertices, f"{family}_HINT_OUTER", _ring(table_r * outer_scale, 0.22))
        inner = _add_ring(vertices, f"{family}_HINT_INNER", _ring(table_r * inner_scale, 0.22))
        supports += _supports_between(outer, inner, family)

    unavailable = set(unavailable_semantic_ids)
    observations = {}
    for entity in topology["entities"]:
        semantic_id = entity["semantic_id"]
        refs = [s["support_id"] for s in supports if semantic_id in s["semantic_ids"]]
        if semantic_id in unavailable:
            observations[semantic_id] = {
                "validity": "unavailable", "confidence": 0.0,
                "provenance": "unavailable", "observation_state": "unavailable",
                "support_ids": [],
            }
        else:
            observations[semantic_id] = {
                "validity": "ok" if refs else "review",
                "confidence": 1.0 if refs else 0.5,
                "provenance": "model_inferred",
                "observation_state": "complete" if refs else "partial",
                "support_ids": refs,
            }
    if asymmetric:
        observations["P3_N"].update(confidence=0.73, observation_state="partial")

    return {
        "schema_version": SCAFFOLD_SCHEMA,
        "topology_id": TOPOLOGY_ID,
        "coordinate_space": "canonical_image_xy_normalized",
        "interpretation": (
            "2-D semantic support only; non-exclusive association, not direct "
            "projection of polished physical facets."
        ),
        "semantic_gauge": {
            "gauge_id": str(gauge_id),
            "orientation_period_deg": 90,
            "quarter_turn_equivalent": True,
            "sequence_stable_required": True,
        },
        "representation_policy": {
            "exclusive_pixel_partition_required": False,
            "direct_projection_claim": False,
            "supports_may_overlap": True,
            "support_may_reference_multiple_physical_entities": True,
            "future_optical_association_cardinality": "many_to_many",
        },
        "vertices": vertices,
        "boundaries": boundaries,
        "semantic_supports": supports,
        "entity_observations": observations,
        "validity": "ok",
        "review_reasons": [],
    }


def _point(vertices, vertex_id):
    if vertex_id not in vertices:
        raise ScaffoldValidationError(f"missing vertex {vertex_id}")
    value = vertices[vertex_id]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ScaffoldValidationError(f"invalid vertex {vertex_id}")
    point = tuple(map(float, value))
    if not all(math.isfinite(v) for v in point):
        raise ScaffoldValidationError(f"non-finite vertex {vertex_id}")
    return point


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a, b, c, d):
    return _orientation(a, b, c) * _orientation(a, b, d) < 0 and \
        _orientation(c, d, a) * _orientation(c, d, b) < 0


def _validate_polygon(points, label):
    if len(points) < 3:
        raise ScaffoldValidationError(f"{label} needs >=3 vertices")
    n = len(points)
    for i in range(n):
        if math.dist(points[i], points[(i + 1) % n]) <= 1e-12:
            raise ScaffoldValidationError(f"{label} has degenerate edge")
        for j in range(i + 1, n):
            if j in (i, (i + 1) % n) or i in (j, (j + 1) % n):
                continue
            if _segments_cross(
                points[i], points[(i + 1) % n],
                points[j], points[(j + 1) % n]
            ):
                raise ScaffoldValidationError(f"{label} self-intersects")


def _area(points):
    return abs(sum(
        x1 * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * y1
        for i, (x1, y1) in enumerate(points)
    )) * 0.5


def _inside(point, polygon):
    x, y = point
    inside, j = False, len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def _check_observation(record, label):
    if record.get("provenance") not in PROVENANCE:
        raise ScaffoldValidationError(f"{label}: invalid provenance")
    if record.get("observation_state") not in OBSERVATION_STATES:
        raise ScaffoldValidationError(f"{label}: invalid observation_state")
    value = float(record.get("confidence"))
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ScaffoldValidationError(f"{label}: invalid confidence")


def validate_scaffold(scaffold, topology=None):
    """Validate geometry/identity without requiring an exclusive pixel partition."""
    topology = topology or canonical_physical_topology()
    validate_topology(topology)
    if scaffold.get("schema_version") != SCAFFOLD_SCHEMA:
        raise ScaffoldValidationError("unsupported scaffold schema_version")
    if scaffold.get("topology_id") != topology["topology_id"]:
        raise ScaffoldValidationError("topology_id mismatch")

    gauge = scaffold.get("semantic_gauge", {})
    if (
        not gauge.get("gauge_id")
        or gauge.get("orientation_period_deg") != 90
        or gauge.get("sequence_stable_required") is not True
    ):
        raise ScaffoldValidationError("invalid semantic gauge")

    policy = scaffold.get("representation_policy", {})
    required_policy = {
        "exclusive_pixel_partition_required": False,
        "direct_projection_claim": False,
        "supports_may_overlap": True,
        "support_may_reference_multiple_physical_entities": True,
        "future_optical_association_cardinality": "many_to_many",
    }
    if any(policy.get(k) != v for k, v in required_policy.items()):
        raise ScaffoldValidationError("representation policy was narrowed")

    vertices = scaffold.get("vertices", {})
    for vertex_id in vertices:
        _point(vertices, vertex_id)

    nesting = {}
    boundary_ids = set()
    for boundary in scaffold.get("boundaries", []):
        bid = boundary.get("boundary_id")
        if not bid or bid in boundary_ids:
            raise ScaffoldValidationError("boundary ids must be unique")
        boundary_ids.add(bid)
        _check_observation(boundary, f"boundary {bid}")
        points = [_point(vertices, v) for v in boundary.get("vertex_ids", [])]
        if boundary.get("closed"):
            _validate_polygon(points, f"boundary {bid}")
        group = boundary.get("nesting_group")
        if group is not None:
            nesting.setdefault(group, []).append(
                (boundary.get("nesting_rank"), bid, points)
            )

    for group, rows in nesting.items():
        rows = sorted(rows)
        if [r[0] for r in rows] != list(range(len(rows))):
            raise ScaffoldValidationError(f"{group}: invalid nesting ranks")
        parent, parent_area = None, None
        for _, bid, polygon in rows:
            area = _area(polygon)
            if parent_area is not None and area >= parent_area:
                raise ScaffoldValidationError(f"{bid}: reversed nested order")
            if parent is not None and not all(_inside(p, parent) for p in polygon):
                raise ScaffoldValidationError(f"{bid}: leaves parent boundary")
            parent, parent_area = polygon, area

    entity_ids, support_ids = set(_index(topology)), set()
    for support in scaffold.get("semantic_supports", []):
        sid = support.get("support_id")
        if not sid or sid in support_ids:
            raise ScaffoldValidationError("support ids must be unique")
        support_ids.add(sid)
        _check_observation(support, f"support {sid}")
        semantic_ids = support.get("semantic_ids", [])
        if not semantic_ids or any(x not in entity_ids for x in semantic_ids):
            raise ScaffoldValidationError(f"{sid}: invalid semantic references")
        if support.get("direct_projection_claim") is not False:
            raise ScaffoldValidationError(f"{sid}: direct projection claim forbidden")
        points = [_point(vertices, v) for v in support.get("vertex_ids", [])]
        if support.get("support_type") == "polygon":
            _validate_polygon(points, f"support {sid}")

    observations = scaffold.get("entity_observations", {})
    if set(observations) != entity_ids:
        raise ScaffoldValidationError("entity observations must cover topology identities")
    for semantic_id, record in observations.items():
        if record.get("validity") not in VALIDITY_STATES:
            raise ScaffoldValidationError(f"{semantic_id}: invalid validity")
        _check_observation(record, f"observation {semantic_id}")
        refs = record.get("support_ids", [])
        if any(ref not in support_ids for ref in refs):
            raise ScaffoldValidationError(f"{semantic_id}: missing support reference")
        if record["observation_state"] == "unavailable" and refs:
            raise ScaffoldValidationError(f"{semantic_id}: unavailable cannot require support")
    return True


def validate_sequence_gauge(scaffolds):
    """Absolute gauge is arbitrary; selected gauge_id may not drift per frame."""
    rows = list(scaffolds)
    if not rows:
        raise ScaffoldValidationError("sequence requires at least one scaffold")
    gauge_ids = set()
    for scaffold in rows:
        validate_scaffold(scaffold)
        gauge_ids.add(scaffold["semantic_gauge"]["gauge_id"])
    if len(gauge_ids) != 1:
        raise ScaffoldValidationError("semantic gauge_id changed within sequence")
    return True


def render_scaffold(scaffold, topology=None, size=640):
    """Render source-free QC. Overlapping supports are outlines, not segmentation."""
    topology = topology or canonical_physical_topology()
    validate_scaffold(scaffold, topology)
    if int(size) < 64:
        raise ValueError("size must be >=64")
    image = Image.new("RGB", (int(size), int(size)), "white")
    draw = ImageDraw.Draw(image)
    margin, span = 0.08 * size, 0.84 * size

    def px(vertex_id):
        x, y = _point(scaffold["vertices"], vertex_id)
        return margin + (x + 1) * 0.5 * span, margin + (y + 1) * 0.5 * span

    for support in scaffold["semantic_supports"]:
        if support["support_type"] == "polygon":
            points = [px(v) for v in support["vertex_ids"]]
            draw.line(points + [points[0]], fill=(185, 185, 185), width=1)
    for boundary in scaffold["boundaries"]:
        points = [px(v) for v in boundary["vertex_ids"]]
        if boundary.get("closed"):
            points += [points[0]]
        draw.line(points, fill=(20, 20, 20), width=3)
    return image


def contract_document():
    """Compact machine-readable v1 schema/invariant summary."""
    return {
        "schema_version": CONTRACT_SCHEMA,
        "physical_topology_schema": TOPOLOGY_SCHEMA,
        "image_plane_scaffold_schema": SCAFFOLD_SCHEMA,
        "topology_id": TOPOLOGY_ID,
        "physical_facet_families": list(FACET_FAMILIES),
        "orientation_labels": list(ORIENTATIONS),
        "orientation_period_deg": 90,
        "provenance_enum": list(PROVENANCE),
        "observation_state_enum": list(OBSERVATION_STATES),
        "validity_enum": list(VALIDITY_STATES),
        "crown_boundary_order_outer_to_inner": list(CROWN_BOUNDARY_ORDER),
        "invariants": [
            "semantic identity exists independently of observation provenance",
            "one stone/sequence uses one stable semantic gauge",
            "fourfold symmetry is a relationship/prior, not coordinate equality",
            "image-plane semantic supports are non-exclusive",
            "semantic supports are not direct polished-facet projections",
            "one support may reference multiple physical semantic entities",
            "future optical regions may associate many-to-many with physical entities",
            "declared crown boundaries are simple, nested, ordered and non-crossing",
        ],
        "future_extension_boundary": {
            "implemented_here": [
                "physical semantic topology",
                "image-plane semantic scaffold",
                "confidence/provenance/observation state",
            ],
            "explicitly_not_implemented_here": [
                "empirical optical or virtual-facet segmentation",
                "optical event tracking",
                "brilliance/fire/scintillation metrics",
                "quality scoring",
                "full 3-D reconstruction",
            ],
        },
    }


def clone_scaffold(scaffold):
    return deepcopy(scaffold)
