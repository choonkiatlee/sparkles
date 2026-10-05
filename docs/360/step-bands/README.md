# Asscher step-band correspondence

Issue #19 adds a semantic spatial layer after `diamond360` preprocessing and before later dynamic descriptors.

## Representation

The implementation deliberately tracks **ordered nested step bands**, not individual facets.

1. Sample registered brightness along 96 rays from the canonical centre.
2. Express radius as `u = distance / silhouette radius in the same direction`, so the outline is `u=1` even through clipped corners.
3. Use the absolute radial derivative of lightly smoothed, ray-median-normalised brightness as edge evidence.
4. Aggregate evidence across the full selected face-up sequence and across eight Asscher-oriented side/corner sectors.
5. Select three persistent ordered boundaries and refine eight sector control points for each.
6. Map that one sequence-level template through each frame's silhouette to produce four masks:
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

The #18 benchmark supplies the real validation set: four complete 256-frame Asscher sequences across Diajewel and Workshop plus one intentionally partial negative case. Before #19 is considered complete, run this stage on the fixed 17-frame core windows for all four complete stones, manually inspect overlays, and record any source/segmentation-specific failures. The 33-frame windows are sensitivity checks rather than template-training windows because #18 showed substantial outer-support degradation with wider pose excursions.

## Limits

These bands are an intermediate recorded-image representation. They are not exact crown/pavilion facet boundaries, do not reconstruct 3-D geometry, do not establish individual-facet identity, and do not prove leakage, fire, light return or cut quality. The centre band is an approximate central/table-like appearance region, not a certified table measurement.
