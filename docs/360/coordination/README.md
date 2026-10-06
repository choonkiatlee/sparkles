# Concentric-band coordination benchmark

Issue #32 measures whether neighbouring Asscher regions occupy brighter/darker **relative activation states together or in alternation**. It is a derived descriptor: it consumes `diamond360-activation/1` from #26 and does not recompute photometry, masks, support, or normalization.

## Measurement contract

The primary inputs are exactly the #26 survivors: coarse-fixed centre, inner and middle `relative_values`, where each trace is `log(regional median) - log(fixed-support whole-stone median)`.

For two aligned band traces `a_t` and `b_t`, the primary candidate is ordinary Pearson level correlation over aligned finite observations:

`r = corr(a_t, b_t)`.

Positive values describe bands occupying relative bright/dark states together; negative values describe alternating/opposed states. This is descriptive coordination, not a quality direction. Fewer than three aligned finite observations or a constant component trace makes the correlation unavailable.

The implementation also retains adjacent source-step events. For each valid pair it records `delta_a`, `delta_b`, whether their signs are the same/opposite/tied, and `min(|delta_a|, |delta_b|)` solely to choose strong coordinated/divergent evidence where **both** bands actually moved. Missing/rejected frames break adjacency; explicit `255 -> 0` requires upstream wrap provenance.

## Benchmark provenance

The primary benchmark is the exact 17-frame wrapped interval `248..255,0..8`; `240..255,0..16` is sensitivity only. The four stones are IGI-LG756520111, IGI-LG756580087, IGI-LG818659722 and IGI-LG836619414.

This validation derives directly from the full #26 benchmark `activation.json` outputs preserved in merged PR #35 history at commit `eccbb4fef10cb33bd91701121b68f9b958b25c4a`. Those outputs were generated from the canonical SHA-verified `benchmark-sources-v1` rotations before repository curation removed the bulky per-stone JSONs. Reusing them is intentional: #32's contract is to consume the retained #26 traces, not rerun brightness measurement.

## Result

**KEEP coarse-fixed centre ↔ inner Pearson correlation.** Core values are `+0.486, +0.434, +0.531, -0.102`; wide values are `+0.281, +0.400, +0.307, -0.027`. The exact ranking of the three positive stones moves around (core→wide rank rho ≈0.4), but the qualitative relationship is stable: the first three remain positively coordinated while LG836619414 remains approximately uncoordinated/slightly alternating.

**KEEP coarse-fixed inner ↔ middle Pearson correlation.** This is the strongest survivor. Core values are `+0.491, -0.624, +0.382, -0.219`; wide values are `+0.207, -0.818, +0.322, -0.708`. Every stone preserves correlation sign and cross-stone core→wide rank rho is ≈0.8. This distinguishes stones whose inner/middle activation amplitudes can be individually similar in scale but whose nested states move together versus against one another.

**REJECT adjacent-change sign agreement as a primary scalar.** It frequently sits near 50% even when Pearson correlation is strongly positive or negative—for example LG756580087 inner↔middle has core `r=-0.624` while same-direction fraction is exactly `0.50`. Pooled rank agreement with Pearson across the eight primary core stone×pair cells is only ≈0.49. Keep same/opposite event labels because they are useful for evidence selection, not as another descriptor field.

**REVISE middle ↔ outer.** It inherits #26's outer support problem. When outer support is healthy, fixed/dynamic correlations agree closely; when support degrades they can disagree sharply. LG836619414 wide has outer persistent support ≈0.199, with middle↔outer `r=-0.289` fixed versus `+0.537` dynamic. LG756580087 wide similarly falls to ≈0.295 support and moves toward zero/positive correlation.

**REVISE semantic coordination rather than promoting it.** Geometry can reverse the interpretation. In the core, centre↔inner is `+0.486` coarse versus `-0.514` semantic for LG756520111, `+0.434` versus `-0.403` for LG756580087, and `+0.531` versus `-0.668` for LG818659722. LG756580087's wide semantic activation remains unavailable upstream. This is useful falsification evidence, not evidence that semantic is automatically superior.

## Redundancy and interpretation

Correlation is not merely another activation-amplitude statistic. Across the eight primary core stone×pair cells, `|r|` has essentially no rank relationship with mean component activation excursion (Spearman ≈ -0.02). Signed `r` versus mean excursion is ≈0.69, reflecting some shared structure, but sign carries information that two individual excursion magnitudes cannot encode. The descriptor therefore adds a genuine pairwise relationship while remaining auditable back to #26.

The output keeps the full symmetric four-band correlation matrix for diagnosis, but only adjacent pairs are candidates for the retained vocabulary. Non-adjacent pairs are not promoted into separate schema fields.

This still does **not** establish a hall-of-mirrors quality score. The safe interpretation is narrower: #32 measures whether nested relative-activation states are coordinated or alternating. Downstream evaluation can test whether this, together with activation/persistence, explains perceived hall-of-mirrors coherence.

## Automatic evidence

For every adjacent pair the runner deterministically selects the strongest coordinated event, strongest divergent event and a typical directional event, then can render both band traces plus the corresponding two source frames. Example core selections include:

- LG756520111 centre↔inner: coordinated `255→0`, divergent `254→255`;
- LG756580087 inner↔middle: coordinated `2→3`, divergent `254→255`;
- LG818659722 centre↔inner: coordinated `6→7`, divergent `254→255`;
- LG836619414 inner↔middle: coordinated `6→7`, divergent `249→250`.

The benchmark commit keeps aggregate numeric evidence rather than reintroducing the full generated image set removed during repository cleanup. A full source rerun can regenerate `coordination.json`, `coordination.csv` and evidence PNGs with `write_stone_outputs(..., processed=...)`.

## Disposition

| candidate | decision | retained role |
|---|---|---|
| coarse-fixed centre↔inner Pearson | **KEEP** | primary adjacent-band coordination |
| coarse-fixed inner↔middle Pearson | **KEEP** | primary adjacent-band coordination |
| coarse-fixed middle↔outer Pearson | **REVISE** | outer/support-sensitive candidate |
| semantic fixed pair correlations | **REVISE** | localisation/QC sensitivity |
| same-direction fraction | **REJECT** as primary | event/evidence audit only |
| non-adjacent pair correlations | **REJECT** as primary | compact matrix diagnostic |
| dynamic-support pair correlations | **REJECT** as primary | support-motion QC only |

Machine-readable values are in [summary.json](summary.json) / [summary.csv](summary.csv), with decisions in [dispositions.json](dispositions.json).
