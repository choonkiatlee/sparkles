# Within-inner tonal articulation research descriptor (#51)

This is the targeted follow-up from #22 for the recurring **pale / flat /
quiet inner-region** observation in the earlier AI-generated evaluations. It deliberately asks a different question from
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
- a brightness-matched pair whose internal articulation differs.

A pair is considered brightness-matched when whole-stone median brightness
differs by no more than 2%. Among those fixed-tolerance candidates, the selector
chooses the largest articulation gap. If no pair meets the tolerance, it falls
back to the closest-brightness pair and records that fallback explicitly. This
makes the requested counterexample genuinely test internal structure at similar
overall brightness without any per-stone tuning.

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
7. pulls the three #22 pale-inner AI-evaluation annotations and the LG818659722 grouped-dark
   control into the benchmark summary.

The #22 annotation file retains the legacy name `human-observations.json`, but those
annotations were AI-generated from the earlier Sparkles evaluations. They are not
independent human labels or perceptual ground truth.

The canonical four-stone run has been completed. Compact results are committed
as `summary.csv`; the reviewed interpretation is in `findings.md` and the
machine-readable decision is in `dispositions.json`.

## Synthetic falsification tests

The unit tests require:

- flat inner support to produce zero spread;
- equal-median regions with different tonal structure to separate;
- raw spread to scale with a uniform brightness multiplier;
- normalized/log variants to remain invariant under that multiplier;
- gaps to remain gaps rather than being interpolated;
- the matched-brightness evidence pair to maximize articulation difference within a fixed 2% brightness tolerance, with an explicit closest-pair fallback;
- upstream `review` validity never to be upgraded.

## Empirical disposition: REVISE

The simple scalar is a useful tonal-range audit primitive, but it does **not**
reliably reproduce the pale/flat/quiet-inner annotations from the earlier AI evaluations.

In particular, labelled pale-inner frames can have medium or high Q90-Q10
spread, so the statistic confounds distributed articulation with cases such as a
mostly pale inner region plus a narrow dark band. The core median ranking is
also window-sensitive, and the four-stone diagnostic shows strong redundancy
with retained inner occupancy/mobility and #49 inner-middle contrast.

For reproducing that AI-evaluation concept, the next research step should test **spatial organization / coverage**
inside the inner region rather than another global spread statistic. This is a hypothesis to test, not a human-perceptual conclusion.

The benchmark writer itself continues to emit
`PENDING_SOURCE_EVIDENCE_REVIEW` because automated measurement must not make a
quality/research-retention decision. The reviewed decision is recorded
separately in `dispositions.json`.
