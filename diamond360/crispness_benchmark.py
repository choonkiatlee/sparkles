"""Run static tier-boundary crispness validation on registered Asscher 360 intervals."""
from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import activation_benchmark as ab
from . import asscher_steps as steps
from . import crispness as c
from . import pipeline

SCHEMA = "diamond360-static-crispness-benchmark/1"
CORE_INDICES = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE_INDICES = list(range(240,256)) + list(range(0,17))


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _accepted_records(processed, indices, wrap):
    metadata = json.loads((Path(processed) / "sequence.json").read_text())
    selected, excluded = ab._select_records(metadata, list(indices), wrap)
    accepted = [record for record in selected if record is not None]
    if len(accepted) < 6:
        raise ValueError(
            "Crispness cross-fit requires at least six accepted registered frames"
        )
    return metadata, accepted, excluded


def _frame_arrays(
    processed,
    records,
    perturbation=None,
    angle_count=96,
    radial_samples=160,
):
    processed = Path(processed)
    ray_edges, ray_supports, sectors = [], [], []
    rgbs, masks, source_paths = [], [], []
    u = angles = None
    for record in records:
        with np.load(processed / record["photometry_path"]) as data:
            brightness = np.asarray(
                data["encoded_brightness"], float
            ).copy()
            valid = np.asarray(data["valid_mask"], bool).copy()
        if perturbation is not None:
            brightness = c.apply_perturbation(brightness, perturbation)
        mask = (
            np.asarray(
                Image.open(
                    processed / record["registration"]["mask_path"]
                ).convert("L")
            )
            > 0
        )
        polar = steps.polar_profiles(
            brightness,
            mask,
            valid,
            angle_count,
            radial_samples,
        )
        edge = steps.edge_evidence(
            polar["profiles"],
            polar["support"],
        )
        ray_edges.append(edge)
        ray_supports.append(polar["support"])
        sectors.append(
            steps.sector_evidence(edge, polar["angles"])
        )
        u, angles = polar["u"], polar["angles"]
        masks.append(mask)
        rgbs.append(
            np.asarray(
                Image.open(
                    processed / record["registration"]["rgb_path"]
                ).convert("RGB")
            )
        )
        source_paths.append(
            record.get("camera_original_path")
            or record["registration"]["rgb_path"]
        )
    return {
        "ray_edges": np.stack(ray_edges),
        "ray_supports": np.stack(ray_supports),
        "sectors": np.stack(sectors),
        "u": u,
        "angles": angles,
        "masks": masks,
        "rgbs": rgbs,
        "source_paths": source_paths,
    }


def _serialise_templates(templates):
    output = []
    for item in templates:
        row = {k: v for k, v in item.items() if k != "controls"}
        row["controls"] = [
            steps._json_control(control)
            for control in (item.get("controls") or [])
        ]
        output.append(row)
    return output


def _geometry_shift(baseline_templates, candidate_templates):
    rows = []
    for base, candidate in zip(
        baseline_templates,
        candidate_templates,
    ):
        base_controls = base.get("controls") or []
        test_controls = candidate.get("controls") or []
        if len(base_controls) != 3 or len(test_controls) != 3:
            rows.append(
                {
                    "fold": base["fold"],
                    "status": "unavailable",
                    "boundaries": {},
                }
            )
            continue
        boundaries = {}
        for name, left, right in zip(
            c.BOUNDARIES,
            base_controls,
            test_controls,
        ):
            boundaries[name] = {
                "baseline_global_u": float(left["global_u"]),
                "candidate_global_u": float(right["global_u"]),
                "absolute_shift_u": float(
                    abs(right["global_u"] - left["global_u"])
                ),
            }
        rows.append(
            {
                "fold": base["fold"],
                "status": candidate.get("status"),
                "boundaries": boundaries,
            }
        )
    return rows


def _full_template_diagnostic(sectors, u):
    template = steps.discover_template(sectors, u)
    out = {
        "status": template["status"],
        "reason": template.get("reason"),
        "boundaries": {},
        "edge_alignment": [],
    }
    if template.get("controls"):
        out["boundaries"] = {
            name: steps._json_control(control)
            for name, control in zip(
                c.BOUNDARIES,
                template["controls"],
            )
        }
        out["edge_alignment"] = steps.boundary_alignment(
            sectors,
            u,
            template["controls"],
        )
    return out


