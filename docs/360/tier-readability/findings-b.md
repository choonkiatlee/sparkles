# PR B findings — spatial coverage, joint nested readability and tonal ordering

Issue: #57  
Implementation: PR #67

## Disposition: **KEEP as research descriptors; proceed to PR C**

PR B does not create a production score. It derives three auditable descriptions
from the canonical PR-A/A2 multiscale eight-sector field:

1. **spatial coverage** for each boundary: Q25 / median / Q75 / Q90 plus IQR and MAD;
2. **joint nested readability**: sector-wise `min(|C-I|, |I-M|)`;
3. **signed instantaneous ordering**: monotonic outward, inner local minimum,
   inner local maximum, or exact tie.

All pair components, sector values and scale-spread diagnostics remain available.

## Why Q25 adds information

Median separation can look respectable even when several directions are nearly
collapsed. Q25 exposes that weak-direction coverage directly.

Strong same-frame examples from the retained benchmark field include:

- **LG756520111, source 4, centre-inner:** Q25 ≈ **0.0080** vs median ≈ **0.1392**;
- **LG756580087, source 7, inner-middle:** Q25 ≈ **0.0215** vs median ≈ **0.2654**;
- **LG818659722, source 253, centre-inner:** Q25 ≈ **0.0764** vs median ≈ **0.2286**.

This is the failure mode PR B was intended to preserve: a few strong sectors
must not make broad tier readability look uniformly good.

## Joint weakest-link is not redundant with pairwise medians

The strongest counterexample is **LG818659722, source 5**.

The weaker of the two pairwise sector medians is approximately **0.1821**, but
the sector-aligned joint weakest-link median is only **0.0482**: a penalty of
approximately **0.1340**.

That happens because the sectors that read well across centre↔inner are not
necessarily the sectors that read well across inner↔middle. Looking only at the
two pairwise medians therefore misses complementary directional collapse.

PR B records this explicitly as `joint_median_penalty` and surfaces the
strongest source-frame counterexample in the benchmark CSV.

## Four-stone wide-window descriptive values

These are research values only; larger is not assumed to mean better.

| stone | C-I Q25 | C-I median | I-M Q25 | I-M median | joint Q25 | joint median |
|---|---:|---:|---:|---:|---:|---:|
| LG756520111 | 0.0244 | 0.0485 | 0.0214 | 0.0350 | 0.0107 | 0.0218 |
| LG756580087 | 0.0408 | 0.0633 | 0.0424 | 0.1407 | 0.0257 | 0.0426 |
| LG818659722 | 0.0515 | 0.0762 | 0.0399 | 0.0790 | 0.0276 | 0.0482 |
| LG836619414 | 0.0343 | 0.0577 | 0.0436 | 0.0752 | 0.0243 | 0.0359 |

## Core / wide stability

Cross-stone Spearman rank correlation across the four benchmark stones:

| profile | Q25 | median |
|---|---:|---:|
| centre-inner | **0.8** | **0.8** |
| inner-middle | **0.8** | **1.0** |
| joint weakest-link | **0.4** | **0.4** |

This is an important distinction.

- Pairwise **Q25 + median** is currently the more stable coverage description.
- The joint weakest-link clearly captures information that pairwise medians
  miss, but its stone-level ordering is more window-sensitive on n=4.
- Therefore the joint field is worth retaining for PR C, but it has **not**
  earned production status or a quality direction.

The joint statistic also inherits substantial scale sensitivity, so PR B keeps
the maximum component scale spread per supported sector and its frame summary.

## Tonal ordering

Ordering is classified from the signed multiscale contrasts without an epsilon
or fitted threshold:

- `C > I > M` — monotonic light→dark outward;
- `C < I < M` — monotonic dark→light outward;
- inner local minimum;
- inner local maximum;
- exact tie.

No ordering state dominates consistently across all four stones/windows, and
there is no evidence here that one ordering is aesthetically superior. The
ordering output should remain descriptive until genuine frame-level human
calibration exists.

## What PR B earns

Keep for PR C:

- Q25 as a weak-direction / coverage-floor descriptor alongside median;
- Q75/Q90 and IQR/MAD as audit context, not extra quality scores;
- sector-aligned joint weakest-link readability;
- explicit complementary-collapse evidence via `joint_median_penalty`;
- exact signed tonal-order state and state fractions;
- component and joint scale-spread diagnostics;
- per-frame values in the JSON and compact per-stone/profile CSV output.

Do **not** yet:

- choose a single master tier-readability scalar;
- fit thresholds;
- claim higher separation is always better;
- promote any field to #45;
- assign a preferred tonal-order state.

## Next step

PR C should calibrate these frame-level quantities against genuinely
human-entered labels and pairwise frame judgments, using leave-one-diamond-out
validation.

The most important comparisons are now:

- median vs Q25 for broad spatial coverage;
- pairwise medians vs joint weakest-link for simultaneous three-tier
  readability;
- whether tonal-order state adds explanatory value after separation magnitude;
- whether the joint field's lower core/wide stability is tolerable once judged
  against human-visible tier structure.
