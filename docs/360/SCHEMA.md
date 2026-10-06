# Output schema 1.0

JSON contains finite numbers or null, never NaN. NPZ maps use NaN for unsupported
values. Paths are relative to the published output directory unless stated.

## Sequence

`schema_version`, `frame_count`, `valid_count`, `dimensions` (unique `[width,height]`),
`ordering` (`natural_filename`/`explicit_manifest`), `sparse`, `source_frame_count`,
`source_manifest` (unaltered parsed upstream manifest), `warnings`, and
`brightness_definition`. `source_frame_count` can be null; unknown completeness
must not be interpreted as complete merely because `sparse` is false.

`segmentation_acceptance` records whether only `ok` silhouettes were registered (`ok_only`) or an explicit caller opted into carrying `review` silhouettes through registration (`ok_or_review`). Review status/reasons remain unchanged and must be treated as QC limitations.

`photometry` records assumed sRGB, formulas, constant gain and mask semantics.
`regions` records radial boundaries and axes. `diagnostics` records request,
accepted/excluded indices, equal-frame weighting, thresholds, paths and statuses.

## Each frame

- `position`: zero-based supplied reading position; filenames NNNN use this.
- `name`, `path`: original filename and path relative to input.
- `source_index`: trailing integer in filename, or null; not viewing angle/time.
- `bytes`, `sha256`: original bytes; `pixel_sha256` includes decoded RGB and shape.
- `status`: `valid`/`invalid`; `error` on invalid frames.
- `width`, `height`, `brightness`: mean/std/p05/p95 of all camera pixels, including
  background. This differs from masked temporal frame means.
- `duplicate_of`/`pixel_duplicate_of`: first identical byte/decoded image filename;
  frames are kept for audit; temporal deduplication applies within the selected subset.
- `camera_original_path`: exact copy for each valid image.
- `segmentation`: `status` (`ok`/`review`/`failed`), reasons, method, background RGB,
  robust border spread/outlier fraction, thresholds, convex vertices `[x,y]`,
  area fraction and mask/boundary paths. Mask PNG values 0/255.
- `geometry` only on accepted masks: centroid `[x,y]`, inclusive bbox
  `[xmin,ymin,xmax,ymax]`, width/height/area, principal axes/eigenvalues,
  eigenvalue ratio, orientation ambiguity/angle, equivalent-moment axis lengths.
- `registration` only on accepted masks: forward/inverse 3×3 matrices, scale,
  canvas size/target extent, interpolation description, rotation flag and paths.
- `photometry_path`, `regions_path`: lossless compressed NPZ, accepted frames only.

Coordinates: pixel centres, x right/y down, origin at top-left pixel centre.
Homogeneous camera-to-diamond multiplication is `M @ [x,y,1]`; its inverse maps
back. Output centre `[127.5,127.5]`; maximum bbox dimension mapped to 192 px.
BBox dimensions use inclusive pixel counts; nearest-mask rasterisation can differ
slightly from the continuous transform. Orientation is modulo 180°, nullable when
principal eigenvalue ratio <1.08; no continuous spin or roll estimate is implied.
Principal-axis lengths are 4√eigenvalue, not 3D dimensions or actual side lengths.

## Photometry NPZ

`encoded_brightness`, `linear_luminance`, `gain_luminance`, `chroma_range` are 256²
float32; `mask`, `valid_mask` are boolean. Background values remain in arrays, so
always use masks. All channels assume recorded RGB is sRGB. Gain may yield >1;
values are intentionally not clipped.

## Regions NPZ

Boolean 256² masks: `centre`, `inner`, `middle`, `outer`; `quadrant_NE/SE/SW/NW`;
`side_E/S/W/N` and `corner_NE/SE/SW/NW`. Each family partitions the geometric
silhouette without overlap. For intensity summaries intersect with `valid_mask`.
Axes remain image-aligned; names are coarse spatial sectors, not actual facets.

## Temporal NPZ and JSON

`mean`, `std`, `relative_dark_fraction`, `support_fraction`: float32 arrays in
respective coordinate space; `support_count`: uint32 valid observation counts.
Camera arrays retain source dimensions; diamond arrays are 256². Mixed camera
sizes skip camera diagnostics with a recorded reason; diamond maps can still run.

