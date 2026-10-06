"""Spatial revisions of within-inner Asscher articulation (#59).

Two deliberately small candidates are tested on the exact #26 coarse-fixed inner
support:

1. spatial participation across a fixed eight-sector partition; and
2. two-sided contrast coverage around the within-inner median.

Neither metric carries an aesthetic direction.
"""
from __future__ import annotations

import math

import numpy as np

from . import articulation as global_articulation

SECTOR_COUNT = 8
COVERAGE_RATIOS = (1.10, 1.15, 1.20)
PRIMARY_COVERAGE_RATIO = 1.15

SPATIAL_MEASURES = (
    "cell_log_spread",
    "contrast_participation",
    "distributed_contrast",
    "adjacent_log_contrast_median",
)
SPATIAL_PRIMARY = "distributed_contrast"


def coverage_key(prefix, ratio):
    return f"{prefix}_{float(ratio):.2f}".replace(".", "p")


COVERAGE_PRIMARY = coverage_key("balanced_coverage", PRIMARY_COVERAGE_RATIO)


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def summarise(values):
    finite = [_finite(value) for value in values]
    finite = [value for value in finite if value is not None]
    result = {
        "finite_frames": len(finite),
        "q10": None,
        "q50": None,
        "q90": None,
        "status": "ok" if len(finite) >= 3 else "unavailable",
        "reasons": [] if len(finite) >= 3 else ["insufficient_finite_frames"],
    }
    if len(finite) < 3:
        return result
    data = np.asarray(finite, float)
    result.update(
        q10=float(np.quantile(data, 0.1)),
        q50=float(np.quantile(data, 0.5)),
        q90=float(np.quantile(data, 0.9)),
    )
    return result


def angular_sector_labels(support, sector_count=SECTOR_COUNT):
    """Partition fixed support into equal angular sectors around its centroid.

    Sector 0 is centred on registered east; sectors then proceed counter-clockwise.
    The partition is geometry-only and therefore identical for every frame sharing
    the fixed support.
    """
    support = np.asarray(support, bool)
    if support.ndim != 2:
        raise ValueError("support must be a 2D mask")
    sector_count = int(sector_count)
    if sector_count < 4:
        raise ValueError("sector_count must be at least 4")

    labels = np.full(support.shape, -1, dtype=int)
    yy, xx = np.nonzero(support)
    if not len(xx):
        return labels, {"centre_x": None, "centre_y": None, "sector_count": sector_count}

    centre_x = float(np.mean(xx))
    centre_y = float(np.mean(yy))
    dx = xx.astype(float) - centre_x
    dy = centre_y - yy.astype(float)
    angles = np.mod(np.arctan2(dy, dx), 2.0 * math.pi)
    width = 2.0 * math.pi / sector_count
    sector = np.floor(np.mod(angles + width / 2.0, 2.0 * math.pi) / width).astype(int)
    labels[yy, xx] = sector
    return labels, {
        "centre_x": centre_x,
        "centre_y": centre_y,
        "sector_count": sector_count,
    }


