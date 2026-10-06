"""Run the PriceScope external Asscher falsification benchmark without label tuning.

The runner deliberately separates source compatibility from interpretation:
complete vendor 360s use the frozen #45 core17 protocol, direct videos use a
declared label-blind research window, and still/locator-only cases remain explicit
pipeline/source mismatches. Source labels are copied only after measurements.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

from . import activation_benchmark as activation_b
from . import asscher_steps
from . import coordination_benchmark as coordination_b
from . import crispness_benchmark as crispness_b
from . import mobility_benchmark as mobility_b
from . import morphology_benchmark as morphology_b
from . import occupancy_benchmark as occupancy_b
from . import opposing_symmetry_benchmark as opposing_b
from . import persistence_benchmark as persistence_b
from . import pipeline
from . import switching_benchmark as switching_b
from . import tier_contrast_benchmark as tier_b
from . import video_source

SCHEMA = "sparkles-external-benchmark-results/1"
MANIFEST_SCHEMA = "sparkles-external-benchmark/1"
CORE_INDICES = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE_INDICES = list(range(240, 256)) + list(range(0, 17))
VIDEO_WINDOW_MAX = 97
MIN_ANALYSIS_FRAMES = 17

PROFILE_FIELDS = {
    "activity.activation.whole_stone_total_excursion":
        ("activation.csv", {"representation":"whole_stone","region":"whole_stone","support_mode":"fixed","trace_type":"raw"}, "total_excursion", "status"),
    "activity.activation.centre_relative_total_excursion":
        ("activation.csv", {"representation":"coarse","region":"centre","support_mode":"fixed","trace_type":"relative"}, "total_excursion", "status"),
    "activity.activation.inner_relative_total_excursion":
        ("activation.csv", {"representation":"coarse","region":"inner","support_mode":"fixed","trace_type":"relative"}, "total_excursion", "status"),
    "activity.activation.middle_relative_total_excursion":
        ("activation.csv", {"representation":"coarse","region":"middle","support_mode":"fixed","trace_type":"relative"}, "total_excursion", "status"),
    "activity.mobility.centre_median":
        ("mobility.csv", {"representation":"coarse","region":"centre","support_mode":"fixed","trace_type":"relative"}, "median", "status"),
    "activity.mobility.inner_median":
        ("mobility.csv", {"representation":"coarse","region":"inner","support_mode":"fixed","trace_type":"relative"}, "median", "status"),
    "activity.mobility.middle_median":
        ("mobility.csv", {"representation":"coarse","region":"middle","support_mode":"fixed","trace_type":"relative"}, "median", "status"),
    "dark_state.occupancy.centre_mean":
        ("occupancy.csv", {"threshold":"0.65","representation":"coarse","region":"centre","support_mode":"fixed"}, "mean", "status"),
    "dark_state.occupancy.inner_mean":
        ("occupancy.csv", {"threshold":"0.65","representation":"coarse","region":"inner","support_mode":"fixed"}, "mean", "status"),
    "dark_state.occupancy.middle_mean":
        ("occupancy.csv", {"threshold":"0.65","representation":"coarse","region":"middle","support_mode":"fixed"}, "mean", "status"),
    "dark_state.persistence.inner_dark_q90_window_fraction":
        ("persistence.csv", {"threshold":"0.65","representation":"coarse","region":"inner","support_mode":"fixed","state":"dark"}, "q90_window_fraction", "status"),
    "temporal_reconfiguration.switching.inner_rate":
        ("switching.csv", {"threshold":"0.65","representation":"coarse","region":"inner","support_mode":"fixed"}, "regional_switch_rate", "status"),
    "temporal_reconfiguration.switching.middle_rate":
        ("switching.csv", {"threshold":"0.65","representation":"coarse","region":"middle","support_mode":"fixed"}, "regional_switch_rate", "status"),
    "nested_step.centre_inner_pearson":
        ("coordination.csv", {"representation":"coarse","pair":"centre__inner"}, "pearson_r", "level_status"),
    "nested_step.inner_middle_pearson":
        ("coordination.csv", {"representation":"coarse","pair":"inner__middle"}, "pearson_r", "level_status"),
    "directional.side_E_W_pearson":
        ("opposing-symmetry.csv", {"surface_id":"coarse_whole","support_mode":"fixed","pair_id":"side_E_W"}, "correlation", "status"),
    "directional.side_N_S_pearson":
        ("opposing-symmetry.csv", {"surface_id":"coarse_whole","support_mode":"fixed","pair_id":"side_N_S"}, "correlation", "status"),
    "directional.corner_NE_SW_pearson":
        ("opposing-symmetry.csv", {"surface_id":"coarse_whole","support_mode":"fixed","pair_id":"corner_NE_SW"}, "correlation", "status"),
    "directional.corner_NW_SE_pearson":
        ("opposing-symmetry.csv", {"surface_id":"coarse_whole","support_mode":"fixed","pair_id":"corner_NW_SE"}, "correlation", "status"),
    "flash_morphology.median_largest_component_fraction":
        ("morphology.csv", {"support_mode":"fixed","threshold":"1.0"}, "median_largest_component_fraction", "status"),
    "flash_morphology.active_frame_fraction":
        ("morphology.csv", {"support_mode":"fixed","threshold":"1.0"}, "active_frame_fraction", "status"),
}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_archive_path(root, relative):
    root = Path(root)
    direct = root / relative
    if direct.is_file():
        return direct
    matches = [
        path for path in root.rglob(Path(relative).name)
        if path.is_file() and str(path).replace("\\", "/").endswith(relative.replace("\\", "/"))
    ]
    if len(matches) == 1:
        return matches[0]
    basename = [path for path in root.rglob(Path(relative).name) if path.is_file()]
    if len(basename) == 1:
        return basename[0]
    raise ValueError(f"archive member not uniquely found: {relative}")


def _entry_path(entry):
    for key in ("path", "artifact_path", "file", "filename", "name"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError("sequence frame entry has no path-like field")


def materialize_archived_sequence(sample, archive_root, destination):
    sequence = sample["media"]["sequence"]
    manifest_path = _find_archive_path(archive_root, sequence["manifest_path"])
    payload = json.loads(manifest_path.read_text())
    destination = Path(destination)
    frames_dir = destination / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    entries = payload.get("frames")
    if not isinstance(entries, list) or not entries:
        raise ValueError("archived sequence manifest has no frame list")
    index_field = "source_index" if payload.get("schema_version") == "diamond360-source/1" else sequence.get("frame_index_field", "index")
    normalized = []
    for entry in entries:
        index = entry.get(index_field)
        if type(index) is not int or index < 0:
            raise ValueError(f"invalid archived frame index: {index!r}")
        raw_path = _entry_path(entry)
        candidate = manifest_path.parent / raw_path
        if not candidate.is_file():
            try:
                candidate = _find_archive_path(archive_root, raw_path)
            except ValueError:
                candidate = _find_archive_path(archive_root, Path(raw_path).name)
        expected = entry.get("sha256")
        actual = _sha256(candidate)
        if expected and expected != actual:
            raise ValueError(f"archived frame hash mismatch: {raw_path}")
        suffix = candidate.suffix.lower() or ".jpg"
        target = frames_dir / f"frame-{index:06d}{suffix}"
        shutil.copyfile(candidate, target)
        normalized.append({
            "source_index": index,
            "path": str(target.relative_to(destination)),
            "sha256": actual,
            "archived_path": raw_path,
        })

    normalized.sort(key=lambda row: row["source_index"])
    indices = [row["source_index"] for row in normalized]
    declared = int(sequence.get("frame_count", sequence.get("frames", len(entries))))
    if indices != list(range(declared)):
        raise ValueError("archived sequence is not complete and contiguous")
    source = {
        "schema_version": "diamond360-source/1",
        "source_type": "archived_vendor_360",
        "source_id": sample["sample_id"],
        "source_frame_count": declared,
        "sequence_complete": True,
        "ordering": sequence.get("ordering"),
        "frames": normalized,
        "adapter": {
            "schema_version": "sparkles-external-archive-sequence-adapter/1",
            "archive_manifest_path": sequence["manifest_path"],
            "archive_manifest_sha256": _sha256(manifest_path),
            "frame_index_field": index_field,
            "timing_seconds": sequence.get("timing_seconds"),
            "calibrated_angles_degrees": sequence.get("calibrated_angles_degrees"),
        },
    }
    (destination / "source-manifest.json").write_text(
        json.dumps(source, indent=2, allow_nan=False) + "\n"
    )
    return source


def prepare_archive_sources(manifest, archive_root, source_root):
    source_root = Path(source_root)
    source_root.mkdir(parents=True, exist_ok=True)
    status = {}
    for sample in manifest["samples"]:
        sample_id = sample["sample_id"]
        destination = source_root / sample_id
        media = sample.get("media") or {}
        try:
            if media.get("sequence"):
                materialize_archived_sequence(sample, archive_root, destination)
                status[sample_id] = {"status":"prepared","adapter":"archived_vendor_360"}
                continue
            assets = media.get("assets") or []
            if sample.get("evidence_type") == "direct_mp4" and len(assets) == 1:
                asset = assets[0]
                archived = _find_archive_path(archive_root, asset["artifact_path"])
                if _sha256(archived) != asset["sha256"]:
                    raise ValueError("archived media hash mismatch")
                source = video_source.extract(archived, destination, sample_id=sample_id)
                status[sample_id] = {
                    "status":"prepared",
                    "adapter":"decoded_video_frames",
                    "frames":source["source_frame_count"],
                }
                continue
            status[sample_id] = {
                "status":"not_applicable",
                "reason":"no_motion_source_contract",
            }
        except Exception as error:
            if destination.exists():
                shutil.rmtree(destination)
            status[sample_id] = {
                "status":"failed",
                "reason":f"{type(error).__name__}: {error}",
            }
    return status


def _window_for_source(source_manifest, evidence_type):
    count = int(source_manifest["source_frame_count"])
    if evidence_type == "vendor_360":
        if count < 256 or not source_manifest.get("sequence_complete"):
            raise ValueError("vendor 360 does not satisfy complete 256-frame contract")
        return {
            "analysis_indices": CORE_INDICES,
            "geometry_indices": WIDE_INDICES,
            "wrap": True,
            "profile_compatible": True,
            "window_policy": "frozen #45 core17 with canonical wide33 geometry",
        }
    if count < MIN_ANALYSIS_FRAMES:
        raise ValueError(f"motion source has only {count} frames; need at least {MIN_ANALYSIS_FRAMES}")
    length = min(count, VIDEO_WINDOW_MAX)
    start = (count - length) // 2
    indices = list(range(start, start + length))
    return {
        "analysis_indices": indices,
        "geometry_indices": indices,
        "wrap": False,
        "profile_compatible": False,
        "window_policy": (
            f"label-blind centred contiguous window, max {VIDEO_WINDOW_MAX} decoded frames; "
            "research projection only"
        ),
    }


def _write_unavailable_steps(destination, error):
    destination.mkdir(parents=True, exist_ok=True)
    payload = {
        "template_status":"unavailable",
        "template_reason":f"external_benchmark_step_failure:{type(error).__name__}:{error}",
        "boundaries":{},
        "frames":[],
    }
    (destination / "steps.json").write_text(json.dumps(payload, indent=2) + "\n")


def _float_or_none(value):
    if value in (None, ""):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _matches(row, criteria):
    for key, expected in criteria.items():
        actual = row.get(key)
        if actual is None:
            return False
        if isinstance(expected, str) and expected.replace(".", "", 1).isdigit():
            try:
                if float(actual) != float(expected):
                    return False
            except ValueError:
                return False
        elif str(actual) != str(expected):
            return False
    return True


def _read_profile_fields(output):
    cache = {}
    fields = {}
    for field_id, (filename, criteria, value_key, status_key) in PROFILE_FIELDS.items():
        if filename not in cache:
            with (Path(output) / filename).open(newline="") as handle:
                cache[filename] = list(csv.DictReader(handle))
        matches = [row for row in cache[filename] if _matches(row, criteria)]
        if len(matches) != 1:
            fields[field_id] = {
                "value":None,
                "status":"unavailable",
                "reasons":[f"expected_one_row_found_{len(matches)}"],
            }
            continue
        row = matches[0]
        reasons = [part for part in (row.get("reasons") or "").split(";") if part]
        fields[field_id] = {
            "value":_float_or_none(row.get(value_key)),
            "status":row.get(status_key) or "unavailable",
            "reasons":reasons,
        }
    return fields


def _run_retained_families(processed, steps_output, indices, wrap, output):
    output = Path(output)
    activation = activation_b.measure_stone(processed, steps_output, indices, wrap=wrap)
    mobility = mobility_b.measure_from_activation(activation)
    coordination = coordination_b.measure_from_activation(activation)
    occupancy = occupancy_b.measure_stone(processed, steps_output, indices, wrap=wrap)
    switching = switching_b.measure_stone(processed, steps_output, indices, wrap=wrap)
    persistence = persistence_b.measure_stone(processed, steps_output, indices, wrap=wrap)
    opposing = opposing_b.measure_stone(processed, steps_output, indices, wrap=wrap)
    morphology = morphology_b.measure_stone(processed, indices, wrap=wrap)
    activation_b.write_stone_outputs(activation, output, processed)
    mobility_b.write_stone_outputs(mobility, output, processed)
    coordination_b.write_stone_outputs(coordination, output)
    occupancy_b.write_stone_outputs(occupancy, output, processed, steps_output)
    switching_b.write_stone_outputs(switching, output, processed, steps_output)
    persistence_b.write_stone_outputs(persistence, output, processed, steps_output)
    opposing_b.write_stone_outputs(opposing, output, processed, steps_output)
    morphology_b.write_stone_outputs(morphology, output, processed)
    return _read_profile_fields(output)


def _validity(cell):
    if not isinstance(cell, dict):
        return {"status":"unavailable","reasons":["missing_result"]}
    validity = cell.get("validity")
    if isinstance(validity, dict):
        return {
            "status":validity.get("status","unavailable"),
            "reasons":list(validity.get("reasons") or []),
        }
    return {
        "status":cell.get("status","unavailable"),
        "reasons":[cell.get("reason")] if cell.get("reason") else [],
    }


def _compact_crispness(result):
    return {
        "upstream_validity":result.get("upstream_validity"),
        "summary":result.get("baseline", {}).get("summary", {}),
        "full_template_diagnostic":result.get("full_template_diagnostic"),
        "evidence_selection":result.get("evidence_selection"),
    }


def _compact_tier(result):
    profile = result.get("tier_readability_profile") or {}
    pairs = {}
    for pair_id, pair in result.get("pairs", {}).items():
        semantic = (((pair.get("boundary_local") or {}).get("multi_scale") or {}).get("semantic") or {})
        pairs[pair_id] = {
            "validity":_validity(semantic),
            "q25_summary":semantic.get("q25_summary"),
            "median_summary":semantic.get("median_summary"),
            "scale_spread_summary":semantic.get("scale_spread_summary"),
        }
    return {
        "research_only":True,
        "quality_direction":None,
        "profile_validity":_validity(profile),
        "profile": {
            key:profile.get(key)
            for key in (
                "q25_summary","median_summary","q75_summary","scale_spread_summary",
                "ordering_fractions","ordering_observations","evidence"
            )
        },
        "pairs":pairs,
    }


def _source_labels(sample):
    return [
        {
            "text":label.get("text"),
            "reviewer":label.get("reviewer"),
            "reviewer_type":label.get("reviewer_type"),
            "categories":label.get("categories"),
            "strength":label.get("strength"),
            "polarity":label.get("polarity"),
        }
        for label in sample.get("labels", [])
    ]


def run_sample(sample, source, output, work):
    source_manifest = json.loads((Path(source) / "source-manifest.json").read_text())
    window = _window_for_source(source_manifest, sample.get("evidence_type"))
    processed = Path(work) / sample["sample_id"] / "processed"
    processed.parent.mkdir(parents=True, exist_ok=True)
    pipeline.run(
        source,
        processed,
        Path(source) / "source-manifest.json",
        gain=1.0,
        diagnostic_indices=window["analysis_indices"],
        accept_review=True,
    )
    steps_output = Path(work) / sample["sample_id"] / "steps"
    step_error = None
    try:
        asscher_steps.run(
            processed,
            steps_output,
            window["geometry_indices"],
            wrap=window["wrap"],
        )
    except Exception as error:
        step_error = f"{type(error).__name__}: {error}"
        _write_unavailable_steps(steps_output, error)

    with tempfile.TemporaryDirectory(prefix="sparkles-external-fields-") as temp:
        profile_fields = _run_retained_families(
            processed,
            steps_output,
            window["analysis_indices"],
            window["wrap"],
            Path(temp),
        )

    research = {}
    try:
        crisp = crispness_b.measure_stone(
            processed,
            window["analysis_indices"],
            wrap=window["wrap"],
        )
        clean = crispness_b.write_stone_outputs(crisp, Path(output) / "crispness")
        research["crispness"] = {
            "status":"measured",
            **_compact_crispness(clean),
        }
    except Exception as error:
        research["crispness"] = {
            "status":"pipeline/source mismatch",
            "reason":f"{type(error).__name__}: {error}",
        }
    try:
        tier = tier_b.measure_stone(
            processed,
            steps_output,
            window["analysis_indices"],
            wrap=window["wrap"],
        )
        tier_b.write_stone_outputs(tier, Path(output) / "tier-readability", processed=processed)
        research["tier_readability"] = {
            "status":"measured",
            **_compact_tier(tier),
        }
    except Exception as error:
        research["tier_readability"] = {
            "status":"pipeline/source mismatch",
            "reason":f"{type(error).__name__}: {error}",
        }

    result = {
        "schema_version":SCHEMA,
        "sample_id":sample["sample_id"],
        "source_type":sample.get("source_type"),
        "evidence_type":sample.get("evidence_type"),
        "group_id":sample.get("group_id"),
        "relation_ids":sample.get("relation_ids") or [],
        "changed_design_variable":sample.get("changed_design_variable"),
        "source_labels":_source_labels(sample),
        "protocol":window,
        "protocol_disposition":(
            "production-compatible #45 protocol"
            if window["profile_compatible"]
            else "research projection only"
        ),
        "step_geometry_error":step_error,
        "retained_profile": {
            "schema_version":"diamond360-descriptor-profile/1-field-projection",
            "profile_compatible":window["profile_compatible"],
            "fields":profile_fields,
        },
        "research_descriptors":research,
        "interpretation": {
            "labels_used_for_measurement":False,
            "quality_thresholds_fitted":False,
            "descriptor_disposition":"pending cross-sample comparison",
        },
    }
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / "result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return result


def unavailable_result(sample, source_status):
    return {
        "schema_version":SCHEMA,
        "sample_id":sample["sample_id"],
        "source_type":sample.get("source_type"),
        "evidence_type":sample.get("evidence_type"),
        "group_id":sample.get("group_id"),
        "relation_ids":sample.get("relation_ids") or [],
        "changed_design_variable":sample.get("changed_design_variable"),
        "source_labels":_source_labels(sample),
        "protocol_disposition":"pipeline/source mismatch",
        "source_status":source_status,
        "retained_profile":{"profile_compatible":False,"fields":{}},
        "research_descriptors":{},
        "interpretation":{
            "labels_used_for_measurement":False,
            "quality_thresholds_fitted":False,
            "descriptor_disposition":"pipeline/source mismatch",
        },
    }


def _markdown(summary):
    lines = [
        "# PriceScope external blind run",
        "",
        "Measurements were generated without consulting source labels. Labels are joined only in the output.",
        "",
        "| sample | evidence | protocol | #45 fields | crispness | tier readability |",
        "|---|---|---|---:|---|---|",
    ]
    for item in summary["samples"]:
        fields = item.get("retained_profile", {}).get("fields", {})
        crisp = item.get("research_descriptors", {}).get("crispness", {}).get("status", "—")
        tier = item.get("research_descriptors", {}).get("tier_readability", {}).get("status", "—")
        lines.append(
            f"| {item['sample_id']} | {item.get('evidence_type') or 'unknown'} | "
            f"{item.get('protocol_disposition')} | {len(fields)} | {crisp} | {tier} |"
        )
    lines += [
        "",
        "## Interpretation boundary",
        "",
        "- production-compatible #45 protocol means the complete vendor 360 satisfied the frozen core17 contract.",
        "- research projection only means the same algorithms were applied to a declared label-blind contiguous video window; source steps are not calibrated angles.",
        "- pipeline/source mismatch is preserved rather than manufacturing motion from stills, previews, or missing media.",
        "- Research crispness and tier-readability outputs are not quality scores. Tier readability has no declared quality direction.",
        "- This artifact does not decide supports/contradicts automatically; those dispositions require comparison with the source claim and the percept each family actually measures.",
        "",
    ]
    return "\n".join(lines)


def run(manifest_path, source_root, output, *, archive_root=None, prepare_sources=False):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"expected manifest schema {MANIFEST_SCHEMA}")
    source_root = Path(source_root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    preparation = {}
    if prepare_sources:
        if archive_root is None:
            raise ValueError("--prepare-sources requires --archive-root")
        preparation = prepare_archive_sources(manifest, archive_root, source_root)

    results = []
    with tempfile.TemporaryDirectory(prefix="sparkles-external-run-") as temporary:
        work = Path(temporary)
        for sample in manifest["samples"]:
            sample_id = sample["sample_id"]
            source = source_root / sample_id
            source_status = preparation.get(sample_id)
            if not (source / "source-manifest.json").is_file():
                result = unavailable_result(
                    sample,
                    source_status or {"status":"missing","reason":"no prepared source contract"},
                )
            else:
                try:
                    result = run_sample(
                        sample,
                        source,
                        output / "per-sample" / sample_id,
                        work,
                    )
                except Exception as error:
                    result = unavailable_result(sample, {
                        "status":"failed",
                        "reason":f"{type(error).__name__}: {error}",
                    })
            destination = output / "per-sample" / sample_id
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "result.json").write_text(
                json.dumps(result, indent=2, allow_nan=False) + "\n"
            )
            results.append(result)

    coverage = {
        "catalogued_samples":len(results),
        "production_compatible_runs":sum(
            item.get("protocol_disposition") == "production-compatible #45 protocol"
            for item in results
        ),
        "research_projection_runs":sum(
            item.get("protocol_disposition") == "research projection only"
            for item in results
        ),
        "pipeline_source_mismatches":sum(
            item.get("protocol_disposition") == "pipeline/source mismatch"
            for item in results
        ),
    }
    summary = {
        "schema_version":SCHEMA,
        "benchmark_id":manifest.get("benchmark_id"),
        "manifest_schema":manifest.get("schema_version"),
        "labels_used_for_measurement":False,
        "quality_thresholds_fitted":False,
        "profile_field_count":len(PROFILE_FIELDS),
        "coverage":coverage,
        "preparation":preparation,
        "samples":results,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    (output / "README.md").write_text(_markdown(summary) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/360/external-benchmark/pricescope/benchmark-manifest.json"),
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--prepare-sources", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(
            args.manifest,
            args.source_root,
            args.output,
            archive_root=args.archive_root,
            prepare_sources=args.prepare_sources,
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(summary["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
