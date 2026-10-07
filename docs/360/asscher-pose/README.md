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
- sequence ranking, transform composition and persistence.

Real-sequence ranking remains the next validation step before #73 is marked
complete. That check should use several existing Sparkles 360 sequences without
tuning the v1 policy to the DiaGem stored angle values.
