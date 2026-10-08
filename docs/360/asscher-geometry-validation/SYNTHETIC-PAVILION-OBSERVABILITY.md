# Synthetic Asscher pavilion observability benchmark (#149)

This is a **separate, synthetic-only experiment** stacked on #118. It is
deliberately **not** another retuning of the DiaGem profile. The target is
generalization to shapes and projected outlines not seen when the
existing image-only changepoint policy was chosen.

## Why this experiment exists

A projected silhouette is the extremal envelope of a three-dimensional
faceted object. The true physical tier transitions are not guaranteed to
produce visible contour slope changes: adjacent tier slopes may coincide,
projection may change the surface generating the extremum, and portions
of an edge may be occluded. Fitting a particular source dot by eye would
conflate model flexibility with physical information.

The simulator draws a shape from specified **synthetic truth**:

- Four concentric, truncated-corner square/octagon rings along the vertical
  axis, ranging from an optional tiny point-like tip through three pavilion
  bands to the girdle. These bands can be called P3/P2/P1 *within the
  synthetic fixture alone*. This generator does **not** model a polished
  crown, table, individual real-world step facet topology or actual light
  return.
- Monotonically increasing radial widths, strictly ordered axial positions,
  variable corner truncation, and optional asymmetric left/right width.
  Ring-matched quads are triangulated into polygonal faces. No assumption
  that a true Asscher should be exactly rotationally/mirror symmetric.
- A documented **orthographic** camera with azimuth/yaw, elevation/tilt and
  in-plane roll, scale and translation. This is a synthetic camera model;
  a real diamond photo may use perspective or unspecified camera pose.
- For each image scanline, collect the **union of projected face triangles**
  and derive its left/right outer extents. A projected **convex hull would
  falsely fill concave/stepped edge regions**; this generator does not use
  convex hulls.
- Independently label exact 3D ring boundaries, ideal 2D silhouette,
  simulated observed boundary points, supported/missing rows, and artificial
  interior stripes (negative controls only). Synthetic 3D truth is not a
  claim that a corresponding real physical facet is identifiable in photos.

Source orientation follows the corrected #91 contract: pointed **pavilion
at upper image y**, girdle near the lower boundary; the lower **crown**
of the real photograph is deliberately outside this synthetic model.

## Observable versus physical

Even if all **three physical pavilion bands** are present, a level-on
profile may have just one or two geometrically distinct external slopes
if neighboring bands are (approximately) collinear. A synthetic-only
visibility oracle can count ring-level slope discontinuities for a level
orthographic projection, with a predeclared detectable slope-jump rule.

For camera tilt or roll, **no one-to-one correspondence is asserted**:
ring projection positions vary with depth/azimuth, and surface generators
may switch. Such cases explicitly return
\`not_identifiable_by_single_ring_rows_under_oblique_pose\`. The ordinary
image-only estimator never receives oracle ring heights or radii.

## Predeclared partition and benchmark

\`diamond360.asscher_pavilion_synthetic.CASES\` contains **three dev
shapes and five held-out shapes** spanning distinct ring proportions,
cut-corner widths, asymmetry, oblique pose, two occlusion patterns, and
boundary noise. Seeds, camera parameters and the existing independent
source-only fitting penalty are fixed in code.

For each synthetic case and each side:

1. Provide the existing #118 \`_fit\` with noisy, *source-exterior-only*
   points from four out of every five supported rows. Its complexity
   penalty and admissible 1–3 projected slopes are left unchanged.
2. Evaluate **image-plane x-position RMSE** on every fifth supported
   row, withheld from the fit. Also report model-selected segment count,
   proposed projected breakpoint y rows and source support.
3. Record when too few exterior points survive the occlusion. Do not fill
   missing rows or mirror an asymmetric right contour into the ground truth.
4. Record the **synthetic-only visibility oracle** separately (or
   \`unknown\` under tilted camera projection), rather than interpreting
   fitted image bends as polished P1/P2/P3 facets.
5. Keep inner virtual-facet stripes **out of geometry input**; their
   presence must not change the contour-based fit.

The report is descriptive and **not** an optimized score: this PR must
not adjust the existing silhouette penalty until we have decided
up-front what would count as meaningful generalization, including
false-positive breakpoints and recoverability under oblique projection.

## Running

From repository root after installing package dependencies:

\`\`\`bash
python -m unittest tests.test_asscher_pavilion_synthetic -v
python -m diamond360.asscher_pavilion_synthetic \
  --output outputs/asscher-pavilion-synthetic
\`\`\`

The focused CI action uploads:

- \`synthetic-pavilion-benchmark.json\`: seeds and parameters, dev/holdout
  split, per-side held-out residuals, selected image-plane breaks, oracle
  observability diagnostic and no-physical-angle gate.
- \`synthetic-pavilion-cases.png\`: four synthetic examples. Green and
  blue represent noisy left/right *outside* observations; the pale filled
  object is synthetic, never derived from the DiaGem/Sergey JPEG.

## Deliberate limitations / subsequent experiments

- Synthetic orthographic ring mesh is only an **Asscher-like morphology**,
  not a ray-traced, fully realistic physical diamond or a recovered
  facet-plane-angle estimator.
- No direct image-to-contour retracing through photographic blur, JPEG
  compression or changing reflections is claimed by this version. The
  observation perturbation simulates *boundary position noise and missing
  support*; future work can render, blur, recompress, re-extract and compare
  on fresh held-out simulated source images.
- Synthetic held-out cases are only a first falsification tool; real held-out
  diamond profiles need to be gathered and assessed separately.
- This experiment **must not change #118's DiaGem proposal** based on a
  closer-looking right-hand dot. External Sergey expert target angles are
  reserved for the later explicit correspondence comparison in #91 PR C.
- Per-source physical P1/P2/P3 angles, polished culet/table identity and
  exact 3D meridional/photo projection remain unverified.

Associated: #91 (external correspondence), #118 (source-only baseline),
#123 (separate virtual-facet project), #149 (this generalization test).
