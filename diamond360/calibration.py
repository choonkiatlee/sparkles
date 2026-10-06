"""Empirical calibration of retained Asscher 360 descriptors against human review.

Issue #22 is an interpretation/calibration layer. It consumes only the canonical
#45 retained descriptor profile plus curated human observations from existing
Asscher evaluations. It does not recompute optical measurements, fit a ranking
model, or assign aesthetic direction to descriptor magnitudes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from . import descriptor_profile as dp


CALIBRATION_SCHEMA = "diamond360-calibration/1"
OBSERVATION_SCHEMA = "diamond360-human-observations/1"

EXPLANATION_LEVELS = {"explained", "partial", "unexplained"}
LINK_ASSESSMENTS = {"supports", "partial", "contradicts", "irrelevant"}
OBSERVATION_ROLES = {"strength", "drawback", "check", "mixed", "neutral"}
HYPOTHESIS_FAMILIES = {
    "activity_motion",
    "dark_state",
    "nested_step",
    "directional",
    "morphology",
    "unexplained_static",
}


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"missing required calibration input: {path}") from exc


def _finite_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"descriptor value must be numeric or null: {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("descriptor value must be finite or null")
    return value


def _validate_profile(comparison):
    if comparison.get("schema_version") != dp.COMPARISON_SCHEMA:
        raise ValueError(
            f"profile comparison schema mismatch: expected {dp.COMPARISON_SCHEMA}, "
            f"got {comparison.get('schema_version')!r}"
        )
    if comparison.get("profile_schema") != dp.PROFILE_SCHEMA:
        raise ValueError(
            f"profile schema mismatch: expected {dp.PROFILE_SCHEMA}, "
            f"got {comparison.get('profile_schema')!r}"
        )

    catalog = comparison.get("field_catalog", {})
    measurement_catalog = catalog.get("measurements", {})
    context_catalog = catalog.get("context", {})
    if set(measurement_catalog) != set(dp.PRODUCTION_FIELD_IDS):
        raise ValueError("profile comparison production vocabulary differs from #45")
    if set(context_catalog) != set(dp.CONTEXT_FIELD_IDS):
        raise ValueError("profile comparison context vocabulary differs from #45")

    stones = comparison.get("stones")
    if not isinstance(stones, list) or not stones:
        raise ValueError("profile comparison requires at least one stone")
    certificates = [stone.get("certificate") for stone in stones]
    if any(not certificate for certificate in certificates):
        raise ValueError("profile comparison contains a stone without certificate")
    if len(certificates) != len(set(certificates)):
        raise ValueError("profile comparison certificates must be unique")

    for stone in stones:
        measurements = stone.get("measurements", {})
        if set(measurements) != set(dp.PRODUCTION_FIELD_IDS):
            raise ValueError(
                f"{stone['certificate']}: profile measurements differ from #45 vocabulary"
            )
        for field_id, cell in measurements.items():
            _finite_or_none(cell.get("value"))
            status = cell.get("status")
            if status not in {"ok", "review", "unavailable"}:
                raise ValueError(
                    f"{stone['certificate']}/{field_id}: unsupported status {status!r}"
                )
    return certificates


def _validate_human_observations(payload, repository_root: Path, certificates):
    if payload.get("schema_version") != OBSERVATION_SCHEMA:
        raise ValueError(
            f"human observation schema mismatch: expected {OBSERVATION_SCHEMA}, "
            f"got {payload.get('schema_version')!r}"
        )

    concepts = payload.get("concept_catalog")
    if not isinstance(concepts, dict) or not concepts:
        raise ValueError("human observation input requires a non-empty concept_catalog")

    reviews = payload.get("stone_reviews")
    if not isinstance(reviews, list):
        raise ValueError("human observation input requires stone_reviews")
    review_certs = [review.get("certificate") for review in reviews]
    if set(review_certs) != set(certificates) or len(review_certs) != len(set(review_certs)):
        raise ValueError("stone_reviews must cover each profile certificate exactly once")
    for review in reviews:
        path = review.get("evaluation_path")
        if not path or not (repository_root / path).exists():
            raise ValueError(
                f"{review.get('certificate')}: evaluation_path does not exist: {path!r}"
            )
        outcome = review.get("outcome")
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError(f"{review.get('certificate')}: missing review outcome")

    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("human observation input requires observations")

    seen_ids = set()
    for observation in observations:
        obs_id = observation.get("id")
        if not obs_id or obs_id in seen_ids:
            raise ValueError(f"observation id must be unique and non-empty: {obs_id!r}")
        seen_ids.add(obs_id)

        certificate = observation.get("certificate")
        if certificate not in certificates:
            raise ValueError(f"{obs_id}: unknown certificate {certificate!r}")

        concept = observation.get("concept")
        if concept not in concepts:
            raise ValueError(f"{obs_id}: unknown concept {concept!r}")

        family = observation.get("hypothesis_family")
        if family not in HYPOTHESIS_FAMILIES:
            raise ValueError(f"{obs_id}: unsupported hypothesis_family {family!r}")

        role = observation.get("role")
        if role not in OBSERVATION_ROLES:
            raise ValueError(f"{obs_id}: unsupported observation role {role!r}")

        explanation = observation.get("profile_explanation")
        if explanation not in EXPLANATION_LEVELS:
            raise ValueError(f"{obs_id}: unsupported profile_explanation {explanation!r}")

        summary = observation.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"{obs_id}: summary must be non-empty")

        frames = observation.get("source_frames", [])
        if (
            not isinstance(frames, list)
            or any(type(index) is not int or index < 0 for index in frames)
            or len(frames) != len(set(frames))
        ):
            raise ValueError(f"{obs_id}: source_frames must be unique nonnegative integers")

        links = observation.get("descriptor_links", [])
        if not isinstance(links, list):
            raise ValueError(f"{obs_id}: descriptor_links must be a list")
        if explanation == "unexplained" and links:
            raise ValueError(f"{obs_id}: unexplained observations cannot claim descriptor links")
        if explanation in {"explained", "partial"} and not links:
            raise ValueError(f"{obs_id}: {explanation} observation requires descriptor links")

        linked_fields = []
        for link in links:
            field_id = link.get("field_id")
            if field_id not in dp.PRODUCTION_FIELD_IDS:
                raise ValueError(
                    f"{obs_id}: descriptor link is not a retained #45 measurement: {field_id!r}"
                )
            if field_id in linked_fields:
                raise ValueError(f"{obs_id}: duplicate descriptor link {field_id}")
            linked_fields.append(field_id)
            if link.get("assessment") not in LINK_ASSESSMENTS:
                raise ValueError(
                    f"{obs_id}/{field_id}: unsupported link assessment "
                    f"{link.get('assessment')!r}"
                )
            rationale = link.get("rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"{obs_id}/{field_id}: rationale must be non-empty")

    return reviews, observations


def _field_orders(comparison):
    orders = {}
    stones = comparison["stones"]
    for field_id in dp.PRODUCTION_FIELD_IDS:
        values = []
        for stone in stones:
            cell = stone["measurements"][field_id]
            value = _finite_or_none(cell.get("value"))
            if value is None:
                continue
            values.append(
                {
                    "certificate": stone["certificate"],
                    "value": value,
                    "status": cell["status"],
                    "reasons": list(cell.get("reasons", [])),
                }
            )
        values.sort(key=lambda row: (-row["value"], row["certificate"]))
        for rank, row in enumerate(values, start=1):
            row["rank_descending"] = rank
            row["rank_ascending"] = len(values) - rank + 1
        orders[field_id] = {
            "sample_size": len(values),
            "direction": "descriptive_only",
            "descending": values,
        }
    return orders


def _rank_lookup(field_orders):
    result = {}
    for field_id, order in field_orders.items():
        for row in order["descending"]:
            result[(field_id, row["certificate"])] = {
                "rank_descending": row["rank_descending"],
                "rank_ascending": row["rank_ascending"],
                "sample_size": order["sample_size"],
            }
    return result


def _review_lookup(reviews):
    return {review["certificate"]: review for review in reviews}


def _stone_lookup(comparison):
    return {stone["certificate"]: stone for stone in comparison["stones"]}


def _family_summary(observations):
    summary = {}
    by_family = defaultdict(list)
    for observation in observations:
        by_family[observation["hypothesis_family"]].append(observation)

    for family in sorted(HYPOTHESIS_FAMILIES):
        rows = by_family.get(family, [])
        explanation_counts = Counter(
            observation["profile_explanation"] for observation in rows
        )
        linked_fields = sorted(
            {
                link["field_id"]
                for observation in rows
                for link in observation.get("descriptor_links", [])
            }
        )
        summary[family] = {
            "observation_count": len(rows),
            "certificate_count": len({row["certificate"] for row in rows}),
            "explanation_counts": {
                level: explanation_counts.get(level, 0)
                for level in ("explained", "partial", "unexplained")
            },
            "linked_field_ids": linked_fields,
        }
    return summary


def _unexplained_concepts(observations):
    grouped = defaultdict(list)
    for observation in observations:
        if observation["profile_explanation"] == "unexplained":
            grouped[observation["concept"]].append(observation)
    return [
        {
            "concept": concept,
            "observation_ids": [item["id"] for item in items],
            "certificates": sorted({item["certificate"] for item in items}),
            "occurrences": len(items),
        }
        for concept, items in sorted(grouped.items())
    ]


def build_calibration_payload(
    comparison,
    human_observations,
    repository_root=".",
):
    repository_root = Path(repository_root)
    certificates = _validate_profile(comparison)
    reviews, observations = _validate_human_observations(
        human_observations, repository_root, certificates
    )
    field_orders = _field_orders(comparison)
    rank_lookup = _rank_lookup(field_orders)
    stone_lookup = _stone_lookup(comparison)
    review_lookup = _review_lookup(reviews)

    profile_window = comparison["window_contract"]["source_indices"]
    profile_window_set = set(profile_window)

    joined_observations = []
    for observation in observations:
        certificate = observation["certificate"]
        stone = stone_lookup[certificate]
        links = []
        for link in observation.get("descriptor_links", []):
            field_id = link["field_id"]
            cell = stone["measurements"][field_id]
            metadata = comparison["field_catalog"]["measurements"][field_id]
            rank = rank_lookup.get((field_id, certificate), {})
            links.append(
                {
                    "field_id": field_id,
                    "assessment": link["assessment"],
                    "rationale": link["rationale"],
                    "measurement": {
                        "value": _finite_or_none(cell.get("value")),
                        "status": cell["status"],
                        "reasons": list(cell.get("reasons", [])),
                        **rank,
                    },
                    "metadata": {
                        key: metadata[key]
                        for key in (
                            "representation",
                            "support_policy",
                            "statistic",
                            "units",
                            "region",
                            "pair",
                            "surface_id",
                            "threshold",
                            "redundancy_group",
                        )
                        if key in metadata
                    },
                }
            )

        source_frames = list(observation.get("source_frames", []))
        joined_observations.append(
            {
                "id": observation["id"],
                "certificate": certificate,
                "review_outcome": review_lookup[certificate]["outcome"],
                "evaluation_path": review_lookup[certificate]["evaluation_path"],
                "concept": observation["concept"],
                "hypothesis_family": observation["hypothesis_family"],
                "role": observation["role"],
                "profile_explanation": observation["profile_explanation"],
                "summary": observation["summary"],
                "source_frames": source_frames,
                "source_frames_in_profile_window": [
                    index for index in source_frames if index in profile_window_set
                ],
                "source_frames_outside_profile_window": [
                    index for index in source_frames if index not in profile_window_set
                ],
                "descriptor_links": links,
            }
        )

    review_status = {}
    for certificate in certificates:
        statuses = Counter(
            cell["status"]
            for cell in stone_lookup[certificate]["measurements"].values()
        )
        review_status[certificate] = {
            "ok": statuses.get("ok", 0),
            "review": statuses.get("review", 0),
            "unavailable": statuses.get("unavailable", 0),
        }

    return {
        "schema_version": CALIBRATION_SCHEMA,
        "profile_schema": comparison["profile_schema"],
        "human_observation_schema": OBSERVATION_SCHEMA,
        "sample": {
            "certificate_count": len(certificates),
            "certificates": certificates,
            "review_outcomes": {
                review["certificate"]: review["outcome"] for review in reviews
            },
            "profile_validity_counts": review_status,
            "interpretation_limit": (
                "Four stones can falsify poor interpretations and surface counterexamples; "
                "they do not support aesthetic thresholds or universal directionality."
            ),
        },
        "window_contract": comparison["window_contract"],
        "machine_evidence": {
            "status": "pending_issue_21_compact_packet",
            "issue": 21,
            "contract_note": (
                "#22 does not duplicate descriptor-native evidence selection. "
                "Compact machine-selected source evidence is attached only after #21 "
                "publishes its final packet contract."
            ),
        },
        "redundancy_groups": comparison.get("redundancy_groups", {}),
        "field_orders": field_orders,
        "family_summary": _family_summary(observations),
        "unexplained_concepts": _unexplained_concepts(observations),
        "observations": joined_observations,
    }


def _csv_rows(payload):
    rows = []
    for observation in payload["observations"]:
        common = {
            "certificate": observation["certificate"],
            "review_outcome": observation["review_outcome"],
            "observation_id": observation["id"],
            "concept": observation["concept"],
            "hypothesis_family": observation["hypothesis_family"],
            "role": observation["role"],
            "profile_explanation": observation["profile_explanation"],
            "human_summary": observation["summary"],
            "source_frames": ";".join(
                str(index) for index in observation["source_frames"]
            ),
            "outside_profile_window": ";".join(
                str(index)
                for index in observation["source_frames_outside_profile_window"]
            ),
        }
        if not observation["descriptor_links"]:
            rows.append(
                {
                    **common,
                    "field_id": "",
                    "link_assessment": "",
                    "descriptor_value": "",
                    "descriptor_status": "",
                    "descriptor_reasons": "",
                    "rank_descending": "",
                    "sample_size": "",
                    "redundancy_group": "",
                    "rationale": "",
                }
            )
            continue

        for link in observation["descriptor_links"]:
            measurement = link["measurement"]
            metadata = link["metadata"]
            rows.append(
                {
                    **common,
                    "field_id": link["field_id"],
                    "link_assessment": link["assessment"],
                    "descriptor_value": measurement["value"],
                    "descriptor_status": measurement["status"],
                    "descriptor_reasons": ";".join(measurement.get("reasons", [])),
                    "rank_descending": measurement.get("rank_descending", ""),
                    "sample_size": measurement.get("sample_size", ""),
                    "redundancy_group": metadata.get("redundancy_group", ""),
                    "rationale": link["rationale"],
                }
            )
    return rows


def write_outputs(payload, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_json = output_dir / "benchmark.json"
    benchmark_json.write_text(
        json.dumps(payload, indent=2, allow_nan=False, sort_keys=False) + "\n"
    )

    rows = _csv_rows(payload)
    fieldnames = [
        "certificate",
        "review_outcome",
        "observation_id",
        "concept",
        "hypothesis_family",
        "role",
        "profile_explanation",
        "human_summary",
        "source_frames",
        "outside_profile_window",
        "field_id",
        "link_assessment",
        "descriptor_value",
        "descriptor_status",
        "descriptor_reasons",
        "rank_descending",
        "sample_size",
        "redundancy_group",
        "rationale",
    ]
    benchmark_csv = output_dir / "benchmark.csv"
    with benchmark_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return benchmark_json, benchmark_csv


def build_calibration(
    repository=".",
    observations_path="docs/360/calibration/human-observations.json",
    output="docs/360/calibration",
):
    root = Path(repository)
    comparison = _load_json(root / "docs/360/profile/comparison.json")
    observations = _load_json(root / observations_path)
    payload = build_calibration_payload(comparison, observations, repository_root=root)
    write_outputs(payload, root / output)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build #22 empirical calibration against Asscher evaluations"
    )
    parser.add_argument("--repository", default=".")
    parser.add_argument(
        "--observations",
        default="docs/360/calibration/human-observations.json",
    )
    parser.add_argument("--output", default="docs/360/calibration")
    args = parser.parse_args(argv)
    build_calibration(args.repository, args.observations, args.output)


if __name__ == "__main__":
    main()
