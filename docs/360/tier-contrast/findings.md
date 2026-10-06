# Adjacent-tier contrast findings

## Final disposition for this research slice: **REVISE**

The adjacent-tier question survives, but the original coarse whole-band scalar
does not. The raw-pixel follow-up shows that **spatial localization, not
standardization, is the useful revision**.

## Coarse baseline: falsified as a production descriptor

The simple candidate is exact and auditable:

    D_ij,t = abs(log(B_i,t) - log(B_j,t))

because the common whole-stone term in the #26 relative traces cancels.

It nevertheless fails the visual question we care about. Whole-band medians can
cancel across directions even when the stepped tiers remain visually distinct.
The committed four-stone baseline also has poor core/wide ranking stability in
its low/typical summaries:

| pair | Q10 core/wide rho | Q50 core/wide rho | Q90 core/wide rho |
|---|---:|---:|---:|
| centre-inner | 0.0 | 0.2 | 0.8 |
| inner-middle | -0.4 | 0.0 | 0.8 |

So the coarse scalar is retained as a falsified baseline, not a descriptor for
#45/#23.

## Standardizing the coarse scalar does not fix it

The raw-pixel run tested the planned robust within-band normalization:

    S_ij,t = D_ij,t / sqrt((R_i,t^2 + R_j,t^2)/2)

with R = 1.4826*MAD/median on the same fixed support.

This changes scale but leaves the spatial averaging problem intact. Its
core/wide rank stability is not materially better:

| pair | standardized Q10 rho | Q50 rho | Q90 rho |
|---|---:|---:|---:|
| centre-inner | -0.8 | 0.4 | 0.0 |
| inner-middle | -0.4 | 0.4 | 0.8 |

A particularly clear counterexample is **LG756520111 frame 248,
inner-middle**: coarse separation is **0.00024**, and standardization only turns
that into **0.0030**. The visible local tier contrast has already been averaged
out of the numerator.

Disposition: **REJECT as the fix; retain as a control.**

## Localized matched-sector contrast fixes the observed failure mode

The revision intersects each adjacent radial band with the existing eight
image-axis side/corner sectors and compares matched local medians:

    L_ij,s,t = abs(log(B_i,s,t) - log(B_j,s,t))

All directional traces are retained. The experimental frame scalar is the median
across sectors; Q75 remains audit context.

This directly repairs the concrete coarse-cancellation examples:

| human evidence | pair / frame | coarse D | standardized S | localized median | localized Q75 | strongest local sector |
|---|---|---:|---:|---:|---:|---|
| LG756520111 readable tiers | inner-middle / 248 | 0.00024 | 0.0030 | **0.0148** | 0.0231 | side_S 0.0439 |
| LG756580087 pale-inner check | centre-inner / 0 | 0.0112 | 0.0708 | **0.0419** | 0.1000 | corner_SW 0.1227 |
| LG818659722 static crispness | centre-inner / 0 | 0.0079 | 0.0218 | **0.1004** | 0.1328 | side_W 0.1380 |
| LG836619414 static crispness | inner-middle / 0 | 0.0127 | 0.0701 | **0.1016** | 0.2120 | side_W 0.2892 |

The cross-window behavior also improves substantially:

| pair | localized Q10 rho | localized Q50 rho | localized Q90 rho |
|---|---:|---:|---:|
| centre-inner | 0.8 | **0.8** | 0.8 |
| inner-middle | 0.4 | **0.8** | 0.8 |

For comparison, coarse Q50 was 0.2 / 0.0 for the two pairs.

This is strong evidence that the **spatial primitive was the main problem**.

## Why this is still REVISE rather than KEEP

The sample is only four stones, and the localized summaries have not yet shown
clear incremental information beyond the retained descriptor vocabulary.

Diagnostic n=4 Spearman results include:

- centre-inner localized Q50 vs mean component activation: **1.0**;
- centre-inner localized Q50 vs nested-step coordination: **1.0**;
- inner-middle localized Q50 vs mean component occupancy: **1.0**.

These are not significance tests, and with n=4 they should not be over-read.
But they are enough to block promotion: the localized metric visibly fixes the
frame-level failure without yet proving that its cross-stone scalar adds a new
dimension.

So the current sub-dispositions are:

- **coarse simple:** REJECT as production descriptor; retain baseline;
- **coarse standardized:** REJECT as remedy; retain control;
- **localized matched-sector:** REVISE / promising;
- **issue #49 overall:** REVISE.

Do **not** add #49 to #45/#23 yet.

## What the next calibration should test

The implementation is now sufficient for a larger sample. The next useful work
is not another normalization formula. It is to run the localized descriptor on
more labelled stones and test whether it predicts human tier readability after
conditioning on activation, occupancy and coordination.

If that larger calibration shows independent value, the most defensible
production candidate is currently **matched-sector median separation**, with the
full eight-sector trace preserved for evidence/audit.

## Boundary with #51

The pale-inner observations remain important counterexamples to conflating the
two hypotheses. A pale/flat inner region may still be strongly separated from
its neighbors. #49 is **between-tier separation**; #51 is **within-inner
articulation**.

Raw aggregate values are in [raw-pixel-summary.csv](raw-pixel-summary.csv);
sensitivity, representative counterexamples and redundancy diagnostics are in
[raw-pixel-findings.json](raw-pixel-findings.json).
