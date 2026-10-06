# Findings — within-inner tonal articulation (#51)

## Decision: REVISE

The proposed scalar is a valid **within-inner tonal-spread audit primitive**, but it is not yet a useful standalone research descriptor for the recurring pale / flat / quiet-inner observation.

The primary candidate is:

```
A_t = Q90(Y_inner,t) - Q10(Y_inner,t)
```

measured on the exact #26 coarse-fixed inner support.

## What worked

- The implementation is deterministic and uses unchanged #26 registration/support.
- Synthetic counterexamples behave correctly: flat support gives zero spread, equal-median regions with different structure separate, and gaps remain gaps.
- Exposure controls behave sensibly. Within each stone, `raw_spread` has ~0.98–0.99 Spearman rank agreement with both whole-median-normalized and log-spread variants.
- The evidence panels visibly track tonal range: low-spread frames look relatively uniform; high-spread frames contain strong light/dark separation.
- The fixed 2% matched-brightness counterexample works on the real sources. For LG756580087, sources 252 and 0 differ by only ~0.7% in whole-stone median brightness, yet raw inner spread changes from 0.250 to 0.460. The primitive is therefore not merely an exposure proxy.
- LG818659722, the grouped-dark control, has the highest core median raw spread (0.494), confirming that the metric is measuring real internal tonal range rather than simple brightness.

## Why it is not KEEP

The intended perceptual target is not simply “does the inner region contain both bright and dark pixels?”. The pale-inner annotations demonstrate that distinction:

- LG756580087 source 0 is explicitly part of the pale-inner check but has raw spread 0.460, the highest frame in its core window.
- LG836619414 source 8 is part of the pale-inner check but has raw spread 0.524, around the upper part of its core distribution.
- LG756520111's labelled pale frames span low/medium/high values rather than clustering at low articulation.

So Q90-Q10 can be large because a mostly pale inner region contains a few strong dark bands, or because broad opposing sectors create a dark/bright split. That is tonal **range**, not necessarily visually rich inner articulation.

The stone-level scalar is also not stable enough in its most natural summary. Core-vs-wide Spearman for raw Q50 is -0.2 (whole-median-normalized/log Q50 are -0.4), even though raw Q10/Q90 are more stable at 0.8.

Finally, the four-stone redundancy diagnostic is high. Raw core Q50 has Spearman 1.0 versus retained inner occupancy, 1.0 versus retained inner mobility, and 1.0 versus #49 inner-middle adjacent-tier contrast. With n=4 these are diagnostic rather than inferential, but they provide no evidence that this scalar adds an independent dimension.

## Interpretation

The failure is useful: the missing information appears to be **spatial organization and coverage of contrast inside the inner region**, not the existence of contrast itself.

A revised descriptor should distinguish, for example:

- a broad pale/quiet panel plus one narrow dark strip;
- balanced, distributed internal contrast across several inner panels;
- one broad grouped dark block opposed to bright sides.

That points toward spatial coverage/component-scale or sub-region contrast organization rather than another global percentile spread.

## Retained output

Keep `raw_spread` and its normalization challengers as auditable research outputs. Do **not** promote them into the retained #45 profile or treat them as an independent quality vote.

The compact four-stone core/wide results are in `summary.csv`; the full source-frame evidence was generated from the canonical release bundles during PR validation.
