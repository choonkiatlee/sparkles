# Diamond 360 preprocessing

Reusable preprocessing and QC for already extracted frame directories. It measures
and preserves recorded imagery; it does **not** score sparkle, fire, leakage or cut
quality. Project status/resume log: [issue #12](https://github.com/choonkiatlee/sparkles/issues/12).

## Run

Python 3.10+; NumPy >=1.24, Pillow >=9.2 and SciPy >=1.10. Tested with Python 3.12.
From the repository root:

```bash
python -m pip install -e .
# Or, when dependencies are already installed, use the module directly:
python -m diamond360.cli /path/to/extracted-sequence \
  --order-manifest /path/to/extracted-sequence/manifest.json \
  --output outputs/stone-run-1 \
  --diagnostic-indices 246,248,250,252,254,255,0,2,4,6,8,10
```

The installed equivalent is `diamond360 INPUT --output OUTPUT`. Input/output must
be disjoint directories. Output must be fresh or empty; each run publishes its
complete output directory atomically, so failure leaves no partial output.
Choose a new run name to repeat a run. Exit 2 denotes invalid arguments/input;
exit 0 means processing finished, **not** that segmentation/QC passed. Read the
accepted-outline count, diagnostics status, warnings and per-frame reasons.

`--order-manifest` is optional. Natural numeric filename order is the fallback;
only an explicit manifest preserves a curated wrapped order such as 254→0.
Accepted manifest order fields: `reading_order`, `reading_order_zero_based`,
`selected_reading_order`, or `faceup_reading_order` + `context_reading_order`.
Existing `frames`/`selected_frames` source hashes are checked when present.
Missing/unlisted/repeated ordered indices and hash mismatches are errors.
The input may contain a `frames/` subfolder; only immediate images there (or in
INPUT when no such subfolder exists) are discovered. Use one sequence per input.
JPEG/PNG/BMP/TIFF, single-frame 8-bit RGB or grayscale only. Convert alpha, palette,
16-bit, EXIF-rotated and animated inputs explicitly upstream, preserving originals.

`--diagnostic-indices` is an explicit comma-separated list of numeric source
indices from filenames. Select visually comparable nearby face-up views yourself;
no automatic face-up detection occurs. Missing/repeated or ambiguous requested indices are
errors. Unaccepted outlines and duplicate frames within the selected subset are
logged and excluded. A duplicate outside the selection does not suppress its
selected counterpart. At least
two accepted unique frames are needed. Omitting this option skips temporal maps.
Sparse selections use equal frame weights, not durations or uniform angles.

`--gain 1.0` defaults to no change. Optional 0.9..1.1 is **one fixed user-supplied
gain for the whole sequence**, stored as a separate unclipped luminance channel.
It does not correct unknown vendor exposure, and temporal maps use raw brightness.
No automatic per-frame exposure matching, histogram equalisation or denoising.

The supplier extractor is maintained by the `research-igi-diamond` skill at
`scripts/extract_diajewel360.py`; it is not duplicated here. It handles validated
Diajewel/Workshop ordering upstream. This package does not fetch vendor data.

## Outputs and QC

| Output | Meaning |
|---|---|
| `sequence.json` | Versioned manifest, source provenance, decisions, exclusions and transforms |
| `camera/NNNN.ext` | Byte-identical original for each valid image; NNNN = supplied position |
| `masks/NNNN.png`, `NNNN-boundary.png` | Camera-space candidate silhouette/boundary, including review-only masks |
| `diamond/NNNN.png` | 256² RGB, centre/scale normalised; no rotation or perspective warp |
| `diamond/NNNN-mask.png`, `NNNN-valid.png` | Nearest silhouette and stricter valid interpolation support |
| `photometry/NNNN.npz` | Encoded brightness, inverse-sRGB luminance, fixed-gain luminance, chroma and masks |
| `regions/NNNN.npz` | Boolean coarse region masks; no facet or windmill identities |
| `temporal-camera.npz`, `temporal-diamond.npz` | Explicit-subset activity maps, when >=2 frames accepted |
| `segmentation.jpg`, `registration.jpg`, `regions.jpg`, `geometry.png` | Labelled derived QC sheets/plots |
| `temporal-camera.jpg`, `temporal-diamond.jpg` | Mean/std/relative-dark/support maps with fixed display ranges |

Review the source image and red contour in segmentation QC before interpreting any
other outputs. `ok` means heuristics did not find a failure; it is not ground-truth
segmentation. `review` candidate masks never supply geometry, registration or
maps. `failed` masks are empty with a recorded reason. Invalid images remain in the
manifest but have no copied/derived frame outputs. QC JPEGs are display previews;
PNG/NPZ and source originals are the data.

## Reproduce archive validation

```bash
python -m unittest discover -v
python -m diamond360.validate_repository \
  --repository . --work-dir .work-360/check-1 --qc-dir outputs/compact-qc-1
```

Use a fresh work directory. The harness reads exact existing ZIP archives; it does
not download or alter research evidence. Only flat original frames and their
manifest are extracted. It runs five datasets, records archive SHA-256, verifies
original copies, compares mean-brightness series and emits compact QC. Generated
stacks and extracted working evidence are ignored by Git. Keep only representative
QC/provenance in commits. To refresh tracked examples, explicitly use
`--qc-dir docs/360/qc`, visually inspect changes, then commit them.

Current data: 79 sparse frames from five stones, across Diajewel and Workshop.
47 complete silhouettes accepted; 32 cropped/border-affected frames flagged.
The three accepted sequences each have 12 nearby face-up frames in their temporal
summaries. Maximum raster centroid discrepancy 0.152 px; maximum difference in
near-face-up per-frame mean brightness 0.000438 (0..1), correlation >0.99998.
These checks do not prove preservation of individual tiny highlights or facets.

See [QC observations](qc/NOTES.md), [validation metadata](qc/validation.json),
[segmentation overview](qc/segmentation-overview.jpg),
[all registered pairs](qc/cross-registration.jpg), [regions](qc/regions.jpg),
[temporal examples](qc/temporal.jpg), [schema](SCHEMA.md) and
[methodology/limitations](METHODOLOGY.md).

## Resume / next work

Read issue #12, PR #13 and latest branch commits; run the suite and validation into
a fresh working directory. Follow the issue's next action. This implementation is
complete within the archived-data scope. Next useful extension is validation on
full continuous rotations and an uncropped Workshop sequence, with existing QC
reviewed before changing thresholds. Better background models/manual masks may
then be warranted. Downstream Asscher quality scoring is outside this package.
