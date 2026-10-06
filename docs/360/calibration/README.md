# Empirical Asscher 360 calibration

Issue #22 calibrates the retained #20/#45 descriptor profile against the visual
observations in the existing Asscher evaluations.

This layer is deliberately **not** another descriptor programme. It does not
recompute masks, traces, thresholds, correlations or morphology, and it does not
fit a score or classifier.

## Inputs

- canonical retained profile: `docs/360/profile/comparison.json`
  (`diamond360-descriptor-profile/1`);
- curated human review annotations: `human-observations.json`;
- compact #21 evidence packets from `docs/360/evidence-packet/`
  (`diamond360-evidence-packet/1`).

Only #45 production measurement IDs can be linked to human observations.
Context-only, REVISE/REJECT, semantic, outer or dynamic-support fields cannot
silently enter calibration.

## Human observation contract

`human-observations.json` normalizes the current four reviews into explicit,
auditable observations. Every observation records:

- certificate and source evaluation;
- normalized visual concept;
- hypothesis family;
- review role (`strength | drawback | check | mixed | neutral`);
- human-selected source frame indices;
- whether the retained profile explains the observation
  (`explained | partial | unexplained`);
- zero or more retained profile fields with a relationship
  (`supports | partial | contradicts | irrelevant`) and rationale.

`unexplained` observations must have **no descriptor links**. This prevents the
calibration exercise from forcing every human phrase into an existing metric.

Human-selected frames may extend outside the exact 17-step machine profile
window. The benchmark records those indices explicitly rather than pretending
the measurement covered them.

## Outputs

`benchmark.json` (`diamond360-calibration/1`) contains:

- the joined human observation + #45 measurement records;
- direction-free ascending/descending sample ranks;
- validity/reasons copied from the profile;
- redundancy-group metadata;
- hypothesis-family coverage;
- recurring unexplained concepts;
- direct references to #21 packet items/contact sheets for every descriptor link.

`benchmark.csv` is the compact calibration table: one row per
observation/descriptor relationship, with descriptor-less rows retained for
unexplained observations.

`findings.md` records the current four-stone interpretation and counterexamples.

## Build

```bash
python -m diamond360.calibration \
  --repository . \
  --observations docs/360/calibration/human-observations.json \
  --output docs/360/calibration
```

The builder writes only `benchmark.json` and `benchmark.csv`. The curated
annotation file and findings remain human-reviewed inputs/interpretation.

## Calibration rules

1. Ranks are descriptive ordering only. Rank 1 never means "best".
2. Activation + mobility and occupancy + switching retain their #45 redundancy
   groups and are not independent votes.
3. Correlation sign is preserved. Positive and negative coordination are
   behaviours, not automatic quality directions.
4. Profile `review`/unavailable states remain visible and are never upgraded.
5. No thresholds, weights, regression, p-values or composite scores are fit on
   the four-stone sample.
6. Human reviews are calibration evidence, not perfect optical ground truth.
7. #22 consumes #21 evidence packets as-is and never re-selects descriptor
   evidence. When a compact packet retains the exact linked field, calibration
   records an `exact_field` reference. When de-duplication removes that scalar's
   native event, calibration records the packet's `family_representative`
   explicitly rather than pretending it is exact field evidence.

## #21 evidence handoff

All four compact packets are now integrated: 4 / 4 / 5 / 4 selected items,
each covering all six available visual roles. Across the 21 curated
observation↔descriptor relationships, 16 resolve to exact selected field
evidence and 5 resolve to an explicit family representative; none is missing.
There are 24 packet-item references because some fields have more than one
selected event. Twelve share at least one frame with the independently
human-selected review frames and twelve are independent source-frame checks.

The distinction between exact and family-level evidence is part of the output
contract and should remain visible in #23.

## Current sample limit

Four complete stones are enough to expose useful matches and falsify simplistic
interpretations, but not enough to establish aesthetic direction or numeric
bands. The current benchmark also mixes vendor pipelines. Buyer-facing
directionality/thresholds should wait for roughly 10+ well-reviewed complete
sequences with broader source coverage.
