# Multi-stone full-sequence benchmark

Issue #18 extends the issue #15 continuous-trace protocol across real Asscher rotations without stone-specific threshold tuning.

## Fixed protocol

- Recover the original ordered supplier sequence upstream; vendor extraction is not part of the benchmark module.
- Run the existing `diamond360` preprocessing at fixed gain `1.0`.
- Use a predeclared visually face-up centre and fixed **17-frame core** / **33-frame sensitivity** windows.
- Measure the existing centre / inner / middle / outer regions on fixed common support.
- Keep raw and normalized temporal measurements together: activation amplitude, relative-dark occupancy, transition count/rate, longest dark/bright runs, pixel switching, and support QC.
- Refuse run/transition interpretation for sparse source indices. Missing frames are not silently interpolated.
- Benchmark runs may explicitly carry `review` silhouettes through registration while preserving their review reasons. Default pipeline behaviour remains `ok`-only.

## Benchmark set

| certificate | pipeline | ordered source | continuous traces | segmentation QC |
|---|---|---:|---:|---|
| IGI-LG756580087 | Diajewel | 256/256 | core + wide | 256 ok |
| IGI-LG756520111 | Workshop | 256/256 | core + wide | 256 review |
| IGI-LG818659722 | Diajewel | 256/256 | core + wide | 256 review |
| IGI-LG836619414 | Diajewel | 256/256 | core + wide | 256 ok |
| IGI-LG811638512 | Diajewel | 128 even frames | withheld | partial source |

The three previously excluded complete sequences were regenerated from their public viewer batches. The reconstructed ordering algorithm exactly reproduces the audited issue #15 mapping for LG756580087; all 16 archived selected originals matched byte-for-byte for each of LG756520111, LG818659722 and LG836619414. Raw 256-frame stacks remain excluded from Git; compact source manifests, hashes and derived traces are committed.

LG811638512 remains intentionally partial: only even source indices were recovered, so continuous run/transition statistics are not inferred from it.

## Run it

Aggregate the committed traces:

```bash
python -m diamond360.benchmark docs/360/benchmark/benchmark.json --output /tmp/sparkles-benchmark
```

To rerun preprocessing from regenerated source directories, place them under `<source-root>/<certificate>/`. Each complete directory must include an authoritative `source-manifest.json` using `diamond360-source/1`, with matching `source_frame_count` and `sequence_complete: true`:

```bash
python -m diamond360.benchmark docs/360/benchmark/benchmark.json \
  --source-root /path/to/recovered-sequences \
  --output /tmp/sparkles-benchmark
```

The run produces `summary.json`, `summary.csv`, `metrics.png`, `sensitivity.png`, `redundancy.png`, and per-stone core/wide traces.

## What survived the benchmark

The four complete stones produce visibly different coarse temporal signatures, but several measurements behave very differently under the 17-frame versus 33-frame windows.

| measurement | disposition | benchmark evidence |
|---|---|---|
| **Region-median dark-state occupancy / transitions** | **Reject** | All 32 stone × window × region rows have dark occupancy = 0 and transition count = 0. The threshold is too coarse at region-median level. |
| **Activation amplitude (p90-p10)** | **Carry forward with support gate** | Discriminates strongly across stones. For the inner core region it ranges from 0.035 to 0.324. Core→wide rank consistency is useful (Spearman ≈ 0.79; median relative change ≈ 12%), but low-support outer regions can move sharply. |
| **Mean relative-dark pixel fraction** | **Provisional** | Differentiates stones/regions and retains core→wide ordering reasonably well (Spearman ≈ 0.78), but median core→wide change is ≈ 31% and it is strongly correlated with pixel switching across core rows (Spearman ≈ 0.87). |
| **Pixel switching** | **Carry forward as a temporal concept; normalize/fix window** | Pixel-level switching remains non-zero and discriminative when the region median is static. Core→wide rank consistency is ≈ 0.80, but “fraction ever switched” mechanically rises with a longer observation window, so raw values must only be compared at the same window length or replaced by adjacent-step transition rates. |
| **Common-support fraction** | **Carry forward as QC only** | Highly repeatable in rank (core→wide Spearman ≈ 0.95), but it measures registration/pose support, not optics. It should gate interpretation rather than enter any quality score. |

### Important failure modes

**Outer-region support is the main pose confound.** LG756580087 falls from 0.824 core support to 0.579 wide; LG836619414 falls from 0.734 to 0.523. The latter stone's outer activation amplitude simultaneously jumps from 0.050 to 0.178. Outer-region optical metrics therefore should not be interpreted without a minimum-support rule or support sensitivity check.

**Segmentation QC is source/framing dependent.** LG756520111 (Workshop) and LG818659722 (Diajewel) are classified `review` on all 256 frames because the foreground/non-uniform border and outline-near-edge checks fire. Their masks remain usable enough for this benchmark only through explicit opt-in; this status is retained as a limitation. Because there is only one Workshop stone, vendor effects cannot be separated cleanly from stone-specific effects yet.

**Dark occupancy and switching are partly redundant.** Across the 16 core stone × region rows, mean relative-dark pixel fraction and fraction-with-transitions have Spearman correlation ≈ 0.87. Activation amplitude is much less correlated with either (≈ 0.12–0.14), so it contributes more independent information.

## Recommendation for the next descriptor stage

Carry forward three pieces:

1. **Activation amplitude**, primarily centre/inner/middle, with common-support gating.
2. **Pixel-level transition structure**, preferably normalized per observed adjacent source step rather than “ever switched”.
3. **Relative-dark pixel level** only provisionally, until we decide whether it adds enough beyond switching to justify both.

Drop region-median dark-state transitions. Treat common support and segmentation status strictly as QC. Do not use any of these as a quality grade or purchase score yet.
