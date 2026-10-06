# Activation descriptor benchmark

This directory completes the real-stone validation for issue #26. It measures **recorded-image activation**, not calibrated radiance, light return, fire, leakage, facet identity, or cut quality.

## Protocol

The primary benchmark is the exact wrapped 17-frame interval `248..255,0..8` on the four complete #18 stones: IGI-LG756580087, IGI-LG756520111, IGI-LG818659722 and IGI-LG836619414. The 33-frame interval `240..255,0..16` is sensitivity only. All stones use the committed `diamond360-source/1` manifests, gain 1.0, review-mask opt-in where required, #19 defaults, and identical source indices inside every coarse/semantic × fixed/dynamic A/B.

Each per-stone/window run produces `activation.json`, `activation.csv`, and standardized evidence panels for Q10/Q50/Q90 and the largest observed adjacent moves. Those full generated outputs are intentionally **not committed**. The repository keeps only the aggregate `summary.json` / `summary.csv`, [dispositions.json](dispositions.json), and the four comparison pairs (eight PNGs) linked below as representative evidence.

## What the benchmark says

**Whole-stone activation survives.** The standardized panels show visibly different recorded whole-stone states at the selected extrema, so the fixed-support whole-stone trace is retained as a separate primitive rather than folded into regional activation.

**Fixed coarse centre/inner/middle survives as the cleanest local baseline.** Persistent support is effectively complete for these bands, and fixed and dynamic measurements are normally identical. Preserve both raw regional brightness for audit and the log-relative trace for the local descriptor; the latter removes the common stone-wide baseline by construction.

**Outer activation needs revision.** Pose/support loss becomes material. For LG836619414, coarse outer persistent support falls from 0.427 in the core to 0.199 in the wide window while fixed raw excursion rises from 0.050 to 0.178. LG756580087 falls from 0.523 to 0.295. This is evidence for support sensitivity, not a basis for inventing a hard cutoff from four stones.

**Semantic localisation is promising but not ready to replace coarse geometry.** Geometry can change the temporal interpretation substantially: relative coarse↔semantic traces are sometimes negatively correlated, while some controls agree closely. LG756580087's wide semantic template is unavailable (`no_supported_middle_outer_edge`), and LG818659722's core template is under `semantic_window_edge` review. In LG836619414, semantic middle fixed support is only 0.084 core / 0.0076 wide and semantic outer is 0.037 / 0.0017.

**Dynamic support is QC, not the primary descriptor.** In well-supported coarse centre/inner/middle it adds essentially no information. Where support is weak it can dramatically alter the trace: LG836619414 wide semantic-outer raw excursion is 0.409 fixed versus 0.053 dynamic; LG756580087 core semantic-outer is 0.121 versus 0.018. Those disagreements are useful warnings about membership/support motion.

**Directional excursions survive; MAD does not win a separate primary role.** Across complete coarse configurations, p90-p10 and MAD rank stones similarly (about 0.91 average rank agreement), but core→wide rank consistency is about 0.90 for p90-p10 versus 0.80 for MAD. Keep Q10/Q50/Q90 with separate bright and dark excursions; retain MAD only as an audit field.

## Falsification examples

The benchmark intentionally includes both disagreements and controls rather than cherry-picked “good” cases.

| case | evidence | reading |
|---|---|---|
| Low geometry disagreement | [LG756520111 core coarse centre relative](per-stone/IGI-LG756520111/core/evidence/coarse-centre-fixed-relative.png) vs [semantic centre](per-stone/IGI-LG756520111/core/evidence/semantic-centre-fixed-relative.png) | Similar excursion magnitude and visibly coherent selected states; semantic geometry can work. |
| Geometry disagreement | [LG818659722 core coarse inner relative](per-stone/IGI-LG818659722/core/evidence/coarse-inner-fixed-relative.png) vs [semantic inner](per-stone/IGI-LG818659722/core/evidence/semantic-inner_step-fixed-relative.png) | Both are auditable, but they select materially different activation patterns; geometry is not interchangeable. |
| Support disagreement | [LG836619414 semantic middle fixed relative](per-stone/IGI-LG836619414/core/evidence/semantic-middle_step-fixed-relative.png) vs [dynamic](per-stone/IGI-LG836619414/core/evidence/semantic-middle_step-dynamic-relative.png) | Large trace/amplitude change accompanies very low persistent support. |
| Outer support disagreement | [LG756580087 semantic outer fixed relative](per-stone/IGI-LG756580087/core/evidence/semantic-outer_step-fixed-relative.png) vs [dynamic](per-stone/IGI-LG756580087/core/evidence/semantic-outer_step-dynamic-relative.png) | Fixed and dynamic definitions diverge strongly, supporting revision rather than a global semantic-outer descriptor. |

## Disposition

| candidate | decision | retained role |
|---|---|---|
| Whole-stone fixed raw activation | **KEEP** | Primary broad-activation primitive |
| Coarse fixed centre/inner/middle raw | **KEEP** | Audit primitive |
| Coarse fixed centre/inner/middle log-relative | **KEEP** | Primary local activation descriptor |
| Coarse fixed outer raw/relative | **REVISE** | Candidate + support sensitivity |
| Semantic fixed centre/inner/middle/outer raw/relative | **REVISE** | Candidate; correspondence/support unresolved |
| Dynamic support, coarse or semantic | **REJECT** as primary | Retain as QC/falsification output |
| Q10/Q50/Q90 bright + dark excursions | **KEEP** | Primary scalar summaries |
| MAD scale | **REJECT** as primary | Retain as audit field |

The machine-readable table expands this to every representation × region × support mode × trace type in [dispositions.json](dispositions.json).

## Validity and limits

Two stones carry upstream segmentation review reasons (`foreground_or_nonuniformity_on_border`, `outline_near_image_edge`). Those reasons propagate into coarse, whole-stone and semantic measurements. Semantic-only warnings remain semantic-only: LG818659722 core inherits `semantic_window_edge`, while the corresponding coarse result does not. LG756580087 wide semantic output is explicitly unavailable while its coarse and whole-stone measurements remain valid.

The sample is only four stones and mixes source pipelines. These results establish a measurement contract and failure modes, not population thresholds. In particular, no minimum support percentage, excellent/good/poor boundary, purchase recommendation, or optical-quality claim is introduced.

## Reproduce

The original 256-frame sources are GitHub Release assets indexed by [../benchmark/source-bundles.json](../benchmark/source-bundles.json). Follow [../benchmark/README.md](../benchmark/README.md) to download and verify them, preprocess with gain 1.0 and `accept_review=True`, run `diamond360.asscher_steps` on the same requested interval, then call `diamond360.activation_benchmark.measure_stone` / `write_stone_outputs`.

Generated per-stone outputs under `docs/360/activation/per-stone/` are ignored by Git except for the small set of already-tracked representative panels. For full reruns, prefer `outputs/` or another local/artifact directory rather than Git history.

Run repository validation with:

```bash
python -m unittest discover -s tests -v
```
