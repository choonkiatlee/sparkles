# Issue #75: constrained semantic Asscher wireframe fitter

This layer turns the accepted/canonicalized geometry views from #73 plus the
stable sequence gauge from #80 into **one stone-level semantic scaffold** using
the #74 topology contract.

The primary rule is that geometry is fitted once per stone. Per-frame image
edges are retained as evidence and residuals; they never redefine the ruler
frame-by-frame.

## Pipeline

```text
#73 canonical geometry views
        +
#80 stable sequence orientation
        +
#19 persistent radial/tier edge evidence
        |
        v
multi-frame consensus evidence
        |
        +-- ordered nested-step constraints
        +-- weak counterpart support
        +-- #74 topology validity
        |
        v
one #74 stone-level semantic scaffold
        |
        +-- per-entity confidence/provenance
        +-- exact supporting source-frame indices
        +-- per-frame support/residual diagnostics
        +-- rejected/unsupported candidate evidence
```

The implementation is in `diamond360.asscher_wireframe`.

## Representation boundary

This is deliberately **not** generic image segmentation and does not assert

```text
every pixel -> exactly one polished physical facet
```

The #74 representation policy is preserved:

- image-plane semantic supports are non-exclusive;
- a support is not a direct projection claim;
- physical semantic identity exists even when image evidence is weak;
- future optical/appearance regions may associate many-to-many with physical
  semantic entities.

The three persistent radial boundaries from `asscher_steps.py` are reused as
ordered image evidence anchors for the crown-facing scaffold. They remain
silhouette-normalized image measurements, not physical facet lengths or angles.

Pavilion P1/P2/P3 structures visible through the table are treated more
conservatively. Version 1 fits persistent inner support loci where evidence
exists and otherwise falls back to low-confidence model support. Those supports
may overlap. They are **not** ray-traced virtual facets and are **not** direct
polished-pavilion projections.

## Fixed stone-level fit

The fitter selects up to seven of the best compatible crown-side geometry
views from the #73 ranking. Each frame is rotated only by the quarter-turn
branch already selected by #80. It then:

1. samples the existing normalized radial edge evidence;
2. discovers one persistent three-boundary template across the selected views;
3. transfers those controls into the explicit #74 semantic scaffold;
4. retains real sector-to-sector asymmetry rather than enforcing equality;
5. records observed/model-inferred state and confidence per support/entity;
6. evaluates every selected frame against that fixed scaffold and serializes
   support/residual evidence separately.

If required ordered evidence is absent, the result is `unavailable`. Weak or
partially inferred evidence produces `review`, not a forced perfect Asscher.

## Anti-circularity test

The synthetic suite includes a deliberately stronger bright/dark edge that
moves between frames while the underlying persistent boundary stays fixed.
The fitted canonical boundary must remain near the persistent geometry. This
guards against the later optical layer moving its own geometry ruler merely
because appearance changes.

Other synthetic checks cover:

- persistent asymmetric evidence;
- missing boundary evidence;
- insufficient compatible views;
- topology-valid scaffold output;
- source-frame provenance;
- stable sequence gauge selection;
- non-exclusive pavilion supports.

Run:

```bash
python -m unittest tests.test_asscher_wireframe -v
```

## Four-stone research benchmark

The dedicated `asscher-wireframe-benchmark` workflow downloads the same four
hash-pinned 256-frame IGI rotations used by the #73/#80 benchmark, preprocesses
them, runs #73/#80, and then runs **the same frozen #75 configuration** on every
stone.

No per-stone threshold or manual vertex placement is allowed.

The workflow produces, for each stone:

- `wireframe.json` with the canonical scaffold and evidence;
- `wireframe-qc.jpg` with the same fixed scaffold over the selected canonical
  geometry views plus a source-free scaffold rendering;
- the exact selected source indices/phases;
- confidence and observed/model-inferred state;
- per-frame residual/support diagnostics;
- rejected radial candidates.

The generated research bundle is uploaded as a workflow artifact rather than
committed as bulk source-derived imagery.

### QC display versus measurement representation

The estimator intentionally measures the fixed 160-pixel normalized luminance
representation with its declared low-pass transfer function. That representation
is designed for stable measurement, not visual appraisal.

Human-facing `wireframe-qc.jpg` therefore uses the original camera RGB at native
source resolution when the processed source sequence is available. The fitted
scaffold is mapped back with #80's exact sequence-gauge-to-camera transform.
This avoids making the diamond look artificially blurred or making an
approximate display mapping look like a geometric fitting error. Changing the
QC rendering does not change the fitted scaffold.

## Validation boundary with #76

#75 is the estimator/frozen-method PR. It does **not** tune against the stored
DiaGem/Sergey values and does not claim the method is externally validated.

#76 must treat this implementation as frozen and attempt to falsify it using:

- neighboring-view semantic stability;
- transfer into non-fitting crown-view frames;
- source-processing perturbations;
- the recovered original DiaGem/Sergey attachments;
- independent target values inspected only after the extraction method is
  frozen.

Any post-validation method change should be declared as a new revision and
re-run over the complete validation set.

## Non-goals

- physical facet-angle recovery;
- full 3-D reconstruction;
- optical/virtual-facet segmentation;
- P3 leakage or hall-of-mirrors scoring;
- brilliance/fire/scintillation scoring;
- a composite Asscher quality score.
