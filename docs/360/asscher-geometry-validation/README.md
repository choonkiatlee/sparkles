# Issue #88: frozen Asscher geometry validation contract

This layer freezes the measurement rules used by #76 before stability or
external-validation results are inspected.

It is deliberately **not** another geometry fitter. The implementation in
`diamond360.asscher_geometry_validation` accepts already-produced #75 result
objects and compares their fixed semantic scaffolds. It contains no image
loader, no fitting entry point and no external target loader.

## Frozen method

The first validation campaign is pinned to:

- #75 merge revision `8bbbbf64754f2bcbb48ab435b731bdf95f7722bc`;
- wireframe schema `diamond360-asscher-wireframe-fit/1`;
- #74 scaffold schema `diamond360-asscher-semantic-scaffold/1`;
- #80 sequence gauge schema `diamond360-asscher-sequence-gauge/1`;
- canonicalized #75 specification SHA-256
  `5805a26f468a8b25664556747576075901e36d46401a41182c9d1469f1f68065`;
- benchmark manifest `docs/360/benchmark/source-bundles.json`, canonical JSON
  SHA-256 `4e9fb4b51d8b2f628ca678ee309bc04e5fc3b0ca22ee0b1a1d35489685cb88f1`.

`assert_frozen_method()` fails closed if the in-tree #75 specification or #80
schema changes. A later fitter revision must therefore declare a new validation
method revision instead of silently reusing these results.

The machine-readable freeze is also recorded in `validation-contract.json`.

## Result schema

Validation records use:

```text
diamond360-asscher-geometry-validation/1
```

Each record preserves:

- frozen estimator revision, schemas, full specification and fingerprint;
- benchmark source bundle filenames, byte counts and SHA-256 values;
- comparison kind / case identity;
- raw per-boundary and per-entity measurements;
- semantic identity and gauge consistency;
- observation provenance / confidence changes;
- topology failures;
- explicit `ok`, `review` or `unavailable` status and reasons.

## Metrics frozen before results

### Boundary displacement

Corresponding semantic boundary vertices are compared in canonical normalized
image coordinates. For every vertex the raw Euclidean displacement is retained.

For crown boundaries, displacement is also divided by the smallest radial
separation to an adjacent crown boundary at the same orientation index:

```text
displacement_tier_fraction
  = displacement_u / local_adjacent_tier_spacing_u
```

This makes the number interpretable as a fraction of local step spacing while
preserving real asymmetry. It is a normalization, **not a quality threshold**.

### Entity displacement

Where an entity has image-plane semantic support, the centroid of its referenced
support is compared between scaffolds. C1/C2/C3, table and girdle additionally
receive a family-local tier-spacing normalization. Pavilion supports remain
non-exclusive semantic support; the metric makes no direct polished-facet
projection claim.

### Identity consistency

The validator checks:

- the same semantic observation IDs exist;
- the same support IDs exist;
- support-to-semantic associations have not changed;
- the sequence-level semantic gauge ID has not changed.

A semantic/gauge change is `unavailable`, not a large numeric displacement that
can be averaged away.

### Evidence changes

For every semantic observation the raw record retains:

- reference/candidate provenance;
- provenance regression;
- observation-state regression;
- validity regression;
- reference/candidate confidence;
- confidence delta.

## Status policy

Version 1 intentionally sets **no numeric displacement pass/fail threshold**.
Those thresholds would be vulnerable to being selected after looking at the
validation outcomes.

- `unavailable`: missing/invalid scaffold, topology failure, or semantic/gauge
  identity cannot be compared without changing the ruler;
- `review`: identity/topology are valid but explicit evidence provenance,
  observation state or validity regresses;
- `ok`: contract remains valid without those regressions.

Raw displacement is always retained when comparison is structurally possible.
Later research may establish defensible thresholds, but that would be a declared
method revision rather than a hidden change to this frozen run.

## Anti-leakage boundary

The validation module accepts only already-produced #75 dictionaries. Its public
record builder has no image, fitter, target-value or target-file argument.

The DiaGem / Sergey values therefore cannot participate in fitting or in the
metric/status definitions above. #91 must perform its independent profile-image
extraction first, serialize that result, and only then compare it with the stored
external values in a separate post-extraction step.

This boundary is tested directly.

## Intended use by #89-#92

- #89 uses these metrics for leave-one-out/subset estimator stability and fixed
  ruler transfer.
- #90 uses the same metrics for source-pipeline and poor-view perturbations.
- #91 keeps external target comparison downstream of target-blind extraction.
- #92 consumes the raw validation records when issuing KEEP / REVISE / REJECT.

No P3 leakage, hall-of-mirrors, brilliance/fire/scintillation or Asscher quality
metric belongs in this layer.

## Tests

Run:

```bash
python -m unittest tests.test_asscher_geometry_validation -v
```

Coverage includes frozen-method fingerprinting, benchmark pinning, raw and
local-tier-normalized displacement, gauge/semantic-ID failures, provenance
status propagation, invalid topology, non-mutation, and the target-blind API
boundary.
