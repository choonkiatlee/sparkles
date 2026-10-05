# Visual QC observations

Stage 2: all 79 archived frames were inspected in per-stone segmentation sheets.
Convex envelopes track the full silhouettes of LG836619414, LG756580087 and
LG811638512 (47 frames). Pale interiors remain included; floor shadows are mostly
excluded. Small edge errors remain: these are approximate photographic outlines.
LG818659722 is cropped top/bottom and LG756520111 bottom near face-up; their
candidate masks remain review-only, not accepted geometry. Some profile views
also trigger conservative fragmented/border checks. Do not override these checks
to manufacture complete outlines. `segmentation-overview.jpg` includes every frame.

Validation data are sparse curated subsets, not uniform or timed full rotations.
Source hashes and exact source indices are preserved in manifests.

Stage 3: 47 accepted masks measured. LG756580087 centroid changes approximately
x=332.3..374.2, y=325.1..361.4 across the selected views; dimensions change with pose.
PCA is ambiguous for 10/16 frames there, 5/16 on LG836619414 and 12/15 on
LG811638512. An apparent axis flip is not stone spin: square silhouette moments
are intrinsically ambiguous. Registration will not use PCA rotation.
`geometry.png` shows ordered samples with original indices, not elapsed time.

Stage 4: inspected registration sheets for all 47 accepted views. Centring and
isotropic scale remove camera translation/size variation; tilt, perspective and
in-plane rotation remain visible. Normalised pairs preserve changing dark/light
step patterns. Source copies match original SHA-256 exactly. Matrix-mapped
centroids equal canvas centre to floating-point precision; this does not measure
segmentation error or prove facet correspondence. Bilinear sampling can attenuate
small highlights; retained originals allow checking this loss. Side/profile views
remain labelled by source index and must not enter face-up temporal summaries.

Stage 5: raw brightness and inverse-sRGB luminance saved without framewise
adjustment. A fixed user-supplied gain (default 1) writes a separate unclipped
channel and never alters raw channels/RGB. Synthetic bright/dark pulses survive;
real LG756580087 near-face-up brightness variation remains visible. Chroma range
is recorded colour variation, not spectral dispersion/fire evidence.

Stage 6: partition overlays inspected on LG756580087 frame 0. Radial bands follow
a square-like (Chebyshev) coordinate, with centre/inner/middle/outer bounds
0.20/0.45/0.70 of the fixed half-extent. Quadrants and eight side/corner wedges
use image axes and intersect the silhouette. Partitions cover each mask exactly,
with no overlap within a partition family. Wedges are not windmill/facet masks;
in-plane roll and perspective make them only approximate diamond regions.

Stage 7: temporal sheets inspected for 12 nearby face-up frames on each of
LG756580087/LG836619414/LG811638512, excluding their context/profile frames.
Centring reduces silhouette-motion effects relative to camera space. The central
and stepped patterns still change, with broad activity bands; residual roll/tilt
means pixels are not homologous facets. Support maps expose varying silhouette
coverage. Grey denotes unsupported pixels; std is undefined with <2 observations.
Dark fraction uses brightness <0.65× each frame's valid-pixel median; fractions
are equal-weight frame counts, not durations. Low std/dark patches can reflect
lighting/obstruction, pose and sampling. No camera-fixed artefact was isolated or
causally identified; the two coordinate systems support inspection, not attribution.

Stage 8: repeatable archive validation ran across all five bundles (79 frames).
47 complete silhouettes canonicalise; 32 cropped/border-affected views remain
review-only, with no fabricated geometry or temporal maps. Maximum raster mask
centroid discrepancy after registration is 0.152 px across the 47 frames.
On the three 12-frame face-up subsets, camera vs normalised mean-brightness
series correlations exceed 0.99998; largest mean difference is 0.000438 (0..1).
These check mean preservation only: fine-highlight preservation still requires
originals, and spatial activity remains affected by roll/perspective.

`cross-registration.jpg` includes all 47 before/after pairs. `validation.json`
records archive SHA-256, source pipelines, dimensions, counts, exclusion indices
and preservation checks. Workshop's bottom-cropped images and Diajewel's
rectangular tightly cropped images are visible source-format failure modes.
Square Diajewel archives pass these checks; unfamiliar or independent capture
pipelines, uniform full rotations, varied backgrounds and calibrated lighting
remain outside this validation. Output publication is atomic and refuses reused
nonempty directories, preventing stale masks/maps from appearing in a new run.
