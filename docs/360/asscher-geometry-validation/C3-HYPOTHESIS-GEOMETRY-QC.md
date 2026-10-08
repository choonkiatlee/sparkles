# #124: Two competing C3/table hypotheses in original camera RGB

## Question

The frozen #96 inner evidence favors u≈0.579 with five selected frames
but can switch to u≈0.478 when a single view is omitted. The v3/v4
experiments proved that global peak suppression and aggregation/ranking
can produce a *stable wrong hypothesis*. Is either detected boundary
geometrically plausible, and do the image-plane edges align with
persistent physical structure or with virtual/reflected facets?

This PR is **diagnostic-only**. It does not refit or update the production
wireframe, redefine a facet, optimize a score, promote v3/v4 or change
the user-facing diamond-quality assessment.

## Predeclared reconstruction (no hand-picked candidate radii)

For each of the four hash-pinned Asschers:

1. Re-run the existing source processing and #73/#80 canonical sequence.
   Reuse exactly the v3 frozen frame/outer selection. Confirm source
   indexes and v3 primary C3 global u against immutable workflow artifact
   37767669755, where the v3 baseline has a C3 estimate.
2. Hold the **full-selected-view outer octagon fixed** for every
   leave-one-out contrast case, so changing the outer edge does not
   masquerade as a C3 effect.
3. Recompute the existing v3 **window-local** peak candidates inside
   the fixed predeclared C3 interval [0.42,0.60]. Filter only by the
   existing sector-support >=0.25 eligibility. Take the *top two* by the
   frozen v3 aggregate score (no target-specific u values).
   If fewer than two survive, mark missing, do not manufacture one.
4. Reconstruct **both eight-vertex C3/table rings** using the existing
   per-sector local peaks, weak opposite-sector smoothing,
   topology ordering, and `_ring_vertices` projection on the
   *same* frozen fitted silhouette.
5. Report both rings' convexity, area, radial variation, adjacent
   sector jumps, opposite-vertex differences and signed separation
   from the unchanged v3 C2 ring. Report per-frame/per-sector peak
   support and radial offsets separately; no arbitrary geometric
   score and no implicit winner.
6. Project both polygons onto each source camera-RGB image using the
   exact #80 `sequence_gauge_to_camera_xy` mapping. A/B panels share
   the same original RGB crop and outer/C2 context. Green circles mark
   **observed frame-sector image-gradient evidence** near the chosen
   candidate; these are not physical-facet labels.
7. Save native-resolution annotated RGB frame triptychs and a
   per-case contact sheet. For each stone render the full-view case
   and up to two largest-C3-change leave-one-out cases. Independently
   include LG756520111's omit-13 and omit-16 cases if selected.
   Every omitted-view case records all five source images, explicitly
   labeling the omitted image *HELD OUT*; it does not contribute to
   candidate fitting or consistency counts.

Each per-stone `hypotheses.json` includes all leave-one-out candidate
sets, even those without a rendered contact sheet. The top-level
`summary.json` links all camera-RGB QC sheets.

## What to inspect visually

- Does one C3 ring follow a clear, closed *structural* junction in all
  source RGB views, while the other follows a changing bright/dark line?
- Are the rings merely scaled near-regular octagons in gauge space,
  or do observed local peaks and camera projection plausibly match
  the corner/side changes of an Asscher table junction?
- Do the C3 hypotheses retain positive separation from C2 at all
  eight vertices, and are any corners unreasonably jagged?
- What changes in the *held-out* frame without allowing that image
  to vote in the candidate fit?
- Do analogous ambiguities appear in the other three stones?
  Report missing hypotheses instead of mislabeling them as resolved.

**Caveat:** The existing normalization is 2-D similarity only. An
overlay will not prove physical identity under oblique view or
reflections. We are assessing observational/geometric consistency,
not performing calibrated 3-D facet recovery.

## Completion

- [ ] Focused frozen-contract + geometry + projection tests green.
- [ ] Four original SHA-256-pinned source rotations replayed without
      changing selected frames or the primary v3 estimate.
- [ ] At least one native source RGB A/B sheet showing competing
      hypotheses for LG756520111, including omit-13 and omit-16.
- [ ] All four stones represented, including explicit missingness.
- [ ] Manual image review written up before designing the next
      estimator revision.

As requested, #90 source stress is not triggered.
