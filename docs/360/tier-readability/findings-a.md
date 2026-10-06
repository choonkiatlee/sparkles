# PR A / A2 findings — boundary-local tier contrast

Issue: #57  
Implementation: PR #61

## Disposition: **KEEP as the research primitive; proceed to PR B/C**

The original PR A result was **REVISE** because two effects were mixed together:

1. core and wide windows independently rediscovered #19 geometry, so the ruler
   moved between sensitivity windows;
2. absolute strip widths `0.025 / 0.040 / 0.055` materially changed some
   magnitudes.

A2 fixes the first problem and makes the second explicit rather than hiding it.

The revised primitive is now:

- one **canonical 33-frame wide #19 geometry** reused for both core and wide
  contrast measurements;
- tier-relative strip scales `alpha = 0.25 / 0.40 / 0.55`;
- signed + absolute contrast preserved for all eight sectors;
- a per-frame/per-sector **multi-scale median consensus**;
- scale spread retained as sensitivity evidence;
- core-only #19 geometry retained only as a diagnostic;
- pair-specific partial geometry remains `review`, never silently upgraded.

This is good enough to be the measurement field consumed by PR B. It is **not**
yet a retained production descriptor.

## Revised measurement

For one boundary with adjacent references:

```
inside_width  = alpha * (boundary - inner_reference)
outside_width = alpha * (outer_reference - boundary)

inside  = [boundary - guard - inside_width, boundary - guard]
outside = [boundary + guard, boundary + guard + outside_width]

signed = log(B_inside) - log(B_outside)
L      = abs(signed)
```

with guard `g = 0.010`.

The three scale results remain auditable. Multi-scale consensus takes the
median over scale **within each frame/sector**; it does not collapse the eight
spatial sectors.

## Contract / falsification result

Focused tests and the full repository suite pass.

The tests now cover:

- exact log-ratio recovery, zero contrast and signed reversal;
- common multiplicative brightness invariance;
- explicit gaps rather than epsilon fixes;
- local sector cancellation hidden by whole-band aggregation;
- asymmetric tier-relative support;
- guarded edge-spike resistance;
- moving registered support without requiring identical persistent pixels;
- multi-scale consensus while retaining sector detail;
- partial-boundary provenance;
- mirrored adjacent-span fallback only as `review`;
- ambiguous/non-separable geometry remaining unavailable;
- explicit reporting of core-only vs canonical boundary movement.

## Four-stone result

The revised benchmark uses the same canonical wide geometry for both windows.

Semantic multi-scale consensus Q50:

| stone | pair | core | wide |
|---|---|---:|---:|
| LG756580087 | centre-inner | 0.0626 | 0.0633 |
| LG756520111 | centre-inner | 0.0589 | 0.0485 |
| LG818659722 | centre-inner | 0.1333 | 0.0762 |
| LG836619414 | centre-inner | 0.0878 | 0.0577 |
| LG756580087 | inner-middle | 0.1467 | 0.1407 |
| LG756520111 | inner-middle | 0.0457 | 0.0350 |
| LG818659722 | inner-middle | 0.1041 | 0.0790 |
| LG836619414 | inner-middle | 0.0977 | 0.0752 |

These values are descriptive only. Larger is not assumed to mean better.

## Core / wide stability

Cross-stone Spearman rank correlation of **semantic Q50** is now:

| pair | alpha=0.25 | alpha=0.40 | alpha=0.55 | multi-scale consensus |
|---|---:|---:|---:|---:|
| centre-inner | 0.8 | 0.2 | 0.8 | **0.8** |
| inner-middle | 1.0 | 1.0 | 1.0 | **1.0** |

For context:

- #49 broad matched-sector Q50: centre-inner 0.8, inner-middle 0.8;
- coarse tier-relative multi-scale control: centre-inner 0.2, inner-middle 0.8.

The main PR-A failure is therefore repaired: centre-inner no longer has 0.2
rank stability merely because core and wide used different semantic rulers.
The multi-scale semantic field reaches 0.8, while inner-middle reaches 1.0.

The single `alpha=0.40` centre-inner result is still only 0.2. This is exactly
why A2 keeps the scale family and consensus rather than nominating one middle
scale as canonical.

## Geometry diagnostics

Freezing geometry does **not** make #19 correspondence problems disappear; it
moves them to the correct place: QC.

The strongest diagnostic remains LG818659722 centre-inner:

- canonical wide median boundary: approximately `u=0.508`;
- independently rediscovered core-only median: approximately `u=0.595`;
- median absolute sector shift: approximately `0.087`;
- maximum sector shift: approximately `0.121`.

The contrast calculation now uses the canonical `u≈0.508` geometry in both
windows, so this movement cannot masquerade as descriptor sensitivity.
However, the consensus contrast itself still changes materially for this stone
(core 0.1333 vs wide 0.0762). That remaining window sensitivity is real
measurement/content sensitivity and should stay visible downstream.

LG756580087 provides the other important case. Its canonical wide #19 template
cannot recover middle-outer, but centre-inner and inner-middle controls remain
supported. They are retained as `review`; inner-middle's missing outer
reference is mirrored from the observed inner-side span and explicitly marked
as such. The full semantic step representation is still unavailable.

## Scale sensitivity

Tier-relative support removes the arbitrary absolute-width unit, but it does
**not** make scale irrelevant.

Across the 16 stone × window × pair cases, the relative range of single-scale
semantic Q50 spans roughly **1% to 82%**. Nine of sixteen cases move by more
than 20%, and five move by more than 50%.

The largest sensitivities are concentrated in LG756580087 and several
centre-inner cases. Therefore:

- no individual alpha is promoted;
- multi-scale consensus is the research default;
- per-sector/per-frame scale spread remains part of the output;
- PR B must not discard scale sensitivity when deriving Q25/median/weakest-link
  summaries.

## Visual evidence

The same-frame panels remain useful after revision:

- the semantic strips visibly follow the localized nested transition rather
  than averaging the whole coarse band;
- broad-sector and boundary-local formulations still produce genuine frame
  rank disagreements;
- the representative `alpha=0.40` overlay is only a visual aid; displayed
  scalar values are the multi-scale consensus.

The existing evaluation annotations are AI-derived, not independent human
ground truth. They remain qualitative cross-checks only. PR C still requires
genuinely human-entered frame labels.

## What A2 earns

Keep for PR B/C:

- canonical fixed #19 measurement geometry;
- tier-relative scale family;
- multi-scale per-sector consensus;
- scale-spread diagnostics;
- full signed and absolute eight-sector field;
- coarse-geometry control;
- geometry-correspondence diagnostics;
- explicit partial/mirrored `review` provenance;
- original-source evidence.

Do **not** yet:

- promote consensus Q50 to #45;
- assign a quality direction;
- choose one alpha;
- collapse the two boundaries into one score;
- fit thresholds on four stones.

## Next step

PR B can now safely consume this field to test:

- spatial coverage / Q25 vs median;
- joint centre→inner→middle weakest-link readability;
- signed instantaneous tonal ordering.

PR C remains the gate for production use: genuine frame-level human labels and
leave-one-diamond-out validation must determine whether these summaries track
visible tier readability and add information beyond the retained descriptor
profile.
