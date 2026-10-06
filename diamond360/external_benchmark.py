"""Run the PriceScope external Asscher falsification benchmark (#64).

The benchmark consumes the normalized source manifest and the pinned v3 archive.
It never changes production thresholds. Media that cannot satisfy an explicit
source contract are reported as source/pipeline mismatches rather than coerced.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import activation_benchmark as activation_b
from . import asscher_steps
from . import coordination_benchmark as coordination_b
from . import crispness_benchmark as crispness_b
from . import diagonal_arms
from . import mobility_benchmark as mobility_b
from . import morphology_benchmark as morphology_b
from . import occupancy_benchmark as occupancy_b
from . import opposing_symmetry_benchmark as opposing_b
from . import persistence_benchmark as persistence_b
from . import pipeline
from . import switching_benchmark as switching_b
from . import tier_contrast_benchmark as tier_b
from .external_media import adapt_archived_sequence, adapt_still, extract_video

SCHEMA = "sparkles-external-benchmark-run/1"
MANIFEST_SCHEMA = "sparkles-external-benchmark/1"
CORE_INDICES = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE_INDICES = list(range(240,256)) + list(range(0,17))

PRIMARY_SAMPLE_IDS = (
    "p3-video-cut-for-weight",
    "p3-video-corrected",
    "p3-video-higher-performance",
    "windmill-24",
    "windmill-22",
    "windmill-20",
    "windmill-18",
    "windmill-16",
    "windmill-14",
    "asscher-eval-glittery",
    "asscher-eval-crispest",
    "asscher-eval-messy-arrows",
    "asscher-eval-nice-dance",
)


def _finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _cell(value, validity=None, *, role="descriptor", relevance=None):
    validity = validity or {}
    return {
        "value": _finite(value),
        "status": validity.get("status", "ok" if _finite(value) is not None else "unavailable"),
        "reasons": list(validity.get("reasons") or []),
        "role": role,
        "relevance": relevance,
    }


def _threshold(wrapper, key="0.65"):
    return wrapper["thresholds"][key]


def _compact_retained(
    activation,
    occupancy,
    switching,
    persistence,
    mobility,
    coordination,
    opposing,
    morphology,
):
    out = {}
    whole = activation["whole_stone"]
    out["activity.activation.whole_stone_total_excursion"] = _cell(
        whole["summary"].get("total_excursion"),
        whole.get("validity"),
        relevance="activity/dance; not a quality direction by itself",
    )
    for region in ("centre", "inner", "middle"):
        a = activation["representations"]["coarse"]["regions"][region]["fixed"]
        out[f"activity.activation.{region}_relative_total_excursion"] = _cell(
            a["relative_summary"].get("total_excursion"),
            a.get("relative_validity"),
            relevance="activity/dance; not a quality direction by itself",
        )
        o = _threshold(
            occupancy["representations"]["coarse"]["regions"][region]["fixed"]
        )
        out[f"dark_state.occupancy.{region}_mean"] = _cell(
            o["summary"].get("mean"),
            o.get("validity"),
            relevance="broad grouped darkness candidate",
        )
        trace = mobility["traces"][f"coarse/{region}/fixed/relative"]
        out[f"activity.mobility.{region}_median"] = _cell(
            trace["summary"].get("median"),
            trace.get("validity"),
            relevance="movement/dance; not a quality direction by itself",
        )

    p = _threshold(
        persistence["representations"]["coarse"]["regions"]["inner"]["fixed"]
    )
    out["dark_state.persistence.inner_dark_q90_window_fraction"] = _cell(
        p["dark"].get("q90_window_fraction"),
        p.get("validity"),
        relevance="persistent darkness candidate",
    )
    for region in ("inner", "middle"):
        s = _threshold(
            switching["representations"]["coarse"]["regions"][region]["fixed"]
        )
        out[f"temporal_reconfiguration.switching.{region}_rate"] = _cell(
            s.get("regional_switch_rate"),
            s.get("validity"),
            relevance="reconfiguration/dance; not a quality direction by itself",
        )

    fixed = coordination["representations"]["coarse"]["fixed"]["pairs"]
    for pair_id, field_id in (
        ("centre__inner", "nested_step.centre_inner_pearson"),
        ("inner__middle", "nested_step.inner_middle_pearson"),
    ):
        pair = fixed[pair_id]
        out[field_id] = _cell(
            pair["level_correlation"].get("pearson_r"),
            pair.get("level_validity"),
            relevance="nested-step coordination; sign is descriptive",
        )

    pairs = opposing["surfaces"]["coarse_whole"]["support_modes"]["fixed"]["pairs"]
    for pair_id, field_id in (
        ("side_E_W", "directional.side_E_W_pearson"),
        ("side_N_S", "directional.side_N_S_pearson"),
        ("corner_NE_SW", "directional.corner_NE_SW_pearson"),
        ("corner_NW_SE", "directional.corner_NW_SE_pearson"),
    ):
        pair = pairs[pair_id]
        out[field_id] = _cell(
            pair["metrics"]["correlation"].get("value"),
            pair.get("validity"),
            relevance="directional coordination; descriptive",
        )

    m = morphology["supports"]["fixed"]["thresholds"]["1.00"]
    out["flash_morphology.median_largest_component_fraction"] = _cell(
        m["summary"].get("median_largest_component_fraction"),
        m.get("validity"),
        relevance="flash spatial scale; not a quality direction by itself",
    )
    out["flash_morphology.active_frame_fraction"] = _cell(
        m["summary"].get("active_frame_fraction"),
        m.get("validity"),
        role="context",
        relevance="context only",
    )
    return out


def _compact_crispness(result):
    return {
        "status": result.get("upstream_validity", {}).get("status"),
        "reasons": result.get("upstream_validity", {}).get("reasons", []),
        "summary": result.get("baseline", {}).get("summary", {}),
        "full_template_status": result.get("full_template_diagnostic", {}).get("status"),
        "research_only": True,
        "quality_direction": None,
    }


def _compact_tier(result):
    profile = result.get("tier_readability_profile") or {}
    return {
        "validity": profile.get("validity"),
        "q25_summary": profile.get("q25_summary"),
        "median_summary": profile.get("median_summary"),
        "q75_summary": profile.get("q75_summary"),
        "scale_spread_summary": profile.get("scale_spread_summary"),
        "ordering_fractions": profile.get("ordering_fractions"),
        "research_only": True,
        "quality_direction": None,
    }


def _representative_indices(count, faceup=False):
    if count <= 0:
        return []
    if faceup and count > 252:
        return [252, 0, 4]
    values = [0, count // 2, count - 1]
    return list(dict.fromkeys(values))


def _copy_representatives(source, manifest, output, faceup=False):
    output.mkdir(parents=True, exist_ok=True)
    lookup = {row["source_index"]: row for row in manifest["frames"]}
    copied = []
    for index in _representative_indices(len(lookup), faceup=faceup):
        row = lookup.get(index)
        if row is None:
            continue
        source_path = Path(source) / row["path"]
        destination = output / f"source-{index:04d}{source_path.suffix.lower()}"
        shutil.copyfile(source_path, destination)
        copied.append({"source_index": index, "path": destination.name})
    return copied


def _run_dynamic(source, output, work, *, faceup):
    manifest = json.loads((Path(source) / "source-manifest.json").read_text())
    count = manifest["source_frame_count"]
    if faceup and count != 256:
        raise ValueError("production face-up adapter requires the 256-frame d360 contract")
    indices = CORE_INDICES if faceup else list(range(count))
    wrap = bool(faceup)
    step_indices = WIDE_INDICES if faceup else list(range(count))

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    processed = work / "processed"
    pipeline.run(
        source,
        processed,
        Path(source) / "source-manifest.json",
        gain=1.0,
        diagnostic_indices=indices,
        accept_review=True,
    )
    steps = work / "steps"
    asscher_steps.run(processed, steps, step_indices, wrap=wrap)

    activation = activation_b.measure_stone(processed, steps, indices, wrap=wrap)
    occupancy = occupancy_b.measure_stone(processed, steps, indices, wrap=wrap)
    switching = switching_b.measure_stone(processed, steps, indices, wrap=wrap)
    persistence = persistence_b.measure_stone(processed, steps, indices, wrap=wrap)
    mobility = mobility_b.measure_from_activation(activation)
    coordination = coordination_b.measure_from_activation(activation)
    opposing = opposing_b.measure_stone(processed, steps, indices, wrap=wrap)
    morphology = morphology_b.measure_stone(processed, indices, wrap=wrap)
    crispness = crispness_b.measure_stone(processed, indices, wrap=wrap)
    tier = tier_b.measure_stone(processed, steps, indices, wrap=wrap)

    return {
        "analysis_mode": "production_faceup_core17" if faceup else "ordered_media_full_sequence",
        "source_frame_count": count,
        "requested_indices": indices,
        "retained_profile": _compact_retained(
            activation,
            occupancy,
            switching,
            persistence,
            mobility,
            coordination,
            opposing,
            morphology,
        ),
        "crispness_research": _compact_crispness(crispness),
        "tier_readability_research": _compact_tier(tier),
        "representative_frames": _copy_representatives(
            source,
            manifest,
            output / "representative-source-frames",
            faceup=faceup,
        ),
    }


def _run_static(source, output, work):
    manifest = json.loads((Path(source) / "source-manifest.json").read_text())
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    processed = work / "processed"
    metadata = pipeline.run(
        source,
        processed,
        Path(source) / "source-manifest.json",
        gain=1.0,
        diagnostic_indices=[0],
        accept_review=True,
    )
    records = [row for row in metadata["frames"] if "registration" in row]
    if len(records) != 1:
        raise ValueError("static geometry adapter requires one accepted registered frame")
    record = records[0]
    with np.load(processed / record["photometry_path"]) as data:
        brightness = np.asarray(data["encoded_brightness"], float)
        valid = np.asarray(data["valid_mask"], bool)
    mask = np.asarray(
        Image.open(processed / record["registration"]["mask_path"]).convert("L")
    ) > 0
    result = diagonal_arms.measure_frame(
        brightness,
        mask,
        valid,
        include_trace=False,
    )
    return {
        "analysis_mode": "static_geometry_only",
        "source_frame_count": 1,
        "diagonal_arm_geometry": result,
        "retained_profile": None,
        "crispness_research": None,
        "tier_readability_research": None,
        "representative_frames": _copy_representatives(
            source,
            manifest,
            output / "representative-source-frames",
        ),
    }


def _verify_asset(sample, archive_root):
    assets = sample.get("media", {}).get("assets") or []
    if not assets:
        raise ValueError("sample has no archived asset")
    if len(assets) != 1:
        raise ValueError("benchmark adapter currently expects one primary archived asset")
    asset = assets[0]
    path = Path(archive_root) / asset["artifact_path"]
    if not path.is_file():
        raise ValueError(f"archived asset missing: {path}")
    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != asset["sha256"]:
        raise ValueError(f"archived asset hash mismatch: {sample['sample_id']}")
    return asset, path


def _prepare_source(sample, archive_root, destination):
    media = sample.get("media") or {}
    provenance = {
        "sample_id": sample["sample_id"],
        "source_url": sample.get("source_url"),
        "source_type": sample.get("source_type"),
        "evidence_type": sample.get("evidence_type"),
    }
    if media.get("sequence"):
        return adapt_archived_sequence(
            archive_root,
            media["sequence"],
            destination,
            provenance=provenance,
        ), True
    asset, path = _verify_asset(sample, archive_root)
    media_type = asset.get("media_type")
    if media_type is None:
        media_type = Path(asset["artifact_path"]).suffix.lower().lstrip(".")
    if media_type in {"mp4", "gif"}:
        return extract_video(
            path,
            destination,
            provenance={**provenance, "archived_asset": asset["artifact_path"]},
        ), False
    if media_type in {"jpg", "jpeg", "png"}:
        return adapt_still(
            path,
            destination,
            provenance={**provenance, "archived_asset": asset["artifact_path"]},
        ), False
    raise ValueError(f"unsupported archived media type: {media_type}")


def _mode(sample):
    media = sample.get("media") or {}
    if media.get("sequence") and sample.get("evidence_type") == "vendor_360":
        return "dynamic_faceup"
    assets = media.get("assets") or []
    if assets:
        kind = assets[0].get("media_type")
        if kind is None:
            kind = Path(assets[0].get("artifact_path", "")).suffix.lower().lstrip(".")
        if kind in {"mp4", "gif"}:
            return "dynamic_ordered"
        if kind in {"jpg", "jpeg", "png"}:
            return "static"
    return "source_mismatch"


def _disposition(kind, note, sample_ids=None, metric=None, observed=None):
    return {
        "kind": kind,
        "note": note,
        "sample_ids": list(sample_ids or []),
        "metric": metric,
        "observed": observed,
    }


def _metric(sample_result, field):
    cell = (sample_result.get("retained_profile") or {}).get(field) or {}
    return cell.get("value") if cell.get("status") != "unavailable" else None


def _tier_median(sample_result):
    cell = (sample_result.get("tier_readability_research") or {}).get("median_summary") or {}
    return _finite(cell.get("q50"))


def _ordered(values, increasing):
    if any(v is None for v in values):
        return None
    pairs = list(zip(values, values[1:]))
    return all(b >= a for a, b in pairs) if increasing else all(b <= a for a, b in pairs)


def build_dispositions(results):
    by_id = {row["sample_id"]: row for row in results}
    dispositions = []

    p3_ids = [
        "p3-video-cut-for-weight",
        "p3-video-corrected",
        "p3-video-higher-performance",
    ]
    p3 = [by_id.get(sample_id) for sample_id in p3_ids]
    if all(row and row.get("status") == "measured" for row in p3):
        for field, increasing, note in (
            (
                "dark_state.occupancy.inner_mean",
                False,
                "Grouped inner darkness is a candidate performance direction for the controlled P3 progression.",
            ),
            (
                "dark_state.persistence.inner_dark_q90_window_fraction",
                False,
                "Persistent inner darkness is a candidate performance direction for the controlled P3 progression.",
            ),
        ):
            values = [_metric(row, field) for row in p3]
            match = _ordered(values, increasing)
            dispositions.append(
                _disposition(
                    "supports_external_case" if match else "contradicts_external_case"
                    if match is False else "pipeline_source_mismatch",
                    note,
                    p3_ids,
                    field,
                    values,
                )
            )
        values = [_tier_median(row) for row in p3]
        match = _ordered(values, True)
        dispositions.append(
            _disposition(
                "supports_external_case" if match else "contradicts_external_case"
                if match is False else "pipeline_source_mismatch",
                "Tier readability is a research candidate for the bad -> corrected -> higher-performance P3 progression.",
                p3_ids,
                "tier_readability_research.median_summary.q50",
                values,
            )
        )
    else:
        dispositions.append(
            _disposition(
                "pipeline_source_mismatch",
                "At least one controlled P3 video could not complete the explicit ordered-media pipeline.",
                p3_ids,
            )
        )

    d360_ids = ["asscher-eval-glittery", "asscher-eval-crispest"]
    d360 = [by_id.get(sample_id) for sample_id in d360_ids]
    if all(row and row.get("status") == "measured" for row in d360):
        values = [_tier_median(row) for row in d360]
        if all(v is not None for v in values):
            dispositions.append(
                _disposition(
                    "supports_external_case" if values[1] < values[0] else "contradicts_external_case",
                    "Karl ranks Crispest worse and specifically flags P3 leakage; lower research tier-readability on Crispest is the predeclared relevant direction.",
                    d360_ids,
                    "tier_readability_research.median_summary.q50",
                    values,
                )
            )
        else:
            dispositions.append(
                _disposition(
                    "pipeline_source_mismatch",
                    "Tier-readability was unavailable for one or both Karl-labelled D360 stones.",
                    d360_ids,
                    "tier_readability_research.median_summary.q50",
                    values,
                )
            )
        dispositions.append(
            _disposition(
                "not_applicable_measuring_different_percept",
                "Activation, mobility, switching and flash morphology have no predeclared quality direction for the Glittery/Crispest pair.",
                d360_ids,
            )
        )
    else:
        dispositions.append(
            _disposition(
                "pipeline_source_mismatch",
                "One or both archived D360 sequences could not complete the face-up production pipeline.",
                d360_ids,
            )
        )

    kashi_ids = ["asscher-eval-messy-arrows", "asscher-eval-nice-dance"]
    kashi = [by_id.get(sample_id) for sample_id in kashi_ids]
    if all(row and row.get("status") == "measured" for row in kashi):
        for field, predicate, note in (
            (
                "dark_state.persistence.inner_dark_q90_window_fraction",
                lambda a, b: b < a,
                "Nice dance should show less persistent inner darkness than the messy-arrows negative control if this descriptor captures the source criticism.",
            ),
            (
                "temporal_reconfiguration.switching.inner_rate",
                lambda a, b: b > a,
                "Nice dance should show more inner-state reconfiguration than the messy-arrows negative control if switching captures the stated dance difference.",
            ),
        ):
            values = [_metric(row, field) for row in kashi]
            if all(v is not None for v in values):
                dispositions.append(
                    _disposition(
                        "supports_external_case" if predicate(*values) else "contradicts_external_case",
                        note,
                        kashi_ids,
                        field,
                        values,
                    )
                )
            else:
                dispositions.append(
                    _disposition(
                        "pipeline_source_mismatch",
                        note,
                        kashi_ids,
                        field,
                        values,
                    )
                )
    else:
        dispositions.append(
            _disposition(
                "pipeline_source_mismatch",
                "One or both Kashi videos could not complete the explicit ordered-media pipeline.",
                kashi_ids,
            )
        )

    corner_ids = [f"windmill-{size}" for size in (24,22,20,18,16,14)]
    corner = [by_id.get(sample_id) for sample_id in corner_ids]
    if all(row and row.get("status") == "measured" for row in corner):
        dispositions.append(
            _disposition(
                "not_applicable_measuring_different_percept",
                "The corner/windmill sweep is a geometry/character experiment, not a monotonic goodness label. Static diagonal-arm outputs are reported without converting 24% -> 14% into quality.",
                corner_ids,
                "diagonal_arm_geometry",
            )
        )
    else:
        dispositions.append(
            _disposition(
                "pipeline_source_mismatch",
                "At least one corner/windmill preview could not complete static normalization; no synthetic motion was created.",
                corner_ids,
            )
        )
    return dispositions


def _markdown(result):
    lines = [
        "# PriceScope external benchmark run",
        "",
        "Blind external run against the normalized #64 manifest. No thresholds or descriptor definitions were tuned to these labels.",
        "",
        "## Samples",
        "",
        "| sample | mode | status | note |",
        "|---|---|---|---|",
    ]
    for row in result["samples"]:
        note = row.get("error") or ""
        lines.append(
            f"| {row['sample_id']} | {row.get('analysis_mode', row.get('planned_mode'))} | {row['status']} | {note.replace('|', '/')} |"
        )
    lines += ["", "## Dispositions", ""]
    for item in result["dispositions"]:
        observed = ""
        if item.get("observed") is not None:
            observed = f" Observed: {item['observed']}."
        metric = f" **{item['metric']}**:" if item.get("metric") else ""
        lines.append(f"- **{item['kind']}**{metric} {item['note']}{observed}")
    lines += [
        "",
        "## Interpretation boundary",
        "",
        "These are falsification checks against external expert/forum interpretations, not ground-truth cut grades. A contradiction is preserved as evidence; activity/switching/flash scale are not automatically quality axes, and static forum previews are never converted into fake motion.",
        "",
    ]
    return "\n".join(lines)


def run(manifest_path, archive_root, output, sample_ids=PRIMARY_SAMPLE_IDS):
    manifest_path = Path(manifest_path)
    archive_root = Path(archive_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"expected {MANIFEST_SCHEMA}")
    selected = {sample_id for sample_id in sample_ids}
    samples = [row for row in manifest["samples"] if row["sample_id"] in selected]
    missing = selected - {row["sample_id"] for row in samples}
    if missing:
        raise ValueError(f"benchmark sample ids missing from manifest: {sorted(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    rows = []

    with tempfile.TemporaryDirectory(prefix="sparkles-external-") as temporary:
        work = Path(temporary)
        for sample in samples:
            sample_id = sample["sample_id"]
            planned = _mode(sample)
            row = {
                "sample_id": sample_id,
                "group_id": sample.get("group_id"),
                "source_type": sample.get("source_type"),
                "evidence_type": sample.get("evidence_type"),
                "labels": sample.get("labels", []),
                "planned_mode": planned,
                "status": "not_run",
            }
            if planned == "source_mismatch":
                row.update(
                    status="pipeline_source_mismatch",
                    error="no archived media with an explicit supported adapter",
                )
                rows.append(row)
                continue
            try:
                source = work / sample_id / "source"
                source.parent.mkdir(parents=True, exist_ok=True)
                source_manifest, _ = _prepare_source(
                    sample, archive_root, source
                )
                sample_output = output / "per-sample" / sample_id
                sample_work = work / sample_id / "analysis"
                if planned == "static":
                    measured = _run_static(source, sample_output, sample_work)
                else:
                    measured = _run_dynamic(
                        source,
                        sample_output,
                        sample_work,
                        faceup=(planned == "dynamic_faceup"),
                    )
                row.update(status="measured", **measured)
                row["source_contract"] = {
                    "schema_version": source_manifest["schema_version"],
                    "source_frame_count": source_manifest["source_frame_count"],
                    "sequence_complete": source_manifest["sequence_complete"],
                    "dimensions": source_manifest["dimensions"],
                }
            except Exception as exc:
                row.update(
                    status="pipeline_source_mismatch",
                    error=f"{type(exc).__name__}: {exc}",
                )
            rows.append(row)

    result = {
        "schema_version": SCHEMA,
        "benchmark_manifest": str(manifest_path),
        "archive_root": str(archive_root),
        "sample_ids": list(sample_ids),
        "samples": rows,
    }
    result["dispositions"] = build_dispositions(rows)
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    (output / "comparison.md").write_text(_markdown(result) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/360/external-benchmark/pricescope/benchmark-manifest.json"),
    )
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="repeat to override the primary #64 sample set",
    )
    args = parser.parse_args(argv)
    result = run(
        args.manifest,
        args.archive_root,
        args.output,
        tuple(args.sample_ids) if args.sample_ids else PRIMARY_SAMPLE_IDS,
    )
    measured = sum(row["status"] == "measured" for row in result["samples"])
    print(f"{measured}/{len(result['samples'])} external samples measured")
    print((args.output / "comparison.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
