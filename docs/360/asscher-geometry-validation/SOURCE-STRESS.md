# Issue #90: source-pipeline and poor-view geometry stress

This stage asks whether the frozen Asscher semantic geometry survives ordinary
source processing, and whether evidence degrades visibly as views move away from
the geometry-support interval.

It does **not** change #75, #88 or #89.

## Frozen representative set

Two retained 256-frame sequences are used for every source perturbation:

- `IGI-LG756520111` — the comparatively stable #89 estimator case;
- `IGI-LG836619414` — the deliberately sensitive #89 comparator.

This choice is fixed before #90 perturbation results are inspected. The purpose
is to test one stronger and one weaker existing geometry case rather than tune
conditions per stone. `IGI-LG818659722` is not used for source-sensitivity
comparison because #89 could not establish a baseline frozen scaffold for it.

## Frozen perturbation matrix

Every condition is applied uniformly to all 256 source frames:

| ID | Operation |
|---|---|
| `downsample-75pct-lanczos` | resize to 75% in each dimension, then restore original dimensions with Lanczos |
| `gaussian-blur-0p7px` | Gaussian blur, radius 0.7 source pixels |
| `exposure-minus-5pct` | encoded-RGB brightness factor 0.95 |
| `exposure-plus-5pct` | encoded-RGB brightness factor 1.05 |
| `contrast-minus-10pct` | encoded-RGB contrast factor 0.90 |
| `contrast-plus-10pct` | encoded-RGB contrast factor 1.10 |
| `jpeg-quality-85-444` | one JPEG quality-85, 4:4:4 encode/decode round-trip |

After the named pixel operation, every derived frame is serialized losslessly as
PNG. This avoids silently adding JPEG recompression to the blur/exposure/etc.
conditions and ensures the JPEG condition contains exactly one lossy round-trip.

The matrix is deterministic and common to both stones. There are no
per-source/per-condition thresholds.

## Hash-valid derived inputs

The retained benchmark source manifests are authoritative and hash-check every
frame. #90 therefore does not edit archived images or bypass ingestion.

For each stress condition it creates a temporary derived
`diamond360-source/1` manifest that:

- preserves source indices, ordering and sequence sampling;
- records the parent frame path/hash;
- records the complete perturbation specification;
- updates every frame path/byte-count/SHA-256;
- records the canonical SHA-256 of the parent manifest.

The normal production path then consumes that derived manifest:

```text
derived source
  -> ingestion
  -> segmentation
  -> registration
  -> photometry
  -> #73 pose/canonicalization
  -> #80 gauge
  -> frozen #75 estimator
```

No stress-specific fitter path exists.

## Source sensitivity outputs

For each condition, #90 compares the perturbed primary scaffold with the
unperturbed primary using the frozen #88 contract:

- canonical boundary displacement;
- local-tier-normalized displacement;
- semantic-support centroid displacement;
- identity/gauge consistency;
- provenance/state/confidence changes;
- explicit unavailable failures.

It also transfers the **unperturbed fixed ruler** onto the same source-index
views after perturbation and records changes in:

- C1/C2/C3 support fraction;
- supported residual;
- per-entity `ok` fraction;
- per-entity confidence.

If the #80 semantic gauge changes under perturbation, fixed-ruler comparison
fails closed instead of trying to post-hoc rotate the result into agreement.

No composite source-quality or robustness score is calculated.

## Poor-view projection stress

The unperturbed primary scaffold is held fixed and transferred across every
canonical/gauged frame in the full 256-frame rotation.

Each frame is assigned its minimum **circular viewer-frame distance** to any
primary #75 geometry-support position. This is an approximate sequence-phase
distance only; it is not a calibrated physical camera angle.

Results are summarized in the frozen bins:

```text
0–4, 5–8, 9–16, 17–32, 33–64, 65–96, 97–128 frames
```

Each bin reports:

- pose status and mean pose score;
- fixed-ruler transfer status;
- mean/median crown-boundary support;
- mean crown-entity confidence.

The full per-frame trace remains available for audit. Geometry and semantic IDs
never move during this experiment; `refit_count` must remain zero.

The question is empirical: does evidence/support generally deteriorate as
projection moves away from the geometry interval, and are weak views exposed as
weak evidence rather than a new confident geometry?

## Output layout

Generated workflow artifacts contain:

```text
summary.json
per-stone/<certificate>/
  summary.json
  baseline-wireframe.json
  poor-view-stress.json
  source-perturbation-qc.jpg
  conditions/<condition>/
    validation.json
    wireframe.json
    fixed-ruler-support.json
    derived-source-provenance.json
```

Perturbed 256-frame source sequences exist only in temporary workflow storage
and are never committed or uploaded as bulk artifacts.

## Reuse by #81

The perturbation specifications, derived-source provenance and component-level
sensitivity tables are intentionally source-profile-friendly. #81 can reuse
these as empirical source-sensitivity evidence without inheriting a geometry
quality score or duplicating the perturbation definitions.

## Non-goals

This does not solve cross-vendor normalization, infer physical facet angles,
track optical/virtual facets, compute P3 leakage/hall-of-mirrors, or score
diamond quality.
