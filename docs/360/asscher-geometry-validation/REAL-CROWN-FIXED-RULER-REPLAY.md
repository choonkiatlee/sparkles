# #92 — Seven original crown frames with one frozen geometry ruler

This PR replays **one** original 256-frame Asscher rotation,
\`IGI-LG756520111\`, using the unchanged frozen #89 geometric method. **One stone-level primary fit** is reproduced, then fixed for all seven frames. There is **no per-frame geometric refitting or threshold selection**.

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

The originally archived #89 primary and transfer SHA-256 digests above are
**historical reference fingerprints**. We inspected their frozen source
selection, phase, semantic gauge, and per-frame entity support counts.
The workflow first tried downloading the original archive from GitHub
Actions, but its job token returned HTTP 401. Rather than skip the real
photographs or disguise a re-fit, the implementation instead **reproduces
one primary geometry fit** with the exact frozen `outer_octagon_v2`
specification on the one pinned source stone. It then hard-checks the
**original #89 chosen source indices (13,16,17,18,19), sequence gauge,
seven source phases/quarter-turns, and the #89 per-frame entity
ok/review/unavailable counts** before accepting the result.

Only the first step calls the original frozen method fitter; **none of
the seven transfer frames refits or moves geometry**. This is a
frozen-method reconstruction, not a byte-for-byte loaded archived
primary scaffold. The alternative `verify_frozen_archive` method
remains available for a separately authenticated downloaded artifact,
with strict SHA matching. Source preprocessing and #73/#80 pose
registration still recover real canonical measurement-frame pixels.

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
