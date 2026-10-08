# #123: registration/overlap confounds in adjacent 360 optical appearance

## Motivation

The opt-in #178 optical-neighbor experiment, squash-merged at
[PR #178](https://github.com/choonkiatlee/sparkles/pull/178), showed real
changes in original-camera RGB appearance across 34 adjacent frame pairs,
without any claim to physical facets.

That initial result also exposed **two different measurement limitations**:

- LG836619414 exhibited several larger gain-normalized appearance changes
  when measured silhouette overlap was approximately 0.93, compared
  with other pairs near 0.99. Its face identity was also uncertain.
- LG818659722's frame 6 to 7 pair had overlap approximately 0.998 but
  **9/16 ambiguous optical tile matches**, alongside substantial
  appearance change. High silhouette overlap does not guarantee that
  an interior reflection can be followed reliably.

A quantitative association between mask overlap and appearance change
**does not prove** that registration errors caused the changes:
lighting, camera angle, true optical behavior, silhouette segmentation and
registration can all co-vary as a diamond rotates.

## Research protocol

Read *only* the immutable successful #178 artifact
([run 37854076791](https://github.com/choonkiatlee/sparkles/actions/runs/37854076791)).
Verify the original #96 benchmark manifest fingerprint, all four stone
identities, frozen anchor positions and every adjacent source-pair index.
No new downloading, rerunning source stress, recomputing geometry or
altering measured #178 image quantities.

For **each of 34 measured pairs**, separately report:

1. Original measured silhouette IoU and a predeclared overlap stratum:
   **low below 0.95**, intermediate [0.95,0.98), high >=0.98.
2. Raw camera luminance gain ratio and normalized median/p90 appearance
   change exactly as #178 stored it.
3. Optical local-patch confidence over the predeclared 4x4 grid:
   proportion measured, ambiguous and unavailable; low matching fraction
   below 0.50, intermediate [0.50,0.75), high >=0.75.
4. Mode of confidently measured *apparent optical texture shifts* and
   its fractional support. This is not independently measured global
   camera motion or physical facet motion.
5. Per-stone median appearance change and ambiguity by overlap stratum.
   A within-stone low-minus-high overlap median contrast is emitted
   only if **both strata are actually observed**; otherwise abstain.
6. Descriptive **within-stone** Spearman association when >=5 pairs
   have varying overlap and change; note that overlapping consecutive
   pairs **share frames**, so the nominal p-value is not independent
   evidence or a causal estimate. Avoid pooled cross-stone regression
   and any derived diamond score.

All optical observations preserve their original source-index pair,
crown-role uncertainty and cannot carry a physical facet semantic ID.

## Tests and decision criteria

- [ ] Invalid source-frame indices, patched archived physical labels,
      missing/duplicated tiles or impossible shifts fail closed.
- [ ] Unavailable frames remain unavailable, not zero change.
- [ ] Fixed low/intermediate/high overlap and patch-confidence strata
      behave as predeclared; within-stone stratified comparison does not
      invent missing high/low bins.
- [ ] Both #123 physical/optical contracts remain intact; no claim that
      a virtual/reflected line is a polished junction.
- [ ] Reproducibly analyze all **34 original adjacent pairs** in all
      **four frozen stones**, with zero image reprocessing or source stress.
- [ ] Report observations and possible confounds, not causal attribution.

**Scope:** an optical measurement *quality-control audit*, not a physical
facet detector, camera calibration, image correction, virtual-facet
classifier, animation renderer, light-performance metric, or diamond
grading model. In particular, an association between high change and low
overlap is a reason for caution, not grounds to subtract a fitted
registration correction from that stone's brightness measurements.

After reviewing the descriptive results, the next genuinely independent
experiment would vary registration or common-interior masks on the
*same original frames*, with a locked protocol, to see whether appearance
contrasts are stable under those controlled changes.
