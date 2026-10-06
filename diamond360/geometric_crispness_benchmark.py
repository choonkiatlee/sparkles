"""Benchmark normalized tier edges and diagonal-arm legibility for issue #55."""
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
from . import crispness as old_crispness
from . import diagonal_arms as arms
from . import normalized_geometry as ng
from . import normalized_tier_edges as tier
from . import pipeline

SCHEMA = "diamond360-geometric-crispness-benchmark/1"
CORE_INDICES = [
    248, 249, 250, 251, 252, 253, 254, 255,
    0, 1, 2, 3, 4, 5, 6, 7, 8,
]
WIDE_INDICES = (
    list(range(240, 256))
    + list(range(0, 17))
)


def _jsonable(value):
    if isinstance(value, dict):
        return {
            str(k): _jsonable(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [
            _jsonable(v)
            for v in value.tolist()
        ]
    if isinstance(
        value, (np.floating, float)
    ):
        value = float(value)
        return (
            value
            if math.isfinite(value)
            else None
        )
    if (
        isinstance(
            value, (np.integer, int)
        )
        and not isinstance(value, bool)
    ):
        return int(value)
    if isinstance(
        value, (np.bool_, bool)
    ):
        return bool(value)
    return value


def _accepted_records(
    processed, indices, wrap
):
    metadata = json.loads(
        (
            Path(processed)
            / "sequence.json"
        ).read_text()
    )
    selected, excluded = (
        ab._select_records(
            metadata,
            list(indices),
            wrap,
        )
    )
    accepted = [
        record
        for record in selected
        if record is not None
    ]
    if len(accepted) < 6:
        raise ValueError(
            "geometric crispness benchmark "
            "requires at least six "
            "accepted frames"
        )
    return metadata, accepted, excluded


def _load_frame(
    processed,
    record,
    perturbation=None,
):
    processed = Path(processed)
    with np.load(
        processed
        / record["photometry_path"]
    ) as data:
        brightness = np.asarray(
            data["encoded_brightness"],
            float,
        ).copy()
        valid = np.asarray(
            data["valid_mask"],
            bool,
        ).copy()
    mask = (
        np.asarray(
            Image.open(
                processed
                / record["registration"][
                    "mask_path"
                ]
            ).convert("L")
        )
        > 0
    )
    if perturbation is not None:
        brightness = (
            old_crispness.apply_perturbation(
                brightness,
                perturbation,
            )
        )
    return ng.normalize_frame(
        brightness,
        mask,
        valid,
    )


def _step_diagnostic(sectors, u):
    template = steps.discover_template(
        np.asarray(sectors),
        np.asarray(u),
    )
    output = {
        "status": template["status"],
        "reason": template.get("reason"),
        "edge_alignment": [],
    }
    if template.get("controls"):
        output["edge_alignment"] = (
            steps.boundary_alignment(
                np.asarray(sectors),
                np.asarray(u),
                template["controls"],
            )
        )
        output["boundaries"] = {
            name: steps._json_control(
                control
            )
            for name, control in zip(
                steps.BOUNDARIES,
                template["controls"],
            )
        }
    return output


def _measure_frames(
    processed,
    records,
    perturbation=None,
    include_evidence=False,
):
    tier_frames = []
    arm_frames = []
    sectors = []
    render = []
    u = angles = None

    for record in records:
        normalized = _load_frame(
            processed,
            record,
            perturbation,
        )
        polar = steps.polar_profiles(
            normalized["brightness"],
            normalized["mask"],
            normalized["valid_mask"],
            angle_count=96,
            radial_samples=240,
        )
        tier_frame = tier.measure_frame(
            polar["profiles"],
            polar["support"],
            polar["u"],
            polar["angles"],
            include_rays=include_evidence,
        )
        arm_frame = arms.measure_frame(
            normalized["brightness"],
            normalized["mask"],
            normalized["valid_mask"],
            include_trace=include_evidence,
        )
        edge = steps.edge_evidence(
            polar["profiles"],
            polar["support"],
        )
        sectors.append(
            steps.sector_evidence(
                edge,
                polar["angles"],
            )
        )
        tier_frames.append(tier_frame)
        arm_frames.append(arm_frame)
        u = polar["u"]
        angles = polar["angles"]

        if include_evidence:
            render.append(
                {
                    "normalized":
                        normalized,
                    "record": record,
                }
            )

    return {
        "tier_frames": tier_frames,
        "tier_summary":
            tier.summarize_frames(
                tier_frames
            ),
        "arm_frames": arm_frames,
        "arm_summary":
            arms.summarize_frames(
                arm_frames
            ),
        "step_diagnostic":
            _step_diagnostic(
                sectors, u
            ),
        "u": u,
        "angles": angles,
        "render": render,
    }


def _relative_change(base, test):
    if base is None or test is None:
        return None
    base = float(base)
    test = float(test)
    if (
        not math.isfinite(base)
        or not math.isfinite(test)
        or abs(base) < 1e-9
    ):
        return None
    return float(
        abs(test-base) / abs(base)
    )


def _absolute_change(base, test):
    if base is None or test is None:
        return None
    return float(
        abs(float(test)-float(base))
    )


def _summary_delta(base, test):
    tier_delta = {}
    for name in tier.BOUNDARIES:
        left = base[
            "tier_summary"
        ][name]
        right = test[
            "tier_summary"
        ][name]
        tier_delta[name] = {
            "transition_width_relative":
                _relative_change(
                    left[
                        "median_transition_width_u"
                    ],
                    right[
                        "median_transition_width_u"
                    ],
                ),
            "confidence_absolute":
                _absolute_change(
                    left["median_confidence"],
                    right["median_confidence"],
                ),
            "longest_gap_absolute":
                _absolute_change(
                    left[
                        "median_longest_gap_fraction"
                    ],
                    right[
                        "median_longest_gap_fraction"
                    ],
                ),
            "fragment_count_absolute":
                _absolute_change(
                    left[
                        "median_fragment_count"
                    ],
                    right[
                        "median_fragment_count"
                    ],
                ),
            "position_residual_relative":
                _relative_change(
                    left[
                        "median_position_residual_mad_u"
                    ],
                    right[
                        "median_position_residual_mad_u"
                    ],
                ),
        }

    arm_delta = {}
    for name in arms.ARM_NAMES:
        left = base[
            "arm_summary"
        ]["arms"][name]
        right = test[
            "arm_summary"
        ]["arms"][name]
        arm_delta[name] = {
            "visibility_absolute":
                _absolute_change(
                    left[
                        "median_visibility_confidence"
                    ],
                    right[
                        "median_visibility_confidence"
                    ],
                ),
            "orientation_absolute":
                _absolute_change(
                    left[
                        "median_orientation_alignment"
                    ],
                    right[
                        "median_orientation_alignment"
                    ],
                ),
            "straightness_relative":
                _relative_change(
                    left[
                        "median_straightness_mad_radius"
                    ],
                    right[
                        "median_straightness_mad_radius"
                    ],
                ),
            "frame_stability_absolute_deg":
                _absolute_change(
                    left[
                        "angular_offset_frame_mad_deg"
                    ],
                    right[
                        "angular_offset_frame_mad_deg"
                    ],
                ),
        }
    geometry_delta = {
        "opposing_axis_misalignment_absolute_deg": {
            pair: _absolute_change(
                base["arm_summary"][
                    "opposing_axis_misalignment_deg"
                ].get(pair),
                test["arm_summary"][
                    "opposing_axis_misalignment_deg"
                ].get(pair),
            )
            for pair in ("SE_NW", "SW_NE")
        },
        "four_arm_spacing_error_absolute_deg":
            _absolute_change(
                base["arm_summary"].get(
                    "median_four_arm_spacing_error_mad_deg"
                ),
                test["arm_summary"].get(
                    "median_four_arm_spacing_error_mad_deg"
                ),
            ),
    }
    return {
        "tier": tier_delta,
        "arms": arm_delta,
        "arm_geometry": geometry_delta,
    }


def _upstream_validity(records):
    reasons = []
    for record in records:
        status = record.get(
            "segmentation", {}
        ).get("status")
        if status == "review":
            reasons.append(
                "source_"
                + str(
                    record["source_index"]
                )
                + ":segmentation_review"
            )
    return {
        "status":
            "review" if reasons else "ok",
        "reasons": reasons,
    }


def _event_candidates(result):
    events = {
        "tier": [],
        "arms": [],
    }
    for pos, frame in enumerate(
        result["baseline"]["tier_frames"]
    ):
        for boundary, row in (
            frame.items()
        ):
            events["tier"].append(
                {
                    "position": pos,
                    "source_index":
                        result[
                            "accepted_indices"
                        ][pos],
                    "boundary": boundary,
                    "width": row[
                        "median_transition_width_u"
                    ],
                    "confidence": row[
                        "median_confidence"
                    ],
                    "gap": row[
                        "longest_low_confidence_gap_fraction"
                    ],
                    "fragments": row[
                        "low_confidence_component_count"
                    ],
                    "position_mad": row[
                        "position_residual_mad_u"
                    ],
                }
            )

    for pos, frame in enumerate(
        result["baseline"]["arm_frames"]
    ):
        for name, row in (
            frame["arms"].items()
        ):
            events["arms"].append(
                {
                    "position": pos,
                    "source_index":
                        result[
                            "accepted_indices"
                        ][pos],
                    "arm": name,
                    "visibility": row[
                        "median_confidence"
                    ],
                    "orientation": row[
                        "median_orientation_alignment"
                    ],
                    "gap": row[
                        "longest_low_confidence_gap_fraction"
                    ],
                    "straightness": row[
                        "trajectory_straightness_mad_radius"
                    ],
                }
            )
    return events


def select_evidence(result):
    events = _event_candidates(result)
    tier_rows = [
        row
        for row in events["tier"]
        if row["width"] is not None
    ]
    arm_rows = [
        row
        for row in events["arms"]
        if row["visibility"] is not None
    ]
    straight_rows = [
        row
        for row in arm_rows
        if row["straightness"] is not None
    ]
    return {
        "tier_narrowest": (
            min(
                tier_rows,
                key=lambda row: (
                    row["width"],
                    -row["confidence"],
                ),
            )
            if tier_rows
            else None
        ),
        "tier_widest": (
            max(
                tier_rows,
                key=lambda row: (
                    row["width"],
                    -row["confidence"],
                ),
            )
            if tier_rows
            else None
        ),
        "tier_longest_gap": (
            max(
                tier_rows,
                key=lambda row: row["gap"],
            )
            if tier_rows
            else None
        ),
        "tier_most_fragmented": (
            max(
                tier_rows,
                key=lambda row: (
                    row["fragments"],
                    row["gap"],
                ),
            )
            if tier_rows
            else None
        ),
        "arm_highest_visibility": (
            max(
                arm_rows,
                key=lambda row:
                    row["visibility"],
            )
            if arm_rows
            else None
        ),
        "arm_longest_gap": (
            max(
                arm_rows,
                key=lambda row:
                    row["gap"],
            )
            if arm_rows
            else None
        ),
        "arm_least_straight": (
            max(
                straight_rows,
                key=lambda row:
                    row["straightness"],
            )
            if straight_rows
            else None
        ),
    }


def measure_stone(
    processed,
    indices,
    wrap=True,
):
    _, records, excluded = (
        _accepted_records(
            processed,
            indices,
            wrap,
        )
    )
    baseline = _measure_frames(
        processed,
        records,
        include_evidence=True,
    )
    sensitivity = {}
    for kind in (
        old_crispness.PERTURBATIONS
    ):
        candidate = _measure_frames(
            processed,
            records,
            perturbation=kind,
            include_evidence=False,
        )
        sensitivity[kind] = {
            "tier_summary":
                candidate[
                    "tier_summary"
                ],
            "arm_summary":
                candidate[
                    "arm_summary"
                ],
            "summary_delta":
                _summary_delta(
                    baseline,
                    candidate,
                ),
        }

    result = {
        "schema_version": SCHEMA,
        "tier_schema": tier.SCHEMA,
        "arm_schema": arms.SCHEMA,
        "normalization":
            ng.specification(),
        "requested_indices":
            list(indices),
        "accepted_indices": [
            int(record["source_index"])
            for record in records
        ],
        "excluded": excluded,
        "upstream_validity":
            _upstream_validity(records),
        "baseline": {
            key: value
            for key, value
            in baseline.items()
            if key not in (
                "render", "u", "angles"
            )
        },
        "pipeline_sensitivity":
            sensitivity,
        "contract": {
            "tier_semantics": (
                "#19 BOUNDARY_WINDOWS; "
                "the held-out frame "
                "estimates local position "
                "only inside the declared "
                "semantic zone"
            ),
            "headline_tier_quantity": (
                "edge transition width in "
                "silhouette-normalized "
                "radius units"
            ),
            "headline_arm_quantities": (
                "visibility/continuity, "
                "orientation coherence, "
                "trajectory straightness, "
                "frame stability"
            ),
            "combined_score": "none",
        },
    }
    result["evidence_selection"] = (
        select_evidence(result)
    )
    result["_render"] = {
        "processed":
            str(Path(processed)),
        "frames":
            baseline["render"],
        "angles":
            baseline["angles"],
    }
    return result


def _normalized_rgb(brightness):
    values = np.asarray(
        brightness, float
    )
    finite = values[
        np.isfinite(values)
        & (values > 0)
    ]
    scale = (
        float(
            np.quantile(finite, .99)
        )
        if finite.size
        else 1.0
    )
    gray = np.clip(
        values
        / max(scale, 1e-6)
        * 255,
        0,
        255,
    ).astype(np.uint8)
    return np.repeat(
        gray[..., None], 3, axis=2
    )


def _tier_overlay(result, event):
    pos = event["position"]
    render = result[
        "_render"
    ]["frames"][pos]
    normalized = render["normalized"]
    image = Image.fromarray(
        _normalized_rgb(
            normalized["brightness"]
        )
    )
    draw = ImageDraw.Draw(image)
    mask = normalized["mask"]
    angles = np.asarray(
        result["_render"]["angles"]
    )
    row = result["baseline"][
        "tier_frames"
    ][pos][event["boundary"]]
    _, outlines, _, _ = (
        steps._ray_geometry(
            mask,
            angles,
            radial_samples=32,
        )
    )
    h, w = mask.shape
    cy, cx = (
        (h-1)/2,
        (w-1)/2,
    )
    points = []
    for i, ray in enumerate(
        row.get("rays", [])
    ):
        if (
            ray is None
            or ray.get("position_u")
            is None
        ):
            continue
        radius = (
            ray["position_u"]
            * outlines[i]
        )
        points.append(
            (
                cx
                + math.cos(
                    angles[i]
                )
                * radius,
                cy
                + math.sin(
                    angles[i]
                )
                * radius,
            )
        )
    if len(points) > 2:
        draw.line(
            points + [points[0]],
            fill="white",
            width=2,
        )
    return image


def _arm_overlay(result, event):
    pos = event["position"]
    render = result[
        "_render"
    ]["frames"][pos]
    normalized = render["normalized"]
    image = Image.fromarray(
        _normalized_rgb(
            normalized["brightness"]
        )
    )
    draw = ImageDraw.Draw(image)
    mask = normalized["mask"]
    yy, xx = np.nonzero(mask)
    cy = float(np.mean(yy))
    cx = float(np.mean(xx))
    radius = (
        ng.effective_diameter(mask)
        / 2
    )
    name = event["arm"]
    arm_idx = arms.ARM_NAMES.index(name)
    angle = arms.ARM_ANGLES[arm_idx]
    ca, sa = (
        math.cos(angle),
        math.sin(angle),
    )
    px, py = -sa, ca
    trace = result["baseline"][
        "arm_frames"
    ][pos]["arms"][name].get(
        "trace", []
    )
    points = []
    for row in trace:
        if row is None:
            continue
        r = (
            row["radius_fraction"]
            * radius
        )
        off = (
            row[
                "offset_radius_fraction"
            ]
            * radius
        )
        points.append(
            (
                cx + ca*r + px*off,
                cy + sa*r + py*off,
            )
        )
    if len(points) > 1:
        draw.line(
            points,
            fill="white",
            width=2,
        )
    return image


def _all_tier_overlay(result, pos):
    render = result["_render"]["frames"][pos]
    normalized = render["normalized"]
    image = Image.fromarray(
        _normalized_rgb(normalized["brightness"])
    )
    draw = ImageDraw.Draw(image)
    mask = normalized["mask"]
    angles = np.asarray(
        result["_render"]["angles"]
    )
    _, outlines, _, _ = (
        steps._ray_geometry(
            mask,
            angles,
            radial_samples=32,
        )
    )
    h, w = mask.shape
    cy, cx = (h-1)/2, (w-1)/2
    for boundary in tier.BOUNDARIES:
        row = result["baseline"][
            "tier_frames"
        ][pos][boundary]
        points = []
        for i, ray in enumerate(
            row.get("rays", [])
        ):
            if (
                ray is None
                or ray.get("position_u")
                is None
            ):
                continue
            radius = (
                ray["position_u"]
                * outlines[i]
            )
            points.append(
                (
                    cx
                    + math.cos(angles[i])
                    * radius,
                    cy
                    + math.sin(angles[i])
                    * radius,
                )
            )
        if len(points) > 2:
            draw.line(
                points + [points[0]],
                fill="white",
                width=1,
            )
    return image


def _all_arm_overlay(result, pos):
    render = result["_render"]["frames"][pos]
    normalized = render["normalized"]
    image = Image.fromarray(
        _normalized_rgb(normalized["brightness"])
    )
    draw = ImageDraw.Draw(image)
    mask = normalized["mask"]
    yy, xx = np.nonzero(mask)
    cy = float(np.mean(yy))
    cx = float(np.mean(xx))
    radius = (
        ng.effective_diameter(mask) / 2
    )
    for name, angle in zip(
        arms.ARM_NAMES, arms.ARM_ANGLES
    ):
        ca, sa = (
            math.cos(angle),
            math.sin(angle),
        )
        px, py = -sa, ca
        trace = result["baseline"][
            "arm_frames"
        ][pos]["arms"][name].get(
            "trace", []
        )
        points = []
        for row in trace:
            if row is None:
                continue
            r = (
                row["radius_fraction"]
                * radius
            )
            off = (
                row[
                    "offset_radius_fraction"
                ]
                * radius
            )
            points.append(
                (
                    cx + ca*r + px*off,
                    cy + sa*r + py*off,
                )
            )
        if len(points) > 1:
            draw.line(
                points,
                fill="white",
                width=1,
            )
    return image


def render_human_evidence(
    result, source_indices, output
):
    output = Path(output)
    output.mkdir(
        parents=True, exist_ok=True
    )
    files = {}
    processed = Path(
        result["_render"]["processed"]
    )
    for source_index in source_indices:
        if (
            source_index
            not in result["accepted_indices"]
        ):
            continue
        pos = result[
            "accepted_indices"
        ].index(source_index)
        record = result[
            "_render"
        ]["frames"][pos]["record"]
        source = Image.open(
            processed
            / (
                record.get(
                    "camera_original_path"
                )
                or record["registration"][
                    "rgb_path"
                ]
            )
        ).convert("RGB")
        tier_overlay = _all_tier_overlay(
            result, pos
        )
        arm_overlay = _all_arm_overlay(
            result, pos
        )
        for image in (
            source,
            tier_overlay,
            arm_overlay,
        ):
            image.thumbnail((420, 420))
        canvas = Image.new(
            "RGB",
            (
                1280,
                max(
                    source.height,
                    tier_overlay.height,
                    arm_overlay.height,
                )
                + 60,
            ),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (10, 8),
            (
                "human-review source "
                + str(source_index)
            ),
            fill="black",
        )
        draw.text(
            (10, 32),
            "original source",
            fill="black",
        )
        draw.text(
            (435, 32),
            "normalized tier transitions",
            fill="black",
        )
        draw.text(
            (860, 32),
            "normalized diagonal traces",
            fill="black",
        )
        canvas.paste(
            source, (10, 55)
        )
        canvas.paste(
            tier_overlay, (435, 55)
        )
        canvas.paste(
            arm_overlay, (860, 55)
        )
        destination = (
            output
            / (
                "human_static_"
                + str(source_index)
                + ".jpg"
            )
        )
        canvas.save(
            destination, quality=90
        )
        files[str(source_index)] = (
            destination.name
        )
    return files


def render_evidence(result, output):
    output = Path(output)
    output.mkdir(
        parents=True, exist_ok=True
    )
    files = {}
    processed = Path(
        result["_render"]["processed"]
    )
    for label, event in (
        result[
            "evidence_selection"
        ].items()
    ):
        if event is None:
            continue
        pos = event["position"]
        record = result[
            "_render"
        ]["frames"][pos]["record"]
        source = Image.open(
            processed
            / (
                record.get(
                    "camera_original_path"
                )
                or record["registration"][
                    "rgb_path"
                ]
            )
        ).convert("RGB")
        overlay = (
            _tier_overlay(
                result, event
            )
            if "boundary" in event
            else _arm_overlay(
                result, event
            )
        )
        source.thumbnail((520, 480))
        overlay.thumbnail((520, 480))
        canvas = Image.new(
            "RGB",
            (
                1060,
                max(
                    source.height,
                    overlay.height,
                )
                + 55,
            ),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (10, 8),
            (
                "source "
                + str(
                    event["source_index"]
                )
                + " · "
                + label
            ),
            fill="black",
        )
        draw.text(
            (10, 30),
            "original source",
            fill="black",
        )
        draw.text(
            (540, 30),
            "normalized measurement overlay",
            fill="black",
        )
        canvas.paste(
            source, (10, 50)
        )
        canvas.paste(
            overlay, (540, 50)
        )
        destination = (
            output / f"{label}.jpg"
        )
        canvas.save(
            destination, quality=90
        )
        files[label] = (
            destination.name
        )
    return files


def write_stone_outputs(
    result,
    output,
    human_source_indices=None,
):
    output = Path(output)
    output.mkdir(
        parents=True, exist_ok=True
    )
    evidence = render_evidence(
        result,
        output / "evidence",
    )
    human_evidence = render_human_evidence(
        result,
        human_source_indices or [],
        output / "evidence",
    )
    clean = {
        key: value
        for key, value
        in result.items()
        if key != "_render"
    }
    clean["evidence_files"] = (
        evidence
    )
    clean["human_evidence_files"] = (
        human_evidence
    )
    (
        output
        / "geometric-crispness.json"
    ).write_text(
        json.dumps(
            _jsonable(clean),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    return clean


def _human_crispness(path):
    if (
        path is None
        or not Path(path).exists()
    ):
        return {}
    payload = json.loads(
        Path(path).read_text()
    )
    output = {}
    for observation in payload.get(
        "observations", []
    ):
        if (
            observation.get("concept")
            == "static_geometric_crispness"
        ):
            output.setdefault(
                observation["certificate"],
                [],
            ).append(
                {
                    key:
                        observation.get(key)
                    for key in (
                        "id",
                        "role",
                        "summary",
                        "source_frames",
                    )
                }
            )
    return output


def _compact(result):
    return {
        "tier_summary":
            result["baseline"][
                "tier_summary"
            ],
        "arm_summary":
            result["baseline"][
                "arm_summary"
            ],
        "step_diagnostic":
            result["baseline"][
                "step_diagnostic"
            ],
        "pipeline_sensitivity":
            result[
                "pipeline_sensitivity"
            ],
        "evidence_selection":
            result[
                "evidence_selection"
            ],
        "upstream_validity":
            result[
                "upstream_validity"
            ],
    }


def run_source_benchmark(
    source_root,
    output,
    bundle_manifest,
    human_observations=None,
):
    source_root = Path(
        source_root
    ).resolve()
    output = Path(output).resolve()
    manifest = json.loads(
        Path(
            bundle_manifest
        ).read_text()
    )
    human = _human_crispness(
        human_observations
    )
    output.mkdir(
        parents=True, exist_ok=True
    )
    stones = []

    with tempfile.TemporaryDirectory(
        prefix=(
            "sparkles-geometric-"
            "crispness-"
        )
    ) as temporary:
        work = Path(temporary)
        for item in manifest["bundles"]:
            certificate = (
                item["certificate"]
            )
            source = (
                source_root
                / certificate
            )
            processed = (
                work
                / certificate
                / "processed"
            )
            pipeline.run(
                source,
                processed,
                source
                / "source-manifest.json",
                gain=1.0,
                diagnostic_indices=
                    CORE_INDICES,
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
            stone_output = (
                output
                / "per-stone"
                / certificate
            )
            human_frames = []
            for observation in human.get(
                certificate, []
            ):
                human_frames.extend(
                    observation.get(
                        "source_frames", []
                    )
                )
            core_clean = (
                write_stone_outputs(
                    core,
                    stone_output / "core",
                    human_source_indices=
                        sorted(
                            set(human_frames)
                        ),
                )
            )
            wide_clean = {
                key: value
                for key, value
                in wide.items()
                if key != "_render"
            }
            (
                stone_output
                / "wide.json"
            ).write_text(
                json.dumps(
                    _jsonable(
                        wide_clean
                    ),
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            )
            stones.append(
                {
                    "certificate":
                        certificate,
                    "pipeline": (
                        "Workshop"
                        if certificate
                        == "IGI-LG756520111"
                        else "Diajewel"
                    ),
                    "human_static_crispness":
                        human.get(
                            certificate,
                            [],
                        ),
                    "core":
                        _compact(
                            core_clean
                        ),
                    "wide":
                        _compact(
                            wide_clean
                        ),
                }
            )

    summary = {
        "schema_version": SCHEMA,
        "normalization":
            ng.specification(),
        "core_indices": CORE_INDICES,
        "wide_indices": WIDE_INDICES,
        "stones": stones,
        "limitations": [
            (
                "Four stones can falsify "
                "unstable definitions but "
                "cannot calibrate aesthetic "
                "thresholds."
            ),
            (
                "Only one Workshop stone is "
                "present, so cross-vendor "
                "invariance cannot be "
                "established."
            ),
            (
                "Controlled perturbations "
                "are stress tests, not "
                "reconstructions of vendor "
                "pipelines."
            ),
        ],
    }
    (
        output / "summary.json"
    ).write_text(
        json.dumps(
            _jsonable(summary),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    rows = []
    for stone in stones:
        for boundary, metrics in (
            stone["core"][
                "tier_summary"
            ].items()
        ):
            rows.append(
                {
                    "certificate":
                        stone[
                            "certificate"
                        ],
                    "pipeline":
                        stone["pipeline"],
                    "family": "tier",
                    "element": boundary,
                    **metrics,
                }
            )
        for name, metrics in (
            stone["core"][
                "arm_summary"
            ]["arms"].items()
        ):
            rows.append(
                {
                    "certificate":
                        stone[
                            "certificate"
                        ],
                    "pipeline":
                        stone["pipeline"],
                    "family": "arm",
                    "element": name,
                    **metrics,
                }
            )

    if rows:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        with (
            output / "comparison.csv"
        ).open(
            "w", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )
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
            "docs/360/benchmark/"
            "source-bundles.json"
        ),
    )
    parser.add_argument(
        "--human-observations",
        type=Path,
        default=Path(
            "docs/360/calibration/"
            "human-observations.json"
        ),
    )
    args = parser.parse_args()
    run_source_benchmark(
        args.source_root,
        args.output,
        args.bundle_manifest,
        args.human_observations,
    )
    print(
        "wrote geometric crispness "
        f"benchmark -> {args.output}"
    )


if __name__ == "__main__":
    main()
