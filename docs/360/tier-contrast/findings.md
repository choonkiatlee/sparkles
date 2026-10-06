# Adjacent-tier contrast findings

## Disposition: **REVISE**

The question remains useful, but the first coarse-fixed whole-band formulation is
not a reliable proxy for visible tier legibility.

The primary candidate was reconstructed exactly for all four complete benchmark
stones from the committed fixed-support per-frame regional medians. This is
mathematically identical to subtracting the retained #26 log-relative traces
because the common whole-stone term cancels.

## What worked

- The measurement is simple, deterministic, auditable and requires no new
  photometric normalization.
- It clearly detects frames where coarse regional medians are strongly
  separated.
- Q90 cross-stone ranks are reasonably stable between the 17-frame core and the
  33-frame sensitivity window: Spearman rho = 0.8 for both centre-inner and
  inner-middle in this four-stone sample.
- Signed contrast remains useful audit context for which adjacent band is
  brighter.

## What failed

The low-tail and typical summaries are not stable enough to act as retained
cross-stone descriptors:

| pair | Q10 core/wide rank rho | Q50 core/wide rank rho | Q90 core/wide rank rho |
|---|---:|---:|---:|
| centre-inner | 0.0 | 0.2 | 0.8 |
| inner-middle | -0.4 | 0.0 | 0.8 |

More importantly, the metric has direct visual counterexamples in the #22
calibration frames:

- **LG756520111:** frame 248 is part of the human evidence for readable nested
  tiers, yet inner-middle separation is only about **0.00024**.
- **LG756580087:** the review's clean broad tiers are visible across
  248/254/0/4 while centre-inner separation remains only about **0.007-0.016**.
- **LG818659722:** static geometry is described as crisp at frame 0 while
  centre-inner separation is only about **0.0079**.
- **LG836619414:** crisp layered tiers at frame 0 coexist with inner-middle
  separation of only about **0.0127**.

So averaging an entire coarse band can erase local adjacent-tier contrast that
the eye still reads clearly.

## Redundancy

At n=4 these are diagnostics only, but they reinforce the concern:

- centre-inner Q50/Q90 rank correlation with mean component activation is 0.8;
- inner-middle Q50/Q90 correlation with mean component activation is 0.8;
- inner-middle Q50/Q90 correlation with mean component occupancy is 0.8.

The simple scalar therefore has not shown convincing incremental information
over the retained vocabulary.

## Standardized challenger

The code implements the planned within-band-spread standardized formulation, but
it is not promoted on the basis of this benchmark.

It still requires the processed pixel arrays from the versioned benchmark source
bundles. More importantly, normalization cannot recover spatial tier contrast
that was already averaged away in the coarse-band numerator. The standardized
candidate should therefore be treated as a falsification/control when the raw
bundles are run, not as an assumed fix.

## Recommended revision

Keep the **adjacent-tier contrast** research question, but change the spatial
primitive before adding more scalar normalization.

The next experiment should compare adjacent radial bands **locally** -- for
example within matched Asscher side/corner sectors or narrow
boundary-neighbourhood strips -- then ask whether local separations aggregate
into the visible impression of readable versus collapsed tiers.

This remains #49 work. It should not be confused with #51, which asks whether
the inner region itself is internally flat/pale even when it is well separated
from its neighbours.

## Downstream recommendation

Do **not** add the current coarse separation values to #45 or #23. Preserve the
code and benchmark as a falsified/revision baseline so the localized successor
has to demonstrate that it fixes these concrete counterexamples rather than
merely producing another correlated scalar.
