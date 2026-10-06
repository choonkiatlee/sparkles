"""Normalize descriptor-native #26-#33 evidence for issue #21.

This is the consolidation boundary between descriptor-specific automatic evidence
selection and the compact buyer-facing evidence packet. It never recomputes an
optical measurement. Production field IDs and redundancy metadata come only
from #45's descriptor_profile contract.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import descriptor_profile as dp


SCHEMA = "diamond360-evidence-candidates/1"
_KINDS = {"frame", "pair", "run"}
_STATUSES = {"ok", "review", "unavailable"}
_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}
_KIND_ORDER = {"frame": 0, "pair": 1, "run": 2}


@dataclass(frozen=True)
class EvidenceLocation:
    """Ordered original source-frame indices used by one evidence event."""

    kind: str
    source_indices: tuple[int, ...]

    def __post_init__(self):
        if self.kind not in _KINDS:
            raise ValueError(f"unknown evidence location kind: {self.kind}")
        if not self.source_indices:
            raise ValueError("evidence location requires at least one source index")
        if any(type(index) is not int or index < 0 for index in self.source_indices):
            raise ValueError("source indices must be nonnegative integers")
        if self.kind == "frame" and len(self.source_indices) != 1:
            raise ValueError("frame evidence requires exactly one source index")
        if self.kind == "pair" and len(self.source_indices) != 2:
            raise ValueError("pair evidence requires exactly two source indices")

    @property
    def key(self):
        return self.kind, self.source_indices

    def sort_key(self):
        return _KIND_ORDER[self.kind], self.source_indices

    def to_dict(self):
        return {"kind": self.kind, "source_indices": list(self.source_indices)}


@dataclass
class EvidenceCandidate:
    descriptor_family: str
    native_id: str
    event_type: str
    location: EvidenceLocation
    profile_field_ids: tuple[str, ...]
    rationale: str
    validity_status: str = "ok"
    validity_reasons: tuple[str, ...] = ()
    redundancy_groups: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    native_payload: dict[str, Any] = field(default_factory=dict)
    panel_reference: str | None = None
    importance: float | None = None

    def __post_init__(self):
        if self.validity_status not in _STATUSES:
            raise ValueError(f"unknown validity status: {self.validity_status}")

    def sort_key(self):
        return (
            self.location.sort_key(),
            self.descriptor_family,
            self.native_id,
            self.event_type,
            self.profile_field_ids,
        )

    def to_dict(self):
        result = {
            "descriptor_family": self.descriptor_family,
            "native_id": self.native_id,
            "event_type": self.event_type,
            "location": self.location.to_dict(),
            "profile_field_ids": list(self.profile_field_ids),
            "rationale": self.rationale,
            "validity": {
                "status": self.validity_status,
                "reasons": list(self.validity_reasons),
            },
            "redundancy_groups": list(self.redundancy_groups),
            "provenance": self.provenance,
            "native_payload": self.native_payload,
        }
        if self.panel_reference is not None:
            result["panel_reference"] = self.panel_reference
        if self.importance is not None:
            result["importance"] = self.importance
        return result


@dataclass(frozen=True)
class EvidenceItem:
    """One exact source location with one or more supporting claims."""

    location: EvidenceLocation
    claims: tuple[EvidenceCandidate, ...]

    def sort_key(self):
        return self.location.sort_key()

    def to_dict(self):
        return {
            "location": self.location.to_dict(),
            "claims": [claim.to_dict() for claim in self.claims],
        }


@dataclass(frozen=True)
class NearDuplicateGroup:
    """Non-destructive temporal grouping for later compact selection."""

    items: tuple[EvidenceItem, ...]

    def sort_key(self):
        return self.items[0].sort_key()

    def to_dict(self):
        return {"items": [item.to_dict() for item in self.items]}


def _reasons(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(";") if part.strip())
    result = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _validity(value):
    value = value or {}
    status = value.get("status", "ok")
    if status not in _STATUSES:
        raise ValueError(f"unknown validity status: {status}")
    return status, _reasons(value.get("reasons", value.get("reason")))


def _combine_validity(*values):
    status = "ok"
    reasons = []
    for value in values:
        item_status, item_reasons = _validity(value)
        if _STATUS_RANK[item_status] > _STATUS_RANK[status]:
            status = item_status
        for reason in item_reasons:
            if reason not in reasons:
                reasons.append(reason)
    return status, tuple(reasons)


def _field_ids(family, **criteria):
    matches = []
    for field_id in dp.PRODUCTION_FIELD_IDS:
        spec = dp.FIELD_SPECS[field_id]
        if spec.get("family") != family:
            continue
        if all(spec.get(key) == value for key, value in criteria.items()):
            matches.append(field_id)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one retained #45 field for {family} evidence "
            f"selector {criteria}, found {len(matches)}"
        )
    return tuple(matches)


def _redundancy_groups(field_ids):
    return tuple(sorted({
        group
        for field_id in field_ids
        for group in [dp.FIELD_SPECS[field_id].get("redundancy_group")]
        if group
    }))


def _schema_provenance(result, family):
    return {
        "descriptor_schema": result.get("schema_version"),
        "requested_indices": list(result.get("requested_indices", [])),
        "accepted_indices": list(result.get("accepted_indices", [])),
        "excluded": list(result.get("excluded", [])),
        "wrap_explicit": bool(result.get("wrap_explicit", False)),
        "issue": dp.SOURCE_SPECS[family]["issue"],
    }


def _check_schema(result, family):
    expected = dp.SOURCE_SPECS[family]["descriptor_schema"]
    actual = result.get("schema_version")
    if actual != expected:
        raise ValueError(
            f"{family} descriptor schema mismatch: expected {expected}, got {actual!r}"
        )


def _candidate(
    result,
    family,
    native_id,
    event_type,
    location,
    field_ids,
    rationale,
    validity=None,
    panel_reference=None,
    native_payload=None,
    importance=None,
):
    status, reasons = _validity(validity)
    return EvidenceCandidate(
        descriptor_family=family,
        native_id=native_id,
        event_type=event_type,
        location=location,
        profile_field_ids=tuple(field_ids),
        rationale=rationale,
        validity_status=status,
        validity_reasons=reasons,
        redundancy_groups=_redundancy_groups(field_ids),
        provenance=_schema_provenance(result, family),
        native_payload=dict(native_payload or {}),
        panel_reference=panel_reference,
        importance=importance,
    )


def _frame_event(
    result,
    family,
    native_id,
    label,
    event,
    field_ids,
    validity,
    panel_reference,
):
    if event is None:
        return None
    return _candidate(
        result,
        family,
        native_id,
        label,
        EvidenceLocation("frame", (int(event["source_index"]),)),
        field_ids,
        f"{family} selected native {label} frame",
        validity=validity,
        panel_reference=panel_reference,
        native_payload=event,
        importance=(
            abs(float(event["delta"]))
            if event.get("delta") is not None
            else None
        ),
    )


def _trace_evidence_candidates(
    result,
    family,
    native_id,
    evidence,
    field_ids,
    validity,
    panel_reference,
):
    indices = list(result.get("requested_indices", []))
    candidates = []
    for label, event in (evidence or {}).items():
        if event is None:
            continue
        if label in {"largest_positive_move", "largest_negative_move"}:
            right_position = int(event["position"])
            if right_position <= 0 or right_position >= len(indices):
                raise ValueError(f"{family} move evidence has invalid position")
            location = EvidenceLocation(
                "pair",
                (int(indices[right_position - 1]), int(indices[right_position])),
            )
            candidate = _candidate(
                result,
                family,
                native_id,
                label,
                location,
                field_ids,
                f"{family} selected native {label} adjacent move",
                validity=validity,
                panel_reference=panel_reference,
                native_payload=event,
                importance=abs(float(event.get("delta", 0.0))),
            )
        else:
            candidate = _frame_event(
                result,
                family,
                native_id,
                label,
                event,
                field_ids,
                validity,
                panel_reference,
            )
        candidates.append(candidate)
    return candidates


def adapt_activation(result):
    _check_schema(result, "activation")
    candidates = []
    whole = result["whole_stone"]
    field_ids = _field_ids(
        "activation",
        representation="whole_stone",
        region="whole_stone",
        support_policy="fixed",
        trace_type="raw",
    )
    candidates.extend(_trace_evidence_candidates(
        result,
        "activation",
        "whole_stone/whole_stone/fixed/raw",
        whole.get("evidence"),
        field_ids,
        whole.get("validity"),
        "evidence/whole-stone.png",
    ))
    regions = result["representations"]["coarse"]["regions"]
    for region in ("centre", "inner", "middle"):
        cell = regions[region]["fixed"]
        field_ids = _field_ids(
            "activation",
            representation="coarse",
            region=region,
            support_policy="fixed",
            trace_type="relative",
        )
        candidates.extend(_trace_evidence_candidates(
            result,
            "activation",
            f"coarse/{region}/fixed/relative",
            cell.get("relative_evidence"),
            field_ids,
            cell.get("relative_validity"),
            f"evidence/coarse-{region}-fixed-relative.png",
        ))
    return candidates


def adapt_occupancy(result):
    _check_schema(result, "occupancy")
    candidates = []
    regions = result["representations"]["coarse"]["regions"]
    key = f"{float(result.get('baseline_threshold', 0.65)):.2f}"
    for region in ("centre", "inner", "middle"):
        cell = regions[region]["fixed"]["thresholds"][key]
        field_ids = _field_ids(
            "occupancy",
            representation="coarse",
            region=region,
            support_policy="fixed",
            threshold=0.65,
        )
        candidates.extend(_trace_evidence_candidates(
            result,
            "occupancy",
            f"coarse/{region}/fixed/k{key}",
            cell.get("evidence"),
            field_ids,
            cell.get("validity"),
            cell.get("evidence_panel"),
        ))
    return candidates


def _pair_candidate(
    result,
    family,
    native_id,
    label,
    event,
    field_ids,
    validity,
    panel_reference,
    importance_key=None,
):
    if event is None:
        return None
    location = EvidenceLocation(
        "pair",
        (int(event["left_source_index"]), int(event["right_source_index"])),
    )
    importance = None
    if importance_key and event.get(importance_key) is not None:
        importance = abs(float(event[importance_key]))
    return _candidate(
        result,
        family,
        native_id,
        label,
        location,
        field_ids,
        f"{family} selected native {label} pair event",
        validity=validity,
        panel_reference=panel_reference,
        native_payload=event,
        importance=importance,
    )


def adapt_switching(result):
    _check_schema(result, "switching")
    candidates = []
    regions = result["representations"]["coarse"]["regions"]
    key = f"{float(result.get('baseline_threshold', 0.65)):.2f}"
    for region in ("inner", "middle"):
        cell = regions[region]["fixed"]["thresholds"][key]
        field_ids = _field_ids(
            "switching",
            representation="coarse",
            region=region,
            support_policy="fixed",
            threshold=0.65,
        )
        for label, event in cell.get("evidence", {}).items():
            candidate = _pair_candidate(
                result,
                "switching",
                f"coarse/{region}/fixed/k{key}",
                label,
                event,
                field_ids,
                cell.get("validity"),
                cell.get("evidence_panel"),
                "switch_fraction",
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def adapt_mobility(result):
    _check_schema(result, "mobility")
    candidates = []
    for region in ("centre", "inner", "middle"):
        native_id = f"coarse/{region}/fixed/relative"
        cell = result["traces"][native_id]
        field_ids = _field_ids(
            "mobility",
            representation="coarse",
            region=region,
            support_policy="fixed",
            trace_type="relative",
        )
        for label, event in cell.get("evidence", {}).items():
            candidate = _pair_candidate(
                result,
                "mobility",
                native_id,
                label,
                event,
                field_ids,
                cell.get("validity"),
                cell.get("evidence_panel"),
                "mobility",
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def adapt_persistence(result):
    _check_schema(result, "persistence")
    key = f"{float(result.get('baseline_threshold', 0.65)):.2f}"
    cell = (
        result["representations"]["coarse"]["regions"]["inner"]["fixed"]
        ["thresholds"][key]
    )
    event = cell.get("evidence", {}).get("dark")
    if event is None:
        return []
    start = int(event["start_position"])
    end = int(event["end_position"])
    indices = list(result["requested_indices"])
    if start < 0 or end < start or end >= len(indices):
        raise ValueError("persistence evidence run positions are invalid")
    field_ids = _field_ids(
        "persistence",
        representation="coarse",
        region="inner",
        support_policy="fixed",
        state="dark",
        threshold=0.65,
    )
    return [_candidate(
        result,
        "persistence",
        f"coarse/inner/fixed/dark/k{key}",
        "dark_q90_run",
        EvidenceLocation("run", tuple(int(x) for x in indices[start:end + 1])),
        field_ids,
        "persistence selected the representative retained dark Q90 run",
        validity=cell.get("validity"),
        panel_reference=cell.get("evidence_panel"),
        native_payload=event,
        importance=float(event.get("observed_run_length_frames", end - start + 1)),
    )]


def adapt_coordination(result):
    _check_schema(result, "coordination")
    candidates = []
    pairs = result["representations"]["coarse"]["fixed"]["pairs"]
    for pair_id in ("centre__inner", "inner__middle"):
        cell = pairs[pair_id]
        field_ids = _field_ids(
            "coordination",
            representation="coarse",
            pair=pair_id,
            support_policy="fixed",
        )
        validity_status, validity_reasons = _combine_validity(
            cell.get("level_validity"),
            cell.get("change_validity"),
        )
        validity = {"status": validity_status, "reasons": list(validity_reasons)}
        for label, event in cell.get("evidence", {}).items():
            candidate = _pair_candidate(
                result,
                "coordination",
                f"coarse/fixed/{pair_id}",
                label,
                event,
                field_ids,
                validity,
                f"evidence/coarse-{pair_id}.png",
                "joint_move_strength",
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def adapt_opposing(result):
    _check_schema(result, "opposing")
    candidates = []
    pairs = (
        result["surfaces"]["coarse_whole"]["support_modes"]["fixed"]["pairs"]
    )
    for pair_id in ("side_E_W", "side_N_S", "corner_NE_SW", "corner_NW_SE"):
        cell = pairs[pair_id]
        field_ids = _field_ids(
            "opposing",
            representation="coarse",
            surface_id="coarse_whole",
            pair=pair_id,
            support_policy="fixed",
        )
        for label, event in cell.get("evidence", {}).items():
            importance_key = (
                "divergence_strength"
                if label == "strongest_divergent"
                else "movement_strength"
            )
            candidate = _pair_candidate(
                result,
                "opposing",
                f"coarse_whole/fixed/{pair_id}",
                label,
                event,
                field_ids,
                cell.get("validity"),
                cell.get("evidence_panel"),
                importance_key,
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def adapt_morphology(result):
    _check_schema(result, "morphology")
    wrapper = result["supports"]["fixed"]
    key = f"{float(result.get('baseline_threshold', 1.0)):.2f}"
    cell = wrapper["thresholds"][key]
    field_ids = _field_ids(
        "morphology",
        representation="whole_stone",
        support_policy="fixed",
        threshold=1.0,
        connectivity=8,
    )
    evidence = wrapper.get("baseline_evidence", {})
    candidates = []
    for label in ("broadest", "most_fragmented"):
        event = evidence.get(label)
        candidate = _frame_event(
            result,
            "morphology",
            f"whole_stone/fixed/k{key}",
            label,
            event,
            field_ids,
            cell.get("validity"),
            "evidence/diagnostic.png",
        )
        if candidate:
            importance = (
                event.get("largest_component_fraction")
                if label == "broadest"
                else event.get("effective_component_count")
            )
            candidate.importance = (
                float(importance) if importance is not None else None
            )
            candidates.append(candidate)
    matched = evidence.get("matched_active_area_pair")
    if matched is not None:
        left = matched["left"]
        right = matched["right"]
        candidates.append(_candidate(
            result,
            "morphology",
            f"whole_stone/fixed/k{key}",
            "matched_active_area_pair",
            EvidenceLocation(
                "pair",
                (int(left["source_index"]), int(right["source_index"])),
            ),
            field_ids,
            "morphology selected a similar-active-area contrast pair",
            validity=cell.get("validity"),
            panel_reference="evidence/diagnostic.png",
            native_payload=matched,
            importance=(
                float(matched["largest_component_fraction_difference"])
                if matched.get("largest_component_fraction_difference") is not None
                else None
            ),
        ))
    return candidates


ADAPTERS = {
    "activation": adapt_activation,
    "occupancy": adapt_occupancy,
    "switching": adapt_switching,
    "persistence": adapt_persistence,
    "mobility": adapt_mobility,
    "coordination": adapt_coordination,
    "opposing": adapt_opposing,
    "morphology": adapt_morphology,
}


def collect_candidates(results: Mapping[str, Mapping[str, Any]]):
    """Normalize the supplied descriptor-native result objects.

    A subset is accepted for focused tests/tools. A full #21 run should supply
    all ADAPTERS keys.
    """
    candidates = []
    unknown = set(results) - set(ADAPTERS)
    if unknown:
        raise ValueError(f"unknown evidence descriptor families: {sorted(unknown)}")
    for family in ADAPTERS:
        if family in results:
            candidates.extend(ADAPTERS[family](results[family]))
    return sorted(candidates, key=lambda item: item.sort_key())


def apply_profile_contract(candidates: Iterable[EvidenceCandidate], profile):
    """Filter/map candidates through the canonical per-stone #45 profile.

    Profile validity can only worsen native evidence validity; it can never
    upgrade a review/unavailable native event.
    """
    if profile.get("schema_version") != dp.PROFILE_SCHEMA:
        raise ValueError(f"expected profile schema {dp.PROFILE_SCHEMA}")
    measurements = profile.get("measurements", {})
    output = []
    for candidate in candidates:
        retained = tuple(
            field_id
            for field_id in candidate.profile_field_ids
            if field_id in dp.PRODUCTION_FIELD_IDS and field_id in measurements
        )
        if not retained:
            continue
        profile_validities = [
            {
                "status": measurements[field_id].get("status", "ok"),
                "reasons": measurements[field_id].get("reasons", []),
            }
            for field_id in retained
        ]
        status, reasons = _combine_validity(
            {
                "status": candidate.validity_status,
                "reasons": candidate.validity_reasons,
            },
            *profile_validities,
        )
        provenance = dict(candidate.provenance)
        provenance["profile_schema"] = dp.PROFILE_SCHEMA
        output.append(replace(
            candidate,
            profile_field_ids=retained,
            redundancy_groups=_redundancy_groups(retained),
            validity_status=status,
            validity_reasons=reasons,
            provenance=provenance,
        ))
    return sorted(output, key=lambda item: item.sort_key())


def merge_exact_duplicates(candidates: Iterable[EvidenceCandidate]):
    """Merge only identical location kind + ordered source indices."""
    grouped = {}
    for candidate in sorted(candidates, key=lambda item: item.sort_key()):
        grouped.setdefault(candidate.location.key, []).append(candidate)
    items = [
        EvidenceItem(location=claims[0].location, claims=tuple(claims))
        for claims in grouped.values()
    ]
    return sorted(items, key=lambda item: item.sort_key())


def _circular_distance(left, right, frame_count):
    delta = abs(int(left) - int(right))
    return min(delta, frame_count - delta)


def location_distance(left: EvidenceLocation, right: EvidenceLocation, frame_count=256):
    if type(frame_count) is not int or frame_count <= 0:
        raise ValueError("frame_count must be a positive integer")
    if any(index >= frame_count for index in left.source_indices + right.source_indices):
        raise ValueError("source index exceeds frame_count")
    return min(
        _circular_distance(a, b, frame_count)
        for a in left.source_indices
        for b in right.source_indices
    )


def group_near_duplicates(
    items: Iterable[EvidenceItem],
    frame_count=256,
    max_distance=1,
):
    """Group temporally nearby evidence without deleting or suppressing it.

    Complete-link greedy grouping avoids the common chaining failure where a
    long sequence of pairwise-near frames becomes one huge cluster.
    """
    if type(max_distance) is not int or max_distance < 0:
        raise ValueError("max_distance must be a nonnegative integer")
    groups: list[list[EvidenceItem]] = []
    for item in sorted(items, key=lambda value: value.sort_key()):
        placed = False
        for group in groups:
            if all(
                location_distance(
                    item.location, existing.location, frame_count=frame_count
                ) <= max_distance
                for existing in group
            ):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return [
        NearDuplicateGroup(tuple(group))
        for group in groups
    ]


def build_inventory(results, profile=None, frame_count=256, near_distance=1):
    candidates = collect_candidates(results)
    if profile is not None:
        candidates = apply_profile_contract(candidates, profile)
    items = merge_exact_duplicates(candidates)
    groups = group_near_duplicates(
        items, frame_count=frame_count, max_distance=near_distance
    )
    return {
        "schema_version": SCHEMA,
        "profile_schema": dp.PROFILE_SCHEMA if profile is not None else None,
        "candidate_count": len(candidates),
        "exact_item_count": len(items),
        "near_group_count": len(groups),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "exact_items": [item.to_dict() for item in items],
        "near_groups": [group.to_dict() for group in groups],
    }


def write_inventory(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


PACKET_SCHEMA = "diamond360-evidence-packet/1"
COVERAGE_ORDER = (
    "activity_motion",
    "relative_dark_state",
    "dark_persistence",
    "nested_step",
    "directional",
    "flash_morphology",
)
_FAMILY_COVERAGE = {
    "activation": "activity_motion",
    "mobility": "activity_motion",
    "occupancy": "relative_dark_state",
    "switching": "relative_dark_state",
    "persistence": "dark_persistence",
    "coordination": "nested_step",
    "opposing": "directional",
    "morphology": "flash_morphology",
}


@dataclass(frozen=True)
class SelectedEvidence:
    item: EvidenceItem
    coverage_families: tuple[str, ...]
    selected_for: str
    near_group_id: int | None
    selection_rationale: str

    def to_dict(self):
        return {
            "location": self.item.location.to_dict(),
            "coverage_families": list(self.coverage_families),
            "selected_for": self.selected_for,
            "near_group_id": self.near_group_id,
            "selection_rationale": self.selection_rationale,
            "claims": [claim.to_dict() for claim in self.item.claims],
        }


def item_coverage(item: EvidenceItem):
    return tuple(sorted({
        _FAMILY_COVERAGE[claim.descriptor_family]
        for claim in item.claims
        if claim.descriptor_family in _FAMILY_COVERAGE
    }, key=COVERAGE_ORDER.index))


def _item_status_rank(item):
    return max(
        (_STATUS_RANK[claim.validity_status] for claim in item.claims),
        default=_STATUS_RANK["unavailable"],
    )


def _profile_value(profile, field_id):
    value = profile.get("measurements", {}).get(field_id, {}).get("value")
    return float(value) if isinstance(value, (int, float)) else None


def _sign_event_rank(claim, profile):
    values = [
        _profile_value(profile, field_id)
        for field_id in claim.profile_field_ids
    ]
    values = [value for value in values if value is not None]
    expected = None
    if values:
        expected = "strongest_divergent" if sum(values) / len(values) < 0 else "strongest_coordinated"
    if claim.event_type == expected:
        return 0
    if claim.event_type in {"strongest_coordinated", "strongest_divergent"}:
        return 1
    return 2


def _claim_role_rank(claim, role, profile):
    """Role-specific preference; no cross-family numeric importance score."""
    if _FAMILY_COVERAGE.get(claim.descriptor_family) != role:
        return (99, 99, claim.native_id, claim.event_type, 0.0)

    if role == "activity_motion":
        family_rank = 0 if claim.descriptor_family == "mobility" else 1
        event_order = {
            "largest": 0,
            "q90": 1,
            "largest_positive_move": 2,
            "largest_negative_move": 2,
            "q10": 3,
            "median": 4,
            "q50": 5,
            "lowest_nonzero": 6,
        }
        event_rank = event_order.get(claim.event_type, 20)
    elif role == "relative_dark_state":
        family_rank = 0 if claim.descriptor_family == "switching" else 1
        event_order = {
            "highest": 0,
            "q90": 1,
            "lowest_nonzero": 2,
            "q50": 3,
            "q10": 4,
        }
        event_rank = event_order.get(claim.event_type, 20)
    elif role == "dark_persistence":
        family_rank = 0
        event_rank = 0 if claim.event_type == "dark_q90_run" else 10
    elif role in {"nested_step", "directional"}:
        family_rank = 0
        event_rank = _sign_event_rank(claim, profile)
    elif role == "flash_morphology":
        family_rank = 0
        event_rank = {
            "matched_active_area_pair": 0,
            "broadest": 1,
            "most_fragmented": 2,
        }.get(claim.event_type, 20)
    else:
        family_rank = event_rank = 20

    # Importance is intentionally after native_id: it can only break ties among
    # events emitted by the same native measurement/event kind.
    importance = -float(claim.importance) if claim.importance is not None else 0.0
    return (
        family_rank,
        event_rank,
        claim.native_id,
        claim.event_type,
        importance,
    )


def _item_role_rank(item, role, profile):
    claims = [
        claim for claim in item.claims
        if _FAMILY_COVERAGE.get(claim.descriptor_family) == role
    ]
    if not claims:
        return (99, 99, 99, "", "", 0.0, item.sort_key())
    best = min(_claim_role_rank(claim, role, profile) for claim in claims)
    role_claim_count = len(claims)
    return (
        _item_status_rank(item),
        -role_claim_count,
        *best,
        item.sort_key(),
    )


def _near_group_lookup(items, groups):
    by_key = {}
    for group_id, group in enumerate(groups):
        for item in group.items:
            by_key[item.location.key] = group_id
    for item in items:
        by_key.setdefault(item.location.key, None)
    return by_key


def _contrast_rank(item, selected, profile):
    """Prefer a visibly distinct native counterexample only as a fill policy."""
    selected_events = {
        (claim.descriptor_family, claim.native_id, claim.event_type)
        for chosen in selected
        for claim in chosen.item.claims
    }
    complement = {
        "broadest": "most_fragmented",
        "most_fragmented": "broadest",
        "strongest_coordinated": "strongest_divergent",
        "strongest_divergent": "strongest_coordinated",
        "highest": "lowest_nonzero",
        "lowest_nonzero": "highest",
        "q90": "q10",
        "q10": "q90",
    }
    best = 20
    for claim in item.claims:
        wanted = complement.get(claim.event_type)
        if wanted is None:
            continue
        if (
            claim.descriptor_family,
            claim.native_id,
            wanted,
        ) in selected_events:
            best = 0
            break
    return (_item_status_rank(item), best, item.sort_key())


def select_compact_evidence(
    items: Iterable[EvidenceItem],
    profile,
    near_groups: Iterable[NearDuplicateGroup] | None = None,
    min_items=4,
    max_items=6,
):
    """Select a compact deterministic visual fingerprint.

    Selection is coverage-first. It never sums descriptor magnitudes across
    families. Native importance is only a final tie-break inside one native
    measurement/event kind.
    """
    if profile.get("schema_version") != dp.PROFILE_SCHEMA:
        raise ValueError(f"expected profile schema {dp.PROFILE_SCHEMA}")
    if type(min_items) is not int or type(max_items) is not int:
        raise ValueError("min_items and max_items must be integers")
    if min_items < 1 or max_items < min_items:
        raise ValueError("require 1 <= min_items <= max_items")

    items = sorted(items, key=lambda item: item.sort_key())
    groups = list(near_groups or group_near_duplicates(items))
    group_lookup = _near_group_lookup(items, groups)
    selected: list[SelectedEvidence] = []
    covered = set()

    for role in COVERAGE_ORDER:
        if len(selected) >= max_items:
            break
        if role in covered:
            continue
        candidates = [
            item for item in items
            if role in item_coverage(item)
            and item.location.key not in {chosen.item.location.key for chosen in selected}
        ]
        if not candidates:
            continue
        chosen = min(candidates, key=lambda item: _item_role_rank(item, role, profile))
        coverage = item_coverage(chosen)
        selected.append(SelectedEvidence(
            item=chosen,
            coverage_families=coverage,
            selected_for=role,
            near_group_id=group_lookup.get(chosen.location.key),
            selection_rationale=(
                f"coverage-first representative for {role}; "
                f"also covers {', '.join(x for x in coverage if x != role) or 'no additional family'}"
            ),
        ))
        covered.update(coverage)

    # Only if broad coverage produced fewer than the requested minimum, add
    # deterministic native contrasts. Nearness alone never deletes a distinct
    # behavioural claim.
    selected_keys = {chosen.item.location.key for chosen in selected}
    while len(selected) < min_items and len(selected) < max_items:
        remaining = [item for item in items if item.location.key not in selected_keys]
        meaningful = [
            item for item in remaining
            if _contrast_rank(item, selected, profile)[1] == 0
        ]
        if not meaningful:
            break
        chosen = min(
            meaningful,
            key=lambda item: _contrast_rank(item, selected, profile),
        )
        coverage = item_coverage(chosen)
        selected.append(SelectedEvidence(
            item=chosen,
            coverage_families=coverage,
            selected_for="contrast_fill",
            near_group_id=group_lookup.get(chosen.location.key),
            selection_rationale=(
                "meaningful native contrast retained after distinct-family "
                "coverage; the soft minimum is never padded with repetition"
            ),
        ))
        selected_keys.add(chosen.location.key)
        covered.update(coverage)

    return selected


def _source_manifest_payload(source_manifest):
    if isinstance(source_manifest, (str, Path)):
        return json.loads(Path(source_manifest).read_text())
    return dict(source_manifest)


def _source_frame_lookup(source_manifest):
    payload = _source_manifest_payload(source_manifest)
    if payload.get("schema_version") != "diamond360-source/1":
        raise ValueError("expected diamond360-source/1 source manifest")
    lookup = {}
    for frame in payload.get("frames", []):
        index = frame.get("source_index")
        if type(index) is not int or index < 0 or index in lookup:
            raise ValueError("source manifest requires unique nonnegative source indices")
        lookup[index] = frame
    return payload, lookup


def _render_indices(location):
    values = list(location.source_indices)
    if location.kind != "run" or len(values) <= 3:
        return values
    return [values[0], values[len(values) // 2], values[-1]]


def _source_refs(location, lookup):
    refs = []
    for index in location.source_indices:
        frame = lookup.get(index)
        if frame is None:
            raise ValueError(f"source index {index} missing from source manifest")
        refs.append({
            key: frame.get(key)
            for key in (
                "source_index",
                "path",
                "sha256",
                "bytes",
                "source_url",
                "batch",
                "stored_position",
            )
            if frame.get(key) is not None
        })
    return refs


def build_packet(
    results,
    profile,
    source_manifest,
    source_manifest_ref=None,
    min_items=4,
    max_items=6,
    near_distance=1,
):
    manifest, source_lookup = _source_frame_lookup(source_manifest)
    frame_count = manifest.get("source_frame_count")
    if type(frame_count) is not int or frame_count <= 0:
        raise ValueError("source manifest requires source_frame_count")
    candidates = apply_profile_contract(collect_candidates(results), profile)
    items = merge_exact_duplicates(candidates)
    groups = group_near_duplicates(
        items,
        frame_count=frame_count,
        max_distance=near_distance,
    )
    selected = select_compact_evidence(
        items,
        profile,
        groups,
        min_items=min_items,
        max_items=max_items,
    )
    selected_payload = []
    covered = set()
    for rank, chosen in enumerate(selected, start=1):
        payload = chosen.to_dict()
        payload["rank"] = rank
        payload["original_frames"] = _source_refs(chosen.item.location, source_lookup)
        payload["render_source_indices"] = _render_indices(chosen.item.location)
        selected_payload.append(payload)
        covered.update(chosen.coverage_families)

    available = {
        role
        for item in items
        for role in item_coverage(item)
    }
    certificate = profile.get("certificate") or manifest.get("certificate")
    if (
        profile.get("certificate")
        and manifest.get("certificate")
        and profile["certificate"] != manifest["certificate"]
    ):
        raise ValueError("profile/source certificate mismatch")

    return {
        "schema_version": PACKET_SCHEMA,
        "profile_schema": dp.PROFILE_SCHEMA,
        "certificate": certificate,
        "window_contract": dp.WINDOW_ID,
        "source": {
            "manifest_schema": manifest["schema_version"],
            "manifest_ref": source_manifest_ref,
            "source_pipeline": manifest.get("source_pipeline"),
            "viewer": manifest.get("viewer"),
            "retrieved_at": manifest.get("retrieved_at"),
            "source_frame_count": frame_count,
        },
        "selection_policy": {
            "coverage_order": list(COVERAGE_ORDER),
            "soft_min_items": min_items,
            "max_items": max_items,
            "near_distance_source_steps": near_distance,
            "global_numeric_score": False,
            "near_groups_are_suppressive": False,
        },
        "inventory": {
            "native_candidate_count": len(candidates),
            "exact_item_count": len(items),
            "near_group_count": len(groups),
            "available_coverage_families": [
                role for role in COVERAGE_ORDER if role in available
            ],
        },
        "selected_count": len(selected_payload),
        "covered_families": [
            role for role in COVERAGE_ORDER if role in covered
        ],
        "uncovered_available_families": [
            role for role in COVERAGE_ORDER
            if role in available and role not in covered
        ],
        "items": selected_payload,
        "contact_sheet": "contact-sheet.jpg",
    }


def _verify_source_frame(path, frame_ref):
    import hashlib

    raw = Path(path).read_bytes()
    expected = frame_ref.get("sha256")
    if expected and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(
            f"source hash mismatch for source index {frame_ref['source_index']}"
        )


def render_contact_sheet(packet, source_root, destination, verify_hashes=True):
    """Render only original supplier frames; no registered/derived substitute."""
    from PIL import Image, ImageDraw

    if packet.get("schema_version") != PACKET_SCHEMA:
        raise ValueError(f"expected packet schema {PACKET_SCHEMA}")
    source_root = Path(source_root)
    destination = Path(destination)
    columns = 2
    tile_w, tile_h = 590, 390
    rows = max(1, (len(packet.get("items", [])) + columns - 1) // columns)
    canvas = Image.new("RGB", (columns * tile_w, 55 + rows * tile_h), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (15, 15),
        f"{packet.get('certificate') or 'diamond'} · compact original-source evidence",
        fill="black",
    )

    for slot, item in enumerate(packet.get("items", [])):
        x0 = (slot % columns) * tile_w
        y0 = 55 + (slot // columns) * tile_h
        render_indices = item.get("render_source_indices", [])
        frame_lookup = {
            frame["source_index"]: frame
            for frame in item.get("original_frames", [])
        }
        frames = []
        for source_index in render_indices:
            frame_ref = frame_lookup[source_index]
            path = source_root / frame_ref["path"]
            if not path.is_file():
                raise ValueError(f"source frame missing: {path}")
            if verify_hashes:
                _verify_source_frame(path, frame_ref)
            with Image.open(path) as image:
                frame = image.convert("RGB")
                frame.load()
            frames.append((source_index, frame.copy()))

        coverage = ", ".join(item.get("coverage_families", []))
        draw.text(
            (x0 + 10, y0 + 8),
            f"{item['rank']}. {item['selected_for']} · {coverage}",
            fill="black",
        )
        draw.text(
            (x0 + 10, y0 + 27),
            f"{item['location']['kind']} source {item['location']['source_indices']}",
            fill="black",
        )
        event_labels = []
        for claim in item.get("claims", []):
            label = f"{claim['descriptor_family']}:{claim['event_type']}"
            if label not in event_labels:
                event_labels.append(label)
        draw.text(
            (x0 + 10, y0 + 46),
            ", ".join(event_labels[:3]),
            fill="black",
        )

        n = max(1, len(frames))
        frame_w = (tile_w - 20 - (n - 1) * 8) // n
        for j, (source_index, frame) in enumerate(frames):
            frame.thumbnail((frame_w, 285))
            px = x0 + 10 + j * (frame_w + 8) + (frame_w - frame.width) // 2
            py = y0 + 78
            canvas.paste(frame, (px, py))
            draw.text(
                (x0 + 10 + j * (frame_w + 8), y0 + 365),
                f"src {source_index}",
                fill="black",
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=90)
    return destination


def write_packet(packet, output, source_root=None, verify_hashes=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    packet_path = output / "evidence.json"
    packet_path.write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    if source_root is not None:
        render_contact_sheet(
            packet,
            source_root,
            output / packet["contact_sheet"],
            verify_hashes=verify_hashes,
        )
    return packet_path
