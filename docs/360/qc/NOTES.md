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
x=349..363, y=355..400 across the selected views; dimensions change with pose.
PCA is ambiguous for 3/16 frames there, 5/16 on LG836619414 and 4/15 on
LG811638512. An apparent axis flip is not stone spin: square silhouette moments
are intrinsically ambiguous. Registration will not use PCA rotation.
`geometry.png` shows ordered samples with original indices, not elapsed time.
