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

## First real four-stone result (8 October 2026)

The initial full frozen-source replay ([workflow 37852681446](https://github.com/choonkiatlee/sparkles/actions/runs/37852681446))
passed. It reported **34 of 34 adjacent ordinal pairs as measurable at the
pair level**. This means source images and overlapping masks existed; it
**does not** mean all local optical-patch shifts were unambiguous.

| IGI certificate | Crown-view metadata | Adjacent pairs | Median gain-normalized absolute change | Observations |
| --- | --- | ---: | ---: | --- |
| LG756520111 | likely crown | 7/7 | 0.0435 | Adjacent source 12–13 and 15–16 show localized changing interior bands and corner reflections; 1–4 of 16 local tiles ambiguous |
| LG756580087 | uncertain | 9/9 | 0.0590 | Some adjacent views have less mask overlap (0.956–0.960); do not label table/crown |
| LG818659722 | likely crown | 9/9 | 0.0585 | Source 6–7 illustrates substantial interior appearance change; 9 of 16 local tiles ambiguous in that pair |
| LG836619414 | uncertain | 9/9 | 0.1666 | Largest changes coincide with lower mask intersection-over-union (~0.93), so registration/silhouette mismatch may confound apparent optical motion |

**RGB visual QC:** The panels show real changes in bright/dark internal
reflections between adjacent source-camera frames, without requiring an
assertion of physical facet identity. However, the motion overlays also
show some orange bars on the registered footprint boundary, which are
*not* evidence of diamond light behavior. The render has therefore been
tightened to display heat only on the **eroded common valid stone interior**,
with a negative-control test for mismatched silhouette masks. This
rendering-only revision does not change any numeric motion metrics.

### Research disposition and next decision

**KEEP as an optical-only exploratory measurement, not a diamond quality
score or an estimator of physical/virtual facet classes.** Patch
correspondence is not yet a calibrated image-flow ground truth. In
particular, low mask overlap and uncertain crown orientation must
remain visible alongside motion measures. Any downstream comparison
should separate photometric change from apparent texture translation
and benchmark camera/gauge registration quality independently.
The original physically unsupported C3/table boundaries remain
unavailable; no source stress was run.
