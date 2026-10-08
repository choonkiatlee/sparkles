# #123 / #124 — connected original-RGB junction diagnostic

## Why this replaces scoring more radial/straight peaks

Visual review of #140 found both apparently regular C3 polygons ran *through
facet interiors*. The #146 source camera-RGB detector correctly abstained from
all eight-sided facet reconstructions on the 20 selected frames, while still
finding long optical contrast lines that may not be polished facet edges.

Neither image brightness, temporal persistence, nor straightness alone is
sufficient to assign a physical facet boundary. The research hypothesis here
is narrower: **do locally co-located line endpoints with two independent
image-gradient orientations, connected by the same directly observed line,
yield a more auditable candidate junction network?**

## Method (observational, not a 3-D reconstruction)

- Reuse the fixed #96 outer silhouette, frame selection and #80
  gauge-to-original-camera mapping. No reprocessing thresholds changed.
- Reuse *all*, not only top-1, independently detected side-direction RGB
  line candidates from #146 (up to three per side), including their directly
  observed contiguous segment spans. Do **not** use the earlier u=0.478 /
  0.579 peak locations or force a table-sized octagon.
- For adjacent side-orientation families, intersect each measured pair of
  line equations. Reject a corner if either actual observed segment is
  more than 0.045 gauge units from the intersection. A geometrically valid
  extension of an unsupported segment does **not** count.
- Require positive oriented gradient evidence from **both** independent
  edge directions within a local ±0.045 gauge-radius neighborhood. Each
  normal must have at least two samples exceeding half the per-frame
  detected edge reference. No corner without two local orientations.
- A graph edge joins two supported junctions only when they reference
  the **same underlying observed line candidate**. Report isolated nodes,
  connected fragments, missing corners, maximal components, and rejection
  reasons. A complete polygon is **never** filled or emitted.
- Gate interpretation on #73 crown-face selection. Only
  `face_selection.status=resolved` and all selected
  `face_role=likely_crown_lobe` may be called *likely crown*; otherwise
  output explicit `uncertain` and avoid interpreting as C3 or table
  structure.
- Per-stone independent candidate counts by frame, eight corner-slot
  support counts, and leave-one-out support summaries (counts only, **no**
  opportunistic estimator refit). Preserve source-index and pose metadata.
- RGB panels: untouched source, all original supported subsegments, and
  junction circles / connections where two-orientation support exists.
  The panel states that every detected corner is still an **image-plane
  candidate**, not confirmed polished-facet geometry.

## Frozen benchmark and controls

Four SHA-256 pinned 360 source bundles; five frozen #96 selected frames
per stone, exact #80 sequence-gauge-to-camera mapping; compare selected
indices to immutable #96 workflow artifact 37755387174.

Focused synthetic tests must check missing-edge abstention, true
line-line intersections close to **supported** spans, no gradient means
no junction even when eight synthetic line positions are supplied,
same-segment graph topology, and unresolved crown-view gating.

Use a stacked draft PR with base #146. Nothing here is a change to the
production/default wireframe estimator, geometry scoring, source stress,
or #140/#146 diagnostic results.

## Visual validation / research disposition

Compare LG756520111 source 13 and 16, LG818659722 source 10, and the other
three stones. Answer with actual original RGB, not just synthetic scores:
are candidate *junctions* coincident with visible facet-to-facet corners?
Are apparent connections instead reflection crossings? How often is
support insufficient? Does the crown-view gate prevent false table claims?
Document KEEP/REVISE/REJECT from this evidence.

**Success is not a completed octagon or a lower numerical displacement**.
The deliverable is credible observational support with explicit
unavailability and a testable decision on whether physical facet topology
can be recovered from these images. No #90 source-stress runs.


## Completed four-stone evidence and virtual-facet review (2026-10-08)

[Workflow 37815198934](https://github.com/choonkiatlee/sparkles/actions/runs/37815198934) passed the focused unit tests, frozen view-selection checks and hash-pinned four-stone native-camera RGB replay. Its downloadable artifact is `asscher-rgb-junction-graph-diagnostic`.

| Certificate | Total candidate junctions, five frames | Connected graph edges | Crown-face identity |
| --- | ---: | ---: | --- |
| LG756520111 | 0 | 0 | likely crown |
| LG756580087 | 8 | 1 | uncertain |
| LG818659722 | 4 | 1 | likely crown |
| LG836619414 | 1 | 0 | uncertain |
| **Total** | **13** | **2** | |

No frame yielded a connected eight-corner polygon, and LG756520111 (the original C3 instability) had no supported junctions at all.

**Source-RGB visual QC and user review:** Some detected straight segments follow **virtual facets / optical reflections**, not the physical facet-to-facet junctions sought by this geometry estimator. The observed connections are too sparse to establish physical boundary identity. A two-orientation image gradient at an intersection and graph continuity are therefore **insufficient positive controls** for physical facet labels. This is a provenance/identifiability limitation, not simply a parameter-tuning issue.

**Research decision: REVISE / no geometry promotion.** Retain the diagnostic and negative result, but do not interpret `junction_evidence.nodes` or `edges` as observed polished-facet junctions: their permitted provenance remains `optical_or_structural_unresolved`. Mark all physical interior facet identities **unavailable** pending independent corroboration. Preserve the frozen #96 outer contour as the only directly supported physical outline. If work continues, prioritize #123's separation of optical/virtual-facet appearance from externally or multi-view corroborated physical geometry. Avoid further peak/line threshold relaxation or an octagon fit engineered around these examples.

No production estimator, method dispatch, or source-stress policy change.
