# Adjacent-tier contrast / articulation (#49)

This module tests whether adjacent Asscher regions remain tonally distinct in a
given recorded view. It is a targeted follow-up to the #22 calibration gap, not
a quality score.

## Primary definition

The primary candidate consumes the retained #26 coarse-fixed relative activation
traces directly.

For band i:

    r_i,t = log(B_i,t) - log(B_whole,t)

For adjacent bands i,j:

    C_ij,t = r_i,t - r_j,t
    D_ij,t = abs(C_ij,t)

The common whole-stone term cancels, so D is exactly the absolute adjacent-band
log brightness ratio. No new photometric normalization is introduced.

Pairs under test:

- centre ↔ inner;
- inner ↔ middle.

The full signed trace is retained for audit. Candidate summaries are Q10
(weak-separation / near-collapse tail), Q50 (typical separation), and Q90
(strongest available separation). There is deliberately no hand-tuned collapse
threshold.

## Standardized challenger

A second formulation tests whether raw inter-band difference is misleading when
one or both bands contain substantial within-region tonal variation.

For each band/frame on the same #26 fixed support:

    R_i,t = 1.4826 * MAD(Y_i,t) / median(Y_i,t)

Then:

    S_ij,t = D_ij,t / sqrt((R_i,t^2 + R_j,t^2) / 2)

This is experimental. Zero spread is surfaced as unsupported; no epsilon is
introduced. The within-band spread is not promoted as a #49 descriptor because
that would overlap the separate #51 within-inner-articulation hypothesis.

## Evidence

For each pair the implementation automatically selects:

- weakest separation;
- representative median separation;
- strongest separation;
- largest percentile-rank disagreement between simple and standardized
  formulations.

When processed frames are available, the evidence panel shows the copied
camera-original frame beside a registered diagnostic overlay outlining both
bands. Original imagery remains the primary evidence.

## Benchmark protocol

Use the canonical #20 benchmark:

- core: 248..255,0..8 (17 frames), primary;
- wide: 240..255,0..16 (33 frames), sensitivity only;
- four complete #18 benchmark stones;
- gain 1.0;
- coarse fixed support;
- no retuning of #19 or photometry.

Per-stone Python flow:

    from diamond360 import asscher_steps
    from diamond360 import tier_contrast_benchmark as tb

    indices = list(range(248, 256)) + list(range(0, 9))
    asscher_steps.run(processed, step_output, indices, wrap=True)
    result = tb.measure_stone(processed, step_output, indices, wrap=True)
    tb.write_stone_outputs(result, output, processed=processed)

Run the same flow on the wide interval only as sensitivity. Source bundles are
the versioned release assets listed in docs/360/benchmark/source-bundles.json.

## Validation questions

The eventual benchmark/disposition must answer:

1. Do low/high D frames visibly correspond to collapsed/distinct adjacent
   layers?
2. Does Q10/Q50/Q90 survive core/wide sensitivity?
3. Does simple separation add information beyond #26 activation, #27 occupancy,
   and #32 nested-step coordination?
4. Does the standardized formulation correct concrete visible failures of the
   simpler D, or merely add noise/complexity?
5. Do pale/quiet inner-panel examples actually have low adjacent separation?
   If not, that is evidence that #51 is a genuinely separate hypothesis rather
   than a failure of #49.

The final issue disposition remains KEEP / REVISE / REJECT after the four-stone
source-frame audit. The implementation does not add #49 to the #45 production
profile automatically.

## Current implementation status

Implemented:

- representation-neutral contrast kernel;
- signed + absolute frame traces;
- Q10/Q50/Q90 summaries;
- robust standardized challenger;
- deterministic source-indexed evidence selection;
- exact #26 coarse-fixed adapter;
- monotone validity propagation;
- camera-original + registered-overlay evidence renderer;
- JSON/CSV per-stone outputs;
- synthetic/integration tests;
- exact reconstruction of the simple candidate from the committed per-frame
  fixed-support benchmark traces;
- four-stone core/wide benchmark, redundancy diagnostics and #22 frame checks.

See [summary.json](summary.json), [summary.csv](summary.csv) and
[findings.md](findings.md).

The current **provisional disposition is REVISE**: whole-band coarse medians
erase local tier contrast in several human-selected readable/crisp frames, and
Q10/Q50 are window-sensitive. The next #49 experiment should localize
adjacent-tier contrast spatially before attempting to retain another scalar.

The standardized challenger remains implemented but empirically pending because
it requires the processed pixel arrays from the versioned release source
bundles. It should be treated as a control/falsification test, not as an assumed
fix for the failed coarse spatial primitive.
