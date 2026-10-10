# #123 — sensitivity of optical appearance to tiny registration errors

## Why

The already merged #178 / #182 / #187 show that original-camera
RGB differences can include shared image drift, ambiguous texture
matches and changing silhouette overlap. The subsequently merged #186
dense 4×4-grid optical switching atlas observed 74 true-consecutive
view pairs; those dark/bright transitions remain **optical appearance**,
not verified physical facets or a diamond-quality grade.

Before discussing perceptual consequences or transferring these
measurements to other sources, test whether the #186 dark/bright
switching is **robust to a one-pixel uncertainty** in source camera
registration or in what counts as the usable stone interior.

## Frozen target-blind experiment

- Exact four original SHA-256-pinned 256-frame source sequences; same
  frozen #96 outer-selected anchor frame indices and #73/#80 pose.
- Exactly the same 74 contiguous pairs and original image-plane
  4×4 bins as #186. One unperturbed trial must numerically reproduce
  the archived #186 median gain-normalized image change and whole-stone
  dark/bright switch fractions to 1e-10.
- **Nine predeclared mapping offsets:** zero and all eight possible
  (-1,0,+1) by (-1,0,+1) one-pixel shifts of the *second* gauged
  source-RGB luminance frame, its stone mask and its source validity.
  Shift uses blank fill and never wraps into the opposite edge.
- **Two footprint choices:** baseline and two extra gauge-pixel
  morphological erosions of both stone masks. The established #186
  eroded common silhouette is still applied after this change.
- Thus 18 trials per pair, all reported rather than tuning which
  displacement best matches observed optics. Every result retains
  exact source indexes, view/crown metadata, supported pixel counts,
  per-bin availability, and full parameter provenance.
- For each appearance metric (normalized median absolute change,
  dark switch fraction, bright switch fraction), record the exact
  baseline and the full supported-trial min/max, range and maximum
  change from baseline. A wide envelope indicates possible
  **measurement sensitivity**, not a facet attribute.
- Render baseline versus predeclared worst absolute-change trial
  as registered, **on-stone-masked** gauge-space change maps for
  inspection. The native original camera RGB comparison for each
  pair remains available in immutable #186's artifact.
- **Explicit missingness:** if an offset/footprint removes common
  support, mark that trial unavailable. Do not assign zero shift or
  zero optical variation.

## Controls

- Pure exposure scaling of a constant image remains zero normalized
  change under all offsets and footprints.
- Artificially misregistering textured but *identical* images produces
  optical differences, proving an appearance change is not
  automatically a virtual facet switching.
- Off-stone contrast changes never affect supported interior metrics.
- Empty masks remain unavailable.
- Four-stone CI must reject any baseline disagreement with immutable
  #186 per-pair results, changed #96 anchor selections or physical
  facet claims.

## Interpretation

This is a **sensitivity envelope**, not a registration correction:
do not subtract the perturbation from the observed difference or
interpret the largest/smallest trial as the true registration.
Comparisons across stones, suppliers, image resolutions, lighting
setups or crown uncertainty are not calibrated.

The old #96 outer geometry and the #92 nonexclusive image-support
handoff remain unchanged; C1/C2/C3/TABLE physical identity is
unavailable. No real/virtual classifier, 3D facet reconstruction,
optical quality score or #90 source stress is introduced.

## Completion

- [ ] Negative controls green.
- [ ] All four original source rotations verified by SHA-256.
- [ ] 74/74 frozen #186 pair baseline values exactly reproduced.
- [ ] Per-pair sensitivity envelopes and original RGB-linked change-map
      visual QC inspected.
- [ ] Research verdict KEEP/REVISE only for this optical QC instrument,
      with any low-overlap or uncertain crown flags carried through.
