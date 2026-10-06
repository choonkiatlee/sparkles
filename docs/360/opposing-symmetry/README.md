# Opposing-region coordination benchmark

Issue #31 measures whether opposite image-space regions brighten/dim together through the selected face-up Asscher sequence. It is a descriptor of organised recorded-image motion, not a symmetry grade and not a claim that more coordination is automatically better.

## Measurement contract

The declared pairs are E↔W, N↔S, NE↔SW and NW↔SE. Each component consumes #26's retained relative activation trace:

`C_(r,t) = log(B_(r,t)) - log(G_t)`

where `B_(r,t)` is supported regional median encoded brightness and `G_t` is the fixed-support whole-stone median. A frame-wide multiplicative brightness change therefore cancels by construction.

The baseline is the existing **coarse whole side/corner sector on fixed support**. Dynamic support is emitted only as QC. Radial localisation experiments restrict the same sectors by coarse inner/middle or semantic inner_step/middle_step masks. Centre-restricted sectors are omitted as too small/ambiguous for this pair question; outer is omitted because #26 already found it pose/support-sensitive.

Three summary families are tested per pair:

- **correlation** — Pearson correlation of the paired finite relative-activation traces;
- **median absolute pair difference** — `median(abs(C_left-C_right))`, equivalently a median absolute log brightness-ratio imbalance;
- **adjacent sign agreement** — fraction of non-flat observed adjacent source-step pairs where both trace changes have the same sign.

Missing/rejected observations break adjacency. Explicit 255→0 adjacency is allowed only when the requested interval declares wrapping. Flat moves are retained in the audit counts but excluded from the sign-agreement denominator.

## Canonical four-stone benchmark

The Action SHA-verified all four `benchmark-sources-v1` release ZIPs and every contained frame, then reran preprocessing, semantic step bands and #31 on:

- core: exactly `248..255,0..8` (17 source steps);
- wide sensitivity: `240..255,0..16` (33 source steps);
- coarse whole sectors plus coarse inner/middle localisation;
- semantic inner_step/middle_step localisation;
- fixed and dynamic support.

The result contains 304 pair rows. Aggregate values are in [summary.json](summary.json) and [summary.csv](summary.csv). Only six automatically selected representative evidence panels are committed.

## Disposition

**KEEP fixed coarse-whole pair correlation as the primary opposing-region coordination summary, separately for all four pairs.** Cross-stone core→wide rank preservation is strong: Spearman rho is **1.0 E/W, 0.8 N/S, 1.0 NE/SW, 0.8 NW/SE**.

The visual evidence falsifies the intended concept. LG818659722 N/S is a high-coordination example (core correlation ≈0.984) with visibly similar large trace moves; LG756520111 N/S is strongly opposing (≈-0.915) with visibly divergent traces. Neither sign is labelled better.

Core coarse-whole fixed pair support ranges from ≈0.69 to ≈0.98. Dynamic support can materially move correlation in lower-support cases, especially LG836619414, so the production definition remains fixed support and the dynamic result remains a QC/falsification view.

**REVISE median absolute pair difference as a comparison scalar; retain it as audit evidence.** It is directly interpretable and relatively support-stable, but baseline core→wide rank preservation is only 0.2–0.4 across the four pair families. It measures persistent axis imbalance more than coordinated motion and is too window/localisation-sensitive to promote yet.

**REJECT adjacent sign agreement as a separate primary scalar; retain same/opposite/flat counts and selected events.** With only 16 adjacent core pairs it is quantized, its core→wide stability is inconsistent, and it is moderately redundant with continuous correlation (pooled core Spearman ≈0.59). Correlation preserves more information.

## Representation / support experiments

**REJECT dynamic support as a separate primary definition.** It changes region membership and can move correlation substantially in lower-support cases.

**REVISE radial restriction as localisation/QC rather than another descriptor family.** Coarse inner/middle can sharpen particular events but does not consistently improve the whole-sector pair definition.

**REVISE semantic radial restriction.** Coarse↔semantic values can change sharply in sign and magnitude. Semantic availability/support is also materially weaker: LG756580087's entire wide-window semantic template is unavailable (`no_supported_middle_outer_edge`); LG818659722's core semantic template is `review` (`semantic_window_edge`); and LG836619414 wide semantic-middle has three unavailable pair cells from zero support. This is useful localisation sensitivity, not evidence that semantic masks are the better default pair representation.

Corner pairs are sufficiently supported in the 17-frame primary window to retain. Their weakest wide-window support falls to roughly 0.51–0.60, so the wider interval remains sensitivity evidence rather than a replacement definition.

## Downstream meaning

The retained output is deliberately **four pairwise observations**, not one symmetry score. An evaluation can say that one axis moves coherently while a diagonal pair alternates or diverges. That is useful evidence for visual balance / organised motion, while the measurement layer makes no quality judgment.

## Evidence

Representative panels plot both #26-relative traces and overlay both opposing regions on the same source frames:

- [high N/S coordination — LG818659722](per-stone/IGI-LG818659722/core/evidence/coarse_whole-fixed-side_N_S.png);
- [strong N/S opposition — LG756520111](per-stone/IGI-LG756520111/core/evidence/coarse_whole-fixed-side_N_S.png);
- [wide fixed-support corner sensitivity — LG836619414](per-stone/IGI-LG836619414/wide/evidence/coarse_whole-fixed-corner_NW_SE.png) versus [the same pair with dynamic support](per-stone/IGI-LG836619414/wide/evidence/coarse_whole-dynamic-corner_NW_SE.png);
- [coarse-inner localisation — LG756520111](per-stone/IGI-LG756520111/core/evidence/coarse_inner-fixed-corner_NE_SW.png) versus [semantic inner-step restriction of the same pair](per-stone/IGI-LG756520111/core/evidence/semantic_inner_step-fixed-corner_NE_SW.png).

The automatic evidence selection and metric values are recorded in [evidence.json](evidence.json).

## Reproduce

After extracting the four canonical source bundles under a certificate-keyed source root:

```bash
python docs/360/opposing-symmetry/build_benchmark.py \
  --source-root /path/to/benchmark-sources \
  --work-root /tmp/issue31-work \
  --output /tmp/issue31-results
```

Focused tests:

```bash
python -m unittest tests.test_opposing_symmetry tests.test_opposing_symmetry_benchmark -v
```

They cover exact pair calculations, gaps/wrap, flat moves, zero-variance correlation, deterministic evidence, semantic-validity isolation, JSON-safe output and invariance to frame-wide multiplicative brightness changes.

Source ZIPs, extracted frames, preprocessing stacks and exhaustive per-stone outputs stay out of Git.
