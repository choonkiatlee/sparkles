# Source / acquisition profile findings

Issue: #81  
North star: #79  
Implementation: PR #93  
Validated workflow: `source-profile-benchmark` run 37680179543

## Overall disposition

**KEEP the source-profile contract and measurement-specific comparability layer.**

The first heterogeneous benchmark successfully profiles six complete 256-frame
rotations spanning three acquisition families:

- three Diajewel sources;
- one Workshop source;
- two independently audited d360.tech sources from the external benchmark.

The useful result is not a ranking of source quality. It is that different
measurement families receive meaningfully different validity states.

In particular:

- sequence/order and normalized spatial measurements are well supported across
  all six sources;
- angular measurements are supported when #73/#80 establish an adequate
  crown-view reference, and remain `review` where that reference is weaker;
- absolute brightness and chromatic amplitude are not promoted to
  cross-source-calibrated quantities;
- source-global background/reference stability can be measured without using
  the diamond's own brightness as an exposure proxy;
- material channel clipping is common enough that luminance/chromatic amplitude
  needs to carry source limitations explicitly.

This is the intended #81 outcome: **measurement uncertainty becomes a first-class
input to later #79 optical/event inference.**

## Benchmark summary

| Source | Pipeline | Pose / phase | median native diameter | background reference | max stone channel clipping |
|---|---|---|---:|---|---:|
| IGI-LG756580087 | Diajewel | review / review | 507 px | ok | 11.8% |
| IGI-LG756520111 | Workshop | ok / available | 433 px | ok | 40.7% |
| IGI-LG818659722 | Diajewel | ok / available | 553 px | ok | 35.0% |
| IGI-LG836619414 | Diajewel | review / review | 491 px | ok | 6.5% |
| d360-79-BB-5159600 | d360.tech | ok / available | 610 px | ok | 11.8% |
| d360-79-BT-5165227 | d360.tech | ok / available | 529 px | ok | 31.1% |

Native diameter is measured in source-camera pixels using #73 crown-lobe
evidence where available, otherwise top-ranked geometry-usable views. None of
these six sources requires upsampling to the existing 160 px common spatial
transfer.

The two `review` pose/phase cases are not source-profile failures. #73 does not
resolve a likely crown lobe for those rotations because one geometric lobe is
already clearly better, so #80 deliberately exposes a review-status phase
reference rather than inventing stronger face identity.

Physical spatial scale is `unavailable` in this benchmark because certificate
face-up dimensions were not supplied to the benchmark invocation. The API
accepts explicit certificate dimensions; it does not infer them from imagery.

The compact machine-readable values are in
[`benchmark-summary.json`](benchmark-summary.json). Full per-source profiles
and pairwise comparisons are retained in the workflow artifact.

## What is safe enough to carry forward

### Ordered dynamics — KEEP

All six sources have authoritative complete ordering and therefore return
`ok` for `ordered_dynamics`.

This validates the existing `diamond360-source/1` provenance contract as the
right basis for temporal work. No ordering is reconstructed from filenames or
visual similarity.

### Spatial optical morphology — KEEP with the common transfer

All six sources return `ok` for:

- `spatial_optical_morphology`;
- `tier_edge_crispness`.

Their pose-conditioned native stone diameters are roughly 433–610 px, safely
above the 160 px normalized research transfer used by #55.

This does **not** mean raw source pixels are directly interchangeable. It means
the existing declared common transfer provides a defensible comparison
coordinate for these sources.

The older source-pipeline experiments explain why this matters:

- #50 raw gradient strength changed by as much as about **34.8% under blur**,
  **43.5% under downsample/resample**, **21.2% under mild sharpening**, and
  **7.3% under JPEG recompression**;
- #55 normalized tier transition width reduced those worst changes to about
  **3.7%**, **7.2%**, **6.5%**, and **2.2%** respectively.

#81 therefore preserves the #55 common-transfer requirement instead of treating
native resolution or raw edge amplitude as cross-source quantities.

### Geometry / angular persistence — KEEP, conditional on #73/#80

Four sources return `ok` for geometry topology and angular persistence.

Two Diajewel sources remain `review` because crown-view identity / phase origin
is not as strongly resolved by #73/#80. This is desirable: #81 consumes those
upstream validity states rather than masking them.

Viewer phase remains explicitly an observed sequence coordinate, not a
laboratory-calibrated camera angle.

## Photometry: the most important limitation

### Background/reference stability — KEEP as a source diagnostic

