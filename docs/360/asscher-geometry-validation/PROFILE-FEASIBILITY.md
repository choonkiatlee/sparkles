# #91 PR A — target-blind Asscher profile-image feasibility

## Purpose and boundaries

The 410 × 319 original post-151 PriceScope profile photograph is a separate
**profile-view** geometric-evidence problem from the frozen #75 **crown-view**
image-plane semantic scaffold. The PR A utility is an *image-only diagnostic*.
It must not (a) infer physical facet angles, (b) assign P1/P2/P3/C1 family
identities, (c) load expert targets, (d) promote projected facet lengths to
physical lengths, or (e) modify the #75/#88 contracts.

The original full-attachment bytes are pinned as:

- Path: \`docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG\`
- Image: 410 × 319 JPEG
- SHA-256: \`0d0d87dfd9d4090dc21d03173b9260abe00556b40c6df05e19fad310fa0bd3a3\`
- Provenance: recovered authenticated full attachment from post 151, via #77
- Attribution caveat: the thread context associates post 151 with the post-156
  photo estimate; post 156 does not explicitly name the source photograph

The 300-pixel inline preview must not replace this archived input.

## Diagnostic specification: diamond360-asscher-profile-feasibility/1

Implementation: \`diamond360.asscher_profile_feasibility\`.

Inputs: a single RGB-decodable image and optional expected SHA-256. The CLI
supports \`--require-original\`, which hard-fails if the SHA-256 does not match
the archived full attachment. The algorithm is deterministic and does not
access any other files.

- Pixel coordinates: origin at upper-left; +x rightward, +y downward.
- Grayscale: encoded RGB luminance weights 0.2126/0.7152/0.0722.
- Edge evidence: grayscale Gaussian smoothing (σ=1.1 px), Sobel derivative,
  gradient magnitude and top 6% edgels within a 7%-margin image ROI.
- Generic candidates: weighted-gradient Hough transform, unoriented
  line inclination from -75° to +75° in 3° steps (positive slopes toward +y),
  normal offset in 1-pixel bins, up to fourteen separated candidates.
- All generic line angles are *image-coordinate inclinations*, not diamond
  facet angles. No estimate from this stage is named P1/P2/P3/C1.
- The reported edge-activity bounding rectangle is a *quantile of edgels*,
  **not** a verified outer diamond silhouette. It must not be treated as an
  outline fit or evidence of table/girdle/culet localization.
- Table, girdle, outline, culet and projection suitability remain
  \`not_assessed\` until their semantic evidence can be independently checked.
- A source with no usable edge evidence is \`unavailable\`, never \`ok\`.
  Other sources are \`review\` until semantic identity and projection criteria
  have been investigated.

This policy is serialized verbatim plus its canonical JSON SHA-256 in every
result. If changed after comparing with Sergey, it constitutes a new method
revision and cannot replace this frozen PR A output.

## Future PR B measurement contract (frozen definitions, not yet estimates)

A future semantic extractor must produce separate records for:

\`\`\`text
left.P1  left.P2  left.P3  left.C1
right.P1 right.P2 right.P3 right.C1
\`\`\`

Each record should retain:

- observation status: \`observed\`, \`model_inferred\`, \`ambiguous\` or
  \`unavailable\`; never imply direct observation for a symmetry prior;
- ordered image-line segment endpoints and supporting pixel coordinates/weights,
  plus candidate and source-image provenance;
- fitted image-line inclination relative to a **measured table-horizontal
  reference** and the direction/sign convention;
- when projection requirements can be defended, the separately labeled
  inferred physical angle, with assumptions and uncertainty; otherwise null;
- confidence/effective support, residuals and a predeclared uncertainty method
  (for example resampling independently supported edgels or endpoint jitter);
- explicit missing/ambiguous/poor-view reasons.

The PR A JSON includes all eight slots with \`status=unavailable\`,
\`provenance=not_measured_pr_a\` and null angle/uncertainty. This prevents
a later consumer from accidentally mistaking generic Hough lines for physical
facet measurements.

### Geometry / suitability conditions to evaluate in PR B

1. Detect the table plane and check whether it is sufficiently level to serve
   as the angle reference; never rotate until the reference is identified.
2. Distinguish an outer silhouette from overlapping internal optical contrast.
3. Identify the girdle and culet region, and the ordered step-line support
   for P1/P2/P3 and C1 **independently on both sides**.
4. Detect or flag visible pavilion side facets / strong projection / tilt;
   do not assign confident physical angles to such images.
5. Preserve actual left/right asymmetry. Do not enforce exact mirror equality.
6. Never interpret apparent image-plane P1/P2 facet lengths as physical lengths.
7. If the evidence does not distinguish a named line family, mark it ambiguous
   or unavailable rather than selecting the line nearest an expected angle.

## Anti-leakage / comparison gate

\`diamond360.asscher_profile_feasibility\` accepts only an image path and
an optional image SHA guard; it cannot accept or read \`ground-truth.json\`.
The future PR B extractor must retain this isolation. Save and fingerprint
the complete target-blind extraction record **before** PR C's comparator reads
Sergey's \`photo_estimate\` values from the fixture's
\`ground-truth.json\`. The comparator must not call back into fitting or
change source selection, ROIs or thresholds based on target disagreement.

Sergey's estimates are independent *image-derived* comparison evidence, not
direct physical measurement. DiaGem's manual reports are separate evidence.
This stage does not validate a full 3D model or #75's crown-view scaffold.

## Outputs and reproducibility

Run from the repository root:

\`\`\`bash
python -m diamond360.asscher_profile_feasibility \
  --image docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG \
  --require-original \
  --output outputs/asscher-profile-feasibility
\`\`\`

Outputs (generated in CI, not committed to git):

- \`profile-feasibility.json\`: image/hash/policy, image-only candidates,
  fail-closed anatomical status, eight explicitly unavailable semantic slots
- \`gradient-evidence.png\`: display-scaled gradient magnitude for audit
- \`unassigned-line-candidates.png\`: source image with generic Hough-line
  proposals (red) and edge-activity bbox (green)

The overlay deliberately has no P1/P2/P3/C1 labels. Reviewers must inspect
the image before asserting that these lines correspond to facets. The
test suite checks a blank source, deterministic candidate output, source
hash enforcement, pixel clipping, archived image identity and eight
unmeasured semantic slots.

## PR A evaluation / handoff

PR A can be merged if the diagnostic is reproducible, accurately labels
generic evidence without claiming physical/semantic geometry, and provides
an image artifact allowing a reviewer to assess whether true profile
boundaries are distinguishable. **It need not and must not match expert angles.**

Before PR B starts, inspect the visual artifacts, record which anatomical
landmarks can be distinguished from reflection boundaries, and decide
whether pure automation can realistically recover all eight families.
Anything ambiguous should remain unavailable. The post-162 rejected image
(rejected in post 163) can be recovered in parallel, as PR C's negative
control; it must not be replaced by an unauthenticated screenshot.
