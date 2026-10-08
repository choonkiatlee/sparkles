# #92: real fixed-region brightness sensitivity to exposure and sampling extent

This is a narrow follow-up stacked on [real replay PR #180](https://github.com/choonkiatlee/sparkles/pull/180). The geometry scaffold, #80 registration, #89 per-frame entity support, source bundle hashes, viewer-frame indices and original image brightness inputs are **identical** to #180. It is not a new facet detector, perspective adjustment, cross-vendor normalizer, or optical quality model.

## The question

The first #92 real-source replay showed apparent temporal brightness changes under a fixed 2-D semantic ruler. How much of those brightness traces is sensitive to choices in how we sample a polygon and how an image was exposed, rather than to stable physically identifiable facet optical behaviour?

**Before inspecting output**, predeclare these paired counterfactual perturbations:

1. **Nominal:** the exact rasterized, unioned non-exclusive #74 support polygon via the merged #166 sampler; its mean brightness and pixel count are required to match the baseline JSON **exactly**.
2. **Core:** binary erosion of the *same* polygon union by one output pixel with 4-connected 2-D structuring element, intersected with the original valid stone mask.
3. **Expanded:** binary dilation of the *same* original polygon union by one pixel using the same cross-shaped element, capped to the original valid stone mask. Neither variant changes a scaffold vertex or provides physical facet ownership.
4. **Exposure only (after canonical registration):** apply synthetic multiplicative 0.85 gain; clipped 1.10 gain; and additive +0.05 clipped to [0,1]. These are deliberate tests of image brightness sensitivity—not calibrated or representative transforms between IGI/Loupe360/v360 capture conditions.
5. **Contrast diagnostic:** for each unchanged valid stone footprint, record the 10th and 90th image quantiles. \`(region_mean - q10)/(q90 - q10)\` is **only** an affine-exposure sensitivity diagnostic, not an empirical vendor correction. Set it \`null\` when global image contrast vanishes. Also record saturation fraction so clipping can be detected.

All variants run on the **original registered pixels** for exactly the 11 predeclared original-source frames \`[250,252,255,0,2,5,8,11,13,16,19]\` and two pinned source bundles from #180. The original #89 artifact is loaded by SHA and its semantic gauge, per-source quarter-turn, support status and confidence retained.

## Separate honest outputs

Each of the 55 entities in every frame records:

- nominal raw mean and 10/90-relative contrast diagnostic;
- original nominal, 1px-core and 1px-expanded pixel counts;
- core and expanded brightness changes, or null if no pixels remain;
- actual counterfactual exposure means and differences;
- contrast differences from the nominal for each exposure variant, nullable when the denominator collapses;
- original support status, confidence, source phase, original archived artifact hashes, unresolved C3/table facet-correspondence status.

A per-entity summary reports **raw observed across-frame intensity range** and separate median absolute and p90 magnitude of each **paired** perturbation. These are not scored against arbitrary pass thresholds or used to pick one polygon size. Both original (likely-crown) LG756520111 and crown-unresolved LG756580087 stay in the benchmark, with unresolved face identity explicit.

The summary PNG displays the predeclared six N-labelled supports and their median absolute shifts under core/expanded/+10%-clipped-gain. It deliberately does not report expert cut grades, projected plane angles, optical quality, physical facet-specific scintillation or cross-vendor-calibrated brightness.

## Why the comparison matters

- If a region's apparent brightness swing resembles or is smaller than the changes induced by only one sampling pixel of geometric footprint change, it is premature to claim robust facet-identified optical dynamics.
- If the clipped +10% exposure perturbation materially changes mean brightness or 10/90-normalized contrast, source imaging may dominate cross-vendor comparisons. **An affine mathematical invariance proof does not establish invariance of vendor images with nonlinear/unknown response.**
- A large stable image-plane photometric variation is still not a unique assignment to a polished C3/table facet, because the original #123/#124 RGB diagnostic did not verify inner polished boundaries.

## Non-goals / guardrails

- No refits, geometry updates, source-specific right-P1 adjustment or virtual-facet classification.
- No source stress benchmark, large synthetic rendering pipeline, or full optical performance score.
- This is a *descriptive sensitivity audit* of two real stones, not held-out proof of a source-invariant optical metric. Any future normalization needs separate calibration and independent source evidence.
- Keep #92's eventual disposition **REVISE** for physical inner facet association; the fixed support sampler itself can be kept provisionally as image-plane instrumentation.

## Running

The dedicated extended #180 workflow runs the usual archived #89 real frame replay, this time with \`--sensitivity\` on both stones. It uploads the original \`real-fixed-ruler-brightness.json\`, the baseline trace PNG, plus \`real-fixed-ruler-sensitivity.json\` and \`real-fixed-ruler-sensitivity.png\` for each stone. Focused regression tests run entirely on synthetic **fixed masks and brightness** first and do not reprocess the full 256 frames locally.

The original archived #89 geometry report and cut-angle comparison #165 are never changed. If this stacked PR is merged after #180's squash merge, rebase/retarget it to include only the sensitivity changes, not duplicate the parent.
