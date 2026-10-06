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
