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
