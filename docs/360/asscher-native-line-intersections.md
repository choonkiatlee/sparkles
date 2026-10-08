# #124 — source RGB straight-line and observed-corner diagnostic

## Why abandon the radial octagon fit for now?

The original camera-RGB evidence from draft #140 confirms the user's visual
criticism: both u≈0.478 and u≈0.579 C3/table *radial octagons cross through
the interiors of visible facets*. Regularity of a plotted octagon and a
high image-gradient / temporal-repeatability score do not establish facet
junction identity. The previous approach used the radial profile to
choose a scale, then interpolated eight vertex radii into a regular-looking
closed contour. This can manufacture a believable polygon from reflections.

**This experiment does not choose another u or fit an inner polygon.** It
tests whether there are long *observed lines* whose finite extents actually
meet at corners in native camera RGB. A future polygon fitter must earn
each side and corner from observable evidence. It may return unavailable.

## Method, frozen before benchmark

- Keep the #96 outer-octagon / #80 gauge and selected crown-facing lobe.
  Report face-role, face-selection metadata and original source index.
  Do not reclassify a pavilion lobe by visual intuition or borrow views
  from the opposite lobe.
- Decode untouched source camera RGB and warp it *only* into the existing
  sequence-gauge pixel grid with the exact inverse affine camera transform.
  OpenCV's local LSD straight-segment detector runs on CLAHE-enhanced
  RGB luminance **for candidate discovery only**. Raw RGB remains the
  unmodified visual evidence in the side-by-side QC.
- Use the eight *observed outer silhouette* side tangents/normals as
  plausible direction families. Keep LSD segments at angles within
  13 degrees of a family, midpoint normal depth between 25% and 90%
  of that outer side, and length >=12% of the corresponding actual
  outer side. These are broad segment filtering criteria, **not** a
  preselected C3/table radius or score calibrated to a stone.
- Report each finite segment's actual endpoints, measured length,
  direction and offset. Do not build any ring from offsets.
- For adjacent line families, accept a **candidate junction** only
  when the observed finite segments cross, allowing <=2.2% of
  diamond diameter for subpixel/occlusion extrapolation and at least
  18 degrees separation. Preserve the intersecting family IDs,
  position and segment lengths. A corner is a *hypothesis*, not yet
  a confirmed facet junction; two reflected lines can cross as well.
- Render a two-panel native RGB comparison for each selected source
  frame: untouched camera pixels and candidate LSD segments with
  small white circles for observed intersections. Include all four
  source bundles and top-level per-stone contact sheets.
- **Never close missing sides, infer unseen corners, or change the frozen
  C3/table estimator.** The method explicitly reports
  `polygon_fit_status = unavailable_not_attempted_without_tracked_junction_cycle`.
  This is a test of evidence extraction, not a claimed table polygon.

OpenCV is an *optional diagnostic-only* dependency installed by the
isolated GitHub workflow, not added to production project dependencies.

## Missing inner scaffold is not missing source-line evidence

The first all-stone run reproduced the correct frozen source selection but
abstained entirely on IGI-LG818659722, because that stone's frozen #96
**inner** scaffold is unavailable. This is not a reason to skip an
independent examination of original RGB lines. The diagnostic now derives
only the *observed physical outer octagon* via the existing
`asscher_outer_octagon.fit_consensus` on the same selected #80-gauged masks,
even when the inner C3/table fit failed. It does **not** fill in any
unavailable inner facet/corner, select a new source view, or modify #96.

The unchanged full source selection is still compared against frozen #96
records in CI; all four stones must supply native RGB evidence when source
frames exist. Geometry remains explicitly `unavailable` unless a
valid image-supported junction cycle is demonstrated, which this
diagnostic does not attempt.

## Visual QC questions

1. Do the long detected line segments lie along actual boundaries,
   especially the table's top and bottom and along corner cutoffs?
   Or do they follow bright/dark internal facet reflections?
2. Do the candidate intersection dots coincide with *visible* facet
   junction corners, rather than crossing bright virtual facets?
3. Is the presumed crown lobe correct? Are we confusing pavilion facets
   viewed through the table with crown table boundaries?
4. Are exact #80 camera transformations placing the lines correctly?
5. Can several mutually compatible line/corner measurements be tracked
   across source frames without forcing them onto the original
   u≈0.478/0.579 radii?

If the resulting segments or intersections are largely reflections,
record **REVISE**; a stable observed RGB line is not sufficient proof of
a physical polished facet boundary. We should not automatically fit
a polygon until independent actual-corner evidence is credible.

## Acceptance

- [ ] Focused finite-intersection, source projection and frozen-contract
      tests pass.
- [ ] Four full pinned source rotations replay; selected source
      indexes verified against immutable #96 artifact.
- [ ] Source-RGB line/intersection contact sheets uploaded for all stones.
- [ ] Human reviews frame 13/16 from LG756520111, and all remaining stones.
- [ ] Document whether a new constrained polygon fitter is warranted,
      or whether more explicit facet-topology/image segmentation evidence
      is needed.

The long #90 source-stress suite stays manual-only and excluded.
