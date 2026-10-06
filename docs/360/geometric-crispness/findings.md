# Geometric crispness v2 findings

Issue #55 revisits the #50 static-crispness result in two deliberately separate
directions: a normalized tier-edge measurement and a diagonal-arm / windmill
legibility prototype.

**Overall disposition: KEEP a small research subset, REVISE the rest, and do
not create a buyer-facing crispness score.** The common spatial transfer does
what #50 needed: transition width becomes much less sensitive to the controlled
source-pipeline perturbations. The diagonal experiment also finds reproducible
oriented structure, but several tempting geometry scalars remain unstable or
ambiguous.

The four-stone benchmark still contains only one Workshop source, so these
results can falsify bad definitions but cannot establish strong cross-vendor
invariance or aesthetic thresholds.

## Common spatial transfer

All frames are mapped to a declared effective diamond diameter of **160 px**
using silhouette area, support-weighted anti-aliasing before downsampling,
bilinear resampling and a fixed 1 px Gaussian low-pass. No benchmark frame is
upsampled: source effective diameters are roughly 185–211 px.

This is intentionally conservative. The normalization policy is fixed without
tuning to the four human labels and is serialized into every result.

**Disposition: KEEP as research infrastructure.**

## A. Normalized tier edges

The held-out frame does not rediscover semantic boundaries. #19 supplies the
three declared semantic radial zones. Inside each zone the frame estimates an
eight-sector consensus locus, and each ray can refine the transition only in a
small local neighbourhood around that locus.

The headline primitive is 10–90% derivative-mass **transition width in
silhouette-normalized radius units**. Gradient amplitude and local contrast are
QC signals only.

### Pipeline stress test

Maximum exact-core changes across the 12 stone × boundary rows:

| Perturbation | v2 transition-width max change | #50 gradient-strength max change | v2 confidence max abs change | v2 longest-gap max abs change |
|---|---:|---:|---:|---:|
| blur | 3.7% | 34.8% | 0.040 | 0.042 |
| downsample / upsample | 7.2% | 43.5% | 0.063 | 0.063 |
| JPEG Q70 | 2.2% | 7.3% | 0.009 | 0.021 |
| mild sharpening | 6.5% | 21.2% | 0.019 | 0.021 |

This is the main success of #55. Transition width is materially less coupled to
the synthetic source pipeline than #50's gradient-amplitude quantity.

Core → wide sensitivity is also small for transition width: median relative
change is about **1.1%**, worst case about **3.6%**.

### Is this just #19 renamed?

No. Using the original #19 edge-ratio diagnostic on the same 12 exact-core
stone × boundary rows, Spearman rho is approximately:

- transition width vs #19 edge ratio: **0.34**;
- soft confidence vs #19 edge ratio: **0.41**;
- longest low-confidence gap vs #19 edge ratio: **-0.25**;
- positional residual MAD vs #19 edge ratio: **0.48**.

Transition width also correlates only about **0.19** with #50's old
gradient-strength primitive. With n=12 these are descriptive checks, not
significance claims, but they are enough to show the new quantity is not merely
the old edge-strength measurement with a new name.

### Remaining weaknesses

The locally estimated position residual is still materially sensitive to
processing and window choice: worst controlled perturbation changes are roughly
12–22%, and the worst core→wide change is about 19%. It remains useful as a
diagnostic but is not ready as a retained scalar.

Soft confidence and gap morphology are much more robust than the old binary
continuity implementation, but their exact level still depends on the chosen
confidence construction/threshold. The full confidence field and longest gap
are more defensible than a fragment count.

### Tier primitive dispositions

- **Transition width — KEEP (research primitive).** Robust enough to continue
  into calibration. It measures one recognizable thing and does not collapse
  into #19 edge strength. This is not yet an aesthetic higher/lower-is-better
  field.
- **Soft confidence field — REVISE / QC.** Useful support information, but the
  absolute confidence level is partly definition-dependent.
- **Longest low-confidence gap — REVISE.** Visually meaningful and much more
  robust than #50 continuity, but not yet calibrated to perceived crispness.