Mean and dark fraction use valid observations per pixel. Population std (ddof=0)
is NaN with <2 observations; mean/dark fraction are NaN with no observations.
`support_fraction = support_count / accepted_frame_count`; zero support is 0.
Dark observation: raw encoded brightness <0.65× that frame's median valid stone
brightness. JSON stores per-frame thresholds and masked means in accepted index
order. Full-scene darkness can be hidden by a relative threshold, so inspect raw
mean/frames too. No interpolation across missing samples or temporal smoothing.

`diagnostics.status`: `not_requested`, `insufficient_accepted_frames`, or `complete`.
`spaces.camera/diamond.status`: `complete` or `skipped`. JSON lists requested and
accepted indices plus exclusion reasons. Fractions are counts of selected images,
not duration, calibrated angle coverage, leakage probability or quality scores.

## Ordered extraction handoff: `diamond360-source/1`

Set `schema_version` to `diamond360-source/1`. `frames` is the authoritative ordered array; legacy order fields are ignored for this version. Unsupported `diamond360-source/*` versions fail explicitly. Each entry requires `source_index` (unique nonnegative integer), `path` (image path within input root) and `sha256` (64 lowercase hex characters). Paths need not contain indices. All discovered images must be listed once; missing, escaping, repeated paths/indices and hash mismatches fail. `source_frame_count`, when provided, bounds the indices. A true `sequence_complete` declaration requires every index 0..count−1. Source/vendor, extractor, URLs/batches, ordering semantics, missing/repeated indices and completeness provenance remain in the manifest. Unknown angle/timing calibration stays null. Legacy curated manifests remain supported.

## Continuous traces: `diamond360-region-traces/1`

Separate command: `python -m diamond360.region_traces PROCESSED --output FRESH --indices 254,255,0,1 --wrap`. Explicit wrap requires known frame count. Source indices must be consecutive; sparse input cannot supply source-step run statistics. Missing/unaccepted/duplicate selected frames become gaps, never interpolated samples. Fixed common support uses accepted frames only. Regional median/amplitude, relative-dark pixel occupancy, median-state runs and pixel-state distributions are measured independently. No threshold is a quality category; paths/units/definitions/exclusions and processed-manifest SHA-256 remain in `traces.json`. CSV, trace plot and common-support mask accompany it. Region-median bright state is not a claim that all pixels are bright.


## Asscher step bands: `diamond360-asscher-steps/1`

`steps.json` records the requested/accepted source indices, exclusions, the
sequence-level template status (`ok`/`review`/`unavailable`), three ordered
boundary names and eight `side_*`/`corner_*` control points per boundary.
Each boundary also records its `semantic_window`, raw `window_margin` (distance
to its nearest window edge in u units), `window_margin_samples`, and
`near_window_edge`. A margin no larger than one radial sample downgrades a
usable template to `review` with reason `semantic_window_edge`; this diagnostic
is not a calibrated probability. Per-frame status remains local edge support
and must be read alongside template and upstream preprocessing status.
The radial coordinate is silhouette-normalised: distance from the registered
canvas centre divided by the silhouette radius in the same direction.

When the template is usable, `regions/NNNN.npz` contains boolean
`centre`, `inner_step`, `middle_step`, `outer_step` masks that partition that
frame's silhouette exactly once. `frames[].boundary_support` records per-frame
local edge matches as QC only; these matches do not move the sequence template.
`coarse_comparison` compares persistent edge evidence at the selected boundaries
with legacy fixed radii 0.20/0.45/0.70. `edge-profile.png` and `overlays.jpg`
are derived QC. The schema does not imply exact physical facet identity, a
windmill label, crown/pavilion separation, 3-D geometry or cut quality.


## Activation descriptors: `diamond360-activation/1`

`activation.json` records one exact requested source-index interval, accepted/excluded
frames, the encoded-brightness definition, upstream validity, whole-stone activation,
and coarse/semantic regional activation.

Whole-stone activation is the median encoded brightness on the fixed common registered
stone support over accepted frames. Regional outputs preserve both:

- `raw_values`: regional median encoded brightness;
- `relative_values`: `log(regional median) - log(whole-stone median)`.

Each regional representation is evaluated with both `fixed` support (the interval
intersection of that region and valid photometric support) and `dynamic` support
(the frame-local region intersected with valid support). Coarse masks are loaded from
each frame's own preprocessing region file; semantic masks come from
`diamond360-asscher-steps/1`.

