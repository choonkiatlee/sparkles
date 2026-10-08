# #123: optical appearance drift across neighboring original 360 views

## Question

Can we quantify how an Asscher **looks** as it rotates without asserting
which bright lines, reflections, virtual facets or physical facets caused
the observed changes? This is the direct follow-up to #140/#146/#162's
negative facet-identity findings and #171/#172/#176's fail-closed
physical/optical provenance split.

## Frozen, target-blind experimental protocol

Four immutable SHA-256-pinned complete original-camera RGB sequences,
processed by the unchanged preprocessing and #73/#80 pose pipeline.
Use the identical #96 outer-octagon **selected source views** (typically
five per stone) as **anchors only**. For each anchor examine the direct
ordinal predecessor and successor (including 255 to 0), deduplicated,
capped at 12 pairs/stone. No comparison of distant "similar-looking"
views and no stone-specific thresholds.

Reject individual comparisons if their canonical source-camera / #80
gauge support is missing. If a stone's face lobe is resolved, only
compare views explicitly marked likely crown-facing; otherwise preserve
the original `uncertain` crown role in every row. Do not silently
claim a table/crown appearance on unresolved stones.

For each admissible pair:

1. Read each **original camera RGB** frame and reproject luminance with
   its existing exact sequence-gauge-to-camera transform (only the
   measured silhouette/registration is trusted).
2. Analyze the common eroded interior to exclude silhouette misalignment
   and segmentation-border artifacts. Record mask-overlap fraction and
   source indices / rotation phases.
3. Separate overall camera exposure: report the *raw median luminance
   ratio* and measure gain-normalized median/p90 absolute appearance
   differences and local gradient-energy differences. Scaling brightness
   by a constant is explicitly tested not to invent normalized change.
4. Within a predeclared 4x4 grid, compare local gradient patterns using
   at most +/-4 pixels of 2D translation and normalized correlation.
   Record each patch's best zero-shift and shifted correlation, runner-up
   margin, overlap pixel count and `measured`, `ambiguous` or
   `unavailable`. Weak texture, invalid masks, and repeated local
   patterns cannot be assigned confident movement.
5. Each measured displacement is **registered optical texture drift**,
   not motion of an identified facet and not a 3D property. No
   optical patch is relabeled C3/TABLE/P1/P2/P3, physical geometry or
   a true/virtual facet classifier.
6. Export all measured adjacent pairs, skipped reasons, per-pair native
   **source camera RGB left/right** and a registered change heatmap
   with optical arrows, plus per-stone contact sheets and JSON.
   There is no success/failure threshold based on diamond quality.

## Important limitations

This does *not* solve image flow, surface triangulation or facet
identification. Residual camera registration changes, illumination
shifts, turning geometry and virtual-facet appearance can all move
the observed gradient pattern. The shift is measured in the **existing
2D #80 gauge** only. The thresholded correlation should be treated
as a QC observation, not precision ground truth for movement.
Raw gain and gain-normalized appearance are reported separately;
localized directional lighting changes will not disappear through
gain normalization.

An all-flat or photometrically featureless patch is unavailable.
An ambiguous shift is **not** replaced by (0,0). Strong repeated
features remain optical. Missing neighboring frames remain visible.

The prior #123 provenance-only adapters preserve physical outer
silhouette evidence separately from the unverified optical appearance
inventory; this experiment consumes the same frozen pose and RGB,
**not** the adapted facet labels. It exports no physical facet identities
and cannot be passed to the optical-to-physical consumer gate.

## Completion checks

- [ ] Synthetic controls: pure gain change has near-zero normalized
      difference; moved textured pattern produces optical shift;
      flat/no-support cases abstain.
- [ ] Four frozen source-bundle hashes and #96 anchor source indices
      reproduced.
- [ ] Source-RGB overlays on actual **neighboring** frames, particularly
      LG756520111 around original frames 13 and 16, reviewed as
      optical appearance (not physical facets).
- [ ] All four stones retain crown-face uncertainty and explicit
      unavailable/ambiguous patch counts.
- [ ] No changes to #96 default estimator, physical C3/table claims,
      diamond-quality scoring or #90 source stress.

Research disposition will be **KEEP/REVISE** for an *optical*
measurement after actual RGB QC. Mere ability to compute local
translations is not evidence that a reflection is a real facet edge.
