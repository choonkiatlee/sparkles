# Synthetic projected Asscher pavilion generalization (issue #148)

This is an independent synthetic baseline for generalization, not another
attempt to tune the DiaGem 2008 profile. One photograph's apparently plausible
slope changes may not identify the physical pavilion tier junctions.

## Anatomical and geometric scope

The pointed pavilion tip is at small image y; the girdle-region envelope is at
large y. Each left/right side has 1–3 visible continuous image-plane straight
stretches with independent ordered normalized-y changepoints and positive
radial x-per-y slopes. No left/right mirror symmetry is forced.

The generator supports image translation, affine shear, pixel-like Gaussian
noise, row blur, missing spans, severe near-girdle shadow occlusion, outliers
and optional interior reflection-like distractions. The latter never enter
the estimator. Ground-truth generating projected knots remain in a separate
record from the strict observation-only estimator input.

**Important limitation:** This is a **2D projected silhouette generator**, NOT
a calibrated 3D Asscher faceting / physical camera model. True P1/P2/P3
facets, perspective/tilt visibility, optical ray paths and physical angles
are unknown. A projected bend is not automatically a polished facet junction.

## Modules

- diamond360/asscher_profile_synthetic.py: deterministic Side/Scene
  definitions, known projected x(y), occlusion/noise and diagnostic image
- diamond360/asscher_profile_projected_fit.py: target-blind robust continuous
  hinge model with fixed complexity penalty, 1–3 apparent straight stretches,
  honest ambiguous/unavailable states, independent left/right fits
- diamond360/asscher_profile_synthetic_benchmark.py: predetermined 12-case
  synthetic evaluation with full diagnostic results and montage
- tests/test_asscher_projected_pavilion_synthetic.py: 10 source-independent
  tests covering known 1/2/3 steps, asymmetry, shear, distractor invariance,
  source-truth leakage, missing evidence, invalid input and determinism
- .github/workflows/asscher-projected-pavilion-synthetic.yml:
  isolated CI with full benchmark artifact upload

The estimator has NO generator, DiaGem, Sergey, original source-image or
physical angle input dependency. Extra truth/optical observation fields are
rejected by its strict API.

## First frozen synthetic holdout result

[PR #150](https://github.com/choonkiatlee/sparkles/pull/150)
[GitHub Actions 37810635543](https://github.com/choonkiatlee/sparkles/actions/runs/37810635543)

| Measurement | 12-case holdout |
| --- | ---: |
| Independent side profiles | 24 |
| True synthetic projected changepoints | 31 |
| Correct proposals within 8 px | 23 |
| Breakpoint recall | 74.2% |
| Breakpoint precision | 88.5% |
| Correct chosen segment counts | 83.3% |
| Mean absolute error, matched breaks only | 1.12 px |
| Explicitly unavailable sides | 3 |
| Ambiguous sides | 1 |

These are synthetic measurements, NOT real-diamond accuracy.

**Keep the failures visible rather than tuning them away.**

- h09_shadow_most_of_right: right side abstains on insufficient source
  support, missing two generating projected changepoints.
- h10_random_dropout: under 50% intermittent dropout the left side returns
  two wrong projected breaks and misses two genuine generating breaks;
  the failure is not caught by the current confidence/status rule.
- h11_sparse_both: both sides abstain and miss one break each.
- h12_weak_changepoint: weak left change missed, weak right produces an
  ambiguous but misplaced bend.
- Clean 1/2/3, asymmetry, moderate blur and sheared 2D cases generally
  recover their projected shape changes.

The 1.12-pixel mean applies only to the matched 23, and does NOT account for
eight missed true breakpoints. All per-side misses, false positives, statuses
and the known generating truth are retained in the JSON report.

Because these 12 holdout results have now been inspected, any subsequent
model tuning should treat this collection as development regression cases,
and build a **fresh truly unseen holdout** before making better-generalization
claims.

## Reproduce

Run from the repo root:

    python -m unittest tests.test_asscher_projected_pavilion_synthetic -v
    python -m diamond360.asscher_profile_synthetic_benchmark --output outputs/asscher-projected-pavilion-synthetic

The output contains synthetic-holdout-report.json (every case, including
failures) and synthetic-pavilion-montage.png. Black markers are generating
image-plane knots; orange rings are estimated projected changepoints.

## Next experiments, NOT part of phase 1

1. Generate a proper 3D faceted pavilion with independent P1/P2/P3 tier
   junctions and project its silhouette under a calibrated camera, allowing
   hidden geometry and left/right asymmetry.
2. Simulate 3D camera pose, oblique-view visibility, external background and
   internal reflections without confusing virtual edges with true silhouette.
3. Freeze a method and assess new unseen synthetic cases plus a panel of
   genuinely independent real profile photos. Only then examine the frozen
   #91 DiaGem/Sergey case as an external qualitative comparator.

No changes to #75 face-up geometry, #88 frozen contract, #91/#118 case-specific
extractor, or #123 virtual-facet research.
