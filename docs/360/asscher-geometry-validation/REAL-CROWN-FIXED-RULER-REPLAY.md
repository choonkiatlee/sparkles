# #92 — Seven original crown frames with one frozen geometry ruler

This PR replays **one** original 256-frame Asscher rotation,
\`IGI-LG756520111\`, using its exact frozen #89 output (CI artifact from run
37830584391). There is no new geometric fitting or threshold selection.

## Why this replay matters

The preceding #166 synthetic smoke demonstrated that image brightness can
be measured against the same semantic source gauge without changing the
geometry. This follow-up checks the wiring against **actual camera RGB
sources**, not synthetic images, while making the modest claim that
canonical low-pass measurement brightness changes under a fixed
image-plane semantic ruler.

## Predeclared real-source evidence

- **Certificate:** IGI-LG756520111
- **Original source bundle SHA-256:**
  \`b45647292c207d46fab8871b66ff62c3aa4a7652c910c5cd975fce10f3c5fc90\`.
- **Original #89 primary-wireframe.json SHA-256:**
  \`a675f82e73c2f099c1d55a4f56e82047041fe668f757c616c665912156d64fda\`.
- **Original #89 transfer.json SHA-256:**
  \`015556c0f2360951fe3458627fe1c49d5bf2f71f07929065fecab52794bf6479\`.
- **Frame indices frozen up front:** \`4, 8, 12, 16, 20, 24, 28\`;
  one crown-view interval crossing the original fit cluster. Several
  are outside the original five geometry-fit frames.
- **Original geometry-view indices:** \`13, 16, 17, 18, 19\`,
  not reselected by the replay.
- **Existing semantic gauge ID:**
  \`asscher-sequence-gauge-v1:253:0\` (from the archived #89 record).
- **Source-face classification:** likely crown lobe (from frozen #89);
  this does NOT verify C3/table's polished facet boundaries.

The archived primary and per-frame transfer are loaded **unchanged**
after byte-level SHA verification. If they drift, the replay fails.
The original hash-pinned source archive is the only downloaded image input.
The preprocessing and #73/#80 pose registration are replayed to
recover exact canonical measurement-frame arrays and source-camera mapping;
the resulting gauge/position/phase/quarter turn must reproduce #89.

The **geometry estimator is never called**: no
\`asscher_wireframe.fit_from_sector_evidence\`, no tuning of #96, no
new selection. Only the frozen \`asscher_semantic_optical_handoff\`
brightness sampler runs on seven actual gauged frames.

## Deliverables

- \`real-crown-handoff.json\`: the seven source records and their fixed
  semantic IDs, source phases, per-entity \`ok/review/unavailable\`
  geometry support, confidence, sample count, and measured image-plane
  mean brightness (null when unavailable).
- \`real-crown-brightness-traces.png\`: simple traces for the fixed north
  semantic supports \`C1_N\`, \`C2_N\`, \`C3_N\`, \`P1_N\`, \`TABLE\`,
  if available. Gaps mean the corresponding support is not observable.
  Horizontal axis is **source index/approximate viewer phase**, not time.
- \`real-crown-fixed-ruler-rgb.png\`: three selected original-camera RGB
  views with the same unaltered geometric scaffold overlaid using the
  existing camera transform, clearly marked **model**, not identified
  polished facets.

The input brightness is the **canonical measurement representation**,
not unmodified camera RGB intensity or cross-vendor appearance
normalization. No normalized brightness is asserted, and no optical
quality or hall-of-mirrors score is produced.

## Reading the scientific result

Passing a fixed-ruler smoke test means semantic identity stays constant,
while **observable brightness and support may change**. It does **not**
prove C3/table polished facet identity, physical P1/P2/P3 plane angles,
or independence of image regions. Source pixels can contribute to
multiple optical support hypotheses. #124 and #123 still imply
REVISE/uncertain inner facet boundaries.

One stone and seven frames are deliberately a small implementation
check, not the completed comprehensive #92 handoff disposition.
Record this evidence alongside #89, #90, #91's inconclusive independent
physical-angle comparison and #124's negative interior junction
diagnostic before making KEEP / REVISE / REJECT.

This PR is a new, separate stage and does not rewrite the frozen
#75/#88/#89/#91 benchmarks or deploy an alternative geometry estimator.