Each trace summary contains Q10/Q50/Q90, bright excursion `Q90-Q50`, dark excursion
`Q50-Q10`, total excursion `Q90-Q10`, and `1.4826 * MAD`. Fewer than three
finite observations make the scalar summary unavailable. Non-positive regional or
whole-stone medians are never logged; affected relative observations are null.

Validity is `ok`/`review`/`unavailable`, composed monotonically from relevant
upstream, representation and local measurement states. Semantic warnings apply only
to semantic measurements. Coarse and whole-stone activation do not inherit #19
semantic status. Support fractions remain diagnostics; this schema defines no
support-quality threshold.

Evidence metadata selects source frames nearest Q10/Q50/Q90 plus the largest positive
and negative observed-adjacent moves. Missing/excluded frames break adjacency and are
never interpolated. CSV and evidence PNGs are derived audit products.

All activation quantities describe recorded-image behavior. They are not calibrated
radiance, light return, fire, leakage, physical facet identity or a quality grade.


## Relative-dark occupancy: `diamond360-relative-dark-occupancy/1`

`occupancy.json` uses the same selected frames, registered photometry, whole-stone
reference and coarse/semantic masks as `diamond360-activation/1`. The whole-stone
reference is exactly `G_t`: median encoded brightness on the fixed common registered
stone support over accepted frames.

For supported region pixels `S_(r,t)`, occupancy is:

`O_(r,t)(k) = count[p in S_(r,t) where Y_t(p) < k * G_t] / count(S_(r,t))`.

The threshold comparison is strict `<`; a pixel exactly equal to `k * G_t` is not
classified dark. The benchmark threshold set is fixed globally at `0.60, 0.65, 0.70`
with `0.65` as the baseline. Per-stone, per-region and per-representation threshold
tuning is not permitted.

Every threshold cell records the full occupancy trace, dark-pixel numerator,
supported-pixel denominator, mean, median, Q10/Q50/Q90, support diagnostics and
monotone `ok`/`review`/`unavailable` validity with reasons. Missing/unobserved
frames remain null and do not enter fixed-support intersections.

Each coarse and semantic region is emitted with both `fixed` and `dynamic` support.
Semantic QC is inherited only by semantic occupancy. Fixed↔dynamic disagreement is
support/mask-motion evidence rather than an automatic measurement failure.

Evidence metadata selects source frames nearest Q10/Q50/Q90 and the largest positive
and negative observed-adjacent occupancy moves. Baseline evidence PNGs annotate the
supported region and the pixels classified relatively dark, so the classification is
auditable against source imagery. Gaps break adjacency and are never interpolated.

Occupancy is a descriptive recorded-image state fraction. It is not leakage, calibrated
light return, fire, physical facet identity, or a quality grade.


## Bright/dark switching: `diamond360-bright-dark-switching/1`

`switching.json` reuses the exact relative-dark state from
`diamond360-relative-dark-occupancy/1`:

`D_(p,t)(k) = 1[Y_t(p) < k * G_t]`.

The comparison remains strict `<`; `G_t` is the same fixed-support whole-stone
median used by #27. The benchmark threshold set is fixed globally at
`0.60, 0.65, 0.70`, with `0.65` as the operational baseline. No threshold is
retuned by stone, region or representation.

For each adjacent requested source-step pair, a switch is:

`W_(p,t) = 1[D_(p,t) != D_(p,t-1)]`.

A pixel is eligible only when it is supported on both sides of that pair.
`fixed` support uses the interval-wide persistent region/valid-support
intersection. `pair_local` support uses the intersection of the two frame-local
supports for that pair. Entering or leaving support is therefore never counted as
a bright↔dark switch.

Missing/rejected frames and invalid whole-stone references break adjacency. Pairs
across gaps are not interpolated. Explicit wrapped source order such as
`255 -> 0` is allowed only through the same validated requested-index contract
used by the activation/occupancy runners.

The primary regional scalar is:

`regional_switch_rate = sum(switched_pixel_pairs) / sum(eligible_pixel_pairs)`.

This pair-normalized rate is the primary cross-window candidate. Raw transition
count and the fraction of pixels that ever switch are not primary descriptors.
Each cell also records the full adjacent-pair switching trace, numerator and
denominator counts, per-pixel switch-rate Q10/Q50/Q90/max, the fraction of
eligible pixels with non-zero rate as a diagnostic, and per-pixel eligible-pair
coverage.

