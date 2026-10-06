"""Run-based bright/dark persistence for registered Asscher 360 sequences."""
from __future__ import annotations

import numpy as np

from . import occupancy as o


def _validate_arrays(brightness, valid_masks, region_masks, observed):
    brightness = np.asarray(brightness, float)
    valid_masks = np.asarray(valid_masks, bool)
    region_masks = np.asarray(region_masks, bool)
    observed = np.asarray(observed, bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape or region_masks.shape != brightness.shape:
        raise ValueError("brightness, valid masks and region masks must be matching frame-height-width arrays")
    if observed.shape != (len(brightness),):
        raise ValueError("observed flags must match frames")
    return brightness, valid_masks & np.isfinite(brightness), region_masks, observed


def _quantile(values, q, method=None):
    if not len(values):
        return None
    kwargs = {"method": method} if method else {}
    return float(np.quantile(np.asarray(values, float), q, **kwargs))


def _boundary_reason(position, side, observed, reference_valid, support):
    count = len(observed)
    neighbor = position - 1 if side == "left" else position + 1
    if neighbor < 0 or neighbor >= count:
        return "window_endpoint"
    if not observed[neighbor]:
        return "gap"
    if not reference_valid[neighbor]:
        return "invalid_reference"
    if not support[neighbor]:
        return "support_loss"
    return "state_change"


def _state_summary(active, availability, observed, reference_valid, support, requested_steps):
    frame_count, pixel_count = active.shape
    eligible = np.any(availability, axis=0)
    longest = np.zeros(pixel_count, dtype=np.int16)
    any_censored_at_longest = np.zeros(pixel_count, dtype=bool)
    all_censored_at_longest = np.zeros(pixel_count, dtype=bool)
    current = np.zeros(pixel_count, dtype=np.int16)
    current_left_reason = np.zeros(pixel_count, dtype=np.int8)
    previous_active = np.zeros(pixel_count, dtype=bool)

    reason_codes = {
        "state_change": 0,
        "window_endpoint": 1,
        "gap": 2,
        "invalid_reference": 3,
        "support_loss": 4,
    }
    total_runs = completed_runs = censored_runs = 0
    censor_boundaries = {
        "left": {"gap": 0, "invalid_reference": 0, "support_loss": 0, "window_endpoint": 0},
        "right": {"gap": 0, "invalid_reference": 0, "support_loss": 0, "window_endpoint": 0},
    }

    def finish(mask, right_reason):
        nonlocal total_runs, completed_runs, censored_runs
        if not np.any(mask):
            return
        lengths = current[mask].astype(np.int16)
        indices = np.flatnonzero(mask)
        left_codes = current_left_reason[indices]
        right_code = reason_codes[right_reason]
        censored = (left_codes != 0) | (right_code != 0)
        old = longest[indices]
        greater = lengths > old
        equal = lengths == old
        if np.any(greater):
            gi = indices[greater]
            longest[gi] = lengths[greater]
            any_censored_at_longest[gi] = censored[greater]
            all_censored_at_longest[gi] = censored[greater]
        if np.any(equal):
            ei = indices[equal]
            any_censored_at_longest[ei] |= censored[equal]
            all_censored_at_longest[ei] &= censored[equal]
        n = int(mask.sum())
        total_runs += n
        censored_runs += int(np.count_nonzero(censored))
        completed_runs += int(np.count_nonzero(~censored))
        for name, code in reason_codes.items():
            if code and name in censor_boundaries["left"]:
                censor_boundaries["left"][name] += int(np.count_nonzero(left_codes == code))
        if right_code:
            censor_boundaries["right"][right_reason] += n

    for position in range(frame_count):
        now = active[position]
        started = now & ~previous_active
        if np.any(started):
            if position == 0:
                current_left_reason[started] = reason_codes["window_endpoint"]
            elif not observed[position - 1]:
                current_left_reason[started] = reason_codes["gap"]
            elif not reference_valid[position - 1]:
                current_left_reason[started] = reason_codes["invalid_reference"]
            else:
                lost = started & ~support[position - 1]
                changed = started & support[position - 1]
                current_left_reason[lost] = reason_codes["support_loss"]
                current_left_reason[changed] = reason_codes["state_change"]
            current[started] = 0
        current[now] += 1

        ended = previous_active & ~now
        if np.any(ended):
            completed = ended & availability[position]
            finish(completed, "state_change")
            unavailable = ended & ~availability[position]
            if np.any(unavailable):
                if not observed[position]:
                    finish(unavailable, "gap")
                elif not reference_valid[position]:
                    finish(unavailable, "invalid_reference")
                else:
                    finish(unavailable & ~support[position], "support_loss")
            current[ended] = 0
            current_left_reason[ended] = reason_codes["state_change"]
        previous_active = now.copy()

    if frame_count:
        finish(previous_active, "window_endpoint")

    values = longest[eligible]
    finite_pixels = int(eligible.sum())
    if not finite_pixels:
        return {
            "finite_pixels": 0,
            "q50_frames": None,
            "q90_frames": None,
            "q90_window_fraction": None,
            "max_frames": None,
            "fraction_nonzero": None,
            "longest_any_censored_fraction": None,
            "longest_all_censored_fraction": None,
            "evidence_run_length_frames": None,
            "total_runs": 0,
            "completed_runs": 0,
            "censored_runs": 0,
            "censor_boundaries": censor_boundaries,
            "_longest": longest,
        }

    q90 = _quantile(values, 0.9)
    evidence_length = int(_quantile(values, 0.9, method="higher"))
    if evidence_length == 0 and np.any(values > 0):
        evidence_length = 1
    return {
        "finite_pixels": finite_pixels,
        "q50_frames": _quantile(values, 0.5),
        "q90_frames": q90,
        "q90_window_fraction": float(q90 / requested_steps) if requested_steps else None,
        "max_frames": int(values.max()),
        "fraction_nonzero": float(np.mean(values > 0)),
        "longest_any_censored_fraction": float(np.mean(any_censored_at_longest[eligible])),
        "longest_all_censored_fraction": float(np.mean(all_censored_at_longest[eligible])),
        "evidence_run_length_frames": evidence_length,
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "censored_runs": censored_runs,
        "censor_boundaries": censor_boundaries,
        "_longest": longest,
    }


def _evidence_event(active, support, observed, reference_valid, summary, target_state):
    length = summary.get("evidence_run_length_frames")
    if not length:
        return None
    frame_count = active.shape[0]
    best = None
    for start in range(0, frame_count - length + 1):
        persistent = np.all(active[start:start + length], axis=0)
        count = int(persistent.sum())
        if count:
            candidate = (count, -start, start, persistent)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None:
        return None

    _, _, start, persistent = best
    end = start + length - 1
    candidates = np.flatnonzero(persistent)
    longest = summary["_longest"]
    representative = int(candidates[np.argmax(longest[candidates])])

    run_start = start
    while run_start > 0 and active[run_start - 1, representative]:
        run_start -= 1
    run_end = end
    while run_end + 1 < frame_count and active[run_end + 1, representative]:
        run_end += 1

    persistent_full_run = np.all(active[run_start:run_end + 1], axis=0)
    left_reason = _boundary_reason(run_start, "left", observed, reference_valid, support[:, representative])
    right_reason = _boundary_reason(run_end, "right", observed, reference_valid, support[:, representative])
    return {
        "state": target_state,
        "start_position": int(run_start),
        "middle_position": int((run_start + run_end) // 2),
        "end_position": int(run_end),
        "observed_run_length_frames": int(run_end - run_start + 1),
        "evidence_window_length_frames": int(length),
        "persistent_pixel_count": int(persistent_full_run.sum()),
        "left_boundary": left_reason,
        "right_boundary": right_reason,
        "left_censored": left_reason != "state_change",
        "right_censored": right_reason != "state_change",
        "representative_flat_pixel": representative,
    }


def persistence_trace(
    brightness,
    valid_masks,
    region_masks,
    whole_stone_values,
    observed,
    support_mode,
    threshold,
):
    """Measure longest dark/non-dark runs in observed source steps."""
    brightness, valid_masks, region_masks, observed = _validate_arrays(
        brightness, valid_masks, region_masks, observed
    )
    if support_mode not in {"fixed", "dynamic"}:
        raise ValueError('support_mode must be "fixed" or "dynamic"')
    threshold = o.validate_relative_dark_threshold(threshold)
    if len(whole_stone_values) != len(brightness):
        raise ValueError("whole-stone values must match frames")

    supported = valid_masks & region_masks
    common = (
        np.all(supported[observed], axis=0)
        if observed.any()
        else np.zeros(brightness.shape[1:], bool)
    )
    support = np.broadcast_to(common, supported.shape).copy() if support_mode == "fixed" else supported
    nominal_union = (
        np.any(region_masks[observed], axis=0)
        if observed.any()
        else np.zeros(brightness.shape[1:], bool)
    )

    states = np.zeros(brightness.shape, dtype=bool)
    reference_valid = np.zeros(len(brightness), dtype=bool)
    for position, (frame, whole, ok) in enumerate(zip(brightness, whole_stone_values, observed)):
        if not ok:
            continue
        state = o.relative_dark_state(frame, whole, threshold)
        if state is None:
            continue
        states[position] = state
        reference_valid[position] = True

    frame_available = observed & reference_valid
    availability = support & frame_available[:, None, None]
    flat_availability = availability.reshape(len(brightness), -1)
    flat_support = support.reshape(len(brightness), -1)
    flat_states = states.reshape(len(brightness), -1)
    requested_steps = len(brightness)

    dark_active = flat_availability & flat_states
    non_dark_active = flat_availability & ~flat_states
    dark = _state_summary(
        dark_active, flat_availability, observed, reference_valid, flat_support, requested_steps
    )
    non_dark = _state_summary(
        non_dark_active, flat_availability, observed, reference_valid, flat_support, requested_steps
    )
    evidence = {
        "dark": _evidence_event(dark_active, flat_support, observed, reference_valid, dark, "dark"),
        "non_dark": _evidence_event(non_dark_active, flat_support, observed, reference_valid, non_dark, "non_dark"),
    }

    for summary in (dark, non_dark):
        summary.pop("_longest", None)

    return {
        "threshold": threshold,
        "support_mode": support_mode,
        "requested_source_steps": requested_steps,
        "observed_frames": int(observed.sum()),
        "valid_reference_frames": int(reference_valid.sum()),
        "eligible_pixel_observations": int(flat_availability.sum()),
        "persistent_support_pixels": int(common.sum()),
        "persistent_support_fraction": float(common.sum() / nominal_union.sum()) if nominal_union.any() else None,
        "normalization": "longest run frames / requested source steps",
        "dark": dark,
        "non_dark": non_dark,
        "evidence": evidence,
        "status": "ok" if flat_availability.any() else "unavailable",
    }


def threshold_sweep(
    brightness,
    valid_masks,
    region_masks,
    whole_stone_values,
    observed,
    support_mode,
    thresholds=(0.60, 0.65, 0.70),
):
    thresholds = tuple(float(value) for value in thresholds)
    if len(thresholds) != len(set(thresholds)):
        raise ValueError("thresholds must be unique")
    return {
        f"{threshold:.2f}": persistence_trace(
            brightness,
            valid_masks,
            region_masks,
            whole_stone_values,
            observed,
            support_mode,
            threshold,
        )
        for threshold in thresholds
    }
