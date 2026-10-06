# Blind external benchmark findings

Issue #64 steps 3–5, run against the normalized PriceScope manifest and the pinned v3 archive. The run was blind with respect to metric tuning: no thresholds, windows, descriptor definitions or score weights were changed to fit these labels.

Run provenance: GitHub Actions `37546261729`, PR head `830e2e2bc08d68d439101a85f91941f505e46be4`, artifact `11451271108` (`sha256:b2e1c99a2d52cd4cdfaee526ff294953b98649846b0f8f08302ff9b31d2e3f82`). All 13 primary benchmark samples completed.

## Headline

The benchmark is already useful because several plausible proxy hypotheses fail. In particular, current relative-dark occupancy/persistence and research tier-readability should **not** be treated as generic Asscher performance scores. The failures are preserved rather than tuned away.

- The controlled P3 progression does not produce the expected monotonic improvement in inner darkness or tier readability.
- Karl’s worse P3 D360 stone (`Crispest`) has **higher**, not lower, current tier-readability than `Glittery`.
- The Kashi `Messy arrows` / `Nice dance` pair does not validate binary switching as a proxy for attractive “dance”; the negative control actually switches more under the benchmark adapter.
- The corner/windmill stills clearly perturb the diagonal-arm geometry response, but the current legibility primitive is not a direct windmill-size estimator and should not be converted into a 24% → 14% goodness axis.

## P3 controlled progression

Source order: `cut for weight / bad p3` → `proper p3` → `lighter / higher performance`. The original clips are all 98 decoded frames and are analyzed in full source order. All headline cells are `review` because the tiny 80×176 simulations trigger `outline_near_image_edge`; this is a source/pipeline caveat, not a hidden threshold adjustment.

| metric | bad p3 | corrected | higher performance | disposition |
|---|---:|---:|---:|---|
| inner relative-dark occupancy mean | 0.2797 | 0.3428 | 0.2907 | contradicts expected decrease |
| inner dark persistence Q90/window | 0.4184 | 1.0000 | 1.0000 | strongly contradicts; corrected/higher saturate at 1.0 |
| research tier readability median | 0.0712 | 0.0708 | 0.0794 | non-monotonic / contradicts simple progression |
| inner switching rate | 0.0506 | 0.0401 | 0.0380 | descriptive only; lower across progression |

Interpretation: the present relative-dark state is tied to each clip’s recorded brightness distribution, so it can classify persistent tonal structure without being a P3 leakage/performance proxy. Tier readability measures separability of nested tonal layers; the P3 article’s performance change is not equivalent to “larger tonal separation”. This is a useful falsification, not a reason to retune the thresholds.

## Karl-labelled D360 pair

Both archived sequences satisfy the normal 256-frame source contract and use the frozen wrapped face-up core `248..255,0..8`. Values remain `review` because of existing segmentation QC flags, but there is no benchmark-specific thresholding.

| metric | Glittery | Crispest | interpretation |
|---|---:|---:|---|
| inner relative-dark occupancy mean | 0.3590 | 0.3294 | lower on Crispest; not predeclared as the P3 discriminator |
| inner dark persistence Q90/window | 0.6471 | 0.5882 | lower on Crispest |
| research tier readability median | 0.0746 | 0.1015 | **opposite** predeclared P3-performance direction |
| inner switching rate | 0.1918 | 0.1739 | descriptive only |

The #55 crispness diagnostics reinforce the percept separation rather than rescuing a quality score. `Glittery` has stronger centre↔inner boundary strength (6.17 vs 5.04), while `Crispest` has stronger inner↔middle strength (4.13 vs 2.65). “Geometric crispness / tier legibility” and Karl’s P3 performance criticism are therefore not interchangeable concepts.

## Kashi motion pair

The original Kashi clips are much longer (1,590 and 1,461 decoded frames). To keep the benchmark bounded without inventing a face-up centre, the explicit adapter uses 99 uniformly spaced frames over each whole clip and records the original indices. These are benchmark-normalized clip steps, **not** production source-step timing.

