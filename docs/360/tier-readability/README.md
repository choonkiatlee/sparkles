# Tier readability — PR A boundary-local contrast

Issue: #57  
Predecessor: #49

This slice tests whether **tonal contrast immediately across an inferred Asscher
tier boundary** is a better primitive for visible tier separation than #49's
broader matched-sector band comparison.

## Measurement

For each of the eight existing image-axis sectors, each source frame and each
adjacent boundary:

```
inside  = [b - g - w, b - g]
outside = [b + g,     b + g + w]

signed = log(B_inside) - log(B_outside)
L      = abs(signed)
```

where `b` is fixed sequence-level boundary geometry, `g = 0.010`, and PR A
tests `w = 0.025 / 0.040 / 0.055` in the declared radial coordinate.

The guard deliberately removes pixels immediately on the boundary. The
measurement is intended to capture **tonal separation across the boundary**,
not edge-gradient strength or sharpening.

## Geometry A/B

Two geometries are measured on the same source pixels:

- **semantic / #19** — the ordered sequence-level Asscher boundary with its
  eight sector control radii; per-frame #19 edge matches do not move the strip;
- **coarse control** — the legacy coarse fixed radial boundary used by the
  original measurement layer.

A full #19 four-band partition remains all-or-nothing. For #57 only, #19 now
also preserves any individually supported boundary controls when another boundary
fails. A partial boundary is usable only for this local two-strip measurement,
is explicitly marked **review**, and does not make the full semantic step
representation available. This matters when, for example, the outer boundary is
missing but centre-inner and inner-middle are still well supported.

This separates two questions:

1. is measuring locally across a boundary useful?
2. does #19 localisation improve on the old coarse boundary?

## Support

The boundary definition is fixed for the sequence. Its normalised strip maps
onto each frame's registered silhouette, so pixel support is evaluated on that
frame's valid pixels rather than intersecting identical pixels across the whole
sequence.

No arbitrary support threshold is used. Per-frame support counts/fractions are
retained as QC. Empty support remains unavailable.

## Controls retained from #49

PR A keeps:

- coarse whole-band adjacent-tier contrast;
- standardized coarse contrast as the falsified normalization control;
- broad eight-sector matched-band contrast.

The new primitive therefore has direct baselines rather than replacing #49's
evidence.

## Synthetic falsification tests

Tests cover:

- exact known log ratios;
- equal tones -> zero;
- common multiplicative brightness invariance;
- signed reversal;
- gaps/non-positive brightness;
- local sector cancellation hidden by whole-band aggregation;
- disjoint inside/outside strip geometry;
- semantic and coarse boundary geometry;
- a narrow high-intensity edge spike excluded by the guard;
- support motion across frames without requiring persistent identical pixels.

## Interpretation caveat

The #19 semantic boundary is itself inferred from persistent radial edge evidence.
That makes a direct magnitude comparison such as `semantic L > coarse L`
partly selection-driven: the semantic geometry is intentionally placed where
persistent edge evidence exists.

PR A therefore does **not** treat a larger semantic-strip number as evidence of
superiority by itself. The useful tests are:

- whether the strip is supported and auditable on the original source frame;
- whether width 0.025 / 0.040 / 0.055 tells the same qualitative story;
- whether core and wide windows remain reasonably stable;
- whether boundary-local measurements repair concrete broad-band cancellation
  cases rather than merely amplifying the selected edge.

Formal human calibration and held-out discrimination remain PR C.

## Benchmark

The PR workflow downloads the canonical four full-sequence source bundles and
runs exact-core and wide windows. Outputs are uploaded as a CI artifact and
include:

- compact comparison CSV/JSON;
- per-stone full auditable JSON;
- width sensitivity;
- original-source + strip-overlay evidence panels.

Generated bulk images/traces are not committed.

## Non-goals for PR A

PR A does **not** choose Q25/median as a production summary, construct the joint
weakest-link nested-readability statistic, interpret tonal ordering, fit human
thresholds, or add a field to the retained production profile. Those decisions
belong to later #57 slices.
