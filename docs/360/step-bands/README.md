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

| Stone | Local evidence | selected `u` boundaries | frame QC | edge ratio vs legacy radii |
|---|---|---|---|---|
| LG756580087 | 8 original near-face-up processed frames | 0.497 / 0.780 / 0.874 | 8/8 ok | 2.14 / 2.15 / 1.87 |
| LG756520111 | 12 original near-face-up frames embedded in its evaluation evidence | 0.528 / 0.755 / 0.887 | 12/12 ok | 1.35 / 3.34 / 1.22 |
| LG818659722 | 12 original near-face-up frames embedded in its evaluation evidence | 0.597 / 0.742 / 0.881 | 12/12 ok | 5.16 / 2.38 / 1.12 |
| LG836619414 | exact 17-frame core window from the retained full 256-frame source | 0.503 / 0.748 / 0.887 | 17/17 ok | 1.78 / 2.24 / 1.25 |

Manual overlay review on these four stones shows the zoned boundaries following the same visually meaningful nested junctions much more consistently than the original unconstrained selector. The two Workshop/Diajewel evidence sets whose preprocessing segmentation is already marked `review` remain review-limited upstream even though their step-template frame support is strong.

For strict #18 parity, the remaining validation gap is rerunning the exact 17 consecutive core frames for LG756580087, LG756520111 and LG818659722. Those complete raw working stacks were deliberately not retained locally; the representative original frames above are useful cross-stone evidence but are not a substitute for that final consecutive-window rerun. The 33-frame windows remain sensitivity checks rather than template-training windows because #18 showed substantial outer-support degradation with wider pose excursions.

## Limits

These bands are an intermediate recorded-image representation. They are not exact crown/pavilion facet boundaries, do not reconstruct 3-D geometry, do not establish individual-facet identity, and do not prove leakage, fire, light return or cut quality. The centre band is an approximate central/table-like appearance region, not a certified table measurement.
