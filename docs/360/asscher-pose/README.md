# Asscher frame suitability and canonical pose

Issue: #73  
Parent research issue: #72

This layer selects image frames that are geometrically suitable for later
semantic Asscher wireframe fitting and maps usable frames into a declared 2-D
canonical pose.

It does **not** identify P1/P2/P3 facets, estimate physical facet angles,
rectify perspective, or score Asscher quality.

## Contracts

The implementation has three explicit contracts:

1. `diamond360-asscher-outline/1`
   - fits an eight-line cut-corner-square scaffold to a silhouette;
   - reports fitted centre, eight image-plane vertices, cardinal axes and
     diagonals;
   - estimates orientation modulo 90 degrees;
   - preserves the unavoidable single-image quarter-turn ambiguity;
   - reports local observed side directions and residuals so projection and
     asymmetry remain visible.

2. `diamond360-asscher-pose/1`
   - turns outline evidence into auditable suitability components;
   - emits `ok | review | rejected | failed`;
   - keeps explicit machine-readable reasons alongside the scalar ranking
     score;
   - treats the score as geometry usability only.

3. `diamond360-asscher-pose-sequence/1`
   - consumes an existing processed `diamond360` sequence;
   - assesses suitability in original camera/segmentation coordinates;
   - canonicalises already-registered photometry through the existing
     `normalized_geometry` transfer;
   - composes the registered transform back to original camera coordinates;
   - keeps geometry rank separate from likely viewing-face role;
   - on a complete ordered rotation, resolves crown-versus-opposite-face only
     when two broad face-on geometry lobes are genuinely competitive;
   - persists per-frame canonical brightness/mask/support and compact QC.

## Canonical transform

Canonicalisation is deliberately restricted to a similarity transform:

```
source
  -> translate fitted outline centre to the canonical centre
  -> rotate fitted cardinal axes onto canonical X/Y
  -> isotropically scale to the declared effective diameter
```

No anisotropic scale, shear, or projective homography is applied. Projection
inconsistency is evidence used to reject or review a frame; it is not warped
away.

Both forward and inverse 3x3 xy transforms are serialized.

## Suitability evidence

Version 1 exposes these components separately:

- clipping margin;
- eight-line outline fit residual;
- outline squareness;
- observed opposite-cardinal-side parallelism;
- outline-centre versus silhouette-centroid offset;
- opposite-corner projection balance;
- edge/boundary support;
- registered valid-support fraction;
- combined projection-consistency score.

Hard rejections and review thresholds are declared by
`diamond360.asscher_pose.specification()`. They are initial deterministic
heuristics, not values fitted to the DiaGem/Sergey ground-truth facet angles.

The PriceScope fixture informs the qualitative policy: prefer low-projection
views and reject conditions consistent with appreciable side/pavilion
projection. The stored P1/P2/P3/C1 values are not inputs to the fit or
thresholds.

## Correct face versus square-on geometry

A square-looking silhouette is not sufficient by itself. In two retained
rotations, both the crown/top side and the opposing pavilion side can produce
plausibly square-on views.

Human validation identified the useful optical distinction:

- a crown/top view shows a closed central table boundary;
- an opposite/pavilion view can show centre-crossing diagonal facet junctions
  that meet through the middle.

The production selector does **not** use the human-labelled source indices.
Instead it keeps the decisions separate:

1. smooth the geometry-suitability trace and find broad competing face-on
   lobes;
2. if the best two lobe scores differ by more than 0.10, keep the geometry
   ranking unchanged;
3. otherwise compare closed-table-boundary continuity over each local lobe;
4. resolve a likely crown lobe only when the median difference is at least
   1.5 local MAD units;
5. keep the opposite face as a valid geometry observation but rank it behind
   likely crown-lobe candidates.

The audit record therefore retains `geometry_rank`, `face_role`, the
geometry-lobe evidence and the final selection rank. A likely opposite face is
not mislabeled as clipping, tilt, or bad geometry.

Per-frame face diagnostics also expose central radial-spoke strength,
centre-crossing diagonal energy and table-boundary continuity. These are
viewing-face evidence only; they do not constitute semantic table/facet fitting.

The two human 0-vs-128 judgements used to validate this behavior are stored in
`human-face-validation.json`. They are validation evidence, not production
inputs.

## Orientation ambiguity

An isolated approximately fourfold Asscher silhouette does not identify which
equivalent side is physical north. The contract therefore records

- `orientation_deg_mod_90`;
- `orientation_period_deg = 90`;
- `quarter_turn_ambiguous = true`.

A later semantic/temporal layer may resolve equivalent quarter-turn branches
using sequence continuity or facet evidence. This layer does not invent that
identity.

## Running on a processed sequence

The sequence runner consumes the existing `sequence.json`, segmentation
masks, registration transforms and photometry files:

```python
from diamond360.asscher_pose_sequence import analyse_processed_sequence

result = analyse_processed_sequence(
    "path/to/processed-sequence",
    "path/to/new-pose-output",
)
```

The output directory contains:

- `asscher-pose.json` — ranked per-frame audit records;
- `canonical/*.npz` — brightness, mask and valid support in canonical pose;
- `asscher-pose-qc.jpg` — compact source-outline/canonical-view QC.

Bulk generated sequence outputs are research artifacts and should not normally
be committed. Keep only compact representative diagnostics when a validation
result needs to be archived.

## Validation status

Synthetic tests cover:

- translation, scale and rotation perturbations;
- the 90-degree orientation equivalence;
- similarity-transform round trips;
- explicit clipping rejection;
- projection-like trapezoidal distortion;
- reduced valid support;
- failed/degenerate silhouettes;
- centre-crossing spokes versus a closed table boundary;
- competing face-on lobe resolution without source-index labels;
- sequence ranking, transform composition and persistence.

The reproducible four-stone real-sequence benchmark uses the retained 256-frame
release bundles and the frozen policy:

- **IGI-LG756520111:** geometry alone preferred the ~129 lobe. The competing
  ~253/0 lobe has stronger closed-table continuity (0.730 versus 0.677,
  2.89 MAD separation), so final selection moves to the crown-side cluster.
- **IGI-LG818659722:** geometry lobes ~6 and ~132 are nearly tied. Closed-table
  continuity selects ~6/0 (0.735 versus 0.710, 2.04 MAD separation).
- **IGI-LG756580087:** the best broad geometry lobe already exceeds the next by
  0.229, so face resolution is not invoked.
- **IGI-LG836619414:** the corresponding geometry gap is 0.272, so face
  resolution is likewise not invoked.

The two ambiguous resolutions independently agree with the human validation
that the frame-0-side view is the likely crown/top side. No source-frame number
is used by production logic.

GitHub Actions run 17 of `asscher-pose-benchmark` passed the focused issue-73
tests, the recorded repository test suite, all four source downloads,
four-stone processing, QC generation and artifact upload. The existing
`geometric-crispness-benchmark` also passed on the same code head, exercising
the shared `normalized_geometry` path.

No threshold was fitted to the DiaGem/Sergey stored P1/P2/P3/C1 angle values.
