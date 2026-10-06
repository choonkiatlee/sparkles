# Geometric crispness v2

Issue #55 revises the static-crispness experiment from #50 in two independent
directions:

1. normalized semantic tier-edge transitions;
2. diagonal-arm / windmill legibility.

This remains research-only. It does not modify the #45 retained profile and
does not produce a combined crispness score.

## Common spatial transfer

Every already-registered frame is mapped onto one declared transfer function
before either experiment:

- effective diamond diameter: area-equivalent silhouette diameter;
- target diameter: 160 px (conservative common resolution; no benchmark source is upsampled);
- fixed output canvas and isotropic resampling;
- support-weighted Gaussian anti-aliasing before any downsample;
- fixed Gaussian low-pass: sigma 1.0 normalized output px;
- no sharpening, deconvolution or contrast enhancement.

The exact transform is serialized into every benchmark output. Controlled
blur/downsample/JPEG/sharpen perturbations are applied **before** this
normalization so the stress test asks whether the normalization actually
reduces pipeline sensitivity.

## A. Normalized tier edges

Boundary identity is inherited from #19's three semantic radial windows. A
held-out frame may estimate the local transition position only inside the
predeclared window; it may not invent or relabel semantic boundaries.

The headline primitive is **10–90% derivative-mass transition width** in
silhouette-normalized radius units. Local contrast and gradient magnitude are
QC support only.

Per boundary the prototype also preserves:

- continuous per-ray confidence;
- longest low-confidence angular gap;
- number of low-confidence components, separating one missing sector from
  fragmented support;
- position residual MAD after removing a low-order four/eight-fold periodic
  shape term.

## B. Diagonal arms

Four predeclared diagonal corridors (NE/NW/SE/SW) are sampled independently.

For each arm the prototype records:

- confidence-weighted visibility;
- orientation coherence;
- longest weak radial gap;
- trajectory straightness;
- angular offset and frame-window stability.

It also reports opposing-axis misalignment and four-arm spacing diagnostics.
Raw gradient amplitude is not a headline output.

## Validation

Synthetic tests cover:

- equivalent source sizes under normalization;
- sharp versus blurred tier transitions;
- fragmented versus single-sector support failure;
- non-Asscher boundary wobble;
- missing diagonal-arm segments;
- curved diagonal arms.

The source benchmark reuses the canonical four stones and exact #20 windows:

- core: `248..255,0..8`;
- wide sensitivity: `240..255,0..16`.

It joins the #22 `static_geometric_crispness` observations and emits
source-first evidence panels. With only one Workshop benchmark stone, no strong
cross-vendor invariance claim is allowed.

## Decision rule

Every primitive receives an independent **KEEP / REVISE / REJECT** disposition.
A successful experiment may reject either the tier-edge or diagonal-arm family.
No scalar buyer-facing crispness score is introduced by this issue.
