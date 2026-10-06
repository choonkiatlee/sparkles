# Bright/dark persistence benchmark

Issue #29 measures how long registered image-space pixels remain continuously in the same relative-dark/non-dark state through an Asscher 360 sequence. It is a temporal descriptor of the recorded imagery, not calibrated duration, physical-facet tracking, leakage, fire, light return or a cut-quality score.

## Measurement contract

Persistence reuses the exact state retained by #27 and #28:

`dark = Y_t(p) < k * G_t`

with strict `<`, `k=0.65` as the baseline, and `0.60/0.70` as fixed global sensitivity probes. `non_dark` is simply the complement; it is not a separately calibrated bright state.

Runs are measured in consecutive requested source steps. Missing/rejected frames, invalid whole-stone references and support loss break runs rather than being bridged. Window endpoints censor runs. The final requested step is never joined back to the first.

For each eligible pixel and state, the kernel records its longest observed run. The principal regional candidate is Q90 longest-run length, also normalized by the **requested** 17/33 source-step window. The denominator is deliberately not each pixel's own support count, so a briefly visible pixel cannot look 100% persistent.

`fixed` support uses pixels supported in the region throughout the observed interval. `dynamic` allows frame-local support, but support loss terminates/censors the current run and re-entry begins a new run.

## Canonical four-stone benchmark

The benchmark SHA-verified all four `benchmark-sources-v1` release ZIPs and every contained source frame, then reran preprocessing with `accept_review=True`, semantic step bands, and persistence on:

- core: exactly `248..255,0..8` (17 source steps);
- wide sensitivity: `240..255,0..16` (33 source steps);
- thresholds: `0.60/0.65/0.70`;
- geometry/support: coarse + semantic × fixed + dynamic.

All requested core/wide frames were accepted. LG756520111 and LG818659722 retain the same upstream segmentation `review` status already documented by the earlier benchmark; LG756580087 and LG836619414 are `ok`.

Machine-readable aggregate results are in [summary.json](summary.json), [summary.csv](summary.csv), and [dispositions.json](dispositions.json). Full per-stone traces remain generated artifacts rather than repository history.

## Result: what survives

**KEEP coarse-fixed inner-band dark Q90 persistence as a secondary temporal descriptor.** Across the four stones its core→wide rank correlation is ≈0.82. Threshold rank correlation versus the baseline is ≈0.82 at `k=0.60` and ≈0.83 at `k=0.70`. Fixed and dynamic support give the same inner-band Q90 in both windows. The core values span about 0.18–0.35 of the 17-step window, so the scalar discriminates without immediately saturating.

**REVISE centre dark persistence.** It is visibly meaningful in individual cases, but core→wide rank correlation is only ≈0.63. Keep the trace/evidence as a diagnostic rather than a retained comparison scalar.

**REVISE middle dark persistence.** Core→wide rank correlation is ≈0.71 and fixed/dynamic support is robust, but at `k=0.70` all four core stones collapse to the same Q90 value. The observable is therefore too threshold-sensitive to promote yet.

**REVISE outer persistence.** Support policy materially changes the answer: dark Q90 fixed↔dynamic disagreement reaches ≈0.13 of the core window and ≈0.09 of the wide window. This is the same outer-support failure mode seen in #26–#28.

**REJECT non-dark Q90 persistence as a scalar.** It saturates at 1.0 for every coarse-fixed stone, region and both windows. The complement state is too common for its 90th-percentile longest run to discriminate this benchmark.

**REJECT Q50 and max as primary summaries.** Q50 is heavily tied/quantized (often 0–1 source steps); max is a single-pixel tail statistic and is correspondingly outlier/censor-sensitive. Both remain audit diagnostics.

**REJECT dynamic support as a separate primary definition for centre/inner/middle.** It duplicates fixed support almost exactly in the retained regions. Keep it as a falsification/QC view.

**REVISE semantic persistence rather than replace coarse geometry.** Dark-run rankings can invert sharply: core inner coarse↔semantic rank correlation is ≈-0.95 and middle ≈0; wide inner ≈-0.87 and middle ≈-1.0. This is localisation sensitivity, not evidence that semantic geometry is a better persistence definition.

## Relationship to occupancy and switching

Persistence is not a deterministic inverse of #28 switching. Within the four-stone core benchmark, cross-stone Spearman correlation of dark Q90 versus occupancy/switching is only ≈0.32/0.32 in centre, ≈0.32/0.32 in inner, and 0/0 in middle. In the wider window those relationships strengthen, so persistence should not be treated as a wholly independent quality axis.

The practical distinction remains useful:

- occupancy: **how much** of a region is dark;
- switching: **how much reconfigures** between adjacent steps;
- persistence: **whether dark states cluster into longer uninterrupted episodes**.

The four-stone evidence supports keeping dark persistence as a **secondary structure descriptor**, especially for identifying "sticky" dark inner-step behaviour, not as another score to add mechanically to occupancy/switching.

## Censoring and evidence

Censoring is explicit in every cell. For retained coarse centre/inner/middle baseline cells, the fraction of pixels whose longest run is censored is generally low-to-moderate rather than dominant; gaps/support/reference failures are separately counted.

Representative panels intentionally remain sparse:

- [LG818659722 core coarse-centre fixed](per-stone/IGI-LG818659722/core/evidence/coarse-centre-fixed.png): high centre dark persistence example.
- [LG836619414 core coarse-centre fixed](per-stone/IGI-LG836619414/core/evidence/coarse-centre-fixed.png): low-persistence centre control.
- [LG818659722 core coarse-inner fixed](per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed.png) vs [semantic inner](per-stone/IGI-LG818659722/core/evidence/semantic-inner_step-fixed.png): geometry/localisation disagreement.
- [LG836619414 wide coarse-outer fixed](per-stone/IGI-LG836619414/wide/evidence/coarse-outer-fixed.png) vs [dynamic](per-stone/IGI-LG836619414/wide/evidence/coarse-outer-dynamic.png): support-sensitive outer case.

Panels show representative long dark/non-dark runs at start/middle/end. Red pixels remain dark through the highlighted dark run; yellow pixels remain non-dark through the highlighted non-dark run. These are falsification aids, not facet identities.

## Reproduce

After preprocessing and Asscher-step outputs exist for a selected interval:

```python
from diamond360 import persistence_benchmark as pb

result = pb.measure_stone(
    processed="/path/to/processed",
    step_output="/path/to/steps",
    indices=[248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8],
    wrap=True,
)
pb.write_stone_outputs(
    result,
    "/tmp/persistence",
    "/path/to/processed",
    "/path/to/steps",
)
```

The canonical source bundles and SHA-256s are indexed by [../benchmark/source-bundles.json](../benchmark/source-bundles.json). The focused persistence test suite covers strict threshold semantics, run boundaries, gaps, invalid references, support loss/re-entry, endpoint censoring, requested-window normalization, validity propagation and evidence generation.

## Repository-size policy

Only aggregate results and six representative evidence panels are committed. Full per-stone persistence JSON/CSV, exhaustive evidence panels, extracted sources and preprocessed stacks remain reproducible generated artifacts and stay out of Git.
