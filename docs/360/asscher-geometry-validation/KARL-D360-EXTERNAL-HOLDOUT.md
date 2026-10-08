# #92 / #64 — archived external D360 falsification (Crispest vs Glittery)

This research PR evaluates the already frozen **#96 outer-octagon v2**
semantic scaffold and **#92 fixed image-plane brightness/sensitivity**
methods on the original 256-frame D360 source media, before interpretation
using expert commentary. It does NOT train the estimator on Karl's labels.

## Why these two independent examples?

- **Crispest**: archived \`asscher-eval-crispest\`, viewer
  \`79-BT-5165227\`, 256 original JPEGs, 648×511; Karl K.'s archived
  commentary flags **face-up top/bottom V / P3 leakage** and comparatively
  weak performance within the initial group.
- **Glittery**: archived \`asscher-eval-glittery\`, viewer
  \`79-BB-5159600\`, 256 original JPEGs, 758×597; Karl's concern centres on
  **small windmills**, a geometric/style observation rather than a
  matching leakage label.

These **source observations are kept out of generator inputs** and
interpreted only after the fixed-method output is stored. The cases are
*external to the four original #89 geometry benchmark stones*; however
the older PriceScope #70 descriptor-falsification work already used both
sequences. Therefore **these are not statistically pristine unseen
holdouts**. This is a descriptive external generalization / falsification
gate, not a fresh blinded estimate of accuracy.

Both sources are exact originals from the pinned 36.57MB v3 PriceScope
release. The archive checksum is verified, and the existing
\`external_media.adapt_archived_sequence\` confirms ordering, complete
256-frame coverage and each source JPEG hash.

## Predeclared, unchanged algorithm

- No source-dependent parameter changes, orientation hacks, new physical
  plane-angle mapping or user-led retuning.
- Run the existing pipeline and #73/#80 registration on both full
  rotations to recover canonical image support.
- Attempt the frozen \`outer_octagon_v2\` primary scaffold *once per
  unseen stone*, using the preexisting pose-view selection. No artificial
  scaffold from generic ideal geometry if it cannot fit.
- On sample indices \`[250,252,255,0,2,5,8,11,13,16,19]\`, use that one
  stone-level scaffold to compute **image-only** per-frame geometric
  support via #89 and source brightness via #92. A missing source gauge
  is recorded as missing, not interpolated or silently broadened.
- For available frames: preserve fixed \`semantic_id\`, non-exclusive
  polygons, observation status/confidence, uncalibrated image-plane
  brightness, per-frame within-source q10–q90 contrast proxy and
  separately fixed 2px inward polygon support control.
- If the standard pose/scaffold fails, produce an explicit
  \`unavailable\` record **rather than fabricate physical identities
  or claim the optical measurement succeeded**.

Note that the estimator may show acceptable relative image-plane
support even when none of the P1/P2/P3 or C3 regions can be certified as
a polished facet. In particular, **fixed P3_N brightness is not
itself a P3 leakage measurement**: leakage involves true optical
ray-path and physical facet association unavailable in the source.
Our results must not be described as confirming or rejecting Karl's
specific P3-leakage statement unless we independently define and
validate an appropriate observable comparison.

## What counts as useful evidence?

**Positive pipeline generalization:** authentic media, stable gauge,
frozen one-per-stone semantic scaffold available, per-frame identities
unchanged, no unsupported physical-angle/score claims, and meaningful
non-null brightness statistics. This establishes the *feasibility* of
support-trace transfer to a different 360 vendor.

**Negative/limitation:** unavailable face role, missing gauge, missing
scaffold or low support; do not turn into false zero brightness. Even a
positive trace is not validation of the proposed C3/table polished
facet boundary or physical P3 leakage mechanism.

The two source collections have **different acquisition pipelines**.
Absolute raw mean brightness and the q10/q90 contrast proxy are not
cross-vendor calibrated; frame-number \`0\` is not physical 0°.
The core indices come from the original #70 wrapped viewer-rotation
convention and aren't guaranteed physical face-up for a D360 sequence.
A valid #73 pose assessment must be considered separately.

## Deliverables

\`diamond360.asscher_semantic_optical_external_d360\` emits one
\`external-result.json\` per stone, with explicit fit/pose status,
missing-frame reasons, frozen method name, stable identity counts, and
a statement that labels were withheld. For successful cases it also
emits per-region brightness PNG and the #180 q10/q90 and 2-pixel
erosion sensitivity JSON/PNG. If the frozen method cannot support a
stone, the result says \`unavailable\` with no fake plots or inferred
facet lines.

The dedicated CI verifies archived source bytes before computation,
runs the target-blind fitting/sampling once and uploads only small
derived reports/images, not original third-party frames.

Research disposition for #92 and #79: regardless of outcome, do not
change #75/#96 frozen thresholds to satisfy these Karl cases. A later
separately versioned method and fresh external cases would be required
to make out-of-sample improvement claims.
