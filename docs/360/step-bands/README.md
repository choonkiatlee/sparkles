# Asscher step-band correspondence

Issue #19 adds a semantic spatial layer after `diamond360` preprocessing and before later dynamic descriptors.

## Representation

The implementation deliberately tracks **ordered nested step bands**, not individual facets.

1. Sample registered brightness along 96 rays from the canonical centre.
2. Express radius as `u = distance / silhouette radius in the same direction`, so the outline is `u=1` even through clipped corners.
3. Use the absolute radial derivative of lightly smoothed, ray-median-normalised brightness as edge evidence.
4. Aggregate evidence across the full selected face-up sequence and across eight Asscher-oriented side/corner sectors.
5. Select one supported persistent boundary inside each broad semantic radial zone:
   centre/inner `u=0.42..0.60`, inner/middle `u=0.64..0.82`, and middle/outer
   `u=0.82..0.92`. A stronger edge outside its zone is not allowed to steal the
   ordinal label; a missing supported edge becomes an explicit failure.
6. Refine eight sector control points for each selected boundary.
7. Map that one sequence-level template through each frame's silhouette to produce four masks:
   `centre`, `inner_step`, `middle_step`, `outer_step`.

Per-frame local edge matches are retained only as QC. They **do not move the masks** or claim that a pixel is the same physical facet from frame to frame. This avoids optical-flow brightness-constancy assumptions that are particularly weak for specular diamond video.

The eight controls use the same side/corner orientation as the existing coarse sectors. They permit a boundary to differ between straight sides and clipped corners without naming a windmill facet. Windmill identity remains intentionally unsupported.

## Run

Run preprocessing first, then select a continuous face-up interval:

```bash
python -m diamond360.asscher_steps /path/to/processed \
  --output /tmp/asscher-steps \
  --indices 248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8 \
  --wrap
```

Outputs:

- `steps.json`: template boundaries, sector controls, per-frame support/failure diagnostics and comparison with the old fixed radii;
- `regions/*.npz`: per-frame semantic masks when the sequence template is usable;
- `edge-profile.png`: persistent radial edge evidence with legacy 0.20/0.45/0.70 radii and selected boundaries;
- `overlays.jpg`: representative registered frames with the new bands overlaid.

The output status is `ok`, `review` or `unavailable`. Weak or inseparable edge structure is surfaced rather than converted into forced correspondence.

## Coarse-mask comparison

`coarse_comparison.edge_alignment` compares persistent radial edge evidence at each detected boundary with the corresponding legacy fixed radius. This is a diagnostic, not a quality score. A ratio above one means only that the detected boundary lies on stronger sequence-persistent image structure.

The new regions should later be compared with coarse-region temporal traces on identical windows. #20 should consume the semantic masks only after this step has passed real-sequence QC.

## Validation

Current automated tests cover:

- recovery of three nested boundaries despite frame-to-frame brightness inversion;
- side/corner boundary variation while preserving ordering;
- exact one-time partition of the silhouette into four bands;
- stronger edge alignment than deliberately offset coarse rings in the synthetic case;
- explicit `unavailable` output when no persistent radial structure exists;
- an end-to-end synthetic processed sequence producing JSON, masks and visual QC.

The #18 benchmark supplies the real validation set: four complete 256-frame Asscher sequences across Diajewel and Workshop plus one intentionally partial negative case.

Local validation found an important failure in the first global-peak selector: on LG756580087 it chose a strong inner reflection near `u=0.245` as the first boundary, while LG836619414 chose the visually corresponding major step junction near `u=0.50`. The semantic-zone rule above fixes that ordinal mismatch rather than tuning peak strength stone-by-stone.

## Exact-core validation · 5 October 2026