def _candidate_events(result):
    events = []
    for pos, frame in enumerate(result["baseline"]["frames"]):
        if frame is None:
            continue
        for boundary, row in frame.items():
            events.append(
                {
                    "position": pos,
                    "source_index": result["accepted_indices"][pos],
                    "boundary": boundary,
                    "strength": row.get("median_peak_z"),
                    "continuity": row.get("supported_fraction"),
                    "gap": row.get("longest_gap_fraction"),
                    "position_mad": row.get("offset_mad_u"),
                }
            )
    return events


def select_evidence(result):
    events = _candidate_events(result)
    finite = [
        event
        for event in events
        if event["strength"] is not None
    ]
    strongest = (
        max(
            finite,
            key=lambda event: (
                event["strength"],
                -event["position"],
            ),
        )
        if finite
        else None
    )
    weakest = (
        min(
            finite,
            key=lambda event: (
                (
                    event["continuity"]
                    if event["continuity"] is not None
                    else 2
                ),
                event["strength"],
                event["position"],
            ),
        )
        if finite
        else None
    )
    continuity = (
        max(
            events,
            key=lambda event: (
                event["gap"]
                if event["gap"] is not None
                else -1,
                -event["position"],
            ),
        )
        if events
        else None
    )

    pipeline_event = None
    best = -1.0
    for kind, sensitivity in result["pipeline_sensitivity"].items():
        for pos, (base_frame, test_frame) in enumerate(
            zip(
                result["baseline"]["frames"],
                sensitivity["scored"]["frames"],
            )
        ):
            if base_frame is None or test_frame is None:
                continue
            for boundary in c.BOUNDARIES:
                base = base_frame[boundary]
                test = test_frame[boundary]
                terms = []
                if (
                    base.get("median_peak_z") not in (None, 0)
                    and test.get("median_peak_z") is not None
                ):
                    terms.append(
                        abs(
                            test["median_peak_z"]
                            - base["median_peak_z"]
                        )
                        / abs(base["median_peak_z"])
                    )
                if (
                    base.get("supported_fraction") is not None
                    and test.get("supported_fraction") is not None
                ):
                    terms.append(
                        abs(
                            test["supported_fraction"]
                            - base["supported_fraction"]
                        )
                    )
                score = max(terms, default=-1)
                if score > best:
                    best = score
                    pipeline_event = {
                        "position": pos,
                        "source_index": result["accepted_indices"][pos],
                        "boundary": boundary,
                        "perturbation": kind,
                        "sensitivity_score": float(score),
                    }
    return {
        "strongest_boundary": strongest,
        "weakest_or_ambiguous_boundary": weakest,
        "continuity_failure": continuity,
        "pipeline_sensitivity": pipeline_event,
    }


def measure_stone(processed, indices, wrap=True):
    processed = Path(processed).resolve()
    metadata, records, excluded = _accepted_records(
        processed,
        indices,
        wrap,
    )
    baseline_arrays = _frame_arrays(processed, records)
    templates = c.build_crossfit_templates(
        baseline_arrays["sectors"],
        baseline_arrays["u"],
    )
    baseline = c.score_crossfit(
        baseline_arrays["ray_edges"],
        baseline_arrays["ray_supports"],
        baseline_arrays["u"],
        baseline_arrays["angles"],
        templates,
    )

    pipeline_sensitivity = {}
    for kind in c.PERTURBATIONS:
        transformed = _frame_arrays(
            processed,
            records,
            perturbation=kind,
        )
        scored = c.score_crossfit(
            transformed["ray_edges"],
            transformed["ray_supports"],
            transformed["u"],
            transformed["angles"],
            templates,
            include_ray_evidence=False,
        )
        rediscovered = c.build_crossfit_templates(
            transformed["sectors"],
            transformed["u"],
        )
        pipeline_sensitivity[kind] = {
            "summary_delta": c.compare_summaries(
                baseline["summary"],
                scored["summary"],
            ),
            "geometry_shift": _geometry_shift(
                templates,
                rediscovered,
            ),
            "rediscovered_templates": _serialise_templates(
                rediscovered
            ),
            "scored": scored,
        }

    result = {
        "schema_version": SCHEMA,
        "descriptor_schema": c.SCHEMA,
        "requested_indices": list(indices),
        "accepted_indices": [
            record["source_index"] for record in records
        ],
        "excluded": excluded,
        "wrap_explicit": bool(wrap),
        "source_frame_count": metadata.get("source_frame_count"),
        "definition": {
            "geometry": (
                "#19-compatible ordered boundaries, discovered on "
                "alternating training frames and scored only on "
                "held-out frames"
            ),
            "strength": (
                "median robust z-score of the strongest local radial "
                "edge near the expected boundary"
            ),
            "continuity": (
                "fraction of 96 rays with local edge z >= 0.8 plus "
                "longest circular unsupported angular gap"
            ),
            "position": (
                "robust MAD of local peak radial offset from the "
                "expected #19 boundary"
            ),
            "pipeline_tests": list(c.PERTURBATIONS),
            "non_goal": (
                "no cut grade, light-return/fire inference, or "
                "combined crispness score"
            ),
        },
        "upstream_validity": ab._upstream_validity(
            records,
            excluded,
        ),
        "crossfit_templates": _serialise_templates(templates),
        "baseline": baseline,
        "full_template_diagnostic": _full_template_diagnostic(
            baseline_arrays["sectors"],
            baseline_arrays["u"],
        ),
        "pipeline_sensitivity": pipeline_sensitivity,
    }
    result["evidence_selection"] = select_evidence(result)
    result["_render"] = {
        "processed": str(processed),
        "records": records,
        "arrays": baseline_arrays,
        "templates": templates,
    }
    return result


