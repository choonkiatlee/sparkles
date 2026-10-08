# #110: frame-16 stability diagnostic (LG756520111)

## Scientific question

The frozen #96 outer-octagon-first estimator regressed in #115's #89
leave-one-out validation for certificate `IGI-LG756520111`. Removing selected
frame 16 changes `C3_TABLE` by more than one local crown-tier spacing.
**Why?** In particular, is it the change in the fitted physical silhouette
or the change in persistent inner-edge evidence?

This is **diagnosis only**. The code neither changes #96's cut thresholds nor
inserts a new policy into production. Strong interior image edges may be
reflections or virtual facets, not physical junctions.

## Reproduction from archived #115 result

The unchanged #96 fitter selects positions `16, 13, 18, 19, 17`. Removing 16
leaves `13, 18, 19, 17`. The #115 evidence records:

| Frozen measurement | All 5 | Without 16 |
|---|---:|---:|
| `GIRDLE_OUTLINE` median vertex residual | 0.009533 | 0.010370 |
| Outer-octagon confidence | 0.975070 | 0.970570 |
| `C1_C2.global_u` | 0.899371 | 0.874214 |
| `C2_C3.global_u` | 0.742138 | 0.742138 |
| `C3_TABLE.global_u` | 0.578616 | 0.477987 |
| `C3_TABLE.sector_support` | 0.875 | 0.750 |

Compared through frozen #88 metrics, `GIRDLE_OUTLINE` moves by at most
`0.006900` normalized units, whereas `C3_TABLE` moves by up to `0.163698`
normalized units / `1.015936` local tier spacings. This **suggests** an
interior-evidence problem, but does not yet identify its source.

## Four-factor diagnostic (predeclared)

The standalone `diamond360.asscher_geometry_frame_ablation` module evaluates:

| | Inner evidence from all five | Inner evidence without frame 16 |
|---|---|---|
| Outer octagon from all five | Original frozen #96 fit | Hold outer fixed, remove 16 only from inner evidence |
| Outer octagon without 16 | Change outer alone, hold inner evidence fixed | Original #115 leave-one-out fit |

The **same** `wireframe.fit_from_sector_evidence` and `outer_octagon.fit_consensus`
are called with their frozen parameters. Source frames remain in the originally
selected order; no frame is reselected as replacement. This is not an
optimization or a proposal to use a five-view silhouette with a four-view
inner model in production.

The comparison includes:
- all three crown-boundary radial/global/sector values and support/confidence;
- full #88 normalized per-boundary displacement, validity and identity;
- vertex-space outer RMS and maximum displacement in a common #80 gauge;
- per-source fitted octagon vertices/residuals;
- overlay of all four full scaffolds on **one and the same** held-in original
  camera-RGB view using #87's exact gauge-to-camera transform;
- fail-closed replay of #115's original primary and frame-16 leave-one-out
  outputs for the unchanged two diagonal cells.

No expert targets, human annotation or virtual-facet physical-label claims
enter the diagnostic.

## How to run

```bash
python -m unittest tests.test_asscher_geometry_frame_ablation -v
python -m diamond360.asscher_geometry_frame_ablation \
  --source-root outputs/asscher-frame16-sources/IGI-LG756520111 \
  --source-manifest docs/360/benchmark/per-stone/IGI-LG756520111/source-manifest.json \
  --reference-dir outputs/frozen-outer-stability \
  --output outputs/asscher-frame16-ablation
```

A dedicated CI job fetches the original SHA-256-verified 256-frame benchmark
bundle and the archived, immutable #115 result from run
[37755387174](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174).
It uploads `diagnostic.json` and `factor-qc.jpg`, but neither source frames
nor bulk derived data are committed.

## Decision rule and research follow-up

If changing only inner evidence reproduces the `C3_TABLE` jump while changing
only the outer fit does not, prioritize investigating the radial-edge/tier
inference and how it aggregates frame support, rather than prematurely
rewriting the face-on selection score.

If outer-only causes the jump, investigate the #96 silhouette normalization and
view-selection consensus. If both contribute or neither reproduces the effect,
preserve that ambiguity and investigate interactions.

Either way #110's later A/B of alternate view policies must remain target-blind,
be predeclared and rerun across the full four-stone #76 validation set.
Do not treat this one diamond as a per-stone tuning target.