def frame_spatial_participation(brightness, support, sector_count=SECTOR_COUNT):
    """Describe how tonal differences are distributed across fixed spatial cells.

    `contrast_participation` is an effective-number fraction computed from the
    absolute log-luminance deviations of cell medians. It approaches 1 when many
    cells participate and is small when contrast is concentrated in few cells.

    `distributed_contrast` multiplies that participation by cell log spread, so
    tiny but spatially widespread noise does not look strongly articulated.
    """
    brightness = np.asarray(brightness, float)
    support = np.asarray(support, bool)
    if brightness.ndim != 2 or support.shape != brightness.shape:
        raise ValueError("brightness and support must be matching 2D arrays")

    labels, geometry = angular_sector_labels(support, sector_count)
    cell_medians = []
    cell_pixels = []
    for index in range(int(sector_count)):
        cell = (labels == index) & np.isfinite(brightness)
        values = brightness[cell]
        values = values[values > 0]
        cell_pixels.append(int(values.size))
        cell_medians.append(float(np.median(values)) if values.size else None)

    valid = [
        (index, value)
        for index, value in enumerate(cell_medians)
        if _finite(value) is not None and float(value) > 0
    ]
    minimum = max(4, int(math.ceil(sector_count / 2)))
    result = {
        "status": "ok" if len(valid) >= minimum else "unavailable",
        "reasons": [] if len(valid) >= minimum else ["insufficient_spatial_cells"],
        "supported_pixels": int(np.count_nonzero(support & np.isfinite(brightness))),
        "valid_cells": len(valid),
        "cell_medians": cell_medians,
        "cell_pixel_counts": cell_pixels,
        "partition": geometry,
        **{key: None for key in SPATIAL_MEASURES},
    }
    if len(valid) < minimum:
        return result

    logs = np.asarray([math.log(float(value)) for _, value in valid], float)
    indices = [index for index, _ in valid]
    centre = float(np.median(logs))
    deviations = np.abs(logs - centre)
    sum_deviation = float(np.sum(deviations))
    sum_squared = float(np.sum(deviations * deviations))

    participation = 0.0
    if sum_squared > 0:
        effective_cells = (sum_deviation * sum_deviation) / sum_squared
        participation = float(effective_cells / len(logs))

    spread = float(np.quantile(logs, 0.9) - np.quantile(logs, 0.1))

    log_by_sector = {index: value for index, value in zip(indices, logs)}
    adjacent = []
    for index in range(int(sector_count)):
        right = (index + 1) % int(sector_count)
        if index in log_by_sector and right in log_by_sector:
            adjacent.append(abs(log_by_sector[index] - log_by_sector[right]))
    adjacent_median = float(np.median(adjacent)) if adjacent else None

    result.update(
        cell_log_spread=spread,
        contrast_participation=participation,
        distributed_contrast=float(spread * participation),
        adjacent_log_contrast_median=adjacent_median,
    )
    return result


def frame_contrast_coverage(values, threshold_ratio=PRIMARY_COVERAGE_RATIO):
    """Measure two-sided area coverage around the inner-region median.

    A pixel is dark when Y < median(Y)/ratio and bright when
    Y > median(Y)*ratio. The balanced statistic is min(p_dark, p_bright), so one
    narrow extreme cannot dominate the result.
    """
    ratio = float(threshold_ratio)
    if not math.isfinite(ratio) or ratio <= 1:
        raise ValueError("threshold_ratio must be finite and greater than 1")

    data = np.asarray(values, float).ravel()
    data = data[np.isfinite(data) & (data > 0)]
    result = {
        "status": "ok" if data.size >= 3 else "unavailable",
        "reasons": [] if data.size >= 3 else ["insufficient_supported_pixels"],
        "supported_pixels": int(data.size),
        "inner_median": None,
        "threshold_ratio": ratio,
        "dark_cutoff": None,
        "bright_cutoff": None,
        "dark_fraction": None,
        "bright_fraction": None,
        "extreme_coverage": None,
        "balanced_coverage": None,
        "coverage_balance": None,
    }
    if data.size < 3:
        return result

    median = float(np.median(data))
    if median <= 0:
        result["status"] = "unavailable"
        result["reasons"] = ["nonpositive_inner_median"]
        return result

    dark_cutoff = median / ratio
    bright_cutoff = median * ratio
    dark = float(np.mean(data < dark_cutoff))
    bright = float(np.mean(data > bright_cutoff))
    total = dark + bright
    balanced = min(dark, bright)
    balance = float(2.0 * balanced / total) if total > 0 else 0.0
    result.update(
        inner_median=median,
        dark_cutoff=float(dark_cutoff),
        bright_cutoff=float(bright_cutoff),
        dark_fraction=dark,
        bright_fraction=bright,
        extreme_coverage=float(total),
        balanced_coverage=float(balanced),
        coverage_balance=balance,
    )
    return result


def measure_frame(
    brightness,
    support,
    coverage_ratios=COVERAGE_RATIOS,
    sector_count=SECTOR_COUNT,
):
    brightness = np.asarray(brightness, float)
    support = np.asarray(support, bool)
    spatial = frame_spatial_participation(brightness, support, sector_count)
    values = brightness[support] if support.any() else np.asarray([], float)
    global_spread = global_articulation.frame_articulation(values).get("raw_spread")

    result = {
        **spatial,
        "global_raw_spread": global_spread,
        "coverage": {},
    }
    for ratio in coverage_ratios:
        coverage = frame_contrast_coverage(values, ratio)
        result["coverage"][f"{float(ratio):.2f}"] = coverage
        for field in (
            "dark_fraction",
            "bright_fraction",
            "extreme_coverage",
            "balanced_coverage",
            "coverage_balance",
        ):
            result[coverage_key(field, ratio)] = coverage[field]
    return result