| metric | Messy arrows | Nice dance | disposition |
|---|---:|---:|---|
| inner dark occupancy mean | 0.0930 | 0.0524 | lower on Nice dance; qualitatively compatible but not predeclared as decisive |
| inner dark persistence Q90/window | 0.0505 | 0.0505 | tie; fails to distinguish |
| inner switching rate | 0.1108 | 0.0677 | opposite the naïve “more switching = nicer dance” hypothesis |
| research tier readability median | 0.0308 | 0.0185 | lower on Nice dance; tier separation is a different percept |

This is informative: a messy stone can create **more** binary state changes than an attractive one. Switching counts reconfiguration, not coherence or pleasing organization. Future “dance” work should therefore look at structured/coherent motion, not simply reward transition frequency.

## Corner / windmill sweep

The six public inline previews are analyzed as one-frame static geometry only; no fake motion is created. Source weight rises as corner break shrinks, reproducing the known weight-retention trade-off.

| corner break | source weight | median diagonal-arm confidence | four-arm spacing MAD |
|---:|---:|---:|---:|
| 24% | 1.44 ct | 0.1765 | 12.67° |
| 22% | 1.47 ct | 0.2722 | 0.25° |
| 20% | 1.51 ct | 0.2458 | 13.22° |
| 18% | 1.52 ct | 0.4000 | 0.27° |
| 16% | 1.55 ct | 0.3178 | 13.07° |
| 14% | 1.56 ct | 0.5473 | 0.20° |

The geometry primitive reacts strongly, but not as a clean size axis: confidence trends upward overall toward the smaller-corner examples, while the spacing diagnostic alternates between near-zero and ~13° on these previews. That pattern is consistent with the descriptor measuring edge/path legibility and preview orientation/aliasing rather than corner-break percentage itself. Therefore this family is **not applicable / measuring a different percept** for direct windmill-size estimation. A future explicit corner-break/windmill-width geometry descriptor would be needed to measure the source variable itself.

## Descriptor-family disposition

| family | disposition from this benchmark |
|---|---|
| relative-dark occupancy | **contradicts** the controlled P3 progression as a generic performance direction; still useful as descriptive grouped-darkness evidence |
| dark persistence | **contradicts** P3 progression and does not separate the Kashi pair under the current adapter |
| switching / mobility / activation | **not a quality axis**; Kashi result shows more switching can accompany the negatively described stone |
| tier readability | **contradicts** a simple P3-quality interpretation on both the P3 progression and Glittery/Crispest; retain as tier legibility only |
| static crispness | **not applicable to generic performance**; boundary-specific crispness and P3 performance separate |
| directional / morphology descriptors | descriptive/contextual here; no external label in these sets supplies a justified one-dimensional quality direction |
| diagonal-arm geometry | responds to the windmill sweep but **does not directly measure corner-break size** |

## What this changes

1. Do **not** turn current retained descriptors into a composite Asscher “goodness” score from these examples.
2. Keep `tier_readability` and `static_crispness` named as percept-specific research descriptors; neither is validated as a P3-performance proxy.
3. For “dance”, develop organization/coherence descriptors rather than assuming more activation or switching is better.
4. For the corner/windmill question, add a direct static geometry measurement of corner-break / windmill width if that design variable matters downstream.
5. Preserve the source/pipeline caveats: P3 simulations are tiny and all headline measurements are `review`; Kashi motion uses an explicit uniform full-clip adapter rather than calibrated 360 angles.

## Coverage boundary

This first blind run covers the 13 primary controlled / labelled samples: three P3 videos, six corner/windmill previews, two Karl-labelled D360 sequences and two Kashi motion examples. The remaining normalized manifest records are secondary, paired-view or locator-only evidence and were not required to answer the primary #64 falsification questions.
