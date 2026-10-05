# Diamond 360 preprocessing design and implementation plan

Objective and authorisation: tracker #12 and the user's staged execution brief.
Produce auditable preprocessing, not optical quality scores. Each stage is tested,
committed, pushed and logged in #12 before starting the next. Execute inline.

Architecture: `diamond360` Python package; NumPy, Pillow and SciPy; unittest.
CLI accepts extracted local frames and optional existing order manifest. Output
schema records source hashes/indices, failures and transformations. Originals
remain byte-identical. Compact QC is committed; bulky outputs are ignored.

Stages (each gets tests first, expected failure, implementation, passing suite,
real-data run/QC, separate commit/push and tracker update):
1. ingestion.py: discover/ingest; manifest ordering and source hashes; test numeric
   order, wrap order, corrupt/duplicate/mixed-size/empty inputs.
2. segmentation.py: segment RGB -> mask/boundary/status; test known polygon,
   flat background failure and clipped/complex background; inspect all five stones.
3. geometry.py: measure mask -> centroid/bbox/axes/ambiguity; test translated and
   near-square shapes; emit trajectory/size/axis QC.
4. registration.py: camera -> centred fixed-size RGB and mask + 3x3 matrices;
   test matrix inverse, alignment and brightness preservation; no perspective warp.
5. photometry.py: recorded sRGB brightness + linear-light luminance, unchanged RGB;
   optional sequence-wide gain only, test real temporal contrast survives.
6. regions.py: masked Chebyshev radial bands, image quadrants/sides/corners;
   test disjoint partitions and mask containment. No facet/windmill segmentation.
7. diagnostics.py: explicit selected frame set -> mean/std/dark fraction/support;
   test missing support, constant frames and temporal pulses. No quality score.
8. validate_repository.py: repeatable safe ZIP-frame extraction and run all five
   saved selections; preserve provenance; visual QC and failure/coverage summary.
9. README/schema/methodology/limitations + full suite and final review.

Review focus: sparse/wrapped selections, disconnected transparent outlines,
shadows/flat backgrounds, square-axis ambiguity, side views/missing support.
Temporal maps use only an explicit near-face-up subset and require visual review.
Full rotations, calibrated angles and independent lighting are not in this archive.

Persistent source of truth: https://github.com/choonkiatlee/sparkles/issues/12
