"""Target-blind 2D projected exterior pavilion changepoints.

The input is *only* image-plane y/x silhouette observations with an estimated
pavilion ROI. The fitter cannot read generating geometry, optical imagery,
Sergey targets, 3D physical angles, or which case produced the observations.
A slope change is not proof of a physical polished facet junction.
"""
from __future__ import annotations

import itertools
import json
from typing import Any

import numpy as np

OBSERVATION_SCHEMA = "sparkles-pavilion-projected-observations/1"
FIT_SCHEMA = "sparkles-pavilion-projected-changepoints/1"

# Predeclared, fixed before looking at the held-out benchmark.
POLICY: dict[str, Any] = {
    "source_anatomy": "upper_pointed_pavilion_tip_to_candidate_girdle",
    "coordinate_system": "image_pixels_y_down",
    "max_visible_straight_stretches": 3,
    "minimum_supported_rows": 24,
    "minimum_observed_y_span_fraction": 0.50,
    "minimum_segment_y_span_px": 17,
    "minimum_points_per_segment": 10,
    "candidate_knot_step_px": 4,
    "minimum_adjacent_slope_change_abs_dx_dy": 0.18,
    "extra_stretch_complexity_cost_px2": 70.0,
    "huber_delta_px": 2.5,
    "robust_irls_steps": 5,
    "minimum_margin_for_stable_model_px2": 30.0,
    "no_forced_symmetry": True,
    "no_facet_identity_or_physical_angles": True,
    "no_expert_targets_or_internal_optical_features": True,
}


def _validate(observations: dict) -> tuple[float, float]:
    if not isinstance(observations, dict) or set(observations) != {
        "schema_version", "source_kind", "pavilion_roi_y_px", "contours"
    }:
        raise ValueError("observation-only schema required; truth/targets are prohibited")
    if (observations["schema_version"] != OBSERVATION_SCHEMA or
            observations["source_kind"] not in {"synthetic_profile", "observed_profile"}):
        raise ValueError("invalid observation schema or source kind")
    roi = observations["pavilion_roi_y_px"]
    if not isinstance(roi, list) or len(roi) != 2 or not all(
            isinstance(v, (int, float)) and np.isfinite(v) for v in roi):
        raise ValueError("invalid source-image pavilion ROI")
    lo, hi = map(float, roi)
    if hi - lo < 50:
        raise ValueError("ROI too short for pavilion step fitting")
    sides = observations["contours"]
    if not isinstance(sides, dict) or set(sides) != {"left", "right"}:
        raise ValueError("independent left/right observations required")
    for side in ("left", "right"):
        rows = sides[side]
        if not isinstance(rows, list):
            raise ValueError("contour observations must be lists")
        previous = float("-inf")
        for item in rows:
            if not isinstance(item, dict) or set(item) != {"y_px", "x_px"}:
                raise ValueError("only observed xy coordinates, no ground truth / optical bands")
            y, x = item["y_px"], item["x_px"]
            if not isinstance(y, (int, float)) or not np.isfinite(y):
                raise ValueError("nonfinite row")
            if x is not None and (not isinstance(x, (int, float)) or not np.isfinite(x)):
                raise ValueError("nonfinite contour coordinate")
            if y <= previous or y < lo or y > hi:
                raise ValueError("rows must be sorted, distinct and within ROI")
            previous = float(y)
    return lo, hi


def _robust_model(y: np.ndarray, x: np.ndarray, breaks: tuple) -> tuple:
    matrix = np.column_stack(
        [np.ones(len(y)), y - y[0]] +
        [np.maximum(y - float(k), 0) for k in breaks]
    )
    weights = np.ones(len(y))
    coef = np.zeros(matrix.shape[1])
    delta = float(POLICY["huber_delta_px"])
    for _ in range(POLICY["robust_irls_steps"]):
        root = np.sqrt(weights)
        coef = np.linalg.lstsq(matrix * root[:, None], x * root, rcond=None)[0]
        residual = x - matrix @ coef
        weights = np.minimum(1.0, delta / np.maximum(np.abs(residual), 1e-12))
    residual = x - matrix @ coef
    huber_loss = np.where(
        np.abs(residual) <= delta, residual ** 2,
        2 * delta * np.abs(residual) - delta ** 2
    )
    return float(np.sum(huber_loss)), coef, float(np.sqrt(np.mean(residual ** 2)))


