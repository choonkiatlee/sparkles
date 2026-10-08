# Human articulation review — 6 October 2026

Follow-up to #59 / #62.

One blinded rater reviewed four predeclared brightness-matched pairs. Certificate IDs, source indices, metric values and descriptor predictions were hidden.

| pair | unblinded mapping | articulation | pale/quiet | metric prefers | agreement |
|---|---|---|---|---|---|
| 1 | LG756580087 · A=4, B=253 | A | B | B | no |
| 2 | LG818659722 · A=5, B=3 | unsure | unsure | A | not scored |
| 3 | LG836619414 · A=0, B=6 | A | B | B | no |
| 4 | LG756520111 · A=254, B=253 | A | B | A | yes |

The current `distributed_contrast` ordering agrees with the articulation judgement on 1 of 3 decisive pairs.

In all three decisive pairs, the side judged more articulated is the opposite side from the side judged paler/quieter. The metric selects the paler/quieter side in two of those three pairs.

## Disposition

- Keep `distributed_contrast` only as a descriptive coarse spatial-distribution primitive.
- Do not treat it as a human-validated articulation proxy.
- Do not tune the fixed eight-sector score to these four pairs.
- Next test: Asscher-specific panel-aware articulation.
- Keep temporal spatial participation on hold until the static panel-aware representation is tested.

This is exploratory evidence from one rater and four pairs, not a calibrated perceptual model.
