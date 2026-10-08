# #123: reconcile the two shipped optical/physical provenance contracts

## Context

Camera-RGB experiments #140, #146 and #162 showed that even straight,
persistent and locally connected image lines can follow **virtual facets**.
Optical evidence is not verified physical geometry.

Two independent #123 adapters (#171 and #172) have already been squash
merged. Both separate the external physical silhouette, unresolved
interior geometry, and useful image-plane optical/virtual appearance.
They expose different *archived output schemas*, however:

- **asscher_facet_provenance (#171):** frozen external GIRDLE_OUTLINE,
  explicitly unavailable C1/C2/C3 physical junctions, per-frame
  original RGB line and junction observations, and all-pair optical
  proximity counts. Its physical-support gate allows only the outer
  observed silhouette.
- **asscher_optical_physical_provenance (#172):** the same source data
  in a per-frame line/junction inventory with optical references and
  repeatable *appearance* counts. Its physical-boundary consumer gate
  refuses polished interior geometry.

Both schemas must remain readable for old artifacts. Neither is an
independently calibrated physical-facet model.

## Reconciliation

1. Tighten #171 input checks to match the protections already
   in #172: a source RGB diagnostic may not assert physical facet
   identity, estimator changes, synthetic corners or extrapolated
   unobserved straight-line segments. Junctions cannot reference a
   missing line candidate.
2. Make #172's consumer gate reject **every** archived RGB interior
   facet boundary, even if a caller changes JSON fields to say
   status=ok and provenance=independently_validated_physical_junction.
   Future independent physical evidence requires a separate,
   validated ingestion path. This adapter cannot self-certify.
3. Run negative tests for false physical labels and missing lines,
   and an explicit same-fixture comparison of both output formats.
4. Replay the same four SHA-256-pinned original-camera diagnostic
   artifacts, independently using both adapters. Require identical
   certificates, frozen selected frames, crown-role metadata,
   physical outer vertices, optical line counts, junction counts and
   unavailable C1_C2 / C2_C3 / C3_TABLE correspondence.

## Scope and merge criteria

Keep the frozen #96 estimator, #92 nonexclusive optical handoff,
the existing two JSON archive schemas, and source-stress policy unchanged.

- [ ] Both legacy test suites and cross-schema negative tests green.
- [ ] Four-stone archived evidence replay green and identical.
- [ ] All physical interior boundaries remain unavailable.
- [ ] No model promotion, no facet angle, no quality score changes.
- [ ] No #90 source stress.

On success, this PR is safe to **squash merge as a provenance contract
fix**, not as proof we can automatically recover polished facet geometry.
The visual-failed PR #140 remains separate and unmerged.
