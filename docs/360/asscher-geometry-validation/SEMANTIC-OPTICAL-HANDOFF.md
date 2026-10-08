# #92: minimal geometry-to-optical support handoff

This is intentionally **only a smoke test**, not a quality metric or a
validated interpretation of individual polished facets. It proves the
shape of the #79 downstream API without changing the #75/#96 geometry
fitter or the #89 fixed-ruler transfer contract.

## Data input

- A **single frozen stone-level #74 semantic scaffold**, in the canonical
  #80 sequence gauge, previously fitted outside this module.
- A per-frame **#89 fixed-ruler transfer** record with the same
  \`semantic_gauge_id\`, stable semantic IDs, source index, approximate
  rotation phase if known, per-entity support/status/confidence and an
  explicit \`refit_performed=false\` stamp.
- Registered, already-canonical measurement-frame 2D brightness, stone
  gauge mask and valid-pixel mask. A separate explicitly normalized
  brightness image may be supplied; if omitted, normalized brightness
  remains \`null\` rather than being guessed.
- No external cut scores, expert calibration or physical facet-angle data.

The geometry-to-image mapping is the **exact existing**
\`asscher_wireframe._scaffold_points_in_gauge\`: the same gauge-mask
centroid and support radius used in native RGB/measurement overlays.
It is not optimized based on a changing bright/dark boundary.

## Output

One row per (semantic ID, source frame):

\`\`\`
semantic_id
source_index
rotation_phase_deg            # nullable if source gauge has no phase
supported_pixel_count
raw_mean_brightness           # input canonical measurement brightness
normalized_mean_brightness    # nullable; supplied externally only
geometry_support_status       # ok / review / unavailable
geometry_confidence
image_support_attribution     # explicitly NON-EXCLUSIVE
physical_facet_correspondence # always not_established at this stage
\`\`\`

**Non-exclusive is essential:** samples are unions of the frozen semantic
polygon supports. The same pixel may legitimately appear in two different
entity support regions (especially pavilion-through-table optical
appearance); this is *not* a literal physical-facet partition.

If a frame reports unavailable geometry support for one semantic ID,
its sample count is zero and brightness is **null**, not falsely
reported as a dark physical facet. Missing source phase also stays null.
Inner C3/table support can be sampled observationally when available,
but its **physical-facet identification remains review/unverified**
under #124 and #123's negative diagnostic. No physical angle/plane,
exclusive pixel owner or optical quality score is inferred.

## Safety and tests

- The module **has no geometry fit entry point** and refuses a transfer
  with \`refit_performed\` anything other than false.
- Source semantic IDs must match the fixed scaffold **exactly**. A
  swapped, missing or invented semantic ID is an error, never repaired
  via re-assignment.
- Sequence gauge IDs must match and brightness/masks must share the same
  sampling canvas.
- Synthetic tests vary brightness across two frames while ensuring
  fixed semantic IDs, unchanged pixel count and scaffold bytes;
  test explicit overlap, unavailable support, uncertain C3,
  normalized-input absence and invalid-source rejection.
- Real four-stone sequence processing and source-stress benchmarks
  are **not rerun in this small PR**. #89 has already frozen
  transfer/identity evidence for those stones. Connecting this API
  to a small set of representative archived canonical frames is the
  next validation gate before any #92 KEEP/REVISE/REJECT decision.

This component is intentionally not a full empirical optical/virtual-facet
tracker. #123 remains the proper home for differentiating optical
appearance regions from polished-facet identity; #81 for source
normalization/comparability.

## Usage

\`\`\`python
from diamond360.asscher_semantic_optical_handoff import sample_sequence
report = sample_sequence(frozen_scaffold, [
    (transfer, measurement_brightness, gauge_mask, valid_mask, None),
    # Further canonical frames with the *same* scaffold and gauge.
])
\`\`\`

### Provenance and limitations

This first PR uses synthetic fixed-scaffold tests to prove the
interface and that the **ruler is not moving**. It is **not** a
completed, independent real-stone #92 handoff validation until
representative actual crown-view frame samples are replayed and
audited with #89 data. The final #92 research decision must include
the inconclusive #91 facet-angle comparison and #124's REVISE
inner-facet finding; it must not promote currently unsupported C3
polished-facet correspondence.
