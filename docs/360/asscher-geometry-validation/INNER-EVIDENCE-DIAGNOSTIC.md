# #124: why C3/table moves when frame 16 disappears

This is an **evidence and normalization diagnostic**, not a production
fitter change. It directly follows [#122](https://github.com/choonkiatlee/sparkles/pull/122)
and uses the immutable #115 validator as its replay target.

## Two separate hypotheses

The frame-16 factor ablation already established that the ~1-local-tier
`C3_TABLE` shift comes from *inner* evidence. It did not say why.

**H1, multimodal inner edge:** `asscher_steps.discover_template` computes a
median across selected frames, then sectors, smooths the resulting curve and
chooses among competing peaks in the predeclared centre-inner window
`u∈[0.42,0.60]`. An inconsistent or virtual/reflected interior edge may lead
to a different global candidate when frame 16 drops out.

**H2, imperfect square-on normalization:** the current #73
`normalized_geometry.normalize_frame` uses a 2-D similarity transform:
centre, in-plane rotation and a *single isotropic scale*. It intentionally
does **not** estimate camera tilt, planar homography, perspective/shear or
true face-on rectification. Then #19 samples an inner radial edge in units of
distance to each frame's own outer silhouette (`u=r/r_outline(theta)`).
Even if the observed outer octagon fits well, differing projection/rotation/
centering and nonphysical interior reflections could move peaks in `u`.

These hypotheses are **not exclusive**. Observed image contrast alone
cannot resolve physical versus optical/virtual facets.

## Exact diagnostic

- Re-run the pinned original LG756520111 256-frame source through the
  *unchanged* #73/#80/#96 pipeline.
- Require the selected frame indices and both global C3/table positions
  (all five and omit frame 16) to exactly reproduce frozen #115 outputs.
- Retain *all* C3 candidate peak locations, prominence, cross-sector support
  and the unchanged score `log1p(prominence / scale) + 1.25 × support`;
  explicitly record both winning/losing hypotheses.
- Persist the all-five and omit-16 consensus edge profiles and all eight
  sector curves, preserving missing pixels as JSON null, **not zero**.
- For each of the five frames/sectors, report three strongest image-edge
  candidates in the C3 window and support near both hypothesis locations.
  These are *unassigned contrast features*, not facet-junction annotations.
- For each frame, record #73 registered orientation, normalization centre,
  isotropic scale, `rectification=none`, source-outline aspect/residual,
  per-ray silhouette radius, and RMS/maximum deviation from the selected
  views' median ray silhouette in the common sequence gauge.
- Produce `c3-evidence-modes.png` overlaying both aggregate radial curves
  on a shared fixed axis with candidate positions shown.

## Limits and next decision

A correlated outline mismatch and inner-edge peak movement supports a
registration/projection *hypothesis*, not proof that rectification will
recover correct physical facet geometry. A photograph of a refracting Asscher
may show entirely different virtual facets even under perfect registration.

Do **not** implement homography/deprojection in this PR or tune the C3
window/peak thresholds. First examine whether the two modes exist in
individual source frames, whether the winning peak changed in `discover_template`
as the frame median changes, and whether source-mask ray radius changes
are of a magnitude plausibly sufficient to account for the observed shift.

Later alternatives (if justified) require an independently declared
revision and complete #76/#89/#90 validation across the pinned stone set.
No numeric fit acceptance threshold is chosen based on LG756520111.

## CI

[Original #115 run](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174)
is retrieved as a read-only artifact. The workflow fetches the
SHA-256-verified original benchmark bundle from GitHub releases, reruns the
existing production pipeline, compares the C3 locations exactly, then
uploads `diagnostic.json` and `c3-evidence-modes.png`.

```bash
python -m unittest tests.test_asscher_geometry_inner_evidence_diagnostic -v
python -m diamond360.asscher_geometry_inner_evidence_diagnostic \
  --source-root outputs/inner-evidence-sources/IGI-LG756520111 \
  --source-manifest docs/360/benchmark/per-stone/IGI-LG756520111/source-manifest.json \
  --reference-dir outputs/frozen-outer-stability \
  --output outputs/asscher-inner-evidence-diagnostic
```
