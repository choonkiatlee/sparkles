# Four-stone calibration findings

These findings use the exact #45 `diamond360-descriptor-profile/1` values and
the normalized observations in `human-observations.json`. They describe what
the retained measurements currently help explain; they do **not** convert the
measurements into quality scores.

## 1. Activity / contrast movement — useful explanatory signal, not quality direction

LG818659722 is the clearest counterexample to "more activity is better". It has
the largest inner activation excursion (0.279) and inner median mobility (0.049)
in the four-stone sample, yet the human review outcome is **Reserve** because the
activity is concentrated in a broad grouped upper/lower dark state.

That makes activation/mobility useful for distinguishing **active vs quiet
recorded behaviour** and for showing that a concerning region is not simply
static/dead. They do not establish whether the resulting rhythm is attractive.
The #45 `activity_motion` redundancy grouping should remain in force.

Current disposition for #23 language: **useful descriptive/explanatory signal;
no buyer-facing high/low quality direction**.

## 2. Dark-state behaviour — strongest current explanatory family

LG818659722 has the highest inner dark occupancy (0.176), highest retained inner
dark Q90 persistence (0.353), and highest inner switching rate (0.170). Those
measurements line up with the human observation that broad inner upper/lower
sectors stay grey/dark together through nearby face-up views.

The useful distinction is not simply "dark = bad". LG756580087 has much lower
centre occupancy and no observed persistent large central blackout, while
LG818659722 combines high dark occupancy/persistence with a particular
directional grouping pattern.

Switching adds temporal evidence, but occupancy and switching share the same
relative-dark state and must not be counted as two independent votes.

Current disposition for #23 language: **occupancy + persistence can explain
persistent/grouped dark-state risk; switching is complementary temporal
evidence, not an extra quality point**.

## 3. Nested-step coordination — sign describes character

LG756580087 has strongly negative inner↔middle coordination (-0.624), matching
the human description of clean broad tiers whose adjacent layers/diagonals
change separately. LG756520111 has positive centre↔inner (0.486) and
inner↔middle (0.491) coordination, consistent with several nested/lower bands
moving together.

Crucially, LG836619414 still has a human **strength** for crisp layered tiers
despite weak/negative centre↔inner (-0.102) and inner↔middle (-0.219)
coordination. This falsifies a simple "more positive correlation = stronger hall
of mirrors" interpretation.

Current disposition for #23 language: **use correlation sign/magnitude to
describe coordinated versus alternating/independent nested motion; do not call
either sign inherently better**.

## 4. Directional organisation — pair-specific behaviour is informative

The N↔S pair gives two unusually clear calibration cases:

- LG818659722: N↔S = +0.984, matching the broad upper/lower sectors moving
  together during the grouped dark-stack behaviour.
- LG756520111: N↔S = -0.915, matching strongly opposed upper/lower temporal
  behaviour.

This is more informative than generic "symmetry" language, but the four pair
values should remain separate. A positive pair correlation can describe an
unattractive grouped dark state just as easily as an attractive balanced one.

Current disposition for #23 language: **use pair-specific directional
coordination/opposition descriptively; no aggregate symmetry score**.

## 5. Flash morphology — useful style dimension, not preference direction

LG756580087 has by far the largest median largest-component fraction (0.344),
matching the review's broad, deliberate tier/flash character. LG836619414 has
the smallest value (0.111), matching its finer mix of broad bands and smaller
rim reflections.

Both are **Shortlist** stones. That is exactly the evidence needed to avoid
turning flash broadness into a universal quality axis.

LG756520111 is also a useful caution: its static architecture is described as
broad/readable while the dynamic morphology value is relatively small (0.126).
Static tier width and dynamic connected-flash scale are related visual ideas,
not the same measurement.

Current disposition for #23 language: **broad vs fragmented/fine flash
structure is a calibrated character descriptor; preference direction remains
unestablished**.

## Recurring observations the retained profile does not explain

Two concepts recur without a defensible retained descriptor link:

1. **Pale / quiet inner panels or tiers** — explicit in LG756520111,
   LG756580087 and LG836619414.
2. **Static geometric crispness / legibility** — explicit in LG818659722 and
   LG836619414.

Tier readability is only partly explained by nested-step temporal coordination:
correlation can say whether layers move together, but not whether static tier
edges are crisp, separated and high-contrast.

### Additional descriptor recommendation

The repeated inner-panel issue is now strong enough to justify a **targeted
follow-up hypothesis**, but not another speculative metric catalogue. The next
candidate should focus narrowly on **inner-panel articulation / tier
contrast-separation/readability** and should be defined from the recurring source
examples before implementation.

Static geometric crispness is also recurrent, but it should not automatically
be merged with the inner-panel concept: one is geometric/edge legibility, the
other is tonal articulation.

Do not add either to #23 as a numeric rule until it has gone through the same
observable → measurement → evidence validation process as #26–#33.

## Counterexamples that should constrain downstream interpretation

- **High activity ≠ better:** LG818659722 is highest on several activity/dark
  reconfiguration measures and is the only current Reserve.
- **More switching ≠ better:** LG818659722 has the highest inner switching rate,
  but the visually important question is the grouped/persistent state that the
  switching occurs within.
- **Positive nested coordination ≠ better:** LG756580087 is strongly negative
  inner↔middle yet visually attractive for independently changing layers.
- **Positive opposing-region coordination ≠ symmetry quality:** LG818659722's
  +0.984 N↔S value describes the very grouped upper/lower behaviour that
  motivates its Reserve verdict.
- **Broader flash components ≠ better:** LG756580087 is broadest and
  LG836619414 finest in this sample; both are Shortlist.

## What #23 can safely consume after #21 evidence integration

The current calibration supports cautious statements such as:

- "inner regions show unusually persistent grouped dark behaviour";
- "nested tiers move mostly together" or "inner and middle tiers alternate";
- "north/south regions are strongly coordinated/opposed";
- "recorded flashes are relatively broad" or "relatively fine/fragmented";
- "activity is high/low relative to the current calibrated sample";

provided each statement links to the #21 compact source evidence and preserves
profile validity warnings.

It does **not** support excellent/good/poor thresholds, a composite score,
absolute light return/fire/leakage claims, or a universal preference direction.

## Sample requirement before numeric interpretation bands

Keep numeric bands out of #23 for now. Revisit directionality/thresholds only
after roughly **10+ well-reviewed complete sequences**, ideally with multiple
stones from each important vendor/source pipeline and enough counterexamples to
test whether observed orderings survive setup changes.
