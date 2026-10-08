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

## Validation cadence (updated 8 October 2026)

**Fast PR gate:** run focused synthetic/frozen-method tests and the complete
four-stone #89 stability, leave-one-out, and fixed-ruler transfer comparison.
Preserve failures, semantic identity, and exact gauge; compare against the
immutable #96 artifact from run 37755387174. Inspect results across **all four
diamonds**, not just LG756520111. The source ZIPs and benchmark manifest
must still match the exact frozen SHA-256 values.

**Source-stress is deliberately deferred.** The #90 two-stone seven-condition
perturbation / poor-view benchmark takes too long for normal iteration. Both
`asscher-window-peak-stress.yml` and the original
`asscher-geometry-source-stress.yml` run only via `workflow_dispatch`.
The research code and archived #96 stress evidence remain available for a
later deliberate manual run; **source-stress is not a PR acceptance gate**.

A successful stability experiment is therefore *provisional*, not a claim
of robustness to sharpening, blur, changes of source gauge, or camera pose.
Do not publish a global `KEEP` conclusion without revisiting that evidence.

Experiments must also preserve the #88 no-numeric-pass-threshold policy and
must never relabel a reflected/virtual contrast peak as a polished junction.
If an experimental candidate changes the primary scaffold or results in new
`unavailable` cases, record both the improvement and that cost.

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