- **Low-confidence fragment count — REVISE / secondary diagnostic.** It
  distinguishes fragmentation from one missing sector synthetically, but is
  threshold-dependent.
- **Position residual MAD — REVISE / QC-only.** Distinct from #19 but still too
  sensitive to processing/window choice.

## B. Diagonal-arm / windmill legibility

The first real-source pass exposed an important implementation failure:
independently choosing the strongest edge at every radius produced zig-zag
traces that jumped between unrelated reflections. The final prototype therefore
uses a smooth-path dynamic program inside each predeclared diagonal corridor.
Source-first panels now show traces that visibly follow coherent diagonal-arm
edges.

### Robust pieces

Across controlled source perturbations:

- median arm-visibility changes are about 0.005–0.017, with worst cases below
  0.030;
- orientation-coherence changes are generally small, with worst cases below
  about 0.034;
- longest-gap changes are at most about 0.063.

Core→wide changes are similarly modest for visibility and orientation
(maximum about 0.030 and 0.041 respectively).

The two #22 human static-crispness examples are directionally sensible:

- **LG818659722**, sources 252 and 0, shows clean four-arm traces with
  per-arm orientation alignment around 0.93–0.96.
- **LG836619414**, sources 0 and 8, still produces coherent diagonal traces
  despite imperfect tier/arm support; its per-arm orientation alignment is
  roughly 0.81–0.91 on those frames.

This captures the key #50 counterexample better than radial tier continuity
alone: a frame can retain legible diagonal architecture even when one boundary
or one arm segment has weak local support.

### What does not survive

Arm straightness is not stable enough. Although the smooth-path change makes
the overlays much more credible, straightness can still change by more than
100% in an isolated downsample case and by more than 60% between core and wide
for an individual arm.

More importantly, a single tracked edge is not a reliable estimate of the
**arm axis**. A diagonal arm has two plausible boundaries and the path can
follow either side. That contaminates angular offset, opposing-axis
misalignment and four-arm spacing. For example, LG818659722 can produce a
large opposing-axis misalignment despite the source panel showing visibly
coherent geometry.

A future axis/symmetry experiment would need to track both arm boundaries and
use their midline, rather than treating one edge trace as the arm centre.

### Arm primitive dispositions

- **Orientation coherence — KEEP (research primitive).** Visually auditable,
  robust to the controlled pipeline perturbations, and directly measures
  whether the detected arm edge has the expected diagonal orientation.
- **Visibility/confidence — REVISE.** Stable enough to be useful context, but
  local contrast affects its level and the current four human labels do not
  calibrate direction.
- **Longest weak radial gap — REVISE.** Useful morphology, but a large local
  gap does not by itself falsify perceived whole-pattern crispness.
- **Trajectory straightness — REVISE / QC-only.** The trace is now coherent,
  but the scalar remains too sensitive in individual cases.
- **Frame-window stability — REVISE / QC-only.** Useful for surfacing unstable
  traces, not yet a perceptual descriptor.
- **Opposing-axis misalignment / four-arm spacing from a single edge —
  REJECT.** The formulation confuses which side of the arm is being followed.

## Comparison with #22

The human evidence panels for LG818659722 sources 252/0 and LG836619414
sources 0/8 are the most useful output of this PR.

They show that static geometric crispness is genuinely composite:

1. **tier transitions can be locally narrow and readable**;
2. **diagonal architecture can remain coherent even where support is locally
   weak**;
3. neither every-tier-boundary-is-continuous nor every-arm-has-no-missing-sector
   is a valid definition of the human concept.

The current benchmark has only positive static-crispness labels for these two
stones, so it cannot yet establish a numeric good/bad direction. These
measurements should therefore stay descriptive until #22 has more positive and
negative examples.

## Final recommendation

Carry forward only two new primary research candidates:

1. **normalized tier transition width**;
2. **diagonal orientation coherence**.

Retain confidence/gap fields as evidence/QC around those candidates. Do not add
position residual, straightness, single-edge arm-axis geometry or any combined
crispness score to the #45 production profile yet.

If the expanded #22 sample repeatedly shows that arm symmetry itself matters,
the next targeted experiment should model **paired arm boundaries + midline**,
not further tune the current single-edge axis scalar.