Ran locally from PR #25 head `cb9b366`, with the JSON syntax fix and semantic-window
margin diagnostic below; no GitHub Actions. All four regenerated sources use the
same exact wrapped indices `248..255,0..8` (17 frames each), default preprocessing,
`gain=1.0`, and the #18 `accept_review=True` policy. No stone-specific thresholds
or semantic windows were changed. Viewer ordering reproduces the full archived
LG756580087 source manifest. All 38 overlapping archived-original hashes match;
there are no mismatches. New core positions without retained originals are recorded
with source batch, stored position and SHA-256 rather than claimed independently verified.

| Stone | matched originals | selected `u` boundaries | template | local frame support | edge ratios vs coarse | upstream segmentation |
|---|---:|---|---|---|---|---|
| [LG756580087](exact-core/IGI-LG756580087/overlays.jpg) | 8 | 0.497 / 0.780 / 0.874 | ok | 17/17 ok | 1.96 / 2.01 / 1.61 | 17/17 ok |
| [LG756520111](exact-core/IGI-LG756520111/overlays.jpg) | 10 | 0.522 / 0.755 / 0.887 | ok | 17/17 ok | 1.35 / 2.81 / 1.39 | 17/17 review |
| [LG818659722](exact-core/IGI-LG818659722/overlays.jpg) | 10 | 0.597 / 0.742 / 0.887 | **review** | 17/17 ok | 5.65 / 1.91 / 1.08 | 17/17 review |
| [LG836619414](exact-core/IGI-LG836619414/overlays.jpg) | 10 | 0.503 / 0.748 / 0.887 | ok | 17/17 ok | 1.78 / 2.24 / 1.25 | 17/17 ok |

Manual inspection of the nine representative overlays per stone (248,250,252,254,
0,2,4,6,8), together with the edge profiles, finds ordered broad central / inner /
middle / outer junctions through the changing brightness. LG756580087 does not
revert to the unrelated reflection at `u≈0.245`. The outer division is approximate,
especially along corners; these masks are broad image bands, not physical facet labels.
LG756520111's late pale frames retain local edge support, but neither its strong
step support nor LG818659722's clears their upstream silhouette uncertainty.

**Confirmed failure/confidence case:** LG818659722's first selected boundary remains
`u=0.597484`, only `0.002516` from the fixed upper limit 0.60, or 0.40 radial samples.
Each boundary now reports `semantic_window`, `window_margin`,
`window_margin_samples` and `near_window_edge`. A usable template within one radial
sample of either limit becomes `review` with reason `semantic_window_edge`.
This exposes prior sensitivity without widening the window or moving the boundary.
The margin is a raw diagnostic, not a calibrated confidence probability. Local
frame statuses describe edge support only; consumers must also check template and
upstream preprocessing status before using masks.

Saved evidence: [summary](exact-core/summary.json),
[artifact hashes](exact-core/artifact-manifest.json), and one directory per stone
with `source-manifest.json`, `preprocessing-qc.json`, `steps.json`, `edge-profile.png`,
`overlays.jpg` and all 17 `regions/*.npz`. The source stacks themselves remain
uncommitted. The detector file hash in the summary identifies the exact code used.

The baseline PR could not import because the `steps.json` trailing-newline string
was malformed; the existing end-to-end test reproduced this and passes after the
fix. The new window-edge regression fails without the margin/status change and
passes with it. `python -m unittest discover -s tests -v`: **54 tests pass**.
The stronger-inner-reflection regression is preserved.

The strict four-stone #18-core rerun gap is closed. The method is suitable for
reviewable broad-band correspondence on these windows, with the explicit review
cases above. Semantic-versus-coarse temporal trace stability remains a downstream
comparison, not established by these edge ratios. The 33-frame windows remain
sensitivity checks because #18 showed outer-support degradation at wider poses.

## Limits

These bands are an intermediate recorded-image representation. They are not exact crown/pavilion facet boundaries, do not reconstruct 3-D geometry, do not establish individual-facet identity, and do not prove leakage, fire, light return or cut quality. The centre band is an approximate central/table-like appearance region, not a certified table measurement.
