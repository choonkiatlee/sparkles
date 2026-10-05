# Methodology and limitations

1. **Ingestion.** Natural numeric discovery or explicit upstream reading order.
   Fully decode each image and preserve bytes, decoded-pixel hashes, dimensions,
   indices and corrupt/duplicate findings. Metadata brightness includes background.
2. **Segmentation.** Median colour of a three-pixel image border; robust colour
   spread (75th percentile distance) sets contrast threshold `max(18,2×spread)`.
   Spread >30 rejects the background model. Gaussian sigma 0.65 is used **only
   for segmentation**, then colour contrast plus RGB gradient >4 find textured
   foreground seeds. Two-iteration dilation/closing joins edges. Largest connected
   component's convex hull is rasterised, then eroded by two pixels to compensate
   dilation. Pale interiors remain inside the envelope. Border foreground,
   implausible area (outside 1..85%), edge proximity and fragmented components
   trigger review. These heuristics can fail without noticing; inspect overlays.
3. **Geometry.** Uniform silhouette-pixel moments estimate centroid/covariance,
   principal axes and inclusive bbox. Near-square eigenvalues make axes ambiguous;
   ratio <1.08 suppresses the reported angle. No robust physical corner inference.
4. **Canonicalisation.** Translate centroid to `[127.5,127.5]`, scale the larger
   bbox dimension to 192 on a 256² canvas. RGB bilinear interpolation, rounded
   uint8; nearest mask. A stricter valid mask requires all bilinear neighbours
   inside an eroded source mask. Empty canvas is black and excluded by masks.
   Matrices and exact originals are retained. No rotation, homography or shape
   flattening: rotation/pose are physical changes and PCA is ambiguous.
5. **Photometry.** Store recorded encoded brightness and inverse-sRGB luminance.
   No framewise matching/equalisation/denoising. One optional fixed gain writes a
   separate channel; default 1. Chroma range records colour variation, not fire.
6. **Regions.** Chebyshev radius with 0.20/0.45/0.70 edges, four image quadrants
   and eight angular side/corner sectors, all masked. No facet/windmill segmentation.
7. **Diagnostics.** Explicit comparable view selection, excluding rejected and
   duplicated frames; streaming mean/population std/relative-dark count/support.
   Camera and diamond spaces use the same accepted indices. No quality scores.

## What QC can and cannot establish

Centre/scale registration does not establish facet correspondence. Tilt, perspective,
in-plane rotation and self-occlusion remain. A fixed canonical pixel can sample
different physical facets; low-frequency regional summaries are safer candidates
for later exploration than per-pixel optical interpretations. Changes near the
outline can be geometry/support changes. Sparse selections can exaggerate or miss
activity; equal frame weights are not uniform time/angle weights.

Retaining both spaces lets you inspect whether an apparent feature stays near a
camera position or moves with the silhouette. It does not identify the cause:
lighting, camera obstruction, reflections and diamond orientation can coexist.
No camera-fixed artefact has been causally isolated by the present validation.
Ordinary dark photography cannot establish leakage; there is no calibrated
illumination, ASET or spectral/radiometric ground truth here.

Bilinear downsampling can attenuate small highlights and coloured flashes.
Mean-brightness preservation is not a test of individual-flash preservation.
Retain originals for colour/flash detail and evaluate processing at alternative
resolutions before using downstream activity metrics quantitatively.

## Known failures / remaining validation

- LG818659722 is cropped top/bottom; LG756520111 is cropped at the bottom near
  face-up. All their saved views fail conservative border/edge acceptance.
  Partial masks are retained for review, not used to invent missing geometry.
- Strong shadows, texture, logos or multiple objects can join or dominate the
  component. A convex hull can bridge missing edges or include background/shadow.
- Transparent, faint or very thin side views may lack connected textured seeds.
  A disconnected faint outer outline surrounding a dark centre can falsely accept
  only the centre as the whole stone; there is no ground-truth outline benchmark
  for this case yet. Visual review remains required. Degenerate post-erosion
  silhouettes fail explicitly instead of aborting the batch.
- RGB backgrounds varying strongly across the image invalidate the constant-border
  model. A clean border alone does not guarantee a clean interior background.
- Palette/alpha/high-bit-depth/EXIF-rotated/multipage images need explicit upstream
  conversion. ICC profiles are not applied; sRGB is an assumption.
- No full continuous rotations, uncropped Workshop sequences or independent
  lighting/capture systems are validated. Archived evidence is 79 curated frames.
- Tiny centre fluctuations and apparent PCA flips are not measures of stone symmetry.

Next meaningful work: obtain/reuse full continuous source stacks and an uncropped
Workshop example, validate source ordering, inspect overlays, and document new
failure modes before changing thresholds. Manual masks/background-plane fitting
are possible future preprocessing extensions. Quality scoring remains separate.
