# #92: archived #89 geometry → real crown-view brightness trace

This is a **small, real-source integration replay**, not a new geometry
estimator, virtual-facet detector, or composite optical score.

## Frozen evidence and precisely selected frames

**Geometry source:** archived immutable workflow
[37830584391](https://github.com/choonkiatlee/sparkles/actions/runs/37830584391),
artifact \`asscher-geometry-stability-outer-v2\`. It contains
\`primary-wireframe.json\` (one frozen stone-level semantic scaffold)
and \`transfer.json\` (per-source-frame fixed-ruler support);
**we do not recalculate them**.

**Source:** two original 256-image IGI sequences from release
\`benchmark-sources-v1\`, each verified against the pinned per-stone
SHA-256 and byte count in \`source-bundles.json\`:
- **IGI-LG756520111:** source 0, 13, 16, 19, 255; crown-face role
  \`likely_crown_lobe\` in the archived #89 transfer, including the
  wrap boundary (255/0).
- **IGI-LG756580087:** source 13, 16, 19; crown-face role
  \`unresolved\`. These frames are **negative metadata controls**,
  NOT independently labelled physical crown/table views.

We regenerate *only* the canonical image arrays and #80 sequence
mapping from the pinned original sources, using the unchanged existing
\`pipeline.run\` and \`analyse_processed_sequence\`. We do **not** call
the wireframe or outer-octagon *fitter*.

The replay fails closed unless the regenerated #80 gauge ID, frame
indices, face roles and quarter-turn phase branches match archived #89.

## Real measurements

Run \`asscher_semantic_optical_handoff.sample_sequence\` on the
**already frozen** per-entity polygons and statuses to obtain:
\`semantic_id\`, \`source_index\`, \`rotation_phase_deg\`,
\`raw_mean_brightness\`, \`normalized_mean_brightness\`,
\`supported_pixel_count\`, \`geometry_support_status\` and
\`geometry_confidence\`.

- \`raw_mean_brightness\` is the **canonical pipeline measurement
  brightness input**, **NOT native vendor RGB** or source-independent
  normalized reflectance.
- \`normalized_mean_brightness\` remains null: #81 source normalization
  is separate and has not been supplied.
- An \`unavailable\` geometry support produces null brightness, not
  fabricated zero/black appearance.
- Supports are **nonexclusive image-plane polygons**. Pixels can be
  counted for more than one semantic ID; this is not a polished
  physical-facet partition.
- C3/TABLE physical identity stays explicitly **unverified**, even when
  frozen #89 supports happen to have \`ok\` status.
- All metric values are **descriptive**, no quality score, no light-return
  conclusion or P1/P2/P3/C3 polished-plane correspondence.
- Source 0/255 wrap is not interpreted as a continuous physical rotation
  without checking phase; frame ordering is explicit in JSON.

## Expected deliverables / quick QC

- \`real-fixed-ruler-smoke.json\`: eight real-source frames, all inherited
  semantic IDs, confidence/support provenance and no-refit evidence.
- \`real-fixed-ruler-traces.png\`: small two-stone review plot of
  selected descriptive entity brightness values. \`C1_N\`,
  \`C2_N\`, \`C3_N\`, \`P1_N\`, \`TABLE\` are **only illustrative semantic
  image-support names**, not physically validated facet masks. NULLs
  leave disconnected points, not interpolation. Source frame indices are\n  displayed at **true cyclic spacing**, with 255 positioned next to 0 and\n  traces intentionally **not connected across unsampled gaps**.

The research gate is showing fixed IDs despite changing optical
appearance. It is **not** a final #92 KEEP decision: #91's external
angle correspondence is inconclusive, and #124/#123 found optical
lines that do not prove physical inner-facet junctions.

## How to reproduce

The dedicated workflow downloads the archived #89 artifact with
\`gh run download 37830584391\`, retrieves just the two pinned source
bundles (verified byte count + SHA-256), then runs:

\`\`\`bash
python -m unittest tests.test_asscher_semantic_optical_real_replay -v
python -m diamond360.asscher_semantic_optical_real_replay \
  --source-root outputs/real-source-bundles \
  --manifest docs/360/benchmark/source-bundles.json \
  --frozen-stability-root outputs/frozen-89-stability \
  --output outputs/real-ruler-optical-smoke
\`\`\`

The workflow verifies exactly 8 frames, 2 stones, identical
semantic IDs and zero refits, with all physical-angle and quality
claims unavailable.
