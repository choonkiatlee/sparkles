# #124 — C3/table peak switching and face-on normalization diagnostic

## Why

The fixed #96 factor experiment in [PR #122](https://github.com/choonkiatlee/sparkles/pull/122)
established that omitting frame 16 from **inner** edge evidence moves the
LG756520111 `C3_TABLE` anchor from about `0.579` to `0.478`, while
changing only the fitted outer octagon moves the geometry by a small amount.

A plausible explanation is imperfect normalization from oblique images into
the canonical frame. The important architectural distinction is that
`normalized_geometry.normalize_frame()` currently permits only a **2-D
similarity** transform: centre, in-plane rotation, and isotropic scale. It
never computes a projective homography, camera tilt, or physically calibrated
square-on view. Moreover, `asscher_steps.polar_profiles()` subsequently
samples radius **relative to each frame's own silhouette**. Therefore simple
translation/scale errors and camera projection must not be conflated.

Another plausible explanation is an optical/virtual edge that moves between
frames and changes the rank of a multimodal radial consensus. Neither
hypothesis is a validated physical-facet identification.

## Frozen, target-blind diagnostic

`diamond360.asscher_inner_evidence_diagnostic` runs the original pinned
256-frame LG756520111 source and no modified estimator code. It:
1. Replays both diagonal arms of #122 against the immutable #115 validation
   artifact (same source selection, C1/C2/C3 radial values and fit status).
2. Saves all candidate radial peaks, prominences, and sector support for each
   five-frame and without-16 template.
3. Repeats the template-only calculation for each of the **five** one-frame
   exclusions, not merely for frame 16.
4. Measures each selected frame's 8-sector evidence at **both** competing
   C3 positions within a fixed `±0.022u` probe, preserving the observed peak
   `u` and strength. No comparison with physical facets is claimed.
5. Records the actual registered-to-canonical matrices, their linear singular
   values, registered orientation/aspect/outline residual, and each
   frame's fitted octagon vertex displacement relative to the frozen median.
6. Produces `c3-evidence.png` (all selected per-view radial evidence,
   both competing C3 positions, full/subset medians) and
   `frame-registration-qc.jpg` (one **fixed scaffold** projected onto
   each of the five original camera-RGB frames using the existing #80 inverse).

Source frames and full processed intermediates are not committed. CI retains
three small generated diagnostic files for human validation.

## How to interpret

- If the contour fit and canonical silhouette geometry agree closely but
  individual radial profiles display mutually competing stable peaks, look
  first at multimodal optical/edge aggregation, without promoting reflected
  lines into polished facets.
- If strongly skewed projections or high normalized silhouette residuals
  correlate with peak shifts, the user's *imperfect normalization* hypothesis
  deserves a **separate** calibrated pose/rectification investigation.
- A silhouette-to-silhouette fit is not independent camera calibration. Small
  residuals cannot prove that an apparent inner edge is a genuine physical
  facet junction or that the diamond is face-on.
- This experiment describes **correlation, not proof of causal correction**:
  we do not warp pixels, assign physical 3-D facet angles, change phase
  anchors, or optimize regularization here.

## Run

```sh
python -m unittest tests.test_asscher_inner_evidence_diagnostic -v
python -m diamond360.asscher_inner_evidence_diagnostic \
  --source-root outputs/inner-evidence-sources/IGI-LG756520111 \
  --source-manifest docs/360/benchmark/per-stone/IGI-LG756520111/source-manifest.json \
  --reference-dir outputs/frozen-outer-stability \
  --output outputs/inner-evidence-diagnostic
```

The CI workflow downloads the exact hash-pinned benchmark media and the
original #115 artifact from [run 37755387174](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174).

## Completion criteria for this diagnostic PR

- [ ] Frozen original outputs replay exactly.
- [ ] Full/omitted candidate distributions and five leave-one-out switches
  remain auditable.
- [ ] Full source-by-sector competing edge support is recorded.
- [ ] Normalization matrices, silhouette geometry and camera-RGB QC are
  available and explicitly distinguished from actual projective rectification.
- [ ] Whether source-16 supplies unique physical-looking support is presented
  only as image evidence, not as a labelled physical facet.
- [ ] Follow-up action is chosen *after* the QC and numeric evidence are read,
  with no per-stone parameter tuning.
