# Spatial articulation revisions (#59)

Issue #59 follows #51 after the global within-inner `Q90-Q10` spread proved
spatially blind. The earlier pale/quiet-inner annotations are **AI-generated
from prior Sparkles evaluations**, not independent human labels. This work
therefore tests source-evidence falsifiability and incremental measurement value;
it does not claim human perceptual validation.

## Candidate 1 — spatial contrast participation

Use the exact #26 **coarse-fixed inner support** and partition it into eight
fixed angular sectors around the support centroid. Sector 0 is centred on
registered east and the remaining sectors proceed counter-clockwise.

For each frame, compute the median luminance in each sector and work in log
luminance so multiplicative brightness changes cancel.

The audit outputs are:

- `cell_log_spread`: Q90-Q10 of the eight log cell medians;
- `contrast_participation`: effective participating-cell fraction from the
  absolute deviations of cell medians from their median;
- `distributed_contrast`: `cell_log_spread * contrast_participation`;
- `adjacent_log_contrast_median`: median absolute difference between adjacent
  sector log medians.

`distributed_contrast` is the primary research candidate. It is deliberately
low when a similar tonal range is concentrated in only a few sectors.

The eight-sector partition is a coarse spatial probe, **not** a claim that the
sectors correspond to physical facets. If it works but localisation is visibly
too crude, issue #59 candidate 3 can test an Asscher-specific panel partition.

## Candidate 2 — two-sided contrast coverage

On the same fixed support, use the frame's inner median `M_t` as the reference.
For a fixed ratio `r > 1`:

- dark: `Y < M_t / r`;
- bright: `Y > M_t * r`;
- `balanced_coverage = min(p_dark, p_bright)`.

The primary ratio is `r = 1.15`, with `1.10` and `1.20` retained as
predeclared sensitivity checks. The use of the **inner median** is intentional:
this candidate asks how much of the inner area participates on both sides of its
own typical level, rather than repeating #27's whole-stone-relative dark
occupancy.

Additional audit outputs retain dark fraction, bright fraction, total extreme
coverage and a two-sided balance statistic.

## Shared controls

Both candidates:

- use the exact #26 coarse-fixed inner support;
- use the 17-frame core as primary and 33-frame wide as sensitivity;
- preserve gaps and upstream validity;
- introduce no per-stone thresholds or tuning;
- are brightness-scale invariant by construction;
- retain #51 `global_raw_spread` beside each frame for direct redundancy tests;
- compare against retained inner activation, occupancy and mobility plus merged
  #49 adjacent-tier contrast;
- automatically select low/median/high and fixed-2%-brightness matched evidence.

The benchmark output uses the legacy
`docs/360/calibration/human-observations.json` path only as a secondary
AI-evaluation consistency check. That filename/schema is a compatibility
misnomer; those annotations are not human ground truth.

## Run

With the canonical full source bundles extracted as documented in
`docs/360/benchmark/README.md`:

```bash
python -m diamond360.spatial_articulation_benchmark \
  docs/360/benchmark/benchmark.json \
  --source-root outputs/benchmark-sources \
  --output /tmp/spatial-articulation \
  --tier-contrast-summary docs/360/tier-contrast/summary.json
```

The per-stone output includes full JSON traces, compact CSVs and separate
source-frame evidence panels for spatial participation and contrast coverage.
The top-level benchmark compares core/wide stability and redundancy. A reviewed
KEEP / REVISE / REJECT decision belongs in `findings.md` / `dispositions.json`,
not in the automated measurement code.

## Canonical four-stone result

The full canonical benchmark was run against the four complete source bundles
with merged #49 as a redundancy comparison.

Reviewed dispositions:

- **KEEP `distributed_contrast`** as a descriptive spatial-organization
  primitive. Core→wide stone-rank Spearman is 0.8 for Q10/Q50/Q90; core-Q50
  Spearman is 0.4 versus #51 global spread, inner occupancy and inner mobility.
- **REJECT `balanced_coverage_1p15` as a standalone descriptor.** Its Q50
  core→wide Spearman is 0.0 and the 10/15/20% sensitivity variants materially
  reorder the four stones; its primary Q50 ordering is also rank-identical to
  occupancy, mobility, #51 spread and #49 inner↔middle contrast in this n=4
  diagnostic.

The important interpretation limit is that distributed contrast is **not a
quality score**. LG818659722 is the highest core-Q50 stone because its broad
grouped-dark structure distributes strong contrast across the inner sectors.
That is genuine spatial organization, but not automatically attractive.

See `findings.md` for the reviewed source-evidence interpretation and
`dispositions.json` for the machine-readable decision. A compact primary
core/wide comparison is retained in `primary-summary.csv`; the full generated
evidence bundle remains reproducible from the canonical release sources.
