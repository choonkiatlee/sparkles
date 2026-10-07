# Issue #89: multi-view stability and fixed-ruler transfer

This stage uses the frozen #88 validation contract to test the already-frozen
#75 semantic Asscher wireframe in two deliberately separate ways.

## A. Estimator stability

The primary #75 scaffold is first reproduced using the exact same geometry-view
selection, #80 gauge and frozen fitter.

For each selected primary geometry view, one leave-one-out run removes that view
and re-runs the same #75 estimator on the remaining accepted views.

Each candidate scaffold is compared to the primary with the #88 contract:

- raw corresponding-boundary displacement in canonical coordinates;
- displacement as a fraction of local adjacent tier spacing;
- semantic-support centroid displacement;
- semantic-ID/support-association consistency;
- semantic gauge consistency;
- provenance, observation-state, validity and confidence changes.

There is no per-stone tuning and no numeric pass/fail cutoff. The purpose is to
measure estimator dispersion, not to choose a convenient tolerance after seeing
the answers.

Each leave-one-out run stores both its validation record and its candidate
wireframe. `stability-qc.jpg` renders the primary and candidate source-free
scaffolds side-by-side for visual audit.

## B. Fixed-ruler transfer

After the primary scaffold is fitted, **the fitter is no longer called**.

The primary C1/C2/C3 and P1/P2/P3 targets are frozen and evaluated against a
wider crown-view window with a usable #80 sequence gauge, including frames
outside the primary fit and frames whose pose assessment has deteriorated to
rejected.

When #73 resolves the crown lobe, its crown peak and lobe radius define this
window directly. When #73 leaves face identity unresolved, #89 does **not**
silently widen to the whole 360: it takes the circular medoid of the primary
geometry-view positions and reuses #73's sequence-size/8 lobe radius, expanding
only enough to contain every primary fitting view. Positions 255 and 0 are
retained as explicit cyclic-wrap controls when needed.

For every transfer frame the result records:

- source index and sequence position;
- approximate #80 viewer phase;
- stable gauge quarter-turn;
- circular distance from the selected crown peak;
- whether the frame participated in the primary fit;
- per-boundary and per-pavilion-locus support;
- per-semantic-entity support/visibility/confidence/residual state;
- explicit `ok`, `review` or `unavailable` support state.

The geometry mode is always:

```text
fixed_primary_scaffold_no_refit
```

and every record stores `refit_performed: false`.

Semantic IDs are inherited from the fixed primary scaffold. Optical/tonal
evidence may strengthen, weaken or disappear, but it cannot silently rename or
move the geometry ruler.

## Transfer status

Transfer uses #75's already-frozen local edge diagnostic (`z >= 0.8`) rather
than introducing a new learned threshold.

For a semantic entity:

- `ok`: all support loci required by that entity are supported;
- `review`: some local evidence exists but the full fixed support is not met;
- `unavailable`: no local evidence is available.

For the frame-level crown summary:

- `ok`: every frozen C1/C2/C3 boundary-sector target is supported;
- `review`: some crown target evidence is available;
- `unavailable`: no crown target evidence is available.

These states describe support for the fixed ruler. They are not Asscher quality
grades.

## Cyclic/gauge audit

The transfer summary explicitly records whether the crown-view interval contains
the sequence's last position and position 0, including the 255 -> 0 boundary for
the retained 256-frame rotations. It also records:

- missing-gauge count;
- quarter-turn branches encountered;
- the semantic gauge IDs used;
- whether one semantic gauge was preserved across all transfer frames;
- refit count (which must remain zero).

## Four-stone benchmark

The integration workflow runs the same implementation over the four hash-pinned
retained sequences:

- IGI-LG756580087
- IGI-LG756520111
- IGI-LG818659722
- IGI-LG836619414

Outputs per stone include:

```text
summary.json
primary-wireframe.json
transfer.json
transfer-qc.jpg
stability-qc.jpg
stability/
  leave-out-XXXX.json
  leave-out-XXXX-wireframe.json
```

The repository keeps only code/docs/tests; generated benchmark images and JSON
remain workflow artifacts.

## Interpretation boundary

This is geometry validation only.

It does not:

- normalize vendor/source appearance;
- compare with DiaGem / Sergey external angle values;
- identify empirical optical/virtual facets;
- calculate P3 leakage, hall-of-mirrors, fire, scintillation or quality;
- convert image-plane geometry into physical facet lengths/angles.

A successful result means the semantic coordinate system is measurably stable
and can be transferred without redefining itself. It does not mean the diamond
is optically good.

## Run locally

With the retained source bundles already extracted:

```bash
python -m diamond360.asscher_geometry_stability \
  --source-root outputs/asscher-geometry-stability-sources \
  --output outputs/asscher-geometry-stability
```

Focused tests:

```bash
python -m unittest tests.test_asscher_geometry_stability -v
```
