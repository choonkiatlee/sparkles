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

## Limitations and acceptance

The sequence normalization is a **2D similarity**, not calibrated view rectification. Broad side-family orientation is only a hypothesis about true inner facet junctions. Corner intersections are not automatically evidence of polished facet corners. Even coherent long lines can be reflections.

- [ ] Synthetic tests show line support, missing-side abstention, valid camera map, independent corner intersections; frozen production method unchanged.
- [ ] All four fixed-source rotations replay with unchanged selected crown frames.
- [ ] Inspect source camera-RGB panels, especially LG756520111 source 13/16 and LG818659722. Determine whether any accepted *segments* actually lie on real facet junctions.
- [ ] Preserve unavailable/partial observations instead of forcing eight supported lines.
- [ ] Declare REVISE/KEEP/REJECT for this observational approach. Do not infer true facet topology solely from its geometric regularity.

No #90 source stress. No alteration to `asscher_steps`, `asscher_wireframe`, estimator routing or product quality score.
