# Output schema 1.0

JSON contains finite numbers or null, never NaN. NPZ maps use NaN for unsupported
values. Paths are relative to the published output directory unless stated.

## Sequence

`schema_version`, `frame_count`, `valid_count`, `dimensions` (unique `[width,height]`),
`ordering` (`natural_filename`/`explicit_manifest`), `sparse`, `source_frame_count`,
`source_manifest` (unaltered parsed upstream manifest), `warnings`, and
`brightness_definition`. `source_frame_count` can be null; unknown completeness
must not be interpreted as complete merely because `sparse` is false.

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
