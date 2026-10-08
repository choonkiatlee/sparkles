# #123 — Spatial atlas of apparent optical texture drift

## Why

Squash-merged [#178](https://github.com/choonkiatlee/sparkles/pull/178)
measured 34 adjacent-camera RGB pairs across four SHA-pinned Asschers
with frozen #96 anchor frames and #80 common image gauge. Image-plane
appearance changes were measurable, but raw local shift arrows can
be misleading because global frame drift, weak correlation, search
window clipping and uncertain crown orientation are mixed together.

The new atlas makes these differences **visible and auditable** without
changing the production estimator or assigning real/virtual facet labels.

## What each 4×4 map means

Each tile corresponds exactly to the prior 4×4 optical texture
correlation window in #178 (there is **no new segmentation**):

| Color/status | Operational meaning |
|---|---|
| Gray / unavailable | No useful gradient or insufficient support |
| Gold / ambiguous | Correlation match inconclusive; **no shift vector** |
| Violet / search-window limited | Local shift reaches the prior ±4-pixel search boundary; **censored, not precise** |
| Slate / no common reference | Confident local shift but fewer than eight confidently measured, non-clipped tiles across that pair |
| Blue / shared image shift | Local shift within 1.5 gauge pixels of the pairwise median among eight or more confident unclipped tiles |
| Orange / local residual shift | Local shift more than 1.5 pixels from that median; potentially changing image appearance, registration or lighting, **not a verified facet moving** |

The pair-common median is an *image registration diagnostic*, not a camera
pose estimate. Difference-from-median is a descriptive spatial residual.
The threshold and all colors are predeclared for every stone; there is
no certificate-specific training, fit, optical quality grade or claim
of geometric correctness. A low silhouette mask-overlap IoU (below .95)
is prominently flagged, without discarding the raw observation.

Per-frame-pair atlases are shown alongside **the original #178
camera-RGB neighbor QC panel**. Per-stone aggregates show 4×4 map
frequencies (denominators and unavailable counts retained), not
hand-picked "best" frames. Each observation preserves adjacent source
indices, crown-face role and all six named categories. Every optical
tile has physical facet identity `null`.

## Frozen negative controls

- All 16 tiles sharing an apparent (1,0) image shift must yield
  **zero local residuals**. Global registration drift is not labeled
  regional optical response.
- One independently changed tile is highlighted but still carries
  **no physical facet label**.
- Offsets hitting the ±4-pixel matching boundary must be **censored**,
  not promoted to a high-confidence optical velocity.
- Fewer than eight eligible unclipped local matches cannot invent
  a global reference or a local residual.
- Ambiguous/missing patches remain separate and cannot fabricate
  a zero-motion vector.
- Forged polished-facet IDs or accepted-geometry source claims fail.
- Archived four-stone anchor frames, face uncertainty, RGB panel
  provenance and optical counts must match #178 exactly.

## Dataset and non-goals

Read immutable [#178 run 37854076791](https://github.com/choonkiatlee/sparkles/actions/runs/37854076791)
artifacts directly. No repeated 256-frame source processing is needed.
The frozen physical geometry baseline stays unchanged.

The dataset contains 34 pairs: LG756520111 seven; LG756580087 nine;
LG818659722 nine; LG836619414 nine. Observed source-RGB optical
measurements are not a calibrated surface-flow field, a real-vs-virtual
facet classifier, an Asscher quality grade, or recovered C3/P3 geometry.
LG756580087 and LG836619414 retain **uncertain crown-facing** metadata.

## PR acceptance

- [ ] Frozen optical / provenance and atlas synthetic tests pass.
- [ ] All 34 original camera-RGB neighbor pairs carried into atlas;
      identical per-stone source selection, numerical input observations,
      unknown physical correspondence and crown-role provenance.
- [ ] Inspect LG756520111 frame 13/16 neighboring pair map and LG836619414
      boundary-limited/camera-drift examples.
- [ ] Record how often apparent local motion could simply be common
      registration drift, ambiguous texture or a clipped search.
- [ ] Keep research-only or revise; do not change the production estimator,
      #92 optical handoff, source stress, physical facet labels or any
      diamond quality score.

**The end goal is optical/perceptual characterization from the actual
online-shopping 360, without pretending its virtual facets are physical
facet junctions.** This PR only provides an auditable stepping stone.

## Four-stone archived RGB results (2026-10-08)

The first complete [original RGB atlas workflow](https://github.com/choonkiatlee/sparkles/actions/runs/37856385262)
replayed the same 34 archived consecutive pairs and passed every
atlas/provenance test. Values below are **tile evidence categories**, not
diamond optical grades or recovered physical facet flow.

| Certificate | Pairs | Shared-reference pairs | Ambiguous tiles | ±4 px clipped tiles | Local residual tiles | Low-IoU pairs | Crown role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| LG756520111 | 7 | 7 | 18/112 | 0 | 2 | 0 | likely crown |
| LG756580087 | 9 | 9 | 12/144 | 9 | 2 | 0 | uncertain |
| LG818659722 | 9 | 8 | 54/144 | 1 | 1 | 0 | likely crown |
| LG836619414 | 9 | 2 | 30/144 | **77** | 0 | **7/9** | uncertain |

Native original RGB and paired atlases reviewed for
LG756520111 source 15→16 and 12→13 and LG836619414 15→16.
The former's measured patch shifts largely share a common gauge-space
translation and should **not** be interpreted as 12 independent active
facets. In the latter, a large fraction of local correlation matches
hit the search boundary while the frozen silhouette overlaps poorly,
consistent with strong view/registration confounding; its apparent
motion must **not** be treated as a precise optical velocity.

LG818659722 has substantial tile ambiguity (54 of 144 patches),
demonstrating why replacing unresolved patches with zero motion would
be misleading.

**Research disposition: KEEP as an opt-in motion/registration/uncertainty
diagnostic, not an "optical sparkle grade" or a valid facet tracker.**
Only five localized residual tile observations appear across the four
stones under the predeclared threshold. A follow-on optical/perceptual
experiment should measure **spatial brightness/contrast modulation at
fixed image regions** independently of texture displacement, with
illumination normalization and view/crown uncertainty exposed, rather
than assuming motion arrows represent virtual-facet behavior.

The production #96 geometry estimator and the #92 physical-correspondence
boundary are unchanged; no #90 source stress.
