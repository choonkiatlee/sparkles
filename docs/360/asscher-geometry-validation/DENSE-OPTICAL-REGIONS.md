# #123: dense contiguous optical brightness/contrast regions

## Why

The original RGB studies show genuine appearance changes as Asschers rotate,
but neither a moving line nor a locally connected corner proves the identity
of a physical polished facet. Both existing optical-motion pilots (#178,
#179) are now squash-merged and kept **optical-only**. #179 compares sparse
source-selected contrast-line candidates (only six *truly consecutive*
windows); #178 samples 34 neighboring source RGB pairs in a limited set
of locations, without a regional brightness/darkness decomposition.

The next bounded question is: **where in the registered image does light or
dark contrast appear, disappear or switch between real consecutive frames?**
Do not ask which crown/pavilion facets these pixels belong to.

## Frozen, reproducible selection

From each of the four SHA-256-pinned 256-frame original-camera RGB sources,
rerun the *unchanged* #73/#80 pipeline and use only the frozen #96 selected
outer-octagon view positions to locate the research window.

In cyclic rotation order, exclude the *largest gap* between selected anchor
positions. The complement is the **shortest contiguous circular source arc
covering all selected views**; extend the arc exactly two source positions
at either end. Analyze **every consecutive pair** in this predeclared
window, including non-selected intervening frames and the 255→0 wrap.

Bound to at most 36 pairs per stone; a longer window is an explicit failure,
not silently truncated or cherry-picked. Keep all crown-view metadata:
resolved-likely-crown permits only neighbors with the same role; unresolved
stones remain uncertain with **no** physical facet interpretation.

For every eligible pair, use the exact #80 sequence-gauge-to-original-camera
map and intersect the two observed stone silhouettes and valid RGB footprints.
Erode the common interior before measurement. An unsupported source is marked
`unavailable` instead of assigning a dark or bright zero.

## Measurements (NOT facets)

- Raw camera-RGB median luminance ratio is retained separately from
  normalized brightness, so an overall exposure change isn't called a
  local flashing feature.
- Normalize each common-interior image by its own median. Record overall
  median and p90 absolute change, and separately the fraction of pixels
  that switch **relative dark** (brightness <0.70×frame median) or
  **relative bright** (>1.30×frame median) status.
- Use a fixed **4×4 rectangular gauge-space image grid**, not facet,
  ring, sector, or physical-boundary polygons. For each directly supported
  grid patch, report median signed/absolute change, dark- and bright-area
  occupancy before and after, switching fractions and extreme
  dark→bright / bright→dark percentages.
- These thresholds are frozen *relative optical descriptors*, not
  physical reflectance or absolute light-return measures. In particular,
  changing lighting, exposure, pose or camera registration can alter
  appearance even when actual diamond facet planes do not move.
- A bin with <80 common interior pixels is unavailable. No physical facet
  labels, angles, virtual-vs-real predictions, performance grades or
  interpreted facet motion. Even strong evidence can be a virtual facet.

## Visual QC

For **every** supported consecutive pair, render original source-camera RGB
A/B crops beside a signed, gain-normalized change map. Map red=relatively
brighter, blue=relatively darker *inside only the common valid eroded stone
footprint*. Outside that region the heatmap is blank, explicitly preventing
#178's initial false image-border contrast. Draw only the measured fixed
4×4 grid. Produce per-stone contact sheets with original source indices,
missingness, and crown-view labels in the JSON.

CI asserts the frozen #96 anchor source indices and *pixel-for-pixel
numeric agreement* of median normalized appearance change with the final
merged #178 artifact for every overlapping pair. This prevents new
region statistics silently changing the optical appearance baseline.

## Acceptance

- [ ] Synthetic examples: pure global exposure scaling cannot create
  normalized flashing, a localized optical darkening can, and off-stone
  changes do not register; 256-cycle wrap and overwide arcs are checked.
- [ ] All four frozen camera-RGB source SHA-256s and #96 anchors match.
- [ ] Every new pair is consecutive, duplicate-free, with unchanged
  overlap results compared with #178 wherever shared.
- [ ] Actual original-RGB comparisons visually reviewed, including
  IGI-LG756520111 around src 13/16 and the high-change but unresolved
  crown-facing IGI-LG836619414.
- [ ] Report the measured/unavailable pair and grid-bin counts, and a
  KEEP or REVISE interpretation of **optical** brightness dynamics only.

No production #96 geometry, #92 handoff, diamond grade, surface angles,
automatic virtual-facet labels, or #90 source stress.
