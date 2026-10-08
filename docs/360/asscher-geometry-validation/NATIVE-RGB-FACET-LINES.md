# #124 — Native camera-RGB line intersections, not radial peak octagons

## Why this experiment

Visual QC of the preceding [#140 C3/table hypothesis overlays](https://github.com/choonkiatlee/sparkles/pull/140) showed both plausible rings cutting through visible facet interiors. Although the radial contrast peaks were persistent, they were **not visibly the physical facet-to-facet junctions**. This is stronger negative evidence than their numerical stability.

This follow-on PR tests a different primitive: **long, coherent straight segments and their intersections in source-camera RGB**. The frozen #96 silhouette supplies orientation and scale but no candidate inner radius. The physical facet identity of even a straight edge remains unproven until visual review.

## Method (predeclared, target-blind)

1. Run the four exact SHA-256-pinned original source bundles and reuse the frozen #96 crown-selected views. Persist the #73 canonical gauge and #80 transforms unchanged. Check selected source indices against archived workflow #115 / run 37755387174.
2. Use `sequence_gauge_to_camera_xy` to resample **unmodified source RGB** into the common gauge, with valid-mask screening. The resampling is an observation convenience; the returned QC is always drawn on original camera RGB.
3. Derive eight expected **orientations** from the measured physical outer octagon. For each orientation independently, search a broad relative offset range [0.34,0.78], with no selected radial-peak hypothesis.
4. For each offset, probe a long segment parallel to its corresponding outer side; measure oriented Sobel RGB gradient, proportion of supported pixels and longest **contiguous** supported run. **Only that observed contiguous subsegment is drawn**, rather than extending a line through unevidenced facet interiors. Bright isolated spots cannot substitute for a long straight candidate. Allow multiple segment hypotheses per side.
5. Label a side unavailable unless coverage >=50%, longest run >=30%, and valid support >=80%. No prior, symmetry inference, or synthetic replacement supplies a missing side.
6. Only if all eight side lines independently pass, their normalized offsets are reasonably coherent (spread <=0.18), and the eight **actual neighbor line intersections** are within 0.06 normalized distance of the observed contiguous segment spans, form a convex polygon inside the measured outer silhouette, render a **tentative** polygon. Extrapolating partial optical fragments into corners is not allowed. Otherwise show only the observed fragments; no closed contour.
7. Export per-frame line candidates and abstentions, side-by-side *native RGB*, evidence segments, and intersection panels. Audit same-side offset consistency across the frozen selected frames. It remains possible that all detected straight features are virtual/reflected boundaries; manual review comes before selection.

The detector does not use the frozen C3 `u=.478/.579` positions, existing radial contrast maxima, the v3/v4 selection score, or any certificate-specific tuning.

## First four-stone visual/measurement result (8 Oct 2026)

The full hash-pinned original camera-RGB diagnostic finished successfully in
[workflow run 37797799152](https://github.com/choonkiatlee/sparkles/actions/runs/37797799152).
Its artifact contains original RGB, observed-only line segments and independent
corner QC for all 20 selected images (5 per stone).

| Diamond | Independently supported inner side counts, selected frames | Closed corner-supported rings |
| --- | --- | --- |
| IGI-LG756520111 | 4, 3, 3, 4, 4 (src 16, 13, 18, 19, 17) | 0/5 |
| IGI-LG756580087 | 4, 7, 6, 7, 2 (src 19, 5, 2, 4, 250) | 0/5 |
| IGI-LG818659722 | 3, 3, 3, 5, 4 (src 8, 13, 11, 6, 10) | 0/5 |
| IGI-LG836619414 | 5, 4, 3, 3, 4 (src 16, 252, 5, 2, 3) | 0/5 |

**The fail-closed corner rule is working:** none of 20 frames passes all
eight independently supported side requirements and no octagon is invented.
Native RGB inspection of LG756520111 src13/src16 and LG818659722 src10
also shows that some independently detected *straight* gradient fragments
appear **inside visible facets**, or along virtual/reflection features,
rather than demonstrated facet-to-facet junctions. Segment straightness
is insufficient to establish physical boundary identity.

The #73 face-lobe resolution is not always decisive:
LG756520111 and LG818659722 have `face_selection.status=resolved`
with selected views marked `likely_crown_lobe`, whereas LG756580087
and LG836619414 have `face_selection.status=not_needed` and selected
views have `face_role=unresolved`. Do not assume these latter sources
confirm crown/table structure from the current metadata.

**Research disposition: REVISE, no estimator promotion.** Keep the
observed-segment diagnostic as a reproducible negative baseline.
The next method should inspect junction/corner **co-occurrence and
connected facet boundary networks** on original RGB rather than
promoting any long contrast line into an octagon. Explicitly distinguish
unresolved face identity and insufficient junction evidence from failure
of the optimization. No certificate-specific radial priors.

## Limitations and acceptance

The sequence normalization is a **2D similarity**, not calibrated view rectification.
Broad side-family orientation is only a hypothesis about true inner facet
junctions. Corner intersections are not automatically evidence of polished facet
corners. Even coherent long lines can be reflections.

- [x] Synthetic and exact-camera-projection tests passed, and the immutable
      estimator specification remains unchanged.
- [x] All four fixed-source rotations replayed with unchanged #96 source
      selection; all five CI workflows completed successfully.
- [x] Reviewed source camera-RGB panels including LG756520111 source 13/16
      and LG818659722. Identified interior contrast fragments and missing
      junction support; true-facet identity **not established**.
- [x] Preserved unavailable/partial observations instead of forcing
      eight supported lines (0/20 closed polygons).
- [x] Research disposition declared: **REVISE**, keep diagnostic only.

No #90 source stress. No alteration to `asscher_steps`, `asscher_wireframe`,
estimator routing or product quality score.
