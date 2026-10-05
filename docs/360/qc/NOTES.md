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
