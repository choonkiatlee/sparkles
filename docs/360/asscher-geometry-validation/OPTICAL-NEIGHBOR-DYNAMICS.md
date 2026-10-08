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

- [x] Frozen #146/#162 archive hashes, selected frames and crown
      provenance replay on all four stones.
- [x] Negative tests: source-frame wrap/gaps, missingness, candidate
      collisions, unsupported RGB lines, forged physical identity.
- [x] JSON and original RGB pair QC for every <=3-frame window,
      with no artificially completed tracks.
- [x] Optical motion/contrast findings and REVISE/KEEP decision
      based on actual visual QC, not numerical stability alone.


## Four-stone result and original RGB review (2026-10-08)

[Workflow 37852805244](https://github.com/choonkiatlee/sparkles/actions/runs/37852805244)
completed its focused tests, frozen source-archive replay and original-camera
RGB pair render successfully. The artifact named
asscher-optical-neighbor-dynamics contains all per-stone JSON and images.

| Certificate | Crown view provenance | Sampled near-neighbor windows (true consecutive) | Tentative optical pairs | Not redetected | Newly detected |
| --- | --- | ---: | ---: | ---: | ---: |
| IGI-LG756520111 | likely crown | 4 (3) | 17 | 7 | 8 |
| IGI-LG756580087 | uncertain | 2 (1) | 16 | 9 | 12 |
| IGI-LG818659722 | likely crown | 4 (1) | 3 | 18 | 14 |
| IGI-LG836619414 | uncertain | 2 (1) | 5 | 3 | 6 |
| **Total** | | **12 (6)** | **41** | **37** | **40** |

These are counts of **threshold-selected optical image observations**, not
numbers of facets, nor a performance rating. A missed match is censored
by the prior RGB line detector and spatial matching threshold.
Six comparisons are genuinely consecutive frames; the other six have
one or two unsampled intermediate rotations. No 256-frame continuity
or optical track through a gap is claimed.

### Visual QC findings

- LG756520111 **src16 -> src17 -> src18**: the original native RGB crops
  visibly change internal bright/dark patterns across genuinely consecutive
  source frames. Several matched contrast candidates show small image-plane
  radial movements (typically of the order of 0.006–0.032 in outer
  silhouette-normalized radial fraction), while other candidates are
  not redetected. This documents appearance variation, **not the
  trajectory of a polished facet**.
- LG818659722 **src8 -> src10**: the RGB appearance of the central region
  changes visibly. Its line detector emits *zero* tentative matched
  candidates over this two-frame gap (five not redetected and four newly
  detected). This is an **important negative example**: neither missing
  candidate pairs nor a changed image means that a physical facet vanished,
  and the intervening src9 was not observed in this pilot.
- LG756580087 **src4 -> src5**: eight tentative matches despite changing
  contrast in the original camera views, but the current crown-facing
  metadata remains *uncertain*. This can inform optical observation
  but cannot be used to validate C3/table geometry.
- LG836619414 also has uncertain crown-facing provenance. Its sparse
  line coincidences are observational evidence only.

**Gradient-strength caveat:** the archived #146 field called
gradient_strength is a *frame-locally normalized directional edge
support measure*. Its change is **not an absolute photometric
brightness change** and cannot establish light return or optical
quality across different illumination conditions. The source-RGB
image comparison is therefore essential.

**Research disposition: KEEP this bounded optical-change diagnostic**,
not a physical-facet estimator or a reliable long-lived feature tracker.
The next step, if useful, is a separate predeclared *dense* contiguous
source-window optical study with better region-level brightness,
darkness/contrast and virtual/reflection ambiguity summaries. Keep
physical surfaces and virtual-facet hypotheses separate, retain missing
detections and unresolved crown metadata, and compare against these
frozen negative examples. No automatic virtual labels, physical
facet angles, quality scores or #90 stress runs.
