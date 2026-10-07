# Karl_K / strmrdr expert observation corpus

Issue #82 turns the Karl_K / strmrdr evidence already archived by #64 into a small machine-readable corpus for downstream falsification. It does **not** add new labels, infer hidden facet identities, or promote expert commentary to objective ground truth.

Files:

- `expert-observation.schema.json` — versioned structural contract (`sparkles-expert-observations/1`);
- `expert-observations.json` — normalized observations and validation-use designations;
- `benchmark-manifest.json` — source/media record of truth inherited from #64;
- `source-catalog.json` — original #64 semantic/provenance catalog.

## Interpretation boundary

`source_wording` in v1 deliberately preserves the existing #64 **catalog paraphrases**. It is not represented as a verbatim PriceScope transcription. `source.wording_fidelity = catalog_paraphrase` makes that explicit. Exact thread/article location, reviewer attribution, sample/media linkage and post number are retained where #64 established them.

Source observation and Sparkles interpretation are separate layers:

```text
reviewer statement / source locality
              ↓
expert-observations.json
              ↓
machine_mapping.status = pending_geometry
              ↓
future #72 semantic geometry / #79 optical events
```

Do not back-fill `P3_N`, `P3_S`, optical-event IDs, or similar semantic identities from the reviewer wording. Those mappings belong to a later pass after #72 is validated.

## Included evidence

v1 contains 27 atomic records from Karl K. / strmrdr-attributed #64 evidence:

- P3 article: explicit P3-angle/performance examples and controlled progressions;
- controlled corner/windmill sweep: geometry/style and preference observations;
- Asscher evaluation thread: sample-specific Karl observations on Target Centre, Glittery, Crispest and the Royal-Asscher-like negative control;
- four atomic records derived from Karl's general 360 heuristics: dance, simultaneous broad darkness, persistent darkness, and ambiguity of grey.

The corpus intentionally excludes #64 material whose reviewer is not established as Karl/strmrdr: the secondary windmill-thread "trade reviewer/designer" records, `Messy arrows`, and later community/purchaser comparison cases.

## Validation partition

The partition is intentionally conservative.

### Development / sanity

P3 simulations and the windmill sweep are `development_sanity`. Some were already used in #64 / PR #70 descriptor falsification, so they must not later be described as untouched independent validation.

### Held-out candidates

The only sample-level held-out candidates are:

- `asscher-eval-glittery`
- `asscher-eval-crispest`

Both have complete archived D360 sequences. All Karl observations attached to a held-out sample are withheld together; for example the Crispest crown-height note stays with the same held-out sample even though the primary downstream optical question is its localized P3 leakage.

These samples are **not globally pristine**: legacy Sparkles descriptors were already run on them in PR #70. They may still serve as independent validation for a new #79 geometry/optical/event method only if their expert observations are excluded from method design, feature selection, thresholding and tuning.

If either sample is inspected or used while developing the future method, change its designation before presenting results.

### Not suitable

Target Centre and the Royal-Asscher-like control preserve useful expert statements but lack complete archived source motion, so v1 marks them `not_suitable` for reproducible machine validation.

General heuristics are `semantic_principle`; they help name phenomena but are not sample outcomes.

## Locality and viewing condition

The corpus keeps reviewer locality as text first. For example Crispest retains:

```text
top and bottom V in the centre between windmills
```

with `viewing_condition = face_up`.

The only source interval recorded in v1 is the frozen PR #70 wrapped face-up core for Crispest (`248..255,0..8`). It is explicitly described as a machine-side bracket of the source's face-up condition, **not** a reviewer-annotated frame interval.

## Anti-leakage rules

When using this corpus downstream:

1. freeze geometry / optical-region / event extraction before reading held-out observations;
2. run the frozen method on the held-out media;
3. compare machine output with phenomenon, locality and viewing condition afterwards;
4. preserve disagreements;
5. never tune thresholds or semantic mappings to make Karl's statement come out true;
6. if a held-out observation influences development, downgrade its validation designation.

The intended question remains narrow:

> Did Sparkles independently recover the same optical/perceptual phenomenon, in the same part/viewing condition of the stone, that the expert described?

That is stronger and more useful than fitting a generic good/bad label.