Every coarse and semantic region is emitted for both `fixed` and
`pair_local` support. Semantic QC propagates only to semantic measurements.
Validity is monotone `ok` / `review` / `unavailable` with machine-readable
reasons.

Baseline evidence panels show the two source frames defining selected transition
pairs, with support, relative-dark state and switched pixels overlaid. Source
steps are ordinal samples, not seconds or calibrated degrees. Registered pixels
are image coordinates, not tracked physical facets.

Switching is descriptive recorded-image reconfiguration. It is not sparkle
frequency, fire, leakage, calibrated light return, physical facet identity or a
quality grade.


## Contrast mobility: `diamond360-contrast-mobility/1`

`mobility.json` is derived directly from an existing
`diamond360-activation/1` result. It does not recompute photometry, regional
masks, normalization, or support.

For a retained activation trace `a_t`, contrast mobility for an observed
adjacent source-step pair is:

`m_t = |a_t - a_(t-1)|`.

The signed delta is retained beside the absolute mobility for audit. Missing,
rejected, non-finite, or non-adjacent source observations break the pair; no
interpolation is permitted. Explicit wrapped adjacency such as `255 -> 0` is
accepted only when the upstream interval declares wrapping.

The primary local inputs inherited from #26 are coarse-fixed centre/inner/middle
`relative_values`, where activation is
`log(regional median) - log(fixed-support whole-stone median)`. Whole-stone
fixed raw activation is also measurable as a separate upstream observable, while
outer and semantic fixed traces preserve their upstream REVISE status. Dynamic
support is not re-derived because #26 rejected it as a primary activation
definition.

Each trace output includes:

- exact upstream activation schema/disposition/summary/support provenance;
- the full adjacent-pair trace with source indices, signed delta and mobility;
- requested and observed adjacent-pair counts;
- median mobility and Q90 mobility;
- monotone inherited validity plus mobility-specific availability reasons;
- deterministic evidence references for largest, median-nearest, Q90-nearest and
  lowest-nonzero events.

The retained primary scalar is median mobility for coarse-fixed
centre/inner/middle relative activation. Q90 remains an upper-tail audit field.
Whole-stone mobility remains auditable but is not retained as a separate primary
scalar.

Source-step units are ordinal observations, not seconds or calibrated degrees.
Contrast mobility is descriptive recorded-image behavior and is not sparkle
frequency, fire, leakage, calibrated light return, physical facet identity or a
quality grade.


## Bright/dark persistence: `diamond360-bright-dark-persistence/1`

`persistence.json` reuses the exact #27/#28 state definition:

`D_(p,t)(k) = 1[Y_t(p) < k * G_t]`.

The comparison remains strict `<`; `G_t` is the same fixed-support whole-stone
median. The benchmark thresholds are globally fixed at `0.60, 0.65, 0.70`,
with `0.65` as the operational baseline. The complementary state is named
`non_dark` in machine output; it is not an independently calibrated bright
state.

A run is a maximal sequence of the same state over consecutive **observed source
steps**. Missing/rejected frames and invalid whole-stone references break and
censor runs. Under `dynamic` support, support loss breaks/censors the run and
re-entry starts a new run. Under `fixed` support, only pixels supported
throughout the observed interval are eligible. Interval endpoints censor runs.
The final requested step is never joined back to the first, even when the source
viewer itself is cyclic.

For every eligible pixel and state, the descriptor records the longest observed
run. Regional summaries include Q50/Q90/max longest-run length, fraction with a
non-zero run, and Q90 normalized by the **requested source-step count**:

`q90_window_fraction = q90_longest_run_frames / requested_source_steps`.

The denominator is deliberately not each pixel's own support count: a pixel that
is supported for only two frames cannot become "100% persistent" merely because
it is dark in both.

Censoring remains auditable. Each cell records total/completed/censored runs,
left/right boundary counts for gaps, invalid references, support loss and window
endpoints, plus the fraction of pixels whose longest run has any/all tied maxima
censored.

Evidence metadata selects representative long dark and non-dark runs. The
associated panel shows run start/middle/end source frames and overlays the pixels
that remain continuously in that state across the highlighted run, together with
left/right censoring reasons.