def _fold_for_position(templates, position):
    for template in templates:
        if position in template["holdout_positions"]:
            return template
    return None


def _overlay_boundary(
    rgb,
    mask,
    angles,
    control,
    frame_row,
):
    image = Image.fromarray(np.asarray(rgb, np.uint8)).copy()
    draw = ImageDraw.Draw(image)
    _, outlines, _, _ = steps._ray_geometry(
        mask,
        angles,
        radial_samples=32,
    )
    targets = steps._periodic_boundary(
        angles,
        control["sector_u"],
    )
    h, w = mask.shape
    cy, cx = (h - 1) / 2, (w - 1) / 2
    expected = []
    observed = []
    rays = frame_row.get("rays", [])
    for i, angle in enumerate(angles):
        radius = targets[i] * outlines[i]
        expected.append(
            (
                cx + math.cos(angle) * radius,
                cy + math.sin(angle) * radius,
            )
        )
        ray = rays[i] if i < len(rays) else None
        if ray is not None and ray.get("supported"):
            radius = ray["peak_u"] * outlines[i]
            observed.append(
                (
                    cx + math.cos(angle) * radius,
                    cy + math.sin(angle) * radius,
                )
            )
    if expected:
        draw.line(
            expected + [expected[0]],
            fill="white",
            width=2,
        )
    for x, y in observed:
        draw.ellipse(
            (x - 1.5, y - 1.5, x + 1.5, y + 1.5),
            fill="black",
        )
    return image


