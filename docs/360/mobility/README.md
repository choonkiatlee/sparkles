# Contrast mobility benchmark

This directory completes issue #30. Contrast mobility measures **continuous adjacent-step change in an already-retained activation trace**. It does not remeasure image brightness, redefine masks/support, introduce a bright/dark threshold, or claim sparkle frequency, fire, leakage, calibrated light return, physical facet identity or cut quality.

## Measurement contract

The implementation consumes the exact `diamond360-activation/1` result from issue #26.

For an activation trace `a_t` and an observed adjacent source-step pair:

`m_t = |a_t - a_(t-1)|`.

The signed delta is retained for audit, but mobility is its absolute value. Missing/rejected/non-finite observations break adjacency and are never interpolated. The explicit `255 -> 0` wrap is accepted only when the upstream requested interval declared wrapping.

No new coarse/semantic or fixed/dynamic experiment is performed. The primary local inputs are exactly the #26 survivors: coarse-fixed centre, inner and middle log-relative activation. Whole-stone fixed raw activation is tested separately because #26 retained it as a distinct broad observable. Coarse outer and semantic fixed traces are emitted only as inherited-REVISE sensitivity/QC. Dynamic-support activation was rejected by #26 as a primary definition and is not re-derived here.

The primary scalar candidate is the **median observed adjacent-step absolute change**. Q90 is calculated as an upper-tail audit candidate. Every output retains the complete pair trace and observed adjacent-pair count.

## Canonical benchmark

The primary interval is exactly `248..255,0..8` (16 requested adjacent pairs); `240..255,0..16` is sensitivity only. The benchmark reruns the four immutable 256-frame ZIPs from GitHub release `benchmark-sources-v1`, verifies release ZIP and frame SHA-256 contracts, reruns preprocessing and #19/#26, then derives mobility from the resulting activation object.

## Result

**KEEP median local relative mobility for coarse-fixed centre/inner/middle.** Across the 12 core stone × band cells, median mobility has pooled Spearman rho ≈0.85 with #26 total activation excursion: related, as expected, but not identical. The strongest disagreement is LG756520111 inner, where excursion ranks much higher than typical adjacent motion. Excursion measures interval range; mobility measures typical step-to-step change.

**Mobility is substantially distinct from #28 threshold switching.** Pooled core median mobility versus switching rate is only rho ≈0.41. LG756580087 is especially useful: centre has relatively high continuous mobility with relatively low switching, while middle has low continuous mobility but high thresholded pixel reconfiguration.

**REJECT whole-stone mobility as a separate primary descriptor.** Its four-stone core median ranking is identical to whole-stone total activation excursion (rho=1.0). The pair trace remains auditable, but another broad scalar would duplicate #26.

**REJECT Q90 as a separate primary scalar; retain it as audit.** Across the 12 primary local core cells, median and Q90 mobility rank very similarly (rho≈0.94). Q90 does not reveal a sufficiently independent ordering to justify another primary field.

**REVISE outer and semantic mobility by inheritance.** #30 does not upgrade an upstream #26 trace whose representation/support contract remains unresolved. Those outputs remain useful for sensitivity and falsification only.

## Cross-window evidence

Cross-stone core→wide rank correlation for median mobility is 1.0 for centre, 0.8 for inner, and 1.0 for middle. Q90 is 0.8, 1.0 and 1.0 respectively. These four-stone ranks are encouraging but do not establish population thresholds.

All 16 core adjacent pairs and 32 wide adjacent pairs are observed for the primary benchmark rows. Upstream segmentation review reasons for LG756520111 and LG818659722 propagate unchanged; the local mobility calculation never upgrades them.

## Representative falsification evidence

Only a small representative set is committed; exhaustive per-stone panels remain generated artifacts.

- [LG756520111 core coarse-inner relative](per-stone/IGI-LG756520111/core/evidence/coarse-inner-fixed-relative.png): strongest mobility-versus-excursion rank disagreement.
- [LG756580087 core coarse-centre relative](per-stone/IGI-LG756580087/core/evidence/coarse-centre-fixed-relative.png): relatively high continuous mobility despite low #28 switching rank.
- [LG756580087 core coarse-middle relative](per-stone/IGI-LG756580087/core/evidence/coarse-middle-fixed-relative.png): low median mobility despite high threshold-switching rate.
- [LG818659722 core coarse-inner relative](per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed-relative.png): strong visible large-mobility event plus near-static control.

The evidence question is deliberately narrow: do larger `|Δa|` pairs correspond to visibly larger changes in the region whose activation trace is being consumed?

## Disposition

| candidate | decision | retained role |
|---|---|---|
| coarse-fixed centre relative median mobility | **KEEP** | primary local continuous-change descriptor |
| coarse-fixed inner relative median mobility | **KEEP** | primary local continuous-change descriptor |
| coarse-fixed middle relative median mobility | **KEEP** | primary local continuous-change descriptor |
| whole-stone raw median mobility | **REJECT** as separate primary | pair-trace audit; redundant with whole-stone excursion |
| Q90 mobility | **REJECT** as separate primary | upper-tail audit |
| coarse-fixed regional raw mobility | **REJECT** as primary | activation audit only |
| coarse outer mobility | **REVISE** | inherits #26 support sensitivity |
| semantic mobility | **REVISE** | inherits #26 representation/support uncertainty |
| dynamic-support mobility | **REJECT / not derived** | #26 already rejected dynamic support as primary |

Machine-readable decisions are in [dispositions.json](dispositions.json); aggregate benchmark values are in [summary.json](summary.json) / [summary.csv](summary.csv).

## Reproduce

Use the release source index at [../benchmark/source-bundles.json](../benchmark/source-bundles.json). For each stone, verify/extract the release ZIP, preprocess at gain 1.0 with `accept_review=True`, run `diamond360.asscher_steps` on the exact wrapped core/wide interval, call `diamond360.mobility_benchmark.measure_stone`, and write outputs with `write_stone_outputs`.

The descriptor code intentionally calls the #26 activation runner and derives mobility from its returned trace object. It does not independently reconstruct photometry or regional activation.

Full per-stone JSON, CSV and exhaustive evidence panels are generated artifacts rather than Git history. Git keeps only the aggregate summary, this disposition, and four representative panels.
