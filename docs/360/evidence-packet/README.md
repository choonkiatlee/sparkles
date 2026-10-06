# Compact descriptor evidence packets

Issue #21 turns the descriptor-native evidence selected by #26–#33 into a small
source-indexed packet for #22 calibration and later Evaluate Asscher reports.

## Contract

Each packet uses `diamond360-evidence-packet/1` and records:

- the canonical #45 profile schema and core-window contract;
- exact original source frame / pair / run indices;
- every merged descriptor-native claim that points at the same exact event;
- retained #45 profile field IDs and redundancy groups;
- native validity/review reasons, never upgraded by #21;
- original source-manifest paths, hashes and source provenance;
- the deterministic selection rationale and near-duplicate group;
- a compact contact sheet rendered from original supplier JPEGs.

Registered frames, masks and overlays may remain useful diagnostics, but they are
not substituted for original-source evidence in the packet contact sheet.

## Selection policy

The selector is coverage-first and deliberately has no global numeric importance
score. It tries to cover these visual roles where evidence exists:

1. activity / motion;
2. relative-dark state / switching;
3. dark-state persistence;
4. nested-step coordination or alternation;
5. opposing-direction organisation;
6. flash morphology.

One exact event can satisfy several roles only when it contains the best
available native evidence tier for each claimed role. Incidental weaker or
wrong-sign claims remain attached for auditability but do not suppress a better
representative elsewhere. For example, switching, nested-step and
opposing-region claims that all select the same adjacent source pair can merge
into one item when each is representative. The nominal 4-item lower target is
soft: if fewer exact items already cover every available role, the packet is
not padded with repetition. The hard cap is six items.

For correlation descriptors, the representative native event follows the sign
of the retained #45 field: coordinated evidence is preferred for positive
correlation and divergent evidence for negative correlation. Morphology prefers
the descriptor-native matched-active-area contrast pair when available.

Near-duplicate grouping is non-destructive. Nearness alone never discards a
different behavioural claim.

## Reproduce the four-stone benchmark

First extract the verified release bundles described in
`docs/360/benchmark/source-bundles.json` under:

```
outputs/benchmark-sources/<certificate>/
```

Then run:

```bash
python -m diamond360.evidence_benchmark \
  --repository-root . \
  --source-root outputs/benchmark-sources \
  --output outputs/evidence-packet
```

The runner verifies the full source manifest, copies only the canonical 17
`core17` originals into temporary preprocessing inputs, calls the existing
#26–#33 descriptor implementations and their native evidence selectors, maps
the results through #45, and writes one `evidence.json` plus one
`contact-sheet.jpg` per stone.

The 1,024 source JPEGs remain release assets rather than Git history.
