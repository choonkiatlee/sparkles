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

## Four-stone results — 8 October 2026

The opt-in #89 run [37775298832](https://github.com/choonkiatlee/sparkles/actions/runs/37775298832) passed its focused tests, source integrity checks, all four-stone primary/leave-one-out fits, fixed-ruler transfer, and three-way baseline comparison against immutable #96 and #131.

| Certificate | Frozen #96 maximum local-tier displacement | #131 window-local | #134 frame-coherent | Primary |
|---|---:|---:|---:|---|
| LG756520111 | 1.015936 | 1.015936 | **1.015936** | review |
| LG756580087 | 0.220310 | 0.220310 | **0.220310** | review |
| LG836619414 | 0.268954 | 0.268954 | **0.268954** | review |
| LG818659722 | unavailable | 0.179538 | **0.179538** | review; one leave-out unavailable |

**No change in maximum stability across the four stones relative to #131.**
Most critically, `LG756520111` still changes C3/table from
`u=0.578616` in the five-frame primary to `u=0.477987` when frame 16
is omitted. The selected frames and the geometric outer fit remain unchanged.

The full image-space candidate audit reveals *why* the score failed:

| LG756520111 | Winner u≈0.478 | Other u≈0.579 |
|---|---:|---:|
| **Five-frame original score** | 1.568 | 2.371 |
| Five-frame fraction of supported views | 1.00 | 1.00 |
| Five-frame median angular misalignment u | 0.0252 | 0.0189 |
| Five-frame new rank score | 2.643 | **3.490** |
| **Without frame 16 original score** | 1.729 | 1.324 |
| Without frame 16 fraction of supported views | 1.00 | 1.00 |
| Without frame 16 median angular misalignment u | 0.0252 | 0.0283 |
| Without frame 16 new rank score | **2.804** | 2.377 |

Even with frame 16 omitted, the 0.579 hypothesis has strong frame-wise
sector support counts **6, 7, 7, 7** versus **4, 8, 8, 6** for 0.478.
However, **both** satisfy the threshold of at least four sectors in
all four remaining views. The chosen binary persistence metric therefore
saturates at 100% for *both* and cannot separate the candidates. Median
angular offsets are close, so changing one scalar score cannot be
justified by a clear physical geometry signal.

**Disposition: REVISE / do not promote the experimental ranker.**
This deliberately negative result is important: persistence of radial
image contrast and eight-sector smoothness *do not identify a physical
Asscher facet junction* in this 360. The next responsible step should
retain **both** hypotheses and flag an ambiguity for physical/virtual
facet separation and geometry validation, rather than reweighting the
score using LG756520111 until one particular mode wins.

The score remains opt-in, no defaults changed; #90 source stress remains
manual/deferred. Per-case scorer diagnostics, comparative JSON and visual
QC are available from the linked successful workflow artifact.

