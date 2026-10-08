# #123 / #124 — connected original-RGB junction graph

## Why

The frozen #96 image-plane C3/table estimator and v3/v4 alternatives can
reliably produce a smooth octagon *through facet interiors*. The independent
native-camera RGB side detector (#146) refuses to draw a ring when sides are
missing (0/20 rings across four stones), but even an isolated straight line
may be an internal reflection or a virtual facet.

A more meaningful **diagnostic** must establish that two measured line
segments both approach a *directly observed* corner and that a connected
network of such corners survives source-view changes. Connectivity is a
stronger observational test than single-line contrast; it still does **not**
establish a polished facet's physical identity.

## Exact evidence and exclusions

- Depends on experimental line extraction from draft PR #146. This PR is
  stacked on that branch; keep the two independent for review.
- Reuse the same frozen #96 outer-view selection, actual original source RGB,
  existing #80 gauge-to-camera transforms, four hash-pinned stones and
  frozen outer octagon. No refitting or relabeling the production estimator.
- Analyze *every* independently retained straight segment hypothesis
  (up to 3 per outer-octagon side family), not just the strongest one.
- For each neighboring pair of measured line equations, calculate the
  normalized 2D intersection. Require the intersection to lie inside
  the physical silhouette and within 0.025 normalized radius of **both
  finite, actually observed contiguous RGB line fragments**.
- Probe five RGB gradient samples *toward the measured fragment* along
  each line at increments of 0.010 normalized units. At least 40%
  of samples on each segment must corroborate its perpendicular edge
  contrast. The threshold is relative to the frozen #146 frame reference.
  The two line signals must be independently present; point-like brightness
  intersections are not enough.
- A *node* is an observed-line intersection hypothesis; an *edge* joins
  adjacent candidate nodes only when both use the **same observed finite
  side segment** and are separated by at least 0.025 normalized units.
  Export *all* nodes, edges and connected components; never invent
  unsupported corners or interpolate a missing side.
- A "supported eight-corner cycle" is reported only when eight connected
  observed corner hypotheses yield one consistent cycle. It is
  **not automatically a physical or optical table-facet boundary**.
  Unresolved source faces remain unavailable for physical-crown inference.
- Original source camera RGB side-by-side: unchanged native RGB and
  observed-only blue line segments, directly supported white corners,
  connected green links. No inferred closed polygon is drawn.

## Falsifiable acceptance

- [ ] The synthetic fully observed octagon yields eight corner nodes,
      eight connected links and a cycle.
- [ ] Removing a side or moving observed segments away from corners
      breaks the cycle without synthetic repair.
- [ ] Flat camera RGB refuses a fabricated connected network.
- [ ] Four stones' SHA-256 source rotations and original #96 selected
      frame indices remain unchanged.
- [ ] Human-review source 13/16 of LG756520111 and comparison stone views,
      explicitly recording false reflected edges and unresolved face role.
- [ ] No full geometry is promoted from this diagnostic without
      independent photographic/physical-facet verification.

**No source-stress workflow**; no production estimator or price/quality
classification change. This is an experiment, not an automated ground-truth
facet segmentation method.
