# PR A findings — boundary-local tier contrast

Issue: #57  
Implementation: PR #61

## Disposition: **REVISE, preserve the primitive and proceed to PR B/C**

PR A establishes a useful **boundary-local matched-sector measurement layer**,
but it does not justify promoting one boundary geometry, strip width, or scalar
summary into the production profile.

The guarded-strip primitive itself is auditable and behaves correctly in
synthetic tests. Source-frame evidence is more directly tied to the visual
question than the original whole-band scalar: the overlay shows exactly which
inside/outside regions produced each local contrast.

The experiment also exposes two important sensitivities that must remain
visible downstream:

1. strip width materially changes some stones/boundaries;
2. #19 semantic boundary correspondence is not uniformly stable between the
   exact-core and wide windows.

This is a useful result rather than a failed experiment: PR B/C can now work
from a localized field while retaining the geometry/sensitivity diagnostics
needed to reject misleading summaries.

## What was tested

For each adjacent boundary, source frame and one of the existing eight
side/corner sectors:

```
inside  = [b - g - w, b - g]
outside = [b + g,     b + g + w]

signed = log(B_inside) - log(B_outside)
L      = abs(signed)
```

with:

- guard `g = 0.010`;
- widths `w = 0.025 / 0.040 / 0.055`;
- fixed sequence-level geometry;
- per-frame valid pixel support retained as QC;
- no fitted support threshold.

Two boundary geometries are compared:

- **#19 semantic boundary controls**;
- **legacy coarse boundary** as an explicit control.

The earlier #49 whole-band and broad matched-sector measurements remain in the
same output for direct comparison.

## Synthetic / contract result

Focused tests and the full repository suite pass.

The tests establish:

- exact log-ratio recovery and signed reversal;
- common multiplicative brightness invariance;
- explicit gaps for invalid brightness;
- local sector contrast survives whole-band cancellation;
- guarded inside/outside strips are disjoint;
- a narrow edge spike inside the guard does not masquerade as broad tonal
  separation;
- fixed normalised geometry can use per-frame valid support without requiring
  identical persistent pixels;
- partial #19 boundaries may be used only as `review` when a *different*
  boundary is missing;
- ambiguous/non-separable #19 geometry cannot be rescued by partial controls.

## Four-stone benchmark

The canonical four source bundles were run on the exact 17-frame core and
33-frame wide windows.

At the middle width `w=0.040`, representative Q50 values are:

| stone | pair | #49 broad sector core | coarse-strip core | semantic-strip core |
|---|---|---:|---:|---:|
| LG756520111 | centre-inner | 0.0726 | 0.0657 | 0.0664 |
| LG756580087 | centre-inner | 0.0478 | 0.0644 | 0.1046 |
| LG818659722 | centre-inner | 0.1004 | 0.1127 | 0.1897 |
| LG836619414 | centre-inner | 0.0380 | 0.0736 | 0.1518 |
| LG756520111 | inner-middle | 0.0421 | 0.0485 | 0.0499 |
| LG756580087 | inner-middle | 0.0502 | 0.0888 | 0.2032 |
| LG818659722 | inner-middle | 0.1021 | 0.1095 | 0.1185 |
| LG836619414 | inner-middle | 0.0921 | 0.0870 | 0.1102 |

These magnitudes are descriptive only. Larger is not assumed to be better.

The same-frame evidence is the strongest reason to keep the primitive:
semantic strips visibly straddle the detected nested transition rather than
averaging the full coarse tier. The automatic rank-disagreement examples also
show that this is genuinely a different frame-level question from #49's broad
sector median; maximum within-sequence rank disagreements at `w=0.040` are
commonly large (roughly 0.44–0.88 against the broad formulation in the core
examples).

## Width sensitivity

Width cannot be selected from the present benchmark.

Across the 16 stone × window × boundary cases, the relative range of semantic
Q50 across the three tested widths is about **5.7% to 59.3%**. Seven of the
sixteen cases move by more than 20% relative to their median width result.

The largest sensitivity is LG756520111 wide inner-middle. Several other
centre-inner and inner-middle cases are materially width-sensitive.

Therefore PR A does **not** nominate 0.040 (or any other width) as a production
constant. It remains a convenient evidence-panel width only.

## Core / wide sensitivity

Cross-stone Spearman rank correlation of semantic Q50 between core and wide is:

| pair | w=0.025 | w=0.040 | w=0.055 |
|---|---:|---:|---:|
| centre-inner | 0.2 | 0.2 | 0.2 |
| inner-middle | 0.8 | 1.0 | 1.0 |

For comparison, #49 broad matched-sector Q50 is 0.8 for both pairs at all three
rows (the broad value itself does not depend on strip width).

The weak centre-inner semantic stability is not just scalar noise. The largest
geometry change is **LG818659722 centre-inner**, whose median #19 sector
boundary moves from approximately `u=0.595` in the core template to
`u=0.508` in the wide template. Other median semantic-boundary shifts are
much smaller (roughly 0.001–0.011 in this benchmark).

That means a downstream descriptor must not silently interpret a changed
semantic boundary as changed diamond behaviour. Geometry correspondence itself
needs to remain part of validity/sensitivity evidence.

LG756580087 also supplies a useful different failure mode: the wide #19
template cannot recover the middle-outer boundary, while centre-inner and
inner-middle remain supported. PR A preserves those adjacent boundaries as
`review` rather than discarding them or pretending the full template passed.

## Visual cross-checks

The automatically selected original-source comparisons are consistent with the
intended measurement claim:

- LG756520111 source 4 is an informative centre-inner disagreement case and is
  also among the existing evaluation-derived tier-readability frames;
- LG756580087 shows large semantic inner-middle separation on frames where the
  visible nested transition is much more local than the broad-band statistic;
- LG836619414 source views with clear nested architecture produce strong local
  boundary examples, while the disagreement panel demonstrates that broad
  sector contrast and boundary contrast need not rank frames the same way;
- LG818659722 demonstrates why the geometry trace must remain auditable: strong
  local contrast can coexist with a core/wide boundary-correspondence change.

The existing calibration annotations are AI-derived from prior evaluations,
not independent human ground truth. They are used here only as qualitative
cross-checks. Independent frame-level labels remain PR C.

## What PR A earns

Keep for the next research slices:

- the guarded boundary-local signed/absolute sector field;
- all eight sector traces rather than only a median;
- #19 semantic and coarse-boundary controls;
- width sensitivity;
- continuous support diagnostics;
- same-frame source evidence;
- explicit partial-boundary `review` handling.

Do **not** yet:

- choose one strip width;
- promote semantic-boundary Q50 to the retained profile;
- claim semantic geometry dominates the coarse control;
- combine the two adjacent boundaries into a score;
- assign a quality direction;
- fit thresholds on four stones.

## Next step

PR B should consume this field and test **spatial coverage + joint nested
readability + signed tonal ordering** while preserving geometry/width
sensitivity. In particular, Q25/median and weakest-link summaries should not be
allowed to hide an unstable boundary correspondence.

PR C remains necessary before any production decision because frame-level
human calibration is the correct test of whether the localized field predicts
visible tier readability beyond the retained activation/occupancy/coordination
vocabulary.
