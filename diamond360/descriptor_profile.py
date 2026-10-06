"""Build the canonical retained Asscher 360 descriptor profile.

This module is a consolidation boundary between the descriptor-validation
programme (#20) and empirical calibration (#22). It does not calculate new
optical measurements and deliberately uses an explicit whitelist rather than
discovering fields from upstream disposition files.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

PROFILE_SCHEMA = "diamond360-descriptor-profile/1"
COMPARISON_SCHEMA = "diamond360-descriptor-profile-comparison/1"
WINDOW_ID = "core17"
CORE_INDICES = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
_STATUS_RANK = {"ok": 0, "review": 1, "unavailable": 2}

SOURCE_SPECS = {
    "activation": {
        "path": "docs/360/activation/summary.json",
        "dispositions": "docs/360/activation/dispositions.json",
        "benchmark_schema": "diamond360-activation-benchmark/1",
        "descriptor_schema": "diamond360-activation/1",
        "issue": 26,
    },
    "occupancy": {
        "path": "docs/360/occupancy/summary.json",
        "dispositions": "docs/360/occupancy/dispositions.json",
        "benchmark_schema": "sparkles-relative-dark-occupancy-benchmark/1",
        "descriptor_schema": "diamond360-relative-dark-occupancy/1",
        "issue": 27,
    },
    "switching": {
        "path": "docs/360/switching/summary.json",
        "dispositions": "docs/360/switching/dispositions.json",
        "benchmark_schema": "sparkles-bright-dark-switching-benchmark/1",
        "descriptor_schema": "diamond360-bright-dark-switching/1",
        "issue": 28,
    },
    "persistence": {
        "path": "docs/360/persistence/summary.json",
        "dispositions": "docs/360/persistence/dispositions.json",
        "benchmark_schema": "sparkles-bright-dark-persistence-benchmark/1",
        "descriptor_schema": "diamond360-bright-dark-persistence/1",
        "issue": 29,
    },
    "mobility": {
        "path": "docs/360/mobility/summary.json",
        "dispositions": "docs/360/mobility/dispositions.json",
        "benchmark_schema": "sparkles-contrast-mobility-benchmark/1",
        "descriptor_schema": "diamond360-contrast-mobility/1",
        "issue": 30,
    },
    "opposing": {
        "path": "docs/360/opposing-symmetry/summary.json",
        "dispositions": "docs/360/opposing-symmetry/dispositions.json",
        "benchmark_schema": "diamond360-opposing-region-symmetry-benchmark/1",
        "descriptor_schema": "diamond360-opposing-region-symmetry/1",
        "issue": 31,
    },
    "coordination": {
        "path": "docs/360/coordination/summary.json",
        "dispositions": "docs/360/coordination/dispositions.json",
        "benchmark_schema": "diamond360-concentric-coordination-summary/1",
        "descriptor_schema": "diamond360-concentric-coordination/1",
        "issue": 32,
    },
    "morphology": {
        "path": "docs/360/morphology/summary.json",
        "dispositions": "docs/360/morphology/dispositions.json",
        "benchmark_schema": "diamond360-flash-morphology-benchmark/1",
        "descriptor_schema": "diamond360-flash-morphology/1",
        "issue": 33,
    },
}

REDUNDANCY_GROUPS = {
    "activity_motion": {
        "relationship": "related_not_additive",
        "description": (
            "Activation excursion and contrast mobility describe related recorded-image "
            "movement and must not be added as independent quality points."
        ),
    },
    "relative_dark_state": {
        "relationship": "shared_state_redundant",
        "description": (
            "Relative-dark occupancy and switching share the same k=0.65 pixel-state "
            "definition; their scalar rankings are redundant enough that downstream code "
            "must not count them as independent votes."
        ),
    },
}

# Each entry is intentionally explicit. Upstream KEEP/REVISE/REJECT files are audit
# evidence, not a source of automatic production-field discovery.
FIELD_SPECS = {
    "activity.activation.whole_stone_total_excursion": {
        "role": "descriptor", "family": "activation", "statistic": "total_excursion",
        "representation": "whole_stone", "region": "whole_stone",
        "support_policy": "fixed", "trace_type": "raw", "units": "encoded_brightness",
        "redundancy_group": "activity_motion",
    },
    "activity.activation.centre_relative_total_excursion": {
        "role": "descriptor", "family": "activation", "statistic": "total_excursion",
        "representation": "coarse", "region": "centre", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio",
        "redundancy_group": "activity_motion",
    },
    "activity.activation.inner_relative_total_excursion": {
        "role": "descriptor", "family": "activation", "statistic": "total_excursion",
        "representation": "coarse", "region": "inner", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio",
        "redundancy_group": "activity_motion",
    },
    "activity.activation.middle_relative_total_excursion": {
        "role": "descriptor", "family": "activation", "statistic": "total_excursion",
        "representation": "coarse", "region": "middle", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio",
        "redundancy_group": "activity_motion",
    },
    "activity.mobility.centre_median": {
        "role": "descriptor", "family": "mobility", "statistic": "median_mobility",
        "representation": "coarse", "region": "centre", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio_per_source_step",
        "redundancy_group": "activity_motion",
    },
    "activity.mobility.inner_median": {
        "role": "descriptor", "family": "mobility", "statistic": "median_mobility",
        "representation": "coarse", "region": "inner", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio_per_source_step",
        "redundancy_group": "activity_motion",
    },
    "activity.mobility.middle_median": {
        "role": "descriptor", "family": "mobility", "statistic": "median_mobility",
        "representation": "coarse", "region": "middle", "support_policy": "fixed",
        "trace_type": "relative", "units": "log_brightness_ratio_per_source_step",
        "redundancy_group": "activity_motion",
    },
    "dark_state.occupancy.centre_mean": {
        "role": "descriptor", "family": "occupancy", "statistic": "mean",
        "representation": "coarse", "region": "centre", "support_policy": "fixed",
        "threshold": 0.65, "units": "fraction", "redundancy_group": "relative_dark_state",
    },
    "dark_state.occupancy.inner_mean": {
        "role": "descriptor", "family": "occupancy", "statistic": "mean",
        "representation": "coarse", "region": "inner", "support_policy": "fixed",
        "threshold": 0.65, "units": "fraction", "redundancy_group": "relative_dark_state",
    },
    "dark_state.occupancy.middle_mean": {
        "role": "descriptor", "family": "occupancy", "statistic": "mean",
        "representation": "coarse", "region": "middle", "support_policy": "fixed",
        "threshold": 0.65, "units": "fraction", "redundancy_group": "relative_dark_state",
    },
    "dark_state.persistence.inner_dark_q90_window_fraction": {
        "role": "descriptor", "family": "persistence", "statistic": "q90_window_fraction",
        "representation": "coarse", "region": "inner", "support_policy": "fixed",
        "state": "dark", "threshold": 0.65, "units": "fraction_of_requested_source_steps",
    },
    "temporal_reconfiguration.switching.inner_rate": {
        "role": "descriptor", "family": "switching", "statistic": "regional_switch_rate",
        "representation": "coarse", "region": "inner", "support_policy": "fixed",
        "threshold": 0.65, "units": "switched_pixel_pairs_per_eligible_pixel_pair",
        "redundancy_group": "relative_dark_state",
    },
    "temporal_reconfiguration.switching.middle_rate": {
        "role": "descriptor", "family": "switching", "statistic": "regional_switch_rate",
        "representation": "coarse", "region": "middle", "support_policy": "fixed",
        "threshold": 0.65, "units": "switched_pixel_pairs_per_eligible_pixel_pair",
        "redundancy_group": "relative_dark_state",
    },
    "nested_step.centre_inner_pearson": {
        "role": "descriptor", "family": "coordination", "statistic": "pearson_r",
        "representation": "coarse", "pair": "centre__inner", "support_policy": "fixed",
        "units": "correlation",
    },
    "nested_step.inner_middle_pearson": {
        "role": "descriptor", "family": "coordination", "statistic": "pearson_r",
        "representation": "coarse", "pair": "inner__middle", "support_policy": "fixed",
        "units": "correlation",
    },
    "directional.side_E_W_pearson": {
        "role": "descriptor", "family": "opposing", "statistic": "correlation",
        "representation": "coarse", "surface_id": "coarse_whole", "pair": "side_E_W", "support_policy": "fixed",
        "units": "correlation",
    },
    "directional.side_N_S_pearson": {
        "role": "descriptor", "family": "opposing", "statistic": "correlation",
        "representation": "coarse", "surface_id": "coarse_whole", "pair": "side_N_S", "support_policy": "fixed",
        "units": "correlation",
    },
    "directional.corner_NE_SW_pearson": {
        "role": "descriptor", "family": "opposing", "statistic": "correlation",
        "representation": "coarse", "surface_id": "coarse_whole", "pair": "corner_NE_SW", "support_policy": "fixed",
        "units": "correlation",
    },
    "directional.corner_NW_SE_pearson": {
        "role": "descriptor", "family": "opposing", "statistic": "correlation",
        "representation": "coarse", "surface_id": "coarse_whole", "pair": "corner_NW_SE", "support_policy": "fixed",
        "units": "correlation",
    },
    "flash_morphology.median_largest_component_fraction": {
        "role": "descriptor", "family": "morphology",
        "statistic": "median_largest_component_fraction",
        "representation": "whole_stone", "support_policy": "fixed",
        "threshold": 1.0, "connectivity": 8, "units": "fraction_of_active_area",
    },
    "flash_morphology.active_frame_fraction": {
        "role": "context", "family": "morphology", "statistic": "active_frame_fraction",
        "representation": "whole_stone", "support_policy": "fixed",
        "threshold": 1.0, "connectivity": 8, "units": "fraction_of_observed_frames",
    },
}

PRODUCTION_FIELD_IDS = tuple(
    field_id for field_id, spec in FIELD_SPECS.items() if spec["role"] == "descriptor"
)
CONTEXT_FIELD_IDS = tuple(
    field_id for field_id, spec in FIELD_SPECS.items() if spec["role"] == "context"
)


def _normalise_reasons(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(";") if part.strip()]
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    raise ValueError(f"unsupported reasons value: {value!r}")


def _normalise_status(value):
    if value not in _STATUS_RANK:
        raise ValueError(f"unsupported validity status: {value!r}")
    return value


def _finite_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"descriptor value must be numeric or null: {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("descriptor values must be finite or null")
    return value


def _combine_validity(*items):
    status = "ok"
    reasons = []
    for item in items:
        item_status = _normalise_status(item.get("status", "ok"))
        if _STATUS_RANK[item_status] > _STATUS_RANK[status]:
            status = item_status
        for reason in _normalise_reasons(item.get("reasons", item.get("reason"))):
            if reason not in reasons:
                reasons.append(reason)
    return {"status": status, "reasons": reasons}


def _value_cell(value, validity, source_refs):
    value = _finite_or_none(value)
    validity = _combine_validity(validity)
    if value is None:
        validity = _combine_validity(
            validity, {"status": "unavailable", "reasons": ["missing_value"]}
        )
    return {
        "value": value,
        "status": validity["status"],
        "reasons": validity["reasons"],
        "source_refs": list(source_refs),
    }


def _load_sources(repository_root):
    root = Path(repository_root)
    sources = {}
    for family, spec in SOURCE_SPECS.items():
        path = root / spec["path"]
        try:
            payload = json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise ValueError(f"{family} source missing: {spec['path']}") from exc
        actual = payload.get("schema_version")
        if actual != spec["benchmark_schema"]:
            raise ValueError(
                f"{family} benchmark schema mismatch: expected "
                f"{spec['benchmark_schema']}, got {actual!r}"
            )
        if payload.get("core_indices") != CORE_INDICES:
            raise ValueError(f"{family} core window differs from {WINDOW_ID}")
        sources[family] = payload
    return sources


def _matches(row, criteria):
    for key, expected in criteria.items():
        actual = row.get(key)
        if isinstance(expected, float):
            try:
                if float(actual) != expected:
                    return False
            except (TypeError, ValueError):
                return False
        elif actual != expected:
            return False
    return True


def _one_row(rows, family, field_id, criteria):
    matches = [row for row in rows if _matches(row, criteria)]
    if len(matches) != 1:
        raise ValueError(
            f"{field_id}: expected exactly one {family} row, found {len(matches)}"
        )
    return matches[0]


def _source_refs(family, extra=()):
    spec = SOURCE_SPECS[family]
    refs = [spec["path"], spec["dispositions"]]
    for ref in extra:
        if ref not in refs:
            refs.append(ref)
    return refs


def _row_cell(source, family, field_id, certificate, spec):
    criteria = {
        "certificate": certificate,
        "window": "core",
        "representation": spec["representation"],
        "support_mode": spec["support_policy"],
    }
    if "region" in spec:
        criteria["region"] = spec["region"]
    if "trace_type" in spec:
        criteria["trace_type"] = spec["trace_type"]
    if "threshold" in spec:
        criteria["threshold"] = spec["threshold"]
    if "state" in spec:
        criteria["state"] = spec["state"]
    if "pair" in spec:
        criteria["pair_id"] = spec["pair"]
    if "surface_id" in spec:
        criteria["surface_id"] = spec["surface_id"]
    row_key = "baseline_rows" if family == "persistence" else "rows"
    row = _one_row(source.get(row_key, []), family, field_id, criteria)
    return _value_cell(
        row.get(spec["statistic"]),
        {"status": row.get("status", "ok"), "reasons": row.get("reasons")},
        _source_refs(family),
    )


def _activation_component_validity(activation, certificate, region):
    row = _one_row(
        activation.get("rows", []),
        "activation",
        f"coordination validity {certificate}/{region}",
        {
            "certificate": certificate,
            "window": "core",
            "representation": "coarse",
            "region": region,
            "support_mode": "fixed",
            "trace_type": "relative",
        },
    )
    return {"status": row.get("status", "ok"), "reasons": row.get("reasons")}


def _coordination_cell(sources, field_id, certificate, spec):
    source = sources["coordination"]
    stones = source.get("stones")
    if not isinstance(stones, list) or len(stones) != len(set(stones)):
        raise ValueError("coordination stones must be a unique ordered list")
    if certificate not in stones:
        raise ValueError(f"{field_id}: certificate absent from coordination stone order")
    pair = source.get("primary_pairs", {}).get(spec["pair"])
    if not isinstance(pair, dict):
        raise ValueError(f"{field_id}: coordination pair missing")
    values = pair.get("core_pearson_r")
    if not isinstance(values, list) or len(values) != len(stones):
        raise ValueError(f"{field_id}: coordination value array does not match stone order")
    left, right = spec["pair"].split("__", 1)
    validity = _combine_validity(
        _activation_component_validity(sources["activation"], certificate, left),
        _activation_component_validity(sources["activation"], certificate, right),
    )
    return _value_cell(
        values[stones.index(certificate)],
        validity,
        _source_refs(
            "coordination", (SOURCE_SPECS["activation"]["path"],)
        ),
    )


def _morphology_cell(source, field_id, certificate, spec):
    matches = [
        stone for stone in source.get("stones", [])
        if stone.get("certificate") == certificate
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{field_id}: expected exactly one morphology stone, found {len(matches)}"
        )
    try:
        cell = matches[0]["windows"]["core"]["supports"]["fixed"]["1.00"]
        summary = cell["summary"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{field_id}: morphology baseline cell missing") from exc
    validity = _combine_validity(
        cell.get("validity", {"status": "ok"}),
        {"status": summary.get("status", "ok")},
    )
    return _value_cell(
        summary.get(spec["statistic"]),
        validity,
        _source_refs("morphology"),
    )


def _field_cell(sources, field_id, certificate):
    spec = FIELD_SPECS[field_id]
    family = spec["family"]
    if family in {"activation", "mobility", "occupancy", "switching", "persistence", "opposing"}:
        return _row_cell(sources[family], family, field_id, certificate, spec)
    if family == "coordination":
        return _coordination_cell(sources, field_id, certificate, spec)
    if family == "morphology":
        return _morphology_cell(sources[family], field_id, certificate, spec)
    raise AssertionError(f"unhandled profile family {family}")


def _catalog_entry(field_id):
    spec = FIELD_SPECS[field_id]
    source = SOURCE_SPECS[spec["family"]]
    entry = {
        "role": spec["role"],
        "descriptor_provenance": {
            "issue": source["issue"],
            "descriptor_schema": source["descriptor_schema"],
            "benchmark_schema": source["benchmark_schema"],
            "summary_path": source["path"],
            "dispositions_path": source["dispositions"],
        },
        "window_contract": WINDOW_ID,
        "representation": spec["representation"],
        "support_policy": spec["support_policy"],
        "statistic": spec["statistic"],
        "units": spec["units"],
    }
    for key in ("region", "pair", "surface_id", "trace_type", "threshold", "state", "connectivity", "redundancy_group"):
        if key in spec:
            entry[key] = spec[key]
    return entry


def _field_catalog():
    return {
        "measurements": {
            field_id: _catalog_entry(field_id) for field_id in PRODUCTION_FIELD_IDS
        },
        "context": {
            field_id: _catalog_entry(field_id) for field_id in CONTEXT_FIELD_IDS
        },
    }


def _window_contract():
    return {
        "id": WINDOW_ID,
        "source_indices": list(CORE_INDICES),
        "wrap_explicit": True,
        "source_step_semantics": "ordinal samples; not seconds or calibrated degrees",
    }


def _audit_refs():
    return {
        family: {
            "summary": spec["path"],
            "dispositions": spec["dispositions"],
            "role": "upstream descriptor evidence/QC; not an additional production feature source",
        }
        for family, spec in SOURCE_SPECS.items()
    }


def build_profile(certificate, sources):
    catalog = _field_catalog()
    return {
        "schema_version": PROFILE_SCHEMA,
        "certificate": certificate,
        "window_contract": _window_contract(),
        "measurements": {
            field_id: _field_cell(sources, field_id, certificate)
            for field_id in PRODUCTION_FIELD_IDS
        },
        "context": {
            field_id: _field_cell(sources, field_id, certificate)
            for field_id in CONTEXT_FIELD_IDS
        },
        "field_catalog": catalog,
        "redundancy_groups": REDUNDANCY_GROUPS,
        "audit_refs": _audit_refs(),
    }


def _comparison_payload(profiles):
    return {
        "schema_version": COMPARISON_SCHEMA,
        "profile_schema": PROFILE_SCHEMA,
        "window_contract": _window_contract(),
        "field_catalog": _field_catalog(),
        "redundancy_groups": REDUNDANCY_GROUPS,
        "stones": [
            {
                "certificate": profile["certificate"],
                "measurements": profile["measurements"],
                "context": profile["context"],
            }
            for profile in profiles
        ],
    }


def _json_text(payload):
    return json.dumps(payload, indent=2, allow_nan=False) + "\n"


def _write_comparison_csv(profiles, destination):
    field_ids = list(PRODUCTION_FIELD_IDS) + list(CONTEXT_FIELD_IDS)
    columns = ["certificate"]
    for field_id in field_ids:
        columns.extend([field_id, field_id + "__status", field_id + "__reasons"])
    with Path(destination).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for profile in profiles:
            row = {"certificate": profile["certificate"]}
            combined = {**profile["measurements"], **profile["context"]}
            for field_id in field_ids:
                cell = combined[field_id]
                row[field_id] = "" if cell["value"] is None else repr(cell["value"])
                row[field_id + "__status"] = cell["status"]
                row[field_id + "__reasons"] = ";".join(cell["reasons"])
            writer.writerow(row)


def build_profiles(repository_root, output_dir):
    """Build deterministic retained profiles from committed benchmark summaries."""
    root = Path(repository_root)
    output = Path(output_dir)
    sources = _load_sources(root)
    certificates = sources["activation"].get("stones")
    if not isinstance(certificates, list) or not certificates:
        raise ValueError("activation stones must be a non-empty list")
    if len(certificates) != len(set(certificates)):
        raise ValueError("activation stones must be unique")
    certificates = sorted(certificates)

    output.mkdir(parents=True, exist_ok=True)
    per_stone = output / "per-stone"
    per_stone.mkdir(exist_ok=True)
    for stale in per_stone.glob("*.json"):
        stale.unlink()

    profiles = [build_profile(certificate, sources) for certificate in certificates]
    for profile in profiles:
        (per_stone / f"{profile['certificate']}.json").write_text(_json_text(profile))

    (output / "comparison.json").write_text(_json_text(_comparison_payload(profiles)))
    _write_comparison_csv(profiles, output / "comparison.csv")
    return profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("docs/360/profile"),
        help="Directory for per-stone profiles and combined comparison files",
    )
    args = parser.parse_args()
    profiles = build_profiles(args.repository, args.output)
    print(f"wrote {len(profiles)} {PROFILE_SCHEMA} profiles to {args.output}")


if __name__ == "__main__":
    main()
