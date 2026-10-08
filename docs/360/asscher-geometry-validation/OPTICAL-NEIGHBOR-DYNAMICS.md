# #123 — sparse neighboring-frame optical appearance motion

## Why

Previous native-camera RGB experiments (#140, #146, #162) demonstrated
that internal reflections / virtual facets can look like straight,
connected, persistent physical edges. #171/#172/#176 have now separated
their *image-plane optical observations* from *physically verified*
external geometry, leaving actual C1/C2/C3 polished boundary
correspondence explicitly unavailable.

Instead of trying to force an inner octagon, ask:

**When an Asscher rotates a frame or two, how do the observed optical
contrast features move or change strength?**

This is optical/perceptual evidence and **not a facet identifier**.

## Predeclared first experiment

- Use only the four hash-verified original source rotations already
  processed by #146 (workflow 37813575116) and #162
  (workflow 37815198934). The SHA-256-pinned source manifest and
  selected source frame sets are unchanged. Do **not** download or
  reprocess the 256 original RGB frames.
- Sort each stone's five frozen selected geometry-support frames by
  its original **rotation position** on the 256-frame cycle. Compare
  adjacent *selected* observations only when the forward source gap
  is <=3 frames. Explicitly record all larger gaps as **not observed**.
  Gap=1 means actually consecutive original source frames; gap=2/3
  leaves 1/2 unseen frames and cannot establish continuous motion.
- From each view use **every observed contiguous RGB line candidate**
  from #146, with original orientation family, normalized radial
  position, gauge midpoint, measured coverage and gradient strength.
  Keep all ambiguous candidates, without selecting a table radius.
- Pair two image-plane observations only if they share one of the
  eight outer-silhouette orientation families; radial displacement
  <=0.045 and normalized image-plane midpoint distance <=0.16.
  Resolve collisions one-to-one by fixed, deterministic distance
  ordering. Pairs are **tentative optical coincidences**, not
  structural tracks or physical facet identities.
- Record signed radial displacement, normalized XY shift, strength and
  coverage changes, and candidates no longer detected/newly detected.
  **Non-redetection is threshold-censored**, not proof a feature
  physically appeared/disappeared, much less a polished facet.
- Each paired view receives a visual comparison of the original
  native-camera RGB (unannotated left-hand crop from #146) and a
  separate optical candidate radial-position plot. Preserve crown
  lobe uncertainty and exact source frame provenance.
- Require the #172/#176 physical/optical provenance adapter to accept
  both upstream source records. Unresolved C1_C2, C2_C3, C3_TABLE
  **always remain physically unavailable**. Neither repeated nor
  moving optical contrasts receive labels of polished *or confirmed
  virtual* facets.

## What to evaluate

Inspect particularly IGI-LG756520111 source 16->17->18->19, and
IGI-LG818659722 source 10->11. Compare observed position and
gradient-strength changes against RGB visual changes, taking into
account that these are 256-step vendor 360s, not calibrated physical
camera rotations. Look for optical differences that may be useful
to downstream step-cut optical/perceptual characterization without
needing false physical facet geometry.

Negative controls: a perfectly stable optical line is **not** physical;
a vanishing candidate is **not** an absent facet; a fake archive
claiming physical facet correspondence is rejected; no transitive
physical track; unresolved crown views stay uncertain; unsampled
frame gaps are visible, never interpolated.

## Scope and limitations

This is a deliberately **sparse pilot**, based on five frozen
geometry-selected source frames per stone. Its optical detections have
their own thresholds and may miss interesting faint bands. The
orientation families are inherited from the frozen outer silhouette;
they do not prove any inner facet's orientation.

If the sparse pairings expose compelling visually consistent patterns,
the next independently scoped research step can sample a *denser
predeclared* contiguous frame window from the original 360 media,
keeping optical appearance measurements and geometry separate.

No new 360 ingestion, source stress, surface angles, production
wireframe, #92 geometry-to-optics handoff, or diamond quality scoring.

## Acceptance

- [ ] Frozen #146/#162 archive hashes, selected frames and crown
      provenance replay on all four stones.
- [ ] Negative tests: source-frame wrap/gaps, missingness, candidate
      collisions, unsupported RGB lines, forged physical identity.
- [ ] JSON and original RGB pair QC for every <=3-frame window,
      with no artificially completed tracks.
- [ ] Optical motion/contrast findings and REVISE/KEEP decision
      based on actual visual QC, not numerical stability alone.