def _side_fit(points: list[dict], roi: tuple) -> dict:
    supported = [(float(p["y_px"]), float(p["x_px"]))
                 for p in points if p["x_px"] is not None]
    n = len(supported)
    if n < POLICY["minimum_supported_rows"]:
        return {"status": "unavailable", "reason": "insufficient_observed_outer_rows",
                "observed_point_count": n, "physical_angles": None}
    y, x = np.asarray(supported, dtype=float).T
    coverage = (y[-1] - y[0]) / (roi[1] - roi[0])
    if coverage < POLICY["minimum_observed_y_span_fraction"]:
        return {"status": "unavailable", "reason": "observed_span_too_short",
                "observed_point_count": n, "observed_y_fraction": round(float(coverage), 5),
                "physical_angles": None}
    minspan = POLICY["minimum_segment_y_span_px"]
    knots = np.arange(
        np.ceil(y[0] + minspan),
        np.floor(y[-1] - minspan) + 1,
        POLICY["candidate_knot_step_px"],
    )
    options = []
    for segments in (1, 2, 3):
        best = None
        combinations = itertools.combinations(knots, segments - 1) if segments > 1 else [()]
        for breaks in combinations:
            borders = (float(y[0]),) + tuple(breaks) + (float(y[-1]),)
            if np.min(np.diff(borders)) < minspan:
                continue
            if any(np.count_nonzero((y >= a) & (y <= b)) <
                   POLICY["minimum_points_per_segment"]
                   for a, b in zip(borders[:-1], borders[1:])):
                continue
            error, coef, rms = _robust_model(y, x, breaks)
            slopes = np.cumsum(coef[1:])
            if len(slopes) > 1 and np.min(np.abs(np.diff(slopes))) < (
                    POLICY["minimum_adjacent_slope_change_abs_dx_dy"]):
                continue
            penalized = error + (segments - 1) * POLICY["extra_stretch_complexity_cost_px2"]
            if best is None or penalized < best["objective"]:
                best = {"segments": segments, "break_y_px": [round(float(k), 3) for k in breaks],
                        "slopes_dx_dy": [round(float(s), 6) for s in slopes],
                        "source_fit_rms_px": round(rms, 5),
                        "huber_loss_px2": round(error, 5),
                        "objective": round(penalized, 5),
                        "coef": [float(c) for c in coef]}
        if best is not None:
            options.append(best)
    if not options:
        return {"status": "unavailable", "reason": "no_supported_continuous_fit",
                "observed_point_count": n, "physical_angles": None}
    options.sort(key=lambda m: (m["objective"], m["segments"]))
    winner = options[0]
    runnerup_margin = (options[1]["objective"] - winner["objective"]
                       if len(options) > 1 else None)
    status = ("ambiguous" if runnerup_margin is not None and
              runnerup_margin < POLICY["minimum_margin_for_stable_model_px2"]
              else "candidate_only")
    return {
        "status": status,
        "observed_point_count": n,
        "observed_y_fraction": round(float(coverage), 5),
        "segment_count": winner["segments"],
        "candidate_break_y_px": winner["break_y_px"],
        "slopes_dx_dy": winner["slopes_dx_dy"],
        "image_plane_fit_rms_px": winner["source_fit_rms_px"],
        "margin_to_next_model_px2": (None if runnerup_margin is None
                                     else round(float(runnerup_margin), 5)),
        "model_options": [{
            "segments": m["segments"], "break_y_px": m["break_y_px"],
            "objective_px2": m["objective"]
        } for m in options],
        "physical_facet_correspondence": "not_established",
        "physical_angles": None,
        "support_y_range_px": [float(y[0]), float(y[-1])],
    }


def fit_observations(observations: dict) -> dict:
    """Strict no-truth estimator. Copy/serialize the result for auditing."""
    bounds = _validate(observations)
    return {
        "schema_version": FIT_SCHEMA,
        "input_schema": OBSERVATION_SCHEMA,
        "source_kind": observations["source_kind"],
        "pavilion_roi_y_px": list(bounds),
        "sides": {
            side: _side_fit(observations["contours"][side], bounds)
            for side in ("left", "right")
        },
        "policy": POLICY,
        "target_parameters_loaded": False,
        "physical_facet_angles": "all_unavailable",
        "explanation": (
            "A 2D projected silhouette changepoint does not identify a polished "
            "facet plane or a physical P1/P2/P3 angle. Mirror symmetry is never forced."
        ),
    }


def fit_json_text(observation_json: str) -> str:
    return json.dumps(fit_observations(json.loads(observation_json)),
                      sort_keys=True, indent=2) + "\n"
