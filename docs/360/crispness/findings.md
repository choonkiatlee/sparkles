# Static tier-boundary crispness findings

Issue #50 asks whether static Asscher tier-boundary crispness can be measured robustly from ordinary vendor 360 imagery without mostly measuring the vendor image pipeline.

**Disposition: REVISE.** The experiment finds useful image-space structure, but none of the three primitives is ready for the buyer-facing retained descriptor profile.

Validation run: GitHub Actions run `37511719011`, implementation head `9bf0db15b26531ee5a2945443d41274543e85da9`, four versioned #18 source bundles, exact core `248..255,0..8`, wide sensitivity `240..255,0..16`. The full generated benchmark remains reproducible from the workflow; only the compact comparison and representative evidence are committed here.

## What was measured

The implementation reuses #19 boundary geometry and scores it on held-out frames through an interleaved two-fold cross-fit.

The three primitives remain separate:

- **strength** — median robust local edge z-score near the expected boundary;
- **continuity** — supported fraction across 96 rays plus longest unsupported angular gap;
- **positional consistency** — robust MAD of local radial peak offsets from the expected boundary.

There is no combined crispness score.

## Exact-core benchmark

| Stone | Boundary | Validity | Coverage | Strength | Continuity | Worst gap | Position MAD |
|---|---|---|---:|---:|---:|---:|---:|
| LG756580087 | centre-inner | review | 0.47 | 4.84 | 0.958 | 0.094 | 0.0172 |
| LG756580087 | inner-middle | review | 0.47 | 5.02 | 0.964 | 0.031 | 0.0228 |
| LG756580087 | middle-outer | review | 0.47 | 3.64 | 0.927 | 0.073 | 0.0240 |
| LG756520111 | centre-inner | review | 1.00 | 2.68 | 0.844 | 0.219 | 0.0136 |
| LG756520111 | inner-middle | review | 1.00 | 5.52 | 0.958 | 0.115 | 0.0199 |
| LG756520111 | middle-outer | review | 1.00 | 4.10 | 0.917 | 0.063 | 0.0200 |
| LG818659722 | centre-inner | review | 1.00 | 3.84 | 0.917 | 0.156 | 0.0129 |
| LG818659722 | inner-middle | review | 1.00 | 4.21 | 0.927 | 0.063 | 0.0242 |
| LG818659722 | middle-outer | review | 1.00 | 3.78 | 0.875 | 0.073 | 0.0213 |
| LG836619414 | centre-inner | ok | 1.00 | 3.31 | 0.927 | 0.198 | 0.0247 |
| LG836619414 | inner-middle | ok | 1.00 | 4.13 | 0.948 | 0.042 | 0.0258 |
| LG836619414 | middle-outer | ok | 1.00 | 3.53 | 0.844 | 0.188 | 0.0235 |

Validity is measurement/QC validity, not diamond quality.

LG756580087 exposes an important anti-circularity result: one 8/9-frame training half cannot independently recover the outer #19 boundary, so the other half cannot be scored. The resulting 8/17 coverage is now explicitly `review`; the full 33-frame sensitivity window recovers both folds. LG756520111 and LG818659722 inherit their existing upstream silhouette `review` status. LG836619414 is the only exact-core case with fully `ok` upstream + cross-fit validity.

## Source-pipeline stress tests

Holding the baseline geometry fixed makes the confound visible.

| Perturbation | Max strength change | Max continuity change | Max position-MAD change | Max rediscovered geometry shift |
|---|---:|---:|---:|---:|
| blur | 34.8% | 0.125 | 14.3% | 0.088 u |
| downsample / upsample | 43.5% | 0.146 | 20.8% | 0.031 u |
| JPEG Q70 | 7.3% | 0.021 | 8.7% | 0.006 u |
| mild sharpening | 21.2% | 0.042 | 6.9% | 0.000 u |

Gradient strength is therefore **not pipeline invariant in level**. Its cross-stone ordering often survives a uniform perturbation, which is encouraging, but that does not prove vendor comparability because the benchmark contains three Diajewel stones and only one Workshop stone.

Continuity is less contrast-like but is still meaningfully resolution-sensitive. Positional MAD changes less in absolute image space under most perturbations, but its stone ordering is not particularly stable when the observation window or resolution changes.

The geometry itself can also move under source processing: the largest case is LG818659722 under blur, where a rediscovered centre-inner boundary moves by about `0.088 u`. This confirms that pipeline sensitivity is not confined to the final scalar.

## Core vs wide sensitivity

Across the 12 stone × boundary rows:

- strength changes by a median **7.1%**, with a worst case of **24.8%**;
- continuity changes by a median **0.018** absolute, worst **0.031**;
- worst-gap fraction changes by a median **0.031** absolute, worst **0.063**;
- position MAD changes by a median **10.5%**, worst **47.0%**.

The exact-core and wide windows therefore tell broadly similar stories for continuity, but strength and especially positional consistency still have meaningful window dependence in individual cases.

## Does this add anything beyond #19?

Yes, but not enough yet for retention.

Across the 12 exact-core stone × boundary rows, Spearman rank correlation with #19 edge ratio is about **0.65** for the new edge-strength primitive and **0.72** for supported-fraction continuity. The relationship is much weaker for longest unsupported gap (**−0.23**) and positional MAD (**−0.10**). The latter two therefore are not merely renamed #19 edge-strength outputs.

That extra information comes with weaker stability, however. The current experiment therefore does not justify adding another production field merely because it is non-redundant.

## Comparison with #22 human observations

The two explicit #22 static-crispness strengths are LG818659722 and LG836619414.

- LG818659722's human-selected frames 252 and 0 generally show strong, well-supported held-out boundaries, so the primitives are directionally compatible with the review.
- LG836619414 is a useful counterexample to a naive rule. At human-selected source 8, the middle-outer boundary has only about **0.708** ray support and a **0.177** longest gap even though the human review still describes crisp nested tiers and coherent diagonal arms.

This means human "static geometric crispness" is broader than "every detected tier boundary is strong and continuous." It also includes the **diagonal-arm architecture**, which this first implementation intentionally does not measure.

The benchmark therefore provides partial correspondence, not a calibrated mapping from these three numbers to the human concept.

## Primitive dispositions

**Boundary strength — REVISE.** Visually intelligible and often stable in rank, but absolute level moves strongly under blur, resolution changes and sharpening. It is also partly redundant with #19 edge alignment.

**Boundary continuity — REVISE.** Adds a useful fragmentation notion and produces visually sensible failures, but changes enough under resampling that it is not yet a vendor-independent buyer-facing descriptor.

**Boundary positional consistency — REVISE / QC-only for now.** It is the most distinct from #19 edge strength, but is sensitive to window/geometry choice and does not cleanly track the human crispness examples.

**Combined crispness score — REJECT for this iteration.** There is no evidence for collapsing the primitives, and doing so would hide the source-pipeline problem.

## Recommended next iteration

If we revisit this family, the next experiment should first put every source through a **declared common spatial transfer function**: common effective diamond size plus fixed low-pass/resampling. Then test an edge-transition-width measure in normalized diamond units rather than relying primarily on gradient amplitude.

A separate diagonal-arm / windmill-legibility hypothesis should be tested rather than silently folded into tier continuity. Cross-vendor claims should wait for more than one Workshop sequence.

Until then, #50 should remain a successful **REVISE** research result and should not change the #45 retained profile.
