# Broad-vs-fragmented bright-flash morphology benchmark

Issue #33 tests whether the spatial shape of the brightest recorded structures distinguishes **broad/coherent flashes** from **fragmented/busy flashes** without turning either appearance into a quality grade.

## Measurement contract

The production experiment is whole-stone morphology. Radial coarse/semantic partitions are deliberately **not** used for connected components because an imposed band boundary can split one physically continuous image-space flash and manufacture fragmentation.

For every observed frame, let `G_t` be the #26 whole-stone median encoded brightness on fixed common registered support. Define a robust within-frame contrast scale on that same fixed support:

`S_t = 1.4826 * median(|Y_t(p) - G_t|)`.

The bright active field is then

`A_t(p;k) = 1[Y_t(p) > G_t + k*S_t]`.

The comparison is strict `>`. The globally fixed baseline is `k=1.00`; `0.90/1.10` are sensitivity probes. There is no per-stone threshold tuning. Connectivity is fixed at **8-connected** pixels.

The initial implementation used a simple multiplicative threshold `Y > k*G_t`. The canonical benchmark falsified that choice: at its baseline one complete Workshop stone had no active frames. The definition was therefore revised globally, before disposition, to the robust-contrast form above. The revised baseline produces active morphology on all four benchmark stones.

For an active mask with connected components `C_j`, the primary per-frame candidate is

`largest_component_fraction = max_j |C_j| / |A_t|`.

A value near 1 means most active pixels form one connected structure; smaller values mean the active area is spread across multiple components. Zero-active frames are **unavailable morphology**, never encoded as 0 or 1.

The runner also records inverse-Simpson effective component count

`N_eff = 1 / sum_j (|C_j|/|A_t|)^2`,

raw component count, active area, boundary contact, and fixed-vs-dynamic support disagreement. These are audit fields unless explicitly retained below.

The interval scalar is the median largest-component fraction over frames where an active field exists. `active_frame_fraction` remains beside it so a stone with few qualifying flashes cannot masquerade as a fully observed morphology estimate.

## Benchmark

Primary window: exact 17-frame wrapped interval `248..255,0..8`.  
Sensitivity window: `240..255,0..16`.

The four complete #18 sources are downloaded from the SHA-verified `benchmark-sources-v1` release assets. Only the 33 required frames are preprocessed; no source images or full generated runs are committed.

At the fixed-support `k=1.00` baseline, median largest-component fraction is:

| certificate | 17-frame core | 33-frame sensitivity |
|---|---:|---:|
| IGI-LG756580087 | 0.344 | 0.311 |
| IGI-LG756520111 | 0.126 | 0.150 |
| IGI-LG818659722 | 0.192 | 0.223 |
| IGI-LG836619414 | 0.111 | 0.112 |

Cross-stone rank order is unchanged core→wide (Spearman rho = 1.0), at `k=0.90` and `k=1.10` versus baseline (rho = 1.0 for both), and fixed→dynamic support at baseline (rho = 1.0).

The threshold probes still affect **availability**: at `k=1.10`, LG756520111 has 11/17 active core frames and LG818659722 8/17. This is why threshold sensitivity and active-frame fraction remain mandatory diagnostics and why `k=1.10` is not treated as another production definition.

## Does it measure morphology rather than active area?

Yes, on this benchmark. Across 64 active baseline core frames, active-area fraction versus largest-component fraction has only modest rank association (rho ≈ 0.24).

The strongest matched-area counterexample is LG818659722: source frames 5 and 7 have almost identical active fractions (0.0435 versus 0.0429) but largest-component fractions of about 0.145 versus 0.495. The diagnostic overlay shows the difference directly.

Automatic evidence panels under [evidence/](evidence/) mark support in blue, the active field in orange, and the largest connected component in red. They include broadest, most-fragmented, matched-area, threshold-sensitive, strongest support-disagreement and control frames.

## Redundancy

Effective component count is almost the same morphology information with the sign reversed: pooled core-frame Spearman versus largest-component fraction is about **-0.96**. It is therefore not retained as a second descriptor.

Across only four stones, baseline median largest-component fraction has Spearman rho ≈ **-0.20** with whole-stone activation excursion and **0.00** with the retained mean inner/middle switching rate. The sample is too small for inference, but it provides no evidence that morphology is merely restating those existing scalar rankings.

## Support boundaries

Fixed common support is the production mode. Dynamic support is retained only as falsification/QC. Cross-stone ranks are identical, but individual frames can differ materially when support changes; LG836619414 source frame 0 differs by about 0.109 in largest-component fraction between fixed and dynamic support.

Boundary-active fraction and count of boundary-touching components remain explicit so future evaluation can identify cases where support clipping is driving the morphology.

## Disposition

| candidate | decision | role |
|---|---|---|
| robust bright active field `G_t + 1.00*S_t` | **KEEP** | baseline state definition |
| fixed-support median largest-component fraction | **KEEP** | primary broad↔fragmented morphology descriptor |
| effective component count | **REJECT** as separate scalar | redundant diagnostic |
| raw component count | **REJECT** as primary | audit only; tiny components dominate count |
| dynamic support | **REJECT** as primary | support-motion QC |
| radial coarse/semantic restriction | **REJECT** for production morphology | boundaries can manufacture fragmentation |
| spatial entropy | **REJECT / not introduced** | no demonstrated incremental information beyond component morphology |

The safe downstream interpretation is descriptive: **larger values mean the selected bright field is concentrated in fewer/larger connected structures; smaller values mean it is spatially fragmented.** This is not a sparkle-quality, fire, light-return, facet-identity or purchase score.

Machine-readable aggregate results are in [summary.json](summary.json) / [summary.csv](summary.csv); final decisions are in [dispositions.json](dispositions.json).
