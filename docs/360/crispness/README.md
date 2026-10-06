# Static tier-boundary crispness

Issue #50 tests whether **static geometric crispness / tier-boundary legibility** can be measured reproducibly from ordinary vendor 360 imagery.

This is a research descriptor, not part of the retained #45 profile yet.

## Measurement contract

The implementation deliberately reuses the #19 Asscher step-band representation rather than building a second geometry detector.

For each expected #19 boundary, each held-out frame is sampled on 96 radial rays. A small local search around the expected boundary produces three separate primitive families:

- **boundary strength** — robust z-score of the strongest local radial edge;
- **boundary continuity** — fraction of rays with #19-style local support plus longest circular unsupported gap;
- **boundary positional consistency** — robust MAD of local peak offsets from the expected boundary.

The three families remain separate. There is no combined crispness score.

## Cross-fit geometry

A direct measurement at the same edges used to build the #19 template would be circular.

The benchmark therefore uses an interleaved two-fold scheme:

1. discover the #19-compatible template on odd frames;
2. score only even frames;
3. discover on even frames;
4. score only odd frames.

The ordinary full-window #19 template is retained only as a diagnostic and for comparison with #19 edge alignment.

## Source-pipeline sensitivity

Every measured stone is re-scored under four controlled image-space perturbations while holding the baseline geometry fixed:

- mild Gaussian blur;
- 2× downsample / bilinear upsample;
- JPEG recompression at quality 70;
- mild unsharp masking.

The same perturbations also rediscover the cross-fit geometry so that measurement sensitivity and geometry sensitivity are reported separately.

These are stress tests, not exact reconstructions of Diajewel or Workshop processing.

## Evidence

The runner automatically identifies per stone:

- strongest boundary example;
- weakest / most ambiguous example;
- largest continuity failure;
- largest source-pipeline sensitivity example.

Evidence panels place the copied original camera frame first and the registered diagnostic second. The diagnostic shows the expected boundary in white and supported local ray peaks in black.

Derived edge maps are not the primary evidence.

## Four-stone benchmark

The canonical validation windows remain:

- core: `248..255,0..8` (17 frames);
- wide sensitivity: `240..255,0..16` (33 frames).

The benchmark uses the four complete #18 source bundles:

- IGI-LG756580087 — Diajewel;
- IGI-LG756520111 — Workshop;
- IGI-LG818659722 — Diajewel;
- IGI-LG836619414 — Diajewel.

It also joins the #22 `static_geometric_crispness` observations for LG818659722 and LG836619414 so the output can be checked against the human review rather than treated as a self-contained image statistic.

Run locally from extracted release bundles:

```bash
python -m diamond360.crispness_benchmark \
  --source-root outputs/crispness-sources \
  --output outputs/crispness-benchmark
```

The pull-request workflow downloads the versioned source bundles, verifies their SHA-256 hashes, runs the full repository tests, executes the core + wide benchmark and uploads the generated benchmark directory as a workflow artifact.

## Decision rule

A primitive should only be retained if it:

1. corresponds visually to the boundary property it claims to measure;
2. is stable across nearby frames and core vs wide windows;
3. adds information beyond #19 template support / edge alignment;
4. survives reasonable source-pipeline perturbations;
5. does not depend on one vendor pipeline.

With only one Workshop stone, the current benchmark can falsify bad vendor-sensitive definitions but cannot establish strong cross-vendor invariance or aesthetic thresholds.

Possible outcomes are **KEEP**, **REVISE** or **REJECT**. A successful issue may end in REJECT.
