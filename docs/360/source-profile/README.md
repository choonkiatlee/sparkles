# Source / acquisition profile

Issue: #81  
North star: #79  
Consumes: \`diamond360-source/1\`, #73 pose output, #80 sequence gauge

This layer answers a deliberately narrower question than diamond evaluation:

> Given how this 360 was acquired and processed, what measurements can Sparkles
> make from it, and which measurements are meaningfully comparable with another
> source?

It does **not** produce a source-quality score and it does not use source
characteristics as proxies for diamond quality.

## Architecture

\`\`\`text
source manifest / ingestion
          │
          ├── source facts / provenance
          ├── source-byte diagnostics
          ├── #73 pose / usable views
          └── #80 sequence phase / orientation
                    │
                    ▼
         diamond360-source-profile/1
                    │
             ┌──────┴──────┐
             ▼             ▼
     assess_measurement   can_compare
\`\`\`

The profile contains evidence. Measurement policy remains a separate function,
so future descriptors do not need to rediscover source assumptions and the
profile does not hard-code diamond-quality meaning.

The machine-readable schema is
[\`source-profile.schema.json\`](source-profile.schema.json).

## Profile sections

### Source identity and provenance

The builder preserves the existing authoritative source contract where present:

- source/vendor pipeline;
- manifest schema;
- viewer/retrieval provenance;
- image dimensions;
- source frame count and completeness;
- ordering provenance/validation;
- d360 bootstrap/still hashes where present.

It consumes these facts rather than inferring vendor identity visually.

### Sequence contract

The profile reports:

- explicit ordering status;
- duplicate source-index/pixel-frame diagnostics;
- declared sampling contract;
- #80 observed viewer-sequence phase when pose output is supplied.

Viewer phase remains explicitly different from a calibrated physical camera
angle.

### Spatial sampling

The profile measures source stone extent in pixels from the existing silhouette
geometry and records compatibility with the #55 declared common spatial
transfer.

Version 1 uses the existing 160 px effective-diameter transfer. A source that
would need upsampling is marked \`review\`; low native sampling is not silently
treated as equivalent resolution.

### Compression / processing diagnostics

Version 1 reports conservative diagnostics rather than attempting to reconstruct
a vendor's preprocessing pipeline:

- JPEG quantization-table summary where present;
- source bytes/pixel;
- scene-dependent 8x8 block-boundary ratio;
- scene-dependent acutance proxy.

The latter two are explicitly diagnostic-only. They are not called effective
resolution. Scene-independent resampling, sharpening-halo and denoising
detectors remain \`unavailable\` until validated rather than being guessed.

### Photometric behaviour

This is intentionally anti-circular.

**Sparkles does not infer exposure drift from whole-stone brightness changes.**
The diamond is expected to change brightness as it rotates, and that change is
the optical signal later descriptors need to measure.

Sequence-global photometric stability is therefore estimated only from
background/reference pixels outside the segmented stone when enough such
support exists. Version 1 records:

- background luminance/channel stability;
- abrupt background-reference changes;
- per-channel clipping inside the stone;
- explicit lack of radiometric/colour calibration.

If no usable source-global reference exists, the corresponding inference is
\`review\`/\`unavailable\`; the diamond itself is not used as its own exposure
meter. Frame-wise photometric normalization is never applied here.

### Pose coverage

#73 output is consumed rather than duplicated. The profile records usable pose
count, crown-lobe coverage and canonical support.

### Physical scale

If certificate face-up dimensions are explicitly supplied, the profile exposes
an approximate image-pixel/mm scale. This is a face-up scale only: it does not
infer depth, 3-D geometry or physical facet angles.

## Measurement policy

\`diamond360.source_profile.assess_measurement(profile, family)\` returns:

- \`ok\`
- \`review\`
- \`unavailable\`

plus explicit reasons.

Current families are:

| Family | Main source requirements |
|---|---|
| \`geometry_topology\` | usable #73 pose + adequate spatial sampling |
| \`spatial_optical_morphology\` | adequate sampling + declared common transfer |
| \`physical_spatial_scale\` | explicit certificate dimensions + pose support |
| \`ordered_dynamics\` | trustworthy explicit ordering / complete sequence |
| \`angular_persistence\` | ordered sequence + #80 phase |
| \`relative_luminance_dynamics\` | source-global photometric stability where observable |
| \`absolute_luminance_amplitude\` | radiometric calibration for a true \`ok\` |
| \`chromatic_activity\` | clipping/stability support; colour calibration is explicit |
| \`tier_edge_crispness\` | adequate sampling + #55 common spatial transfer |

\`can_compare(left, right, family)\` applies pairwise constraints on top of the
per-source assessment.

Important examples:

- within-source optical dynamics may remain usable while absolute brightness
  comparison across vendors is only \`review\`;
- angular persistence may be comparable in declared viewer-phase coordinates
  while still carrying the explicit caveat that viewer phase is not calibrated
  physical angle;
- cross-source chromatic comparison remains \`review\` without colour
  calibration;
- spatial morphology uses the declared common transfer rather than raw pixel
  equivalence.

No universal numeric comparability score is produced.

## Controlled source perturbations

\`apply_diagnostic_perturbation\` supplies the frozen issue-81 stress family:

- downsample/resample;
- mild blur;
- mild sharpening;
- exposure shift;
- contrast shift;
- JPEG recompression;
- modest white-balance shift.

Unit tests verify the contract and the most important anti-circularity
condition. The heterogeneous benchmark runs the same source profiler over real
retained source families.

This harness is infrastructure for answering the stronger question in later
measurement work:

\`\`\`text
controlled source perturbation
        ├── does the source diagnostic move?
        └── does the optical measurement move?
\`\`\`

Comparability thresholds should be tightened only when that paired sensitivity
evidence supports doing so.

## Running

From an existing processed sequence and #73/#80 pose output:

\`\`\`python
from diamond360.source_profile import build_from_processed

profile = build_from_processed(
    "path/to/processed",
    pose="path/to/asscher-pose.json",
    certificate_dimensions_mm=[6.42, 6.39],  # optional
)
\`\`\`

Then:

\`\`\`python
from diamond360.source_profile import assess_measurement, can_compare

assess_measurement(profile, "angular_persistence")
can_compare(profile_a, profile_b, "spatial_optical_morphology")
\`\`\`

## Benchmark

\`diamond360.source_profile_benchmark\` runs the frozen code over the retained
benchmark bundles and automatically includes extra source directories containing
a \`source-manifest.json\`.

CI downloads the four retained Diajewel/Workshop rotations and attempts to add
the two audited d360.tech sources from #64. External d360 retrieval is allowed
to fail without invalidating the four-source benchmark because vendor
availability is not under repository control.

The benchmark emits:

- one \`source-profile.json\` per source;
- \`summary.json\` with measurement-family states;
- pairwise comparability results for every source pair.

Bulk source images remain outside Git.

## Non-goals

- reconstructing preprocessed vendor originals;
- a universal source-quality score;
- laboratory photometric calibration;
- forcing two vendor systems to be equivalent;
- semantic facet extraction;
- optical/virtual-facet tracking;
- quality scoring;
- treating source characteristics as diamond characteristics.
