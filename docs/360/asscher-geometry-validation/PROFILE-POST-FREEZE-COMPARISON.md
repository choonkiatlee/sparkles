# #91 PR C — independent post-freeze DiaGem / Sergey correspondence audit

**Conclusion at the current level of evidence: INCONCLUSIVE for
P1/P2/P3/C1 physical facet-angle correspondence.** This is an explicitly
negative/abstaining comparison, not a claim that the external photo-derived
estimates agree or disagree with the recovered silhouette.

## What the independently frozen image report actually supports

PR #118 fitted the original 410×319 DiaGem photo **before opening Sergey
angle targets** and used a background-first external contour with the
correct source orientation: pointed **pavilion at the TOP**, shorter
**crown** below the maximum-width/girdle *candidate*.

The exact frozen image-only report was uploaded by CI run
[37798814740](https://github.com/choonkiatlee/sparkles/actions/runs/37798814740),
artifact \`asscher-profile-physical-evidence/pavilion-refinement.json\`:

- Original source image SHA-256:
  \`0d0d87dfd9d4090dc21d03173b9260abe00556b40c6df05e19fad310fa0bd3a3\`.
- Frozen JSON report **byte-level SHA-256**:
  \`63bebfce1c6946c375ee79bcf81fbe56404ebeb3cc71ae860787befa6265132c\`.
- Upper pavilion LEFT: two projected outer-contour slope changes around
  \`(161.868,79)\` and \`(102.431,131)\`, present under 4/4 predeclared
  complexity penalties.
- Upper pavilion RIGHT: two projected changes around \`(251.44,79)\` and
  \`(296.59,117)\`, **model-dependent**, present under only 2/4 penalties.
- A point-like top/culet-region candidate and widest central band are
  not evidence of a polished culet facet or proven girdle plane.
- All eight *physical* P1/P2/P3/C1 angle slots remain \`unavailable\`.
  Segment slope in the image is **not** calibrated polished facet-plane
  inclination. The right-hand lower pavilion point was specifically
  highlighted as uncertain in image review, but **was not retuned**.

The frozen report's exact bytes, extraction-policy hash, original photo
SHA and upper-pavilion orientation are checked *before* reading the
independent reference. If any disagree, CI fails closed.

## Independent reference opened only after validation

The original ground-truth fixture
\`docs/360/geometry-ground-truth/diagem-2008-asscher/ground-truth.json\`
records **Sergey's photograph-based estimates** from post 156.
Their evidence class is \`photo_estimate\`, **not** physically measured
facet angles. He quotes ±1° uncertainty.

| Label | Right photo estimate | Left photo estimate |
|---|---:|---:|
| P1 | 50° | 49.5° |
| P2 | 42° | 41° |
| P3 | 31° | 30° |
| C1 | 43.5° | 46° |

**All eight numerical deltas are unavailable.** The observed outline
bends cannot, without independently verified polished-facet junctions
and a justified camera/projection model, be assigned to P1/P2/P3/C1 in
the order that would conveniently reproduce the targets. Moreover the
crown region is shadow-affected and does not establish C1.

This is a meaningful output for #76/#92: the external fixture has not
validated physical-angle recovery. Do **not** infer disagreement, error
bar calibration or accuracy from our lack of eligible measurements.

## Negative control and limitations

Sergey rejected a subsequent image (post 163) due to visible pavilion
side facets / projection effects. Its **exact original rejection-image
bytes have not been verified for this PR**, so this audit does not claim
that an original-photo unsuitable-view test has passed. The recorded
state is \`unverified_rejected_original_source_not_included\`.
A synthetic substitute must not be passed off as historical source media.

The verified external outline is useful **projected silhouette evidence**.
It is not itself a semantic reference for the **face-up crown-view #75**
scaffold, nor physical proof of every interior C3/table vertex.
The latest #124 original-RGB line/junction diagnostic also finds
straight reflected/optical features and sparse supported junctions, so
no extra geometry confidence is borrowed from those traces.

This PR does **not** modify #75, #88, #118, #149, the frozen output,
geometry templates, expert measurements or method thresholds.

## Reproduction

First regenerate the image-only output (using the same immutable pinned
original) with the already merged #118 stages:

\`\`\`bash
mkdir -p outputs/asscher-profile-physical-evidence
IMG=docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG
OUT=outputs/asscher-profile-physical-evidence
python -m diamond360.asscher_profile_auto_exterior \
  --image "$IMG" --require-original --output "$OUT"
python -m diamond360.asscher_profile_auto_changepoints \
  --image "$IMG" --auto-json "$OUT/auto-exterior.json" --output "$OUT"
python -m diamond360.asscher_profile_endpoint_candidates \
  --image "$IMG" --auto-json "$OUT/auto-exterior.json" \
  --joint-json "$OUT/joint-changepoints.json" --output "$OUT"
python -m diamond360.asscher_profile_pavilion_refinement \
  --image "$IMG" --auto-json "$OUT/auto-exterior.json" \
  --joint-json "$OUT/joint-changepoints.json" \
  --endpoint-json "$OUT/endpoint-candidates.json" --output "$OUT"

# Post-freeze stage ONLY: it cannot refit or alter the image source.
python -m diamond360.asscher_profile_external_comparison \
  --frozen-profile-json "$OUT/pavilion-refinement.json" \
  --reference-json docs/360/geometry-ground-truth/diagem-2008-asscher/ground-truth.json \
  --output "$OUT/post-freeze-comparison.json"
\`\`\`

A separately runnable focused test (also in CI) authenticates exact
artifact bytes and asserts every reference is preserved without
fabricating a corresponding angle or numerical delta. The output is
machine-readable for the eventual #92 KEEP/REVISE/REJECT synthesis.

**Research disposition:** #91's post-freeze audit is complete for the
available image-only evidence, but the *scientific question of physical
facet-angle correspondence remains unresolved*. This must be recorded
as **unavailable**, not counted as proof of agreement, and certainly
not solved by source-specific threshold fitting.
