# #92: sensitivity of fixed-ruler optical traces to exposure and support-zone choice

This is **diagnostic only**, stacked on #180, which replays two original source
360 videos on **frozen** stone-level #89 geometry and #89 per-frame support.
The goal is to determine whether observed temporal brightness fluctuations
are robust to simple radiometric and support-boundary choices before downstream
work infers contrast/optical performance from any trace.

The source images, gauge, original supported semantic IDs, frozen scaffold,
archived #89 transfer rows and source indices remain unchanged. We do **not**
estimate physical facet planes or adjust the C3/table ring to improve curves.

## Two independently interpretable perturbations

**Exposure / photometric sensitivity**

For each selected frame, compute the empirical mid-rank percentile of *each
pixel* against the distribution of all pixels in that frame's frozen valid
stone/gauge mask. Average the percentiles in each frozen semantic polygon.

Unlike absolute canonical measurement brightness, mid-rank percentile
is mathematically unchanged by a **uniform positive affine exposure**
transform \`a * brightness + b\` when no saturation/clipping changes the
pixel ordering. This is a *negative control*, not a promise that vendor
lighting differences can be fully corrected. A nonlinear source transform,
local reflection, clipped highlights, gamma changes, different poses or
refraction may all modify the empirical image distribution and rank.

Also report the original full-stone masked median/IQR of canonical input
brightness and each entity's mean-minus-median/IQR (null when the reference
IQR vanishes). **No inter-vendor standardization** is inferred or fitted.

**Support-zone sensitivity**

With the exact same original stone-level scaffold and per-frame #89 statuses,
sample four deliberately fixed pixel-footprint variants:

- Original polygon union (exact #166 baseline).
- 1-pixel morphological inset.
- 2-pixel inset.
- 1-pixel outset (exploratory; may spill onto adjacent optical image regions).

All zones are intersected with the existing frame's valid stone/gauge pixels;
no unavailable entity becomes supported and no missing pixel is filled. Source
polygons **do not move** and brightness does not influence geometric placement.

For each semantic ID, report baseline raw brightness range across 11 original
frames, baseline percentile-rank range, and the median/maximum absolute
difference in rank between the baseline and each alternate sampling footprint.

The diagnostic is non-exclusive and supports many-to-many appearance: the
same pixel may appear in more than one semantic support zone, even when its
strong internal edge is a virtual facet rather than a polished facet.

## Expected interpretation, never a score

- If baseline raw image brightness varies but within-frame rank hardly moves,
  frame-wide exposure/photometry is a plausible contributor. This does **not**
  prove real return is invariant.
- If rankings vary when a zone is inset by one or two pixels, brightness is
  sensitive to poorly localized bright/dark boundaries; using that mean as
  a precise facet-level performance measure would be premature.
- Robustness to these *particular* footprints is NOT evidence that C3/table's
  polished physical-facet correspondence is correct, or that a region is a
  unique facet rather than a mixture of reflections.
- Null baseline or eroded support stays null, never a zero optical return.
  Viewer source indices are nominal rotation phases, not calibrated
  physical angles. The frozen LG756580087 crown face remains unresolved.
- This test does not produce scintillation, contrast grade, light-return
  quality score, cross-source normalization, P3 leakage or a physical
  facet-angle estimate. Future models must define separate domain-appropriate
  observability, calibration and stability gates.

## Provenance and artifacts

PR #180 processes **exactly two checksum-pinned full source sequences**
LG756520111 (likely crown face) and LG756580087 (face-role unresolved), and
downloads the exact archived [#89 fixed transfer artifact](https://github.com/choonkiatlee/sparkles/actions/runs/37830584391).
This stacked experiment reuses the **same** registered frames in memory
before they are deleted; no extra full-sequence source retrieval or geometry
fit occurs.

After one real replay, outputs per stone:
- \`real-fixed-ruler-brightness.json\`, original unchanged source brightness
  measurements from #180.
- \`real-fixed-ruler-traces.png\`, original unchanged brightness trace render.
- \`real-support-sensitivity.json\`, fixed mask variants, empirical rank
  samples, per-frame stone distribution and per-entity sensitivity.
- \`real-support-sensitivity.png\`, rank traces and compact footprint
  perturbation summary.

The new fast tests explicitly assert known affine exposure invariance, gauge
mask and frozen polygon support identity, bounded erosions/outset, null
preservation, unresolved C3/table label, all 55 entity IDs and no facet
scores. **Do not change the original #166 handoff algorithm.**

This is research input into [#92](https://github.com/choonkiatlee/sparkles/issues/92),
not an automatic KEEP of all inner facets nor a new method revision.

## Deliberate failure modes to inspect

Rank traces can stay stable even when absolute brightness moves because of
frame-wide exposure, yet remain highly sensitive to clipped highlights or
a two-pixel boundary exclusion. Conversely, genuine facet-like optical changes
can alter relative rank without proving polished facet identity. The frozen
`ok/review/unavailable` geometry statuses are always printed alongside
sample counts; regions with absent support must not be plotted as zero.
