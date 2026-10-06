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