Every coarse and semantic region is emitted for both `fixed` and `dynamic`
support. Semantic QC propagates only to semantic measurements. Primary benchmark
interpretation should inherit #27/#28's prior evidence: coarse-fixed
centre/inner/middle first (especially inner/middle), with dynamic, semantic and
outer cells retained primarily as support/localisation falsification.

Persistence is descriptive recorded-image run structure. It is not duration in
seconds/degrees, physical-facet tracking, calibrated light return, fire, leakage
or a quality grade.

## Concentric-band coordination: `diamond360-concentric-coordination/1`

`coordination.json` is derived directly from an existing
`diamond360-activation/1` result. It does not recompute photometry, masks,
regional support or activation normalization.

The primary inputs inherited from #26 are coarse-fixed centre/inner/middle
`relative_values`, where activation is
`log(regional median) - log(fixed-support whole-stone median)`. The retained
adjacent-pair candidates are centre↔inner and inner↔middle. Middle↔outer is
emitted but inherits outer-band REVISE/support sensitivity. Semantic fixed
correlations remain localisation/QC sensitivity. Dynamic support is not promoted;
middle↔outer dynamic correlation is retained only to expose support-motion
disagreement.

For aligned component traces `a_t` and `b_t`, level coordination is ordinary
Pearson correlation over aligned finite observations:

`r = corr(a_t, b_t)`.

At least three aligned finite observations are required. A constant component
trace makes the correlation unavailable rather than emitting NaN. Positive
correlation describes coordinated relative activation states; negative
correlation describes alternating/opposed states. Neither direction is a quality
grade.

The output also preserves an adjacent-event audit trace with `delta_a`,
`delta_b`, `same`/`opposite`/`tie` relationship and
`joint_move_strength = min(abs(delta_a), abs(delta_b))`. Same/opposite fractions
are audit candidates rather than retained primary summaries. Missing/rejected
observations break adjacency, and wrapped adjacency such as `255 -> 0` is only
valid when the upstream activation interval explicitly declared wrapping.

A symmetric four-band correlation matrix is retained for compact diagnostic
inspection, but non-adjacent correlations are not promoted as separate primary
descriptors. Pair validity composes monotonically from both component activation
validities plus local mathematical availability; upstream KEEP/REVISE/REJECT
disposition remains separate provenance.

Evidence metadata selects the strongest coordinated event, strongest divergent
event and a typical directional event. The writer can render both band traces and
the corresponding source-frame pair.

Concentric coordination describes recorded-image relationships. It is not
physical-facet tracking, calibrated light return, fire, leakage, a
hall-of-mirrors score or a quality grade.



## Broad-vs-fragmented flash morphology: `diamond360-flash-morphology/1`

`morphology.json` measures the spatial connectedness of a whole-stone **bright active field**. It intentionally does not partition the stone into coarse or semantic radial bands, because imposed band boundaries can split a connected flash and manufacture fragmentation.

For each observed frame, `G_t` is the #26 median encoded brightness on fixed common registered stone support and

`S_t = 1.4826 * median(|Y_t(p) - G_t|)`

on that same fixed support. Active pixels satisfy the strict comparison

`Y_t(p) > G_t + k*S_t`.

The global benchmark threshold set is `0.90, 1.00, 1.10`, with `1.00` the baseline; per-stone tuning is forbidden. The connected-component convention is fixed at 8-connectivity.

Every frame records active/support pixel counts, active fraction, raw component count, largest-component pixels, `largest_component_fraction = largest_component_pixels / active_pixels`, largest-component/support fraction, inverse-Simpson effective component count, and support-boundary contact diagnostics. A frame with no active pixels has unavailable morphology rather than an invented coherence value.

Both `fixed` common support and `dynamic` frame-local support are emitted. The threshold reference and robust scale remain fixed-support quantities in both modes so changing support does not silently change the photometric state definition. Fixed support is the retained production mode; dynamic support is QC.

Summaries include active-frame fraction and medians/quantiles of morphology only over active frames. Evidence selection deterministically surfaces broadest, most fragmented, matched-active-area, threshold-sensitive, strongest support-disagreement and low-disagreement cases.

The retained primary descriptor is the fixed-support median largest-component fraction at `k=1.00`. Effective/raw component counts remain diagnostic. The descriptor is recorded-image morphology, not calibrated light return, fire, physical-facet identity, sparkle quality or a purchase grade.
