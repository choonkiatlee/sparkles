# #124: frozen #96 vs semantic-window-local peak experiment

## Motivation

The preceding frozen #127 diagnostic showed that `C3_TABLE` can jump
from `u≈0.579` to `u≈0.478` when frame 16 is omitted, **even though the
original ~0.579 contrast maximum remains present**. In the current method,
`find_peaks(consensus, distance=15)` suppresses neighboring peaks
*globally* before the algorithm filters into the predefined C3/table
`[.42,.60]` window. A stronger outside-window peak near `u=.629`
deletes an otherwise eligible `u=.579` observation, then is itself
rejected as out of window.

This experiment tests whether changing **only the scope of minimum-distance
peak suppression** addresses that failure without harming other Asschers.

## Predeclared treatment and control

**Control `outer_octagon_v2`:** fully frozen and default; original
`find_peaks(consensus, distance=15)` on the complete radial consensus,
then global candidate assembly and semantic selection.

**Treatment `window_local_peaks_v3_experiment`:** use exactly the existing
C3, C2 and C1 windows `[.42,.60]`, `[.64,.82]`, `[.82,.92]`.
Apply the unchanged minimum peak separation **independently within each
window** before unioning candidate peaks. Score prominence on the original
unmodified full consensus and use precisely the same per-sector support,
candidate scoring, inner-step radius windows, topology, silhouette fit,
source normalization, semantic gauge, missing-evidence handling and transfer.

For the treatment, a missing local peak **stays unavailable**, rather than
manufacturing a candidate from a raw strongest sample. This is conservative
and may worsen previously available estimates. Those failures count.

Control and treatment share the same frozen #96 `wireframe.specification()`
hash and #88 benchmark source manifest; a **distinct versioned method ID
plus fail-closed policy specification** identifies the experimental branch.
The default production method is unchanged. No per-diamond conditions,
tuned windows, modified thresholds, target angles or learned geometry.

## Required independent validation

1. Generic adversarial synthetic peaks just inside and outside a semantic
   window; demonstrate that the treatment retains the inside peak while
   the control's global nonmaximum suppression discards it. Retain
   an assertion that the explicit control path is identical to the default.
2. Four-stone #89 refit, leave-one-out and fixed-ruler transfer using the
   *same* selected frames, masks and outer octagon method:
   [frozen #96 comparator](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174).
3. Two-stone full seven-perturbation #90 stress plus poor-view:
   [frozen #96 comparator](https://github.com/choonkiatlee/sparkles/actions/runs/37755387140).
4. Pair by certificate and perturbation under the *unchanged* #88 metric
   schema, including selected indices, refit failures, maximum
   local-tier displacement, support/provenance regressions, semantic
   ID swaps, and exact gauge changes.
5. Review raw camera-RGB wireframes with specific attention to crown-tier
   spatial plausibility. Lower displacement does **not** imply correctness.

Both workflows download source bundles and verify **exact SHA-256** from the
#88 manifest. They retrieve original immutable #96 artifacts by run ID
rather than recomputing a moving baseline. They emit `summary.json`,
per-stone reports and `window-peak-comparison.json`.

## Interpretation

The diagnostic identified an **algorithmic cross-window suppression
mechanism** for a particular discontinuity, *not* a physically correct
C3 facet junction. Reflections and virtual facets can still produce image
contrast, and the #73 canonical transform is similarity-only: it does
not turn an oblique view into a calibrated front-on diamond.

A KEEP decision requires no severe regressions on other stones and
credible geometry support; otherwise report REVISE/REJECT explicitly.
Do not silently merge experimental selection into the default fitter.
Any promotion requires a separate reviewed frozen method revision.
