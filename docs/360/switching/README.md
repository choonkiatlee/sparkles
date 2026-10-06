# Bright/dark switching benchmark

This directory completes issue #28. It measures **recorded bright/dark state reconfiguration** between adjacent source steps; it is not sparkle frequency, calibrated angle/time, leakage, fire, physical facet identity or a quality score.

## Measurement contract

The state is reused exactly from issue #27:

`D_(p,t)(k) = 1[Y_t(p) < k * G_t]`

with strict `<`, encoded brightness `Y`, and the same-frame fixed-support whole-stone median `G_t`. The operational baseline is `k=0.65`; `0.60/0.70` are sensitivity probes only.

For an observed adjacent requested pair:

`W_(p,t) = 1[D_(p,t) != D_(p,t-1)]`

A pixel counts only when supported on both sides. Missing/rejected frames break adjacency. `fixed` uses interval-wide persistent support; `pair_local` uses the two-frame support intersection. Entering/leaving support never becomes a switch.

The primary regional scalar tested here is:

`regional_switch_rate = total switched pixel-pairs / total eligible pixel-pairs`.

The primary window is exactly `248..255,0..8` (16 adjacent pairs). `240..255,0..16` is sensitivity only.

## Canonical sources

The benchmark uses the four immutable 256-frame ZIPs from GitHub release `benchmark-sources-v1`, indexed by [../benchmark/source-bundles.json](../benchmark/source-bundles.json). Every release ZIP SHA-256 and every frame SHA-256 is verified before preprocessing.

As a migration check, the release-based rerun exactly reproduced the aggregate rows from an independently regenerated, hash-verified live-vendor run. The release assets are therefore the canonical reproducible input; no vendor fetch is needed.

## Result: what survives

**KEEP coarse-fixed inner and middle regional switching rate.** Core→wide cross-stone rank correlation is 0.8 in both bands. Threshold rank ordering is unchanged at both `k=0.60` and `0.70` versus `0.65`. Fixed and pair-local support are effectively identical here.

**REVISE centre regional switching rate rather than promote it as a primary scalar.** Threshold ordering is perfectly stable, but core→wide cross-stone rank correlation is only 0.4. The full centre pair trace remains useful, and its per-pixel Q90 is more window-stable, but the four-stone sample does not justify a primary centre switching scalar yet.

**REVISE outer switching.** Persistent fixed support falls to 0.199 for LG836619414 wide and 0.295 for LG756580087 wide. Fixed↔pair-local rate disagreement reaches about 0.046, so support choice materially changes the answer.

**REJECT pair-local support as a separate primary definition for centre/inner/middle.** Centre and inner are exactly identical to fixed support in all benchmark cells. Middle is also effectively duplicated: maximum absolute baseline rate difference is about 0.0012 and correlation is >0.9999. Keep pair-local output as QC/falsification.

**REVISE semantic switching; do not replace coarse geometry.** LG756580087 wide semantic bands are unavailable, LG836619414 wide semantic support collapses to 0.0076 in middle and 0.0017 in outer, and coarse↔semantic pair traces can disagree strongly. Semantic output remains localisation/QC evidence.

## Candidate summaries

| candidate | disposition | reason |
|---|---|---|
| regional switched/eligible pixel-pair rate | **KEEP** for coarse fixed inner/middle | direct normalized regional reconfiguration rate |
| regional rate, centre | **REVISE** | weak core→wide rank persistence (ρ=0.4) |
| regional rate, outer | **REVISE** | support-sensitive |
| per-pixel Q90 switch rate | **KEEP** as secondary diagnostic | active-tail summary; core→wide rank ρ≈0.82/0.89/0.95 for centre/inner/middle |
| per-pixel Q50 switch rate | **REJECT** as primary | heavily tied/quantized; often 0 or one switch per core window |
| fraction of pixels with any switch | **REJECT** as primary | still grows with observation opportunity; median core→wide increase is about 0.08/0.07/0.10 in centre/inner/middle |
| raw transition count | **REJECT** | mechanically window-length dependent |

The normalized regional rate does **not** mechanically rise with window length; it usually falls in the wider pose interval. Levels still depend on the declared pose window, so cross-stone comparison must use the same interval contract.

## Relationship to #27 occupancy

The scalar rankings are highly correlated with occupancy in this four-stone sample: pooled Spearman ρ≈0.92 across the 12 core coarse-fixed centre/inner/middle cells; inner and middle are each ρ=1.0 across stones.

That does **not** make the temporal trace redundant. For those same 12 traces, about 47%–84% of switching (mean ≈64%) is bidirectional state churn that cancels in the net occupancy change. Occupancy says **how much is dark**; switching says **how much of the spatial state reconfigured between adjacent steps**.

Disposition: retain switching as a complementary temporal/motion descriptor, but do not treat its scalar ranking as an independent quality axis to be naively added to occupancy. Redundancy with #30 contrast mobility remains for #30 to resolve.

## Evidence

Representative panels are intentionally sparse:

- [LG818659722 core coarse-inner fixed](per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed.png): high switching example.
- [LG818659722 core semantic-inner fixed](per-stone/IGI-LG818659722/core/evidence/semantic-inner_step-fixed.png): coarse↔semantic comparison.
- [LG836619414 core coarse-middle fixed](per-stone/IGI-LG836619414/core/evidence/coarse-middle-fixed.png): retained middle-band example.
- [LG836619414 wide coarse-outer fixed](per-stone/IGI-LG836619414/wide/evidence/coarse-outer-fixed.png) vs [pair-local](per-stone/IGI-LG836619414/wide/evidence/coarse-outer-pair_local.png): support-sensitive outer case.

Full pair traces are reproducible but deliberately not committed.

## Reproduce

Download and verify the release ZIPs using [../benchmark/source-bundles.json](../benchmark/source-bundles.json), then for each stone:

1. preprocess the complete source with gain `1.0`, its `diamond360-source/1` manifest, and `accept_review=True`;
2. run `diamond360.asscher_steps` on the exact core/wide wrapped interval;
3. call `diamond360.switching_benchmark.measure_stone` and `write_stone_outputs`.

Run repository tests with:

```bash
python -m unittest discover -s tests -v
```

The benchmark run used for this disposition passed all 109 repository tests.

## Repository-size policy

Git keeps only [summary.json](summary.json), [summary.csv](summary.csv), [dispositions.json](dispositions.json), this README, and five representative evidence panels. Full per-stone switching JSON and exhaustive evidence remain generated artifacts, not repository history.
