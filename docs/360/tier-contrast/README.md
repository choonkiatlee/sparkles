# Adjacent-tier contrast / articulation (#49)

This research slice asks whether adjacent Asscher tiers remain tonally distinct in
recorded views. It is a follow-up to the #22 calibration gap, not a cut grade or
quality score.

## 1. Coarse baseline

The first candidate consumes the retained #26 coarse-fixed relative activation
traces directly.

For band i:

    r_i,t = log(B_i,t) - log(B_whole,t)

For adjacent bands i,j:

    C_ij,t = r_i,t - r_j,t
    D_ij,t = abs(C_ij,t)

The whole-stone term cancels exactly, so D is the absolute log brightness ratio
between the two coarse bands. We test centre↔inner and inner↔middle, preserve
signed contrast for audit, and summarize Q10/Q50/Q90 without a tuned collapse
threshold.

The four-stone committed-trace benchmark is in [summary.json](summary.json) and
[summary.csv](summary.csv).

## 2. Standardized coarse challenger

To test whether a coarse brightness difference is misleading when either band is
internally variable, the raw-pixel run also computes:

    R_i,t = 1.4826 * MAD(Y_i,t) / median(Y_i,t)
    S_ij,t = D_ij,t / sqrt((R_i,t^2 + R_j,t^2) / 2)

The same #26 fixed support is used. Zero spread is unsupported rather than
epsilon-adjusted. This is a control only: within-band spread is not promoted as a
#49 descriptor because that would overlap #51.

## 3. Localized matched-sector revision

The coarse benchmark produced direct counterexamples: entire-band medians can be
almost equal even while the eye clearly sees separated tiers. The revision keeps
the same adjacent-tier question but changes only the spatial primitive.

Each coarse radial band is intersected with the existing eight image-axis
side/corner sectors. For each matched sector and frame:

    L_ij,s,t = abs(log(B_i,s,t) - log(B_j,s,t))

All eight local traces are retained. The experimental frame-level scalar is the
median across matched sectors; Q75 is retained as audit context. Sector labels
are image locations, not facet identities.

This is intentionally simpler than introducing new semantic/facet segmentation:
it tests whether spatial averaging was the actual failure mode while reusing
existing masks and fixed-support rules.

## Evidence and benchmark

The benchmark remains the canonical #20 protocol:

- core: 248..255,0..8 (17 frames), primary;
- wide: 240..255,0..16 (33 frames), sensitivity;
- four complete benchmark stones;
- gain 1.0;
- fixed support;
- no stone-specific tuning.

The raw-pixel run uses the versioned release bundles listed in
[../benchmark/source-bundles.json](../benchmark/source-bundles.json). It
preprocesses only the 33 required source indices while preserving their original
256-frame source indices/provenance.

Generated per-stone evidence panels compare the camera-original frame with a
registered overlay. For the localized formulation the overlay shows the
strongest matched sector for that selected frame.

Committed aggregate outputs:

- [raw-pixel-summary.csv](raw-pixel-summary.csv): all four stones, core + wide,
  simple / standardized / localized Q10/Q50/Q90;
- [raw-pixel-findings.json](raw-pixel-findings.json): sensitivity,
  representative human-frame counterexamples, redundancy diagnostics and
  candidate dispositions;
- [findings.md](findings.md): interpretation.

## Result

**Issue disposition: REVISE.**

The three candidate outcomes are deliberately different:

| candidate | disposition | reason |
|---|---|---|
| coarse simple separation | **REJECT as production descriptor; keep as baseline** | whole-band averaging erases visible local tier separation; Q10/Q50 are window-sensitive |
| coarse standardized separation | **REJECT as fix; keep as control** | rescales the failed numerator but cannot recover spatial structure that has already been averaged away |
| localized matched-sector separation | **REVISE / promising** | fixes the concrete cancellation counterexamples and improves Q50 core/wide rank stability, but incremental cross-stone information is not established at n=4 |

Localized Q50 has core/wide rank Spearman rho = **0.8 for both adjacent pairs**,
versus **0.2** for coarse centre-inner Q50 and **0.0** for coarse inner-middle
Q50. However, several localized summaries remain strongly rank-correlated with
retained activation/occupancy/coordination fields in this four-stone sample.

Therefore #49 should **not** yet be added to #45/#23. The implementation and
evidence are retained so a future larger calibration set can test whether the
localized descriptor adds independent predictive value.

## Boundary with #51

A pale or internally flat inner region can still be strongly separated from its
neighbors. #49 measures **between-tier separation**; #51 asks about
**within-inner articulation**. The raw-pixel results reinforce that these should
remain separate hypotheses.
