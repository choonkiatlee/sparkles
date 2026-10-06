# Within-inner tonal articulation research descriptor (#51)

This is the targeted follow-up from #22 for the recurring **pale / flat /
quiet inner-region** observation. It deliberately asks a different question from
#49:

- #49: are adjacent coarse tiers tonally separated?
- #51: how much tonal structure exists *inside* the coarse inner region?

## Primary observable

The falsifiable baseline is measured on the exact existing #26 **coarse-fixed
inner support**:

```
A_raw,t = Q90(Y_inner,t) - Q10(Y_inner,t)
```

No new registration, region tuning or per-stone mask selection is introduced.

Three normalization challengers are retained alongside the raw value:

- `raw_spread / whole_stone_median`;
- `log(Q90) - log(Q10)`;
- `raw_spread / whole_stone_Q90_minus_Q10`.

The raw spread remains the primary baseline. The challengers are controls for
exposure / brightness scale, not additional votes.

## Evidence contract

Each run automatically selects:

- lowest-articulation frame;
- median-articulation frame;
- highest-articulation frame;
- the closest pair of frames by whole-stone brightness.

The matched-brightness pair is selected by brightness *first* and merely reports
the resulting articulation gap. This avoids cherry-picking a large descriptor
difference at different exposure.

Per-frame outputs preserve inner pixel Q10/Q50/Q90, all candidate measures,
whole-stone references, source index, support and upstream validity.

## Four-stone benchmark

Use the canonical release source bundles already indexed by
`docs/360/benchmark/source-bundles.json`. Extract them under a certificate-keyed
source root exactly as documented in `docs/360/benchmark/README.md`, then run:

```bash
python -m diamond360.articulation_benchmark \
  docs/360/benchmark/benchmark.json \
  --source-root outputs/benchmark-sources \
  --output /tmp/inner-articulation
```

After #49 is available locally, include its summary for the sibling redundancy
check:

```bash
python -m diamond360.articulation_benchmark \
  docs/360/benchmark/benchmark.json \
  --source-root outputs/benchmark-sources \
  --output /tmp/inner-articulation \
  --tier-contrast-summary docs/360/tier-contrast/summary.json
```

The runner:

1. preprocesses each complete canonical source at fixed gain 1.0 with explicit
   review-frame acceptance, preserving upstream QC;
2. measures both the 17-frame core and 33-frame wide windows;
3. writes per-stone JSON/CSV plus original/registered source-frame evidence;
4. compares core/wide stability;
5. compares core raw Q10/Q50/Q90 against retained inner activation, occupancy
   and mobility from the #45 profile;
6. optionally compares the same summaries against both #49 adjacent-tier pairs;
7. pulls the three #22 pale-inner observations and the LG818659722 grouped-dark
   control into the benchmark summary.

## Synthetic falsification tests

The unit tests require:

- flat inner support to produce zero spread;
- equal-median regions with different tonal structure to separate;
- raw spread to scale with a uniform brightness multiplier;
- normalized/log variants to remain invariant under that multiplier;
- gaps to remain gaps rather than being interpolated;
- the matched-brightness evidence pair to prioritize brightness similarity;
- upstream `review` validity never to be upgraded.

## Disposition rule

Do **not** promote this descriptor to #23 or the retained #45 feature contract
merely because the implementation exists.

KEEP only if the canonical source evidence shows that low articulation
repeatedly corresponds to the pale/flat/quiet-inner observations, survives
normalization, and adds information beyond #26/#27/#30 and #49.

Otherwise REVISE the spatial primitive or REJECT it.

The benchmark writer therefore emits
`PENDING_SOURCE_EVIDENCE_REVIEW` until the source-frame evidence has actually
been inspected. No quality direction, leakage claim or four-stone threshold is
encoded.
