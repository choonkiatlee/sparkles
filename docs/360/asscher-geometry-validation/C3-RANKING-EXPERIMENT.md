# #124: C3/table candidate ranking — four-stone opt-in experiment

## Prior evidence

- [#127](https://github.com/choonkiatlee/sparkles/pull/127) (now squash-merged):
  frame 16 changes the winner of a C3/table radial-contrast competition.
  Original #96 globally suppresses a candidate near `u≈0.579` with a
  stronger `u≈0.629` maximum outside the C3 search window.
- [#131](https://github.com/choonkiatlee/sparkles/pull/131) (merged as
  **REVISE, not adopted**): localizing suppression within each semantic window
  retains the `u≈0.579` candidate but **still selects `u≈0.478`** when
  frame 16 is omitted. The unchanged prominence-plus-sector-support ranking
  is therefore a second source of instability.
- #73 pose normalization remains *similarity only*, not projective square-on
  rectification. Reflected/virtual optical lines may remain even when the
  silhouette fits perfectly. The label `C3_TABLE` is a semantic hypothesis,
  **not verified polished-facet geometry**.

## Declared three-way, target-blind experiment

- **Control:** frozen `outer_octagon_v2` (#96) from
  [run 37755387174](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174).
- **Intermediate:** opt-in `window_local_peaks_v3_experiment` (#131) from
  [run 37767669755](https://github.com/choonkiatlee/sparkles/actions/runs/37767669755).
- **Treatment:** opt-in `c3_frame_coherence_v4_experiment`.

The treatment uses **identical** #131 candidate collection, predefined
radial windows, outer octagon fit, pose gauge, photometry, and candidate
prominence/sector support. For **C3 only**, it appends two fixed terms
to the existing candidate score:

```
score = log1p(prominence / baseline_prominence_scale)
      + 1.25 * cross_sector_support
      + 1.25 * fraction_of_views_with_4_of_8_supported_sectors
      - 1.25 * median_abs_sector_peak_offset / C3_window_width
```

Existing `1.25` support coefficient is reused. Frame support requires
the existing `z≥0.8` local-peak criterion in at least half the sectors;
local search radius `0.035u`. Spatial consistency is a median offset
between candidate radial position and the eight sector-median local peaks
within `0.045u`. The negative term is normalized by the existing
`0.18u` C3 semantic window width. No fitted coefficients, no
LG756520111-specific settings, no additional faceting constraints.

**This is a falsifiable experiment, not an assumed correct model.**
Persistence across frames could equally well indicate persistent reflected
facet edges. The algorithm therefore records all competing candidate scores
and per-frame sector counts for manual review, without reinterpreting
brightness as a physical surface edge.

C1/C2, C2/C3 selection and original #96 production defaults are **untouched**;
the treatment is a distinct fail-closed method ID with a frozen policy
specification.

## Acceptance and decision

1. Test a synthetic high-contrast transient challenger and steady multi-view
   candidate, including original default-path identity and invalid-method
   failure cases.
2. On exactly the four frozen benchmark Asschers, compare primary fits,
   leave-one-out displacements, confidence/provenance, unavailable counts,
   semantic/gauge identity and fixed-ruler transfer against *both* frozen
   methods, using unchanged #88 numeric/descriptive metrics.
3. Publish per-candidate base score, supported-view fraction, angular
   coherence and total score, plus each leave-one-out C3 winner.
4. Inspect original-camera RGB overlay QC and avoid accepting a numerically
   stable but physically implausible inferred wireframe.
5. Mark **REVISE/REJECT** if the original frame-16 instability remains
   or new per-stone failures appear. Do **not** change production defaults.

As requested, **no automatic source-stress tests**; #90 is manual-only and
any robustness/physical facet claims are explicitly provisional.
