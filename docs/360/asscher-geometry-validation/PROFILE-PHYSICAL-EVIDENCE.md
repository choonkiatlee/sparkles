# #91 PR B1: separate physical from optical/virtual-facet evidence

## Why this correction matters

The step-cut profile photograph is an optical rendering of a transparent
solid, **not a drawing of all polished facet boundaries**. Bright/dark lines
can be reflections, refractions, apparent virtual facets, displaced images of
real junctions, image compression, shadows or background detail. Strong
straight image gradients from PR A are *appearance observations*, not
inherently physical P1/P2/P3/C1 edges.

The user's review of PR A flagged this category error before writing an
extractor. **PR B is therefore silhouette/physical-correspondence-first**, not
Hough-line-to-facet mapping.

## Stage B1: a provenance and gating contract

Module: \`diamond360.asscher_profile_physical_evidence\`
Schema: \`diamond360-asscher-profile-physical-evidence/1\`

This is the **first increment** of PR B, not a completed angle extractor.

- Uses only the image and target-blind PR A diagnostic.
- Retains all generic gradient-supported line segments as
  \`unclassified_image_edge\`, \`physical_measurement_eligible=false\`,
  with **no** named semantic facet.
- Reserves explicit unavailable slots for table-left/table-right,
  girdle-left/girdle-right and culet image landmarks.
- Reserves a list for independently traced, auditable image-coordinate
  boundary annotations, with distinct classes:
  \`external_silhouette_candidate\`,
  \`visible_surface_junction_candidate\`,
  \`table_edge_candidate\`, \`girdle_edge_candidate\`,
  \`culet_candidate\`, \`optical_contrast_only\`,
  \`ambiguous_or_occluded\`, \`unclassified_image_edge\`.
- Requires an explicit source-image manual trace and reviewer notes
  for physical-candidate claims. This is a *corroborated hypothesis*,
  not a proof that the segment is a polished facet junction.
- Optical and ambiguous annotations cannot be marked eligible for
  physical-angle measurement.
- Does not let any annotation, including an independently traced
  external silhouette, acquire a P1/P2/P3/C1 label at this stage.
- Keeps all eight semantic angle slots unavailable until a later
  independent projection/geometry check validates physical correspondence.
- Never loads \`ground-truth.json\`, Sergey values or comparisons.

This intentionally rejects the tempting shortcut of assigning an optical
line a physical facet name because it sits at a plausible position or slope.
The policy is serialized and hashed; once a later extractor is validated,
freeze its output before PR C performs any expert comparison.

## What can and cannot be measured from one profile

In a good side view, portions of **external silhouette, table edge, girdle**
and potentially some real surface junctions may be independently identifiable.
But other internal step lines are not necessarily geometrically located.
A single transparent, potentially tilted and uncalibrated photograph may
lack the evidence to distinguish individual pavilion physical planes from
their optical images. If so, declaring P1/P2/P3 unavailable is the correct
research conclusion. Even the exterior projected line direction is an
**apparent image-plane inclination**, not automatically a true dihedral angle.

PR B2 should first perform an explicit exterior silhouette/source-background
segmentation and establish table/girdle/culet support without trusting
interior reflection gradients. Only then attempt semantic facet-family
identification where an independent physical interpretation is defensible.

Any uncertain real-vs-virtual line may need *manual adjudication*. Reviewers
must annotate without reading numerical Sergey targets; source-image
visual corroboration is permitted, nearest-target-angle assignment is not.

## Adversarial invariant

Synthetic tests add strong interior horizontal and diagonal appearance bands
while preserving the underlying exterior physical silhouette. These bands
may affect generic line candidates, but **cannot create semantic facet
observations or change a physical angle**. Tests also reject promoting
automated generic lines directly to physical geometry, forged target loading,
undocumented physical-boundary claims and assigning semantic facet IDs
during B1.

## Run

\`\`\`bash
python -m unittest tests.test_asscher_profile_physical_evidence -v

python -m diamond360.asscher_profile_physical_evidence \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --require-original \
  --output outputs/asscher-profile-physical-evidence/review-template.json
\`\`\`

The generated JSON **does not** contain physical-angle estimates or expert
targets. The original 410×319 JPEG and exact SHA-256 are checked by
\`--require-original\`.

## Remaining PR B work before extracting physical geometry

1. Produce image-only explicit segmentation of the real external outline;
   mark uncertain/glare/background regions as unsupported rather than
   inventing contours.
2. Identify a table level and girdle anchor, and test projection conditions;
   reject or downweight visible pavilion side facets.
3. Where a true physical surface junction can actually be identified,
   correlate a supported segment to source geometry, with annotation
   provenance, uncertainty and independent left/right adjudication.
4. Estimate **apparent** line inclinations from verified physical segments,
   preserving table-reference and camera assumptions; no auto-filled slots.
5. Build additional synthetic negative controls for virtual features,
   occlusion, tilt, reflection, and alternative illumination.
6. Freeze results before PR C reads independent image-derived Sergey targets.

Non-goals: using internal contrast as geometry, universal 3D reconstruction,
physical length inference from projected facet widths, or quality scoring.


## B2 — independent background-separated exterior contour proposals

Module: \`diamond360.asscher_profile_outer_contour\`, schema
\`diamond360-asscher-profile-outer-contour/1\`.

The purpose of this increment is to establish whether the **outer projected
silhouette** can be traced from the uniform background without consulting
interior step/virtual-facet edges. It is not a geometry-to-physical-angle fit.

**Mechanism:** estimate the encoded-RGB background from two small upper corner
patches; Gaussian-smooth the RGB image; segment pixels distinct from that
background at three fixed RGB-distance thresholds; close tiny breaks and take
the largest connected foreground component with holes filled. Only the
predeclared upper/main image region is processed. The low/shadow band is
excluded. At every source-image row, report left/right silhouette candidates
separately from three threshold runs. Rows with missing evidence, border bleed
or a cross-threshold endpoint spread over 8 pixels are downgraded to
\`review\` / \`unavailable\`, never silently averaged into a precise contour.
The background itself is rejected if reference patches are inconsistent.

**Two image-only proposals** are emitted:

- \`upper_profile_width_region\`: a narrow upper outer width region; **not
  automatically the polished table**.
- \`widest_cross_threshold_stable_region\`: the widest stable contour region; **not
  automatically the girdle plane**.

The proposed silhouette is only a *projection*. Even when its outline is
well separated from background, a photograph does not directly determine
which polished side-facet plane produced a given apparent segment. Table,
girdle and culet remain \`unavailable\` pending independent verification.
All eight named facet-angle slots remain \`unavailable\`, with no virtual
edges used in geometry estimation.

### Adversarial falsification gate

On synthetic profiles, changing numerous strong internal horizontal/diagonal
virtual-looking lines without changing the exterior must leave contour
coordinates essentially unchanged. Blank sources fail closed. Tested tilted
and partially occluded images must not imply physical angles or accepted
camera projection. This proves a **specific algorithmic isolation property**,
not source-level accuracy on an actual refractive diamond.

Generate QC:

\`\`\`bash
python -m unittest tests.test_asscher_profile_outer_contour -v
python -m diamond360.asscher_profile_outer_contour \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --require-original \
  --output outputs/asscher-profile-outer-contour
\`\`\`

Produces \`outer-contour.json\` and \`outer-contour-candidates.png\`.
Green contour points mean cross-threshold stable *candidates*; orange points
mean threshold-sensitive rows; blue rectangles are broad image-only regions.
All are proposals, not accepted anatomical boundaries. Inspect these on the
original photo before attempting to fit named P1/P2/P3/C1.

**Limitations:** a bright/transparent outer edge may resemble the background,
and table/wing reflections may touch the actual silhouette. Largest-component
segmentation can therefore miss or absorb source detail; uncertainty is
exposed with multi-threshold support but cannot make a wrong silhouette true.
A human reviewer should explicitly assess each outer interval and reject
unsupported regions. Changing this fixed policy after seeing expert targets
would require a new declared method revision.


### Original photo result — fixed B2 algorithm, 2026-10-08

Workflow [37757795235](https://github.com/choonkiatlee/sparkles/actions/runs/37757795235) completed successfully. The archived JPEG hash matched; all focused synthetic/integration tests passed. The original-photo output is intentionally **unavailable**, not \`ok\` or a physical-facet fit:

- 207 source rows evaluated; 46 stable contour rows, 97 threshold-sensitive rows, remainder unavailable.
- Relatively stable outer-rim candidates exist near the tip/upper crown, for example at y=75 x≈173–242 and y=85 x≈160–250.
- Lower sides are unstable, e.g. y=200 candidate x≈45–362 varies by as much as 70 pixels across the predeclared background thresholds; rows near y=210–245 fail the contour-QC width/background checks.
- Thus the widest *stable* supported row (around y=174–176) does **not** mark the true widest stone/girdle region; do not promote the blue QC rectangle to a girdle measurement.
- \`table\`, \`girdle\`, \`culet\`, projection suitability, and P1/P2/P3/C1 family identities remain unverified/unavailable.

**Visual verdict:** the contour proposal tracks parts of the real outer wing more usefully than the earlier internal-band Hough overlay, but insufficient consistent evidence survives around the projected girdle and lower pavilion. No numerical pavilion-angle experiment should proceed using these raw contours as certified physical boundaries. Next work must involve explicit independent outline corroboration (potentially assisted) and a projection/suitability assessment, not adjusting background thresholds to force a prettier fit.

This photo-derived verdict is independent of Sergey's stored angle targets.


## B2b — human-assisted anatomical source review (not physical truth)

Rather than guessing that internal virtual facets correspond to polished planes,
this stage presents seven broad source-image ROIs on the full **original**
410×319 profile and asks a reviewer to decide what is actually observable:

| Region | Question, not an automatic feature label |
|---|---|
| A | Upper central bright edge — is an external table edge genuinely visible? |
| B/C | Left/right upper outer silhouettes, separately |
| D/E | Left/right widest projected profile — possible girdle-region evidence |
| F | Lower pavilion/culet vicinity — can the exterior be separated from shadow? |
| G | Interior horizontal/diagonal band **negative control** — optical contrast, not automatically a physical junction |

All proposal boxes are intentionally broad, pre-authored using **image-only
visual inspection**, with \`proposed_by=assistant_visual_image_only\`,
\`reviewer_verdict=unreviewed\` and null facet identity. They are **not**
a hand-traced physical geometry ground truth.

Module: \`diamond360.asscher_profile_assisted_review\`, schema
\`diamond360-asscher-profile-assisted-review/1\`. The tool validates the
archived original file's exact SHA-256, produces a numbered overlay
(\`assisted-review-regions.png\`) and a standalone offline mobile-friendly
\`assisted-review.html\` with the full photo embedded. No authentication,
network dependency, third-party JavaScript, model prediction or target-angle
JSON is used.

A reviewer can select an ROI, assign \`likely_external_contour\`,
\`possible_table_edge\`, \`possible_girdle_edge\`,
\`optical_appearance_only\`, \`ambiguous\` or \`not_visible\`; provide
reasoning; and optionally tap 2-40 points in the original source coordinate
system for *tentative* physical-region candidates. Taps remain inside
the chosen ROI. The HTML exports a compact source-hashed reviewer JSON,
which can be validated and merged into the untouched worksheet via:

\`\`\`bash
python -m diamond360.asscher_profile_assisted_review \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --output outputs/asscher-profile-physical-evidence \
  --review path/to/profile-human-review.json
\`\`\`

No reviewer assertion, however confident, becomes a certified physical facet
or automatically yields P1/P2/P3/C1 angles. The validator rejects attempts to
mark the internal negative-control region G as exterior contour, rejects
out-of-ROI traces, altered source identity, missing notes and any externally
loaded targets. This preserves the provenance distinction between
\`assistant_visual_image_only\` suggestions and
\`image_only_reviewer_assessment\`. A future independent geometric model or
more views are still required to establish actual physical facet families.

**Next handoff:** inspect the numbered original overlay, explicitly review
at least the outer regions B/C and ambiguous lower regions D/E/F, and return
the export JSON or written verdicts. Only after the evidence is reviewed should
we attempt angle extraction; ambiguous optical bands should stay excluded.


## B2c — trace outer contours first, then find change points

The profile silhouette should carry substantially more weight than interior
virtual-facet/brightness lines. The fitting problem is separated into two
auditable stages, and interior-feature analysis is now a *different issue*:
[#123](https://github.com/choonkiatlee/sparkles/issues/123).

### Stage 1: explicitly traced left/right external profiles

Use \`asscher_profile_outline_changepoints\`'s standalone
\`exterior-tracer.html\`, which embeds the hash-pinned **original** source.
A reviewer traces **separate** ordered image-only point sequences:

- \`left_crown\`, \`right_crown\`;
- \`left_pavilion\`, \`right_pavilion\`.

Annotate only external stone/background contours supported by the source, with
a reason and \`reviewed_image_only\` provenance. Empty strokes remain
\`unavailable\`; ambiguous/hidden portions should not be bridged across.
The tracing tool has no interior gradient proposals, P1/P2/P3/C1 labels,
expert estimates or assumed three-step break locations.

The exported JSON is \`diamond360-asscher-exterior-traces/1\`: exact source
SHA-256, original pixel coordinates, four independent stroke slots and
reviewer notes. The parser rejects non-finite/off-image points, wrong
left/right side, non-increasing y, extra (possibly target-bearing) input
fields or unreviewed traces. It is a candidate appearance-of-the-outline
record, not a validated 3-D physical angle.

### Stage 2: parsimonious piecewise contour and changepoints

\`diamond360-asscher-exterior-changepoints/1\` uses the reviewed source
coordinates alone. It fits independent left/right crown/pavilion strokes
with orthogonal total-least-squares straight segments and predeclared
penalized dynamic programming. The hard cap is **three straight segments per
side/region** (two internal breakpoints); fewer or none are valid. The first
pass fixes an additional-segment penalty of 40 pixel² and requires at least
six supported points across a minimum 12-pixel y-span per segment. It records
the raw source endpoints, orthogonal residual, apparent image-plane tangent,
candidate change-point coordinates and a runner-up model cost.

The presence of **three physical pavilion tiers** is a *topological upper
bound*, NOT three guaranteed visible profile lines and definitely not three
guaranteed observed facets in this projection. In an oblique view a
silhouette is an *envelope* of facets; a change in the projected extremal
boundary need not equal the junction of adjacent pavilion facets. Treat
the fitted segments and bends as exploratory external-profile hypotheses
until camera/projection and facet identity are independently corroborated.

The reported model-selection cost margin is **not a calibrated confidence
interval**. Uncertainty from tracing, occlusion, and projection remains a
future requirement; we are not using this initial model to claim precise
P1/P2/P3 angles.

### Falsification and usage

Focused synthetic tests cover one, two and three identifiable slope segments,
smooth profiles without genuine changepoints, left/right asymmetry, source
pinning and null physical-angle outputs. The fitting API accepts only
reviewed external point traces—not image intensity, Hough peaks or a file of
expert angle targets. This proves a deliberate separation of inputs; it does
not yet demonstrate that the actual DiaGem profile has three distinguishable
physical pavilion slopes.

Generate the original-photo trace worksheet and an empty, auditable
pre-review changepoint result:

\`\`\`bash
python -m diamond360.asscher_profile_outline_changepoints \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --output outputs/asscher-profile-physical-evidence
\`\`\`

Open the generated \`exterior-tracer.html\` in a browser and export
\`exterior-traces.json\` after tracing *only the supported outside edges*. To
fit the **reviewed image-only traces**:

\`\`\`bash
python -m diamond360.asscher_profile_outline_changepoints \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --traces path/to/exterior-traces.json \
  --output outputs/asscher-profile-reviewed-traces
\`\`\`

The resulting \`exterior-changepoints-overlay.png\` shows the independently
traced contour paths and any image-slope change-point candidates. This
does **not** change the frozen #75 Asscher geometry estimator, consume
DiaGem/Sergey angle targets, or declare physical facet-angle estimates.
If the photograph cannot support a segment, \`unavailable\` is the
appropriate result.


## B2d — automatic exterior proposals, independently of internal virtual facets

The user cannot conveniently hand-trace the source. An *automatic,
review-first* silhouette proposer therefore precedes human adjudication.

Implementation: \`diamond360.asscher_profile_auto_exterior\`, schema
\`diamond360-asscher-auto-exterior/1\`. Source usage: exact original JPEG
sha-pinned by \`--require-original\`. **This is a prototype for this
standardized, approximately centered profile framing**; it is not a generic
view-independent, physically calibrated Asscher renderer.

### Algorithm and provenance

- Smooth the original RGB photo; estimate **row-dependent background**
  from image margins, rather than treating every outside pixel as the same
  RGB constant.
- For left/right crown and pavilion independently, search a broad corridor
  around a weak, normalized kite-shaped profile prior (top, widest equatorial
  zone, narrowing lower pavilion). The prior only initializes a corridor;
  it is not a polished-facet angle or accepted geometry. Its normalized
  anchor fractions and every penalty/threshold are explicitly frozen in
  the serialized output policy.
- Score *outside-to-inside* RGB background separation and local cross-edge
  contrast; prefer a continuous source-image path via dynamic programming
  and a moderate tangent/slope-change penalty.
- Repeat the search with three predeclared optical-evidence weightings.
  For each source pixel row, retain actual suggested xy position,
  cross-gradient strength, inside/outside separation, and disagreement among
  the model variants.
- **Green** overlay spans are \`edge_supported_candidate\` with sufficient
  local evidence and cross-variant stability. **Orange** spans are
  \`weak_or_ambiguous\`: those coordinates may be prior-guided extrapolation,
  virtual/overlapping feature contamination or an unsupported edge.
  All paths, even green ones, are unverified hypotheses.
- Optional initial change-point fits operate only on contiguous *supported*
  source-image runs, without filling weak gaps. These retain null semantic
  facet IDs, exploratory image-plane tangent directions and raw support
  residuals. A three-tier pavilion acts only as the upper bound on how many
  straight stretches could be distinguishable, **not an enforced three-facet
  fit**.

The fitter receives NO PR A Hough peaks, internal brightness-band labels,
human-derived angles or \`ground-truth.json\`. Dedicated adversarial tests
modify bright horizontal/diagonal internal bands while leaving the true
exterior unchanged; proposed contour coordinates must remain unchanged.
Blank photos are explicitly unavailable even if the path prior generates
a mathematical curve.

### Evaluate and falsify on the original

\`\`\`bash
python -m unittest tests.test_asscher_profile_auto_exterior -v
python -m diamond360.asscher_profile_auto_exterior \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --require-original \
  --output outputs/asscher-profile-auto-exterior
\`\`\`

Inspect:

- \`auto-exterior-overlay.png\`: direct source photo with strong vs weak
  automatic outside-contour suggestions, separately for crown/pavilion.
- \`auto-exterior.json\`: every per-row xy point, evidence, variant spread,
  support status and only **exploratory** supported-run changepoints.

The source photograph's lower pavilion blends into the platform/shadow;
**do not infer its true culet** from the normalized image prior.
Green does not prove physical facet junctions or calibrated 3-D angle.
Human visual validation can use the generated overlay as a reference without
requiring them to draw the entire contour. If a region is visibly off-outline,
reject it and record the uncertainty rather than adjusting policy to agree
with Sergey's target angles. A versioned future iteration may improve
contour extraction on an independent validation set.

Original profile "edge support fraction" is a *detector-side evidence rate*,
not a segmentation precision/recall or a confidence probability. Comparing
variants only explores three predetermined photometric assumptions; it does
not cover all true source uncertainty or camera projection ambiguity.

The separate interior virtual-facet research is #123. The photographed
physical pavilion plane identifiers and all eight P1/P2/P3/C1 physical
angles remain unavailable until independently supported.


## B2d v2 correction — outside/background contact is the objective

The first automated proposer (\`auto-exterior/1\`) was **rejected on visual
inspection**: despite its continuity regularizer, maximizing local contrast
selected bright **interior** virtual-face boundaries rather than the much
fainter actual stone/background boundary on the upper crown. **Do not use v1
results for physical geometry, landmarks or changepoints.**

The revised \`diamond360-asscher-auto-exterior/2\` makes a different,
fundamental observation:

- Model the nearly constant RGB background using samples taken at the **left
  and right outer image borders in each row**. No internal/central face
  pixels are used to establish the background reference.
- From each side's outside image border, scan *inwards* until the **first
  persistent deviation** from background is found (at least 5 of the
  following 7 pixels exceed a predeclared RGB separation). This criterion
  does not reward the strongest or brightest inner face.
- Compare low/moderate contact thresholds 7/9/12 RGB units, preserve the
  first-contact coordinates and threshold disagreement on each source row,
  and median-filter **only across five neighboring image rows** for minor
  JPEG noise. No 3D/pavilion-angle target or rigid polygon attracts the
  trace inward.
- If a threshold misses a faint real edge and snaps to the bright interior,
  the difference is exposed as an **uncertain** contour span, rather than
  silently declaring that interior line physical.
- The lower platform/shadow region is excluded from automatic *supported*
  points regardless of algorithmically proposed coordinates, and the
  provisional y≈212 crown/pavilion phase split is not a verified girdle.

Added adversarial regression: draw a faint outer silhouette, then a much
brighter internal virtual face on top. **The external path must remain
unchanged.** Photo-only sanity checks require the y=100/y=160 proposed
crown outline to remain outside the obvious central table boundaries.
Synthetic internal stripes, blank images and original-source hash guards
remain in CI.

The photo-derived outward-first proposal and its green/orange support overlay
still require independent review, especially near the lower pavilion. A
background-first contour is more plausible physical evidence than a
brightness-maximizing Hough line, but it is **not** proof that every edge is
the correct 3D silhouette or that it corresponds to a specific P1/P2/P3 plane.
The internal/virtual optical problem remains tracked separately in #123.


## B2e — full-contour changepoints rather than per-fragment lines

The first image-plane overlay on the corrected background-first v2 silhouette
failed to find most expected visual bends despite a much more credible outer
trace. Root cause: the original \`asscher_profile_outline_changepoints\`
function was called *separately for each uninterrupted supported pixel run*.
Short 1–5-pixel quality-control gaps fragmented each crown into four separate
regressions; a typical run was too short to justify more than one line.
It also used a fixed y≈212 split to represent crown/pavilion, before the
outer girdle region had been localized.

The new **independent** module
\`diamond360.asscher_profile_auto_changepoints\` consumes only frozen
\`diamond360-asscher-auto-exterior/2\` source coordinates and a pinned method
SHA-256, not any optical internal edge, Sergey target angle or inferred
physical facet label. Earlier assisted human-review and manual trace APIs
are unchanged.

- Combine **all supported rows** separately on the left and right, keeping
  missing spans absent rather than filling them with guesses.
- Jointly find a *band* of near-maximum projected width where both external
  contours are supported. Its actual y interval is an observed envelope
  candidate, **not a certified girdle physical junction or a forced symmetry
  rule**. An unavailable band blocks subsequent semantic inference.
- Fit crown and pavilion independently, excluding the widest band, with a
  **continuous piecewise-linear hinge function** \(x(y)\), not independent
  unconnected lines. The fitting cap is three supported straight stretches
  per crown/pavilion side, but 1/2/unavailable outcomes are allowed.
- Minimum span, source sample count, and model-complexity penalty are fixed
  before comparison with any targets. No \`ground-truth.json\` reading.
- Rerun model selection at four predetermined additional-segment penalties
  to expose which breakpoint candidates disappear when the parsimony cost
  changes. These are **stability diagnostics**, NOT posterior probabilities
  or calibrated measurement intervals. Left/right choices remain independent.
- Draw supported original contour and inferred continuous line fits only
  between nearby *actual* observed source rows; no overlay across long
  missing-image intervals.

Example on the one archived original photo (image-only coordinates, **not**
polished angles): a shared widest region around y≈201–221; crown slope-change
candidates around left y≈80/132 and right y≈80/118; a model-dependent right
pavilion bend around y≈246. These locations are only visual hypotheses.
The latter and the right crown model are sensitive to complexity penalty.
The lower pavilion and shadow/culet are still weakly observed; their physical
facet-plane attribution remains unsupported.

**Important:** The fact that a piecewise straight line can follow the outer
profile does not prove it is a specific polished pavilion facet. A profile
silhouette is the projected extremal envelope of a 3-D faceted stone and may
switch generators with camera pose or obscure physical tiers. In particular,
it is not valid to label those bends P1/P2/P3 or compare numerical slopes
against Sergey before the target-blind geometry output is frozen and a camera
model is assessed. No change is made to the #75 face-up frozen method.

Run the new experiment after source-hash-pinned v2 contour generation:

\`\`\`bash
python -m diamond360.asscher_profile_auto_changepoints \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --auto-json outputs/asscher-profile-physical-evidence/auto-exterior.json \
  --output outputs/asscher-profile-physical-evidence
\`\`\`

Inspect \`joint-changepoints-overlay.png\` and \`joint-changepoints.json\`
from the focused CI artifact. Yellow dots indicate candidates surviving
all four penalty variants; orange dots indicate model-sensitive candidates.
The two amber horizontal lines delimit the **candidate** maximum-width band.

Dedicated synthetic regression checks include 1/2/3 visible straight
stretches, small missing-evidence gaps, an unavailable one-sided contour,
an internal-reflection negative control and the source-locked original.
This is an image-only change-point feasibility experiment, not a scored
reconstruction of the diamond's physical three-tier facet model.


## B2f — missed table cap and last pavilion change: separate endpoint detector

Human feedback on the improved joint fit: outer crown and pavilion lines now
mostly follow the stone, but the tiny **top table cap** and the **last lower
pavilion change** were missing on both sides. These are two *different
observability failures* from the middle-profile line fit:

1. The old automatic exterior ROI began at y≈60 while the real source's
   tiny topmost horizontal-ish exterior ridge is around y≈54–55.
2. The pavilion trace stopped at y≈276 even though some source-background
   evidence survives further down, before the platform shadow overwhelms it.
   Consequently the last slope transition had insufficient lower support for
   a two-segment model.

The new module \`asscher_profile_endpoint_candidates\`, schema
\`diamond360-asscher-profile-endpoints/1\`, is additive. It does not retune
already supported middle-crown or first pavilion changepoints.

**Top endpoint:** First sustained foreground contact from *above*, for
each central source-image column, under three fixed background thresholds.
A top cap is only proposed when at least five consecutive columns support
an approximately level ridge, with threshold disagreement ≤2 pixels. This
locates the outside apex/cap instead of promoting the very dark horizontal
*internal* reflection below it to a table.

**Bottom endpoint:** Extend the independently supported left and right
pavilion contours locally/inward over a short additional range, using
foreground/background separation and limited step length. Exit rather than
force a bottom trace when the outside region becomes shadow-contaminated.
For sufficiently supported terminal extensions, compare one versus two
continuous pavilion slopes with an independently fixed improvement rule,
minimum endpoint support and a penalty-stability test. The left/right
candidates are deliberately independent; a possible terminal bend on one
side is **not reflected across** as a manufactured bend on the other.

**Crucial anatomical caveat:** The detected short top cap has not been
certified as the physical polished table. Likewise a projected slope
change in the lower exterior does not prove a polished P1/P2/P3 facet junction.
All eight physical facet-angle measurements remain unavailable, and the
independent Sergey comparison still belongs in PR C.

The focused CI runs image-only synthetic/reflection controls, blank-image
tests, source-hash/method-version checks, and emits
\`endpoint-candidates.json\` and \`endpoint-review-overlay.png\`
composited over the previous joint-fit image. Green lower points are
supported *candidates*; orange points are shadow-limited. The top cap and
terminal-change proposals require source-image visual review.


## B2g — apex correction and conditional head-on mirror symmetry

Source-image review identified that the uppermost 8–9-pixel-wide
near-horizontal appearance is plausibly the rasterized **projected apex
(point-like silhouette)**, not a verified physical flat table edge. It also
must **not** be called the culet: the photo's top/bottom orientation and the
particular polishing topology must be established independently. The
existing source-y contact points are retained for backward compatibility,
but the endpoint schema now records \`projected_apex_xy_px\` and explicitly
\`physical_table_identity=not_established\` and
\`physical_culet_identity=not_established\`. The overlay renders **one**
apex marker, not two presumed physical table corners.

The user's suggested symmetric fit is useful, but only **conditionally**:

1. **Image-plane outline consistency diagnostic:** Estimate a candidate
   vertical reflection axis from *independently observed* left/right extrema
   in the broad maximum projected-width band, and compute observed paired
   crown contour midpoint offsets from that axis. Also check how far the
   projected top apex lies from that same axis. These diagnostics can **reject**
   gross asymmetry; they cannot prove the camera is head-on.
2. **Independent camera/stone assumptions:** To adopt mirror symmetry as a
   geometric model, separately record that the camera was verified to be
   approximately head-on **and** that mirror-symmetric stone geometry is a
   modeling assumption. A photograph can look approximately symmetric yet
   have tilt or genuine left/right facet-angle asymmetry. The full provenance
   and rationale belong in a source-hashed \`pose-review-template.json\`
   that the reviewer may explicitly fill. Numeric expert target angles
   are forbidden here.
3. **Missing right terminal only:** If an independent left terminal
   changepoint is observed in the image, right remains unsupported, the
   source outline's observed left/right consistency checks pass, and **both**
   independent assumptions above are explicitly confirmed, propose
   \`right_x = 2*axis_x - left_x\`, \`right_y = left_y\`.
   Output status \`conditional_symmetry_model_inferred\`, never
   \`observed\`. Preserve every actual right-side observed point and do not
   overwrite independently extracted right changepoints. If the review
   is absent, publish only a clearly marked counterfactual mirrored
   preview, **not** a replacement for the detected right outline.
4. **Asymmetric observation retained:** Preserve source-image asymmetry
   in the independently detected profiles. Mirror-model values never
   count as evidence of a polished facet junction or recovered P1/P2/P3
   physical angle, and they cannot improve validation by matching
   Sergey's external photo estimates.

Implementation: \`diamond360.asscher_profile_conditional_symmetry\`,
schema \`diamond360-asscher-conditional-profile-symmetry/1\`. It takes only
the source-hash-pinned auto-exterior v2, joint-width report and endpoint
reports, plus an **optional** explicit source-matching pose review.

To inspect the *counterfactual* without claiming a head-on determination:

\`\`\`bash
python -m diamond360.asscher_profile_conditional_symmetry \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --auto-json outputs/asscher-profile-physical-evidence/auto-exterior.json \
  --joint-json outputs/asscher-profile-physical-evidence/joint-changepoints.json \
  --endpoint-json outputs/asscher-profile-physical-evidence/endpoint-candidates.json \
  --output outputs/asscher-profile-physical-evidence
\`\`\`

The overlay draws a center-axis guide and a distinctly colored **unapplied
right-side mirror hypothesis**. Only a separate \`--pose-review\` with a
properly sourced, human-reviewed head-on assessment and an explicit
mirror-symmetric-stone modeling assumption can elevate that hypothesis to
a *conditional inferred* point. Green/bright-line agreement alone is not
pose confirmation.

The focused suite verifies no symmetric inference without both assumptions,
no overwriting an independent right-side candidate, rejection of inconsistent
observed symmetry, no expert-angle leakage, and preservation of all physical
angle unavailability. This lets us examine whether symmetry could help
recover an obscured bottom-right change without smuggling an optical prior
into the evidence.


## B2h — pavilion-focused source-data fit; crown deferred

Review feedback: the existing crown outline is close enough for now and
the **pavilion** is the most important geometric target. Do not tune
crown optical structure, retrofit facet-angle targets, or force a presumed
physical three-tier model into the observed image.

The new \`diamond360.asscher_profile_pavilion_fit\` is deliberately
additive to v2 background-first external contours, common maximum-width
band, endpoint proposals and pose-review schema. It does **not** change
any upstream crown or silhouette outputs.

**Independent pavilion evidence**: starting just below the candidate
maximum-width band, collect each side's actual source-supported outside
pixels plus *only* shadow-aware terminal-extension points that passed
source/background QC. Preserve their side, original source coordinates
and separate algorithmic provenance; do not fill occluded rows. Fit
1/2/3 *apparent* continuous silhouette slopes on each side independently,
using the already-predeclared source-only complexity penalties. Report
breakpoints, residuals and model-penalty sensitivity; no facet ID or
physical plane/dihedral angle.

**Pavilion symmetry sensitivity (separate model)**: take a reflection
axis from independently observed width-band extrema and check paired
left/right pavilion midpoint residuals. For rows with *both* observed
outer edges, fit one actual measured half-width \((x_R-x_L)/2\); for
supported left-terminal rows *after* right source support ends, use
\(a-x_L\) to generate a possible \`MODEL_ONLY_NOT_PIXEL_OBSERVED\`
right-hand position \(x_R^{model}=2a-x_L\). Thus the inferred right
extension never masquerades as an observed edge. A shared continuous
piecewise *radius* fit can be previewed even before a pose assessment,
but is **not adopted** unless both independent head-on and stone
mirror-symmetry assumptions are explicitly supplied in the source-hashed
pose review *and* crown/pavilion paired image diagnostics are compatible.
Model variants cannot override an independent right terminal candidate.
An approximate 2D mirror image alone is not proof of head-on camera pose
or symmetric physical facet angles.

**Tip/shadow QC**: terminate source-supported traces when the
background/shadow separation fails. The fitted pavilion covers the
observed extent only; \`tip_or_culet_xy_px=null\` persists if no source
evidence supports the true projected convergence. No invented symmetric
bottom tip, no invented third physical pavilion plane. The overlay crops
the pavilion only and keeps actual left/right source contours in
different solid colors and inferred right-tail points in a distinct
counterfactual color. Independently observed and model-inferred
changepoints have separate provenance. The incomplete right side must
not be treated as new ground truth.

Run after the previous automatic source-only stages:

\`\`\`bash
python -m diamond360.asscher_profile_pavilion_fit \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --auto-json outputs/asscher-profile-physical-evidence/auto-exterior.json \
  --joint-json outputs/asscher-profile-physical-evidence/joint-changepoints.json \
  --endpoint-json outputs/asscher-profile-physical-evidence/endpoint-candidates.json \
  --output outputs/asscher-profile-physical-evidence
\`\`\`

Outputs are \`pavilion-fit.json\` and \`pavilion-only-overlay.png\`.
A separate \`--pose-review\` may be passed for a *conditional modeled*
symmetric profile, but it does not alter the independently observed
left/right output or any physical angle fields.

**Falsification**: the focused tests cover independent observed versus
inferred provenance, missing right end while left survives, asymmetric
right displacement vetoing symmetry, explicit head-on plus stone
assumption for conditional adoption, retained independent right
candidate, forged/stale source/target data and a source-hash-locked,
reproducible real-photo overlay. The true stone's physical facet tiers
and optical interior remain separate tasks (#91 PR C and #123).