def measure_keys(coverage_ratios=COVERAGE_RATIOS):
    keys = [*SPATIAL_MEASURES, "global_raw_spread"]
    for ratio in coverage_ratios:
        for field in (
            "dark_fraction",
            "bright_fraction",
            "extreme_coverage",
            "balanced_coverage",
            "coverage_balance",
        ):
            keys.append(coverage_key(field, ratio))
    return tuple(keys)


def articulation_trace(
    frames,
    support,
    source_indices,
    whole_medians=None,
    coverage_ratios=COVERAGE_RATIOS,
    sector_count=SECTOR_COUNT,
):
    """Measure both #59 candidates without interpolating missing frames."""
    frames = list(frames)
    source_indices = list(source_indices)
    if len(frames) != len(source_indices):
        raise ValueError("frames and source_indices must have equal length")
    n = len(frames)
    whole_medians = [None] * n if whole_medians is None else list(whole_medians)
    if len(whole_medians) != n:
        raise ValueError("whole_medians must align with frames")

    keys = measure_keys(coverage_ratios)
    rows = []
    for position, (frame, source_index, whole_median) in enumerate(
        zip(frames, source_indices, whole_medians)
    ):
        if frame is None:
            measured = {
                "status": "gap",
                "reasons": ["unobserved_frame"],
                "supported_pixels": 0,
                "valid_cells": 0,
                "cell_medians": [None] * int(sector_count),
                "cell_pixel_counts": [0] * int(sector_count),
                "partition": {
                    "centre_x": None,
                    "centre_y": None,
                    "sector_count": int(sector_count),
                },
                "coverage": {},
                **{key: None for key in keys},
            }
        else:
            measured = measure_frame(
                frame,
                support,
                coverage_ratios=coverage_ratios,
                sector_count=sector_count,
            )
        rows.append(
            {
                "position": position,
                "source_index": source_index,
                "whole_median": _finite(whole_median),
                **measured,
            }
        )

    return {
        "frame_trace": rows,
        "summaries": {
            key: summarise([row.get(key) for row in rows])
            for key in keys
        },
    }


def _finite_rows(frame_trace, key):
    return [row for row in frame_trace if _finite(row.get(key)) is not None]


def _extreme(frame_trace, key, largest):
    rows = _finite_rows(frame_trace, key)
    if not rows:
        return None
    if largest:
        return max(rows, key=lambda row: (float(row[key]), -row["position"]))
    return min(rows, key=lambda row: (float(row[key]), row["position"]))


def _nearest(frame_trace, key, target):
    rows = _finite_rows(frame_trace, key)
    if not rows or target is None:
        return None
    return min(rows, key=lambda row: (abs(float(row[key]) - target), row["position"]))


def select_evidence(frame_trace, key):
    summary = summarise([row.get(key) for row in frame_trace])
    return {
        "measure": key,
        "lowest": _extreme(frame_trace, key, False),
        "median": _nearest(frame_trace, key, summary.get("q50")),
        "highest": _extreme(frame_trace, key, True),
        "matched_brightness_pair": global_articulation.matched_brightness_pair(
            frame_trace, key
        ),
    }


def rank_agreement(frame_trace, left, right):
    pairs = [
        (float(row[left]), float(row[right]))
        for row in frame_trace
        if _finite(row.get(left)) is not None and _finite(row.get(right)) is not None
    ]
    if len(pairs) < 3:
        return {"paired_frames": len(pairs), "spearman": None}
    left_ranks = np.asarray(global_articulation._average_ranks([p[0] for p in pairs]), float)
    right_ranks = np.asarray(global_articulation._average_ranks([p[1] for p in pairs]), float)
    if np.std(left_ranks) == 0 or np.std(right_ranks) == 0:
        rho = None
    else:
        rho = float(np.corrcoef(left_ranks, right_ranks)[0, 1])
    return {"paired_frames": len(pairs), "spearman": rho}
