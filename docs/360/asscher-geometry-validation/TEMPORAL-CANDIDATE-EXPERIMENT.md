# #124 — frame-wise C3/table candidate corroboration (v4 research)

## Why

The archived full-rotation #127 diagnostic isolates the LG756520111
leave-out-frame-16 discontinuity: after global nonmaximum suppression,
a still-present u≈0.579 peak loses to u≈0.478.
The independent window-local v3 ablation (#131) keeps the 0.579
candidate available but **still selects 0.478**, showing that
prominence + aggregate eight-sector support does not distinguish
temporally repeated features from a few unusually strong contrast lines.

The desired physical inference is the geometry of observed Asscher
facet tier boundaries — **not merely a persistent reflection**.
Any success is a falsifiable signal, not proof of polished-facet identity.

## Locked, target-blind alternatives

- **#96 control `outer_octagon_v2`:** completely unchanged, archived
  full four-stone #89 run 37755387174.
- **v3 control `window_local_peaks_v3_experiment`:** predeclared
  C3/C2/C1 semantic-window peak suppression with the original
  `log1p(prominence/scale)+1.25*sector_support` ranking, archived #89
  run 37767669755.
- **v4 treatment `temporal_candidate_v4_experiment`:** *same* v3
  candidate set and original prominence and sector geometry. Only the
  ranking of eligible candidates within each existing window changes.
  For each candidate, evaluate *individual* frame×sector
  brightness-gradient peaks within u±0.025; retain frame-sector votes
  when the existing robust z-score >=0.8. A frame votes for that
  candidate when at least four of eight sectors corroborate it.
  Rank eligible candidates by the following **predeclared priority**:
  (1) count of corroborating frames, (2) total corroborating
  frame-sector pairs, (3) lower median candidate-centred radial offset,
  (4) the original prominence+aggregate-support score.
  Candidates with no corroborating frames are unavailable; do not
  fabricate a physical boundary from weak contrast. No target-radial
  prior, C3-specific scoring, window changes or per-certificate tuning.

These thresholds were inherited from existing #19/#75 local-match
semantics (z≥0.8, half of eight sectors), while the narrower ±.025
window tests the specific stated within-frame radial hypothesis.
The method has its own fail-closed policy record; old #96/v3
wireframe specifications remain byte-identical and default unchanged.

## Per-candidate diagnostics

Every successful v4 wireframe records a `candidate_ranking` structure
with an exhaustive row for each eligible global candidate in each
semantic window: original prominence/support and score, supporting
frame count, support by frame and sector, median radial offset and
selected candidate u. Missing supports remain explicit. The original
camera-source QC overlays and #88 identity/displacement metrics are
unchanged.

## Independent frozen experiment

CI reprocesses all four hash-pinned source rotations, the exact #73/#80
selection and #96 outer octagon. Runs complete #89 leave-one-out and
fixed-ruler transfer with method `temporal_candidate_v4_experiment`,
then compares the *same* unchanged #88 metrics to immutable v2 and v3
artifacts. Report and visually inspect changes for **every stone**,
especially new unavailable cases, swapped semantic IDs, wild C3 ring
geometry, transfer failure and any apparent stability gains produced
by choosing a potentially virtual/optical edge.

An improvement only on LG756520111 is **insufficient for promotion**.
Source stress stays manual-only, explicitly **not a prerequisite** for
this iteration. No direct camera tilt or projective rectification is
introduced.

## Gate and interpretation

A successful research PR preserves diagnostics and the opt-in alternative
without changing the default. A future deliberate method promotion must
independently review the camera-RGB overlays and semantic identity;
reduced instability alone is not evidence of the true facet structure.
Report KEEP/REVISE/REJECT, with actual four-stone data, on the PR.
