# Multi-stone full-sequence benchmark

Issue #18 extends the issue #15 continuous-trace protocol across real Asscher rotations without changing preprocessing thresholds per stone.

## Fixed protocol

- Recover the original ordered supplier sequence upstream; vendor extraction is not part of the benchmark module.
- Run the existing `diamond360` preprocessing at fixed gain `1.0` with no stone-specific threshold tuning.
- Use a predeclared visually face-up centre and fixed **17-frame core** / **33-frame sensitivity** windows.
- Measure the existing centre / inner / middle / outer regions on fixed common support.
- Keep raw and normalized temporal measurements together: activation amplitude, relative-dark occupancy, transition count/rate, longest dark/bright runs, pixel switching, and support QC.
- Refuse run/transition interpretation for sparse source indices. Missing frames are not silently interpolated.

## Benchmark set

| certificate | pipeline | ordered source | committed continuous traces | role |
|---|---|---:|---:|---|
| IGI-LG756580087 | Diajewel | 256/256 | core + wide | issue #15 reference |
| IGI-LG756520111 | Workshop | 256/256 recovered | no | cross-pipeline case |
| IGI-LG818659722 | Diajewel | 256/256 recovered | no | cross-stone case |
| IGI-LG836619414 | Diajewel | 256/256 recovered | no | cross-stone case |
| IGI-LG811638512 | Diajewel | 128 even frames | no | explicit sparse failure case |

The complete working sequences for the middle three stones were validated during their research passes but deliberately excluded from Git to keep research bundles compact. The manifest preserves their exact viewer/provenance chain. LG811638512 remains intentionally `partial`: temporal run statistics must not be fabricated from its even-only sequence.

## Run it

To aggregate whatever continuous trace files are already committed:

```bash
python -m diamond360.benchmark docs/360/benchmark/benchmark.json --output /tmp/sparkles-benchmark
```

To rerun the same preprocessing + trace workflow after regenerating the complete source directories, place them under `<source-root>/<certificate>/`. Each complete directory must include an authoritative `source-manifest.json` using `diamond360-source/1`, with `source_frame_count` matching the benchmark and `sequence_complete: true`; this prevents filename order from being mistaken for source order. Then run:

```bash
python -m diamond360.benchmark docs/360/benchmark/benchmark.json \
  --source-root /path/to/recovered-sequences \
  --output /tmp/sparkles-benchmark
```

The repository includes the current `summary.json` / `summary.csv` for the committed reference traces. A fresh run creates `summary.json`, `summary.csv`, `metrics.png`, `sensitivity.png`, `redundancy.png`, and per-stone preprocessing/trace outputs. A missing complete-source directory remains visible as `source_missing`; a partial sequence remains `partial_source`.

## Current evidence and metric disposition

The checked-in numeric reference remains LG756580087 until the intentionally uncommitted sequences are regenerated. Its region-median dark-state transition count is zero across both fixed windows, while pixel-level transition fractions are non-zero. That is a useful warning: **region-median dark-state transitions are provisional and may be too coarse**, whereas pixel switching, activation amplitude and relative-dark pixel occupancy remain worth benchmarking. Common-support fraction is QC, not an optical quality metric.

Do not infer cross-stone robustness from the single committed numeric reference. The purpose of this harness is to make the next recovery/run mechanical and to force unsupported or sparse cases to remain explicit rather than being quietly compared.