def _panel(source, overlay, title, destination):
    source = source.copy()
    overlay = overlay.copy()
    source.thumbnail((520, 480))
    overlay.thumbnail((520, 480))
    height = max(source.height, overlay.height) + 50
    canvas = Image.new("RGB", (1060, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")
    draw.text((10, 28), "original source", fill="black")
    draw.text(
        (540, 28),
        "registered diagnostic: expected boundary (white), "
        "supported local peaks (black)",
        fill="black",
    )
    canvas.paste(source, (10, 48))
    canvas.paste(overlay, (540, 48))
    canvas.save(destination, quality=90)


def render_selected_evidence(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    render = result["_render"]
    processed = Path(render["processed"])
    arrays = render["arrays"]
    templates = render["templates"]
    files = {}
    for label, event in result["evidence_selection"].items():
        if event is None:
            continue
        pos = event["position"]
        boundary = event["boundary"]
        template = _fold_for_position(templates, pos)
        if template is None or not template.get("controls"):
            continue
        boundary_index = c.BOUNDARIES.index(boundary)
        row = result["baseline"]["frames"][pos][boundary]
        overlay = _overlay_boundary(
            arrays["rgbs"][pos],
            arrays["masks"][pos],
            arrays["angles"],
            template["controls"][boundary_index],
            row,
        )
        source = Image.open(
            processed / arrays["source_paths"][pos]
        ).convert("RGB")
        destination = output / f"{label}.jpg"
        _panel(
            source,
            overlay,
            (
                f"source {event['source_index']} · "
                f"{boundary} · {label}"
            ),
            destination,
        )
        files[label] = destination.name
    return files


def write_stone_outputs(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence_files = render_selected_evidence(
        result,
        output / "evidence",
    )
    clean = {
        key: value
        for key, value in result.items()
        if key != "_render"
    }
    clean["evidence_files"] = evidence_files
    (output / "crispness.json").write_text(
        json.dumps(
            _jsonable(clean),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    return clean


def _human_crispness(path):
    if path is None or not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text())
    output = {}
    for observation in payload.get("observations", []):
        if (
            observation.get("concept")
            == "static_geometric_crispness"
        ):
            output.setdefault(
                observation["certificate"],
                [],
            ).append(
                {
                    "id": observation.get("id"),
                    "role": observation.get("role"),
                    "summary": observation.get("summary"),
                    "source_frames": observation.get(
                        "source_frames",
                        [],
                    ),
                }
            )
    return output


def _compact_window(result):
    return {
        "summary": result["baseline"]["summary"],
        "full_template_diagnostic": result[
            "full_template_diagnostic"
        ],
        "pipeline_summary_delta": {
            kind: item["summary_delta"]
            for kind, item in result[
                "pipeline_sensitivity"
            ].items()
        },
        "pipeline_geometry_shift": {
            kind: item["geometry_shift"]
            for kind, item in result[
                "pipeline_sensitivity"
            ].items()
        },
        "evidence_selection": result["evidence_selection"],
        "upstream_validity": result["upstream_validity"],
    }


def run_source_benchmark(
    source_root,
    output,
    bundle_manifest,
    human_observations=None,
):
    source_root = Path(source_root).resolve()
    output = Path(output).resolve()
    manifest = json.loads(Path(bundle_manifest).read_text())
    human = _human_crispness(human_observations)
    output.mkdir(parents=True, exist_ok=True)
    stones = []

    with tempfile.TemporaryDirectory(
        prefix="sparkles-crispness-"
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = item["certificate"]
            source = source_root / certificate
            order_manifest = source / "source-manifest.json"
            processed = work / certificate / "processed"
            processed.parent.mkdir(parents=True, exist_ok=True)
            pipeline.run(
                source,
                processed,
                order_manifest,
                gain=1.0,
                diagnostic_indices=CORE_INDICES,
                accept_review=True,
            )
            core = measure_stone(
                processed,
                CORE_INDICES,
                wrap=True,
            )
            wide = measure_stone(
                processed,
                WIDE_INDICES,
                wrap=True,
            )
            stone_output = output / "per-stone" / certificate
            core_clean = write_stone_outputs(
                core,
                stone_output / "core",
            )
            wide_clean = {
                key: value
                for key, value in wide.items()
                if key != "_render"
            }
            (stone_output / "wide.json").write_text(
                json.dumps(
                    _jsonable(wide_clean),
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            )
            stones.append(
                {
                    "certificate": certificate,
                    "pipeline": (
                        "Workshop"
                        if certificate == "IGI-LG756520111"
                        else "Diajewel"
                    ),
                    "human_static_crispness": human.get(
                        certificate,
                        [],
                    ),
                    "core": _compact_window(core_clean),
                    "wide": _compact_window(wide_clean),
                }
            )

    summary = {
        "schema_version": SCHEMA,
        "descriptor_schema": c.SCHEMA,
        "core_indices": CORE_INDICES,
        "wide_indices": WIDE_INDICES,
        "stones": stones,
        "limitations": [
            (
                "Four stones can falsify unstable definitions "
                "but cannot calibrate aesthetic thresholds."
            ),
            (
                "The vendor comparison is unbalanced: three "
                "Diajewel stones and one Workshop stone."
            ),
            (
                "Pipeline perturbations are controlled stress "
                "tests, not exact reconstructions of vendor "
                "image pipelines."
            ),
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(
            _jsonable(summary),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    rows = []
    for stone in stones:
        for boundary, metrics in stone["core"]["summary"].items():
            rows.append(
                {
                    "certificate": stone["certificate"],
                    "pipeline": stone["pipeline"],
                    "boundary": boundary,
                    **metrics,
                }
            )
    with (output / "comparison.csv").open(
        "w",
        newline="",
    ) as handle:
        fieldnames = (
            list(rows[0])
            if rows
            else ["certificate"]
        )
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=Path(
            "docs/360/benchmark/source-bundles.json"
        ),
    )
    parser.add_argument(
        "--human-observations",
        type=Path,
        default=Path(
            "docs/360/calibration/human-observations.json"
        ),
    )
    args = parser.parse_args()
    run_source_benchmark(
        args.source_root,
        args.output,
        args.bundle_manifest,
        args.human_observations,
    )
    print(f"wrote crispness benchmark -> {args.output}")


if __name__ == "__main__":
    main()
