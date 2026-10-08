# #123 — optical appearance is not physical facet geometry

## Why this boundary is needed

The original camera-RGB evidence has falsified multiple plausible-looking
interior facet fits. #140's radial C3 octagons cut through facet interiors.
#146's coherent straight-line diagnostic found no complete supported inner
octagons on 20 frozen frames; some lines follow virtual facets. #162's
two-orientation junction graph found local connected optical features but did
not resolve polished facet identity (13 optical junction candidates and two
connections across 20 frames).

These observations are useful for interpreting an Asscher's **optical
behavior**, but must not become false labels for physical C1/C2/C3, table,
P1/P2/P3 facets or geometry/angle inputs.

## Explicit read-only data lanes

`diamond360.asscher_optical_physical_provenance` is a **separate research
adapter** for the complete #146 and #162 archived JSON diagnostic outputs.
No estimator selection, segmentation, pose, or image-processing code changes.

1. **External physical evidence:** retain the frozen #96 **observed outer
   silhouette** as a measured external boundary and the unchanged sequence
   gauge. No assumption of calibrated 3-D reconstruction.
2. **Interior optical appearance:** store source frame indices, original
   directly observed line segment endpoints, eight-side *orientation
   family*, gradient coverage, and graph-linked junction candidates as
   `image_plane_optical_contrast_candidate`. Every row explicitly says
   `possible_virtual_or_reflected_facet=true`, keeps the source and
   line-to-junction references, and has `facet_semantic_id=null`.
   A repeated feature is still only repeatable **appearance**.
3. **Physical interior geometry:** `C1_C2`, `C2_C3` and `C3_TABLE`
   are all `physical_correspondence_unavailable` with status
   `unavailable` and `vertices_topology_order=null`.
   There is no copying from bright edges, even in resolved crown views.
   Pavilion physical angles and facet geometry remain outside this adapter.
4. **Consumer safety:** `require_physical_boundary` refuses unresolved
   interior geometry. Malformed segment/graph references, changed frozen
   source selections, an input that claims verified polished facet
   correspondence, or missing source manifest fingerprints all fail closed.
5. **Crown view uncertainty:** carry the original resolved-likely-crown
   versus uncertain face-lobe classification. A resolved view is a
   *prerequisite to interpreting crown geometry*, never physical proof.
   The previous `#92` fixed non-exclusive image-region handoff remains
   independent; brightness changes there cannot re-label facets.

## Frozen cohort reproducibility

The fast CI reads the **immutable and already successfully checked**
diagnostics from #146 (run 37797799152) and #162 (run 37815198934).
Both must claim the exact original four-stone benchmark source manifest
SHA-256 and source indices must match **by certificate and frame**.
No redownload/reprocessing of 360 videos is necessary.

For each of the four stones emit `per-stone/<certificate>/provenance.json`
and a compact summary. Assert that *every* optical segment and graph
junction has no physical semantic facet label and *every* interior
physical boundary is explicitly unavailable. Optical feature counts are
descriptive, not an accuracy or grading metric.

Synthetic negative tests include a perfectly repeatable strong line in
resolved crown views (still not physical), missing evidence, malicious
polygon/physical-identity claims, inconsistent source-frame references,
out-of-range graph line refs and invalid coordinates.

## Research decision and next experiment

**KEEP the data-model separation, not the claim of a solved facet detector.**
The next substantive experiment under #123 may study view-to-view
co-variation of optical appearance, with explicit negative examples
from the RGB visual review. The physical side should only advance with
independent surface-junction evidence or a separately validated
multi-view/projective model; neither radial-peak stability nor a straight
gradient is acceptable ground truth.

This PR does **not** promote #140, #146 or #162 as physically correct
facet detectors, rewrite the production #96 scaffold, infer physical
facet angles, assign a diamond quality score, or trigger #90 source stress.