All six sources have a usable source-global background/reference region and all
six pass the current stability thresholds.

Median background-luminance MAD is approximately:

- 0 for the two Diajewel examples with uniform backgrounds;
- 0 for the Workshop example;
- 0.00028 for LG818659722;
- 0.00239 for d360 Glittery;
- 0.00028 for d360 Crispest.

This supports the anti-circular design: source-global behaviour can often be
characterized from pixels outside the segmented diamond.

### Whole-stone "exposure drift" — REJECT as an inference

The implementation deliberately never estimates exposure drift from the
diamond's own mean brightness.

A unit test changes diamond brightness strongly while holding the background
fixed and verifies that this is **not** labelled exposure drift.

That distinction should remain permanent unless independent acquisition
metadata supplies a stronger exposure reference.

### Stone channel clipping — KEEP as a warning

Every benchmark source exceeds the current 2% material-clipping threshold in at
least some frames. Maximum per-channel clipping ranges from roughly **6.5% to
40.7%** across the six examples.

Consequently:

- `relative_luminance_dynamics` remains `review`;
- `absolute_luminance_amplitude` remains `review`;
- `chromatic_activity` remains `review`.

This does not say the videos are unusable. It says amplitude and colour claims
must acknowledge information lost at the recording boundary.

### Absolute cross-source brightness — KEEP as `review`

None of the sources is radiometrically calibrated.

Therefore an encoded luminance value from one vendor must not be interpreted as
the same physical light output as the same number from another vendor.

The pairwise policy keeps absolute luminance at `review` unless later sources
supply real radiometric calibration.

### Chromatic activity — KEEP as `review`

None of the six sources is colour calibrated, and clipping is material.

RGB/chroma observations can still be retained as source-visible behaviour, but
must not be renamed an illumination-independent Fire measurement.

## Compression / processing diagnostics

### JPEG quantization table — KEEP as provenance/diagnostic, not discriminator

All six benchmark sources have the same median decoded JPEG quantization-table
value, **48.5**.

It therefore does not distinguish these acquisition families by itself.

### Bytes/pixel and acutance — KEEP as diagnostic context only

Median encoded bytes/pixel varies roughly from **0.052 to 0.097**, while the
scene-dependent acutance proxy varies roughly from **0.014 to 0.022**.

Those differences confirm that one JPEG-number or one generic sharpness score is
not an adequate source model. In v1 these remain descriptive diagnostics only.

Scene-independent resampling, sharpening-halo and denoising inference remains
explicitly `unavailable` until a validated detector exists.

## Controlled perturbation harness

The v1 harness covers:

- downsample/resample;
- blur;
- sharpening;
- exposure shift;
- contrast shift;
- JPEG recompression;
- white-balance/channel shift.

Focused tests verify expected directional behaviour and the anti-circular
photometry contract. Existing #50/#55 evidence supplies the strongest current
measurement-sensitivity result for static geometry.

Future descriptor families should add their own perturbation sensitivity to the
same framework rather than weakening the source profile into a one-size-fits-all
threshold.

## What #81 now provides to #79

Downstream optical/perceptual work can ask separately:

```python
assess_measurement(profile, family)
can_compare(profile_a, profile_b, family)
```

and receive `ok | review | unavailable` with reasons.

That allows a future optical event to carry both:

1. evidence that the event occurred in the source sequence; and
2. evidence about how strongly that event may be interpreted or compared across
   acquisition systems.

The profile is therefore a **measurement-uncertainty layer**, not a quality
model.

## Remaining limitations / future calibration

- Find same-physical-diamond captures from different acquisition systems where
  possible; these would be the strongest cross-source validation fixture.
- Feed explicit certificate face-up dimensions into future physical/perceptual
  scale benchmarks.
- Add measurement-sensitivity experiments as new #79 event/perceptual
  primitives appear.
- Do not promote scene-dependent blur/sharpening proxies into comparability
  gates without independent validation.
- Do not create a universal source-quality score.

## Reproducibility

Green workflow run: **37680179543**.

The run passed:

- all focused #81 tests;
- the full repository test suite;
- retained benchmark-source retrieval;
- both audited d360.tech extractions;
- six-source end-to-end profile generation;
- pairwise measurement comparability generation;
- artifact upload.

Workflow artifact SHA-256:

`12e3ed37792f28590a2bc2426568633354dbf9c6dea3c5c1a3f9c4a0f2a75d78`
