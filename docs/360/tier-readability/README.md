# Tier readability — PR A / A2 boundary-local contrast

Issue: #57  
Predecessor: #49

This slice tests whether **tonal contrast local to an Asscher tier boundary** is
a better primitive for visible tier separation than #49's broad matched-sector
band comparison.

## Revised measurement contract

For each of the existing eight image-axis sectors, each source frame and each
adjacent tier boundary, use one fixed sequence-level boundary geometry and
measure guarded strips on both sides.

The strip widths are no longer absolute constants. For scale fraction
`alpha`:

```
inside_width  = alpha * (boundary - inner_reference)
outside_width = alpha * (outer_reference - boundary)

inside  = [boundary - guard - inside_width, boundary - guard]
outside = [boundary + guard, boundary + guard + outside_width]

signed = log(B_inside) - log(B_outside)
L      = abs(signed)
```

PR A2 tests the small declared family:

- `alpha = 0.25`
- `alpha = 0.40`
- `alpha = 0.55`

with guard `g = 0.010`.

This makes support relative to the local tier spacing rather than to an
arbitrary absolute radial width. The three scale results remain available.
A per-frame/per-sector **multi-scale consensus** is the median across scale;
scale spread is retained as a sensitivity diagnostic. The eight spatial
sectors are not collapsed by this step.

## One canonical ruler

The original PR A benchmark rediscovered #19 geometry independently in the
17-frame core and 33-frame wide windows. That made core/wide sensitivity partly
a moving-ruler test.

PR A2 instead:

1. discovers one canonical #19 template from the 33-frame wide window;
2. reuses that exact geometry for both core and wide contrast measurements;
3. separately discovers a core-only #19 template for **geometry diagnostics
   only**;
4. never lets the diagnostic template move the contrast strips.

This separates measurement sensitivity from boundary-correspondence
sensitivity.

## Pair-specific geometry validity

#19 remains the source of semantic boundary controls.

A local pair can remain usable when another boundary is missing:

- individually supported partial controls are retained as `review`;
- if a neighbouring reference required only for tier-relative width is missing,
  its span may be mirrored from the observed opposite side, also as `review`;
- ambiguous/non-separable geometry is never rescued and remains
  `unavailable`.

Every fallback is explicit in the output provenance.

## Geometry A/B

Two geometries are still measured on the same source pixels:

- **semantic / #19** — canonical wide-window sequence geometry;
- **coarse control** — legacy fixed radial boundaries, using the same
  adjacent-tier-relative scale fractions.

The coarse control separates the value of boundary locality from the value of
#19 semantic localization.

## Support and sharpening guard

The geometry is fixed for the sequence, but the normalized strip maps onto
each frame's registered silhouette. Pixel support is therefore evaluated on
that frame's valid pixels.

No arbitrary support-count threshold is fitted. Counts/fractions remain QC.
Empty support remains unavailable.

The guard excludes the immediate edge so this is intended to measure broad
tonal separation across a tier transition rather than the edge-gradient /
sharpening behaviour studied in #50.

## Controls retained from #49

PR A/A2 keeps:

- coarse whole-band adjacent-tier contrast;
- standardized coarse contrast as the falsified normalization control;
- broad eight-sector matched-band contrast.

The revised local primitive therefore remains directly comparable with #49.

## Falsification tests

Tests cover:

- exact known log ratios and zero contrast;
- common multiplicative brightness invariance;
- signed reversal;
- gaps/non-positive brightness;
- sector cancellation hidden by whole-band aggregation;
- relative strip geometry and asymmetric neighbouring tier spans;
- disjoint guarded inside/outside support;
- narrow edge spikes excluded by the guard;
- moving registered support without requiring identical persistent pixels;
- multi-scale consensus without collapsing the spatial sectors;
- partial-boundary review handling;
- rejection of ambiguous/non-separable geometry;
- explicit detection of core-only vs canonical boundary movement.

## Benchmark

The CI workflow downloads the canonical four full-sequence source bundles and
runs both the exact 17-frame core and 33-frame wide windows using the **same
canonical wide #19 geometry**.

Outputs include:

- compact comparison CSV/JSON;
- all three scale fractions;
- per-sector multi-scale consensus and scale spread;
- core-only vs canonical geometry diagnostics;
- auditable per-stone JSON;
- original-source + strip-overlay evidence panels.

Bulk generated evidence remains in CI artifacts rather than the repository.

## Non-goals

PR A/A2 still does **not**:

- choose Q25/median spatial coverage as a production descriptor;
- construct the joint centre→inner→middle weakest-link statistic;
- interpret tonal ordering as quality;
- fit thresholds on four stones;
- add a retained #45 production-profile field.

Those decisions belong to later #57 slices after this measurement primitive is
stable enough to calibrate.
