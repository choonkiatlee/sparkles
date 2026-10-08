# Asscher thumbnail generation and approval — #143

## Why this is separate from the index's existing generic thumbnail

The existing `thumbnail_url` always remains a representative retailer still /
first original frame, with no crown-orientation claim. The optional
`face_up_thumbnail_url` is only emitted for a **human-reviewed**, exact-hash
derived thumbnail. The compact C2.5 table prefers that field when present and
falls back to the previous thumbnail otherwise.

## Candidate generator

`diamond_catalogue.faceup_thumbnail` uses existing production methods:

- `diamond360.segmentation.segment` on small source RGB copies;
- `asscher_pose.assess_frame` and `face_orientation_cues`;
- `asscher_pose_sequence.resolve_face_lobes` on 32 uniform circular proxy
  samples from a *declared complete* original ordered rotation;
- `asscher_outer_octagon.assess_record`, fitted outer contour (or an explicitly
  **unverified** background-segmented contour as a review-only fallback);
- tightly crop original full-colour pixels with 12% padding and encode
  reproducible 128px WebP. There is no image synthesis, enhancement, physical
  angle assertion or untrusted interpolation of facet geometry.

A plausible crown-looking outline **does not** prove a crown viewpoint.
The original method may not resolve the crown lobe (especially on sparse
uniform samples). Candidate results then explicitly say
`unverified_pose_candidate`; rejection of the strict outer model is reflected
by `selection_method=rejected_outer_geometry_review_only`. A still-only crop
has status `unverified_still_crop` and can **never** be published as a
face-up thumbnail through the approval path.

Each candidate record contains the original
`source.sha256`/`source_index`/`frame_position` and the derivative
`sha256`, crop bounds, source-selection/gating diagnostics, and algorithm
version. Original source media bytes and evidence references remain unchanged.

## Review two actual diamonds

The `asscher-thumbnail-preview` workflow runs on the PR and has a public
Actions artifact named `faceup-review-two-published-stones`.
It downloads only 32 original-frame samples for each of:
`igi-lg756520111` and `igi-lg816611062`, verifying every JPEG against
the original immutable hash. It writes for each:

- `<diamond-id>-crop.jpg` large original-colour crop for review;
- `<diamond-id>.webp` small target icon;
- `<diamond-id>-opposite-crop.jpg` second original-colour frame roughly half a cycle away, when recoverable. Use it to check whether the main crop is actually crown-facing rather than pavilion-facing;
- `<diamond-id>.json` provenance, exact hashes, detailed suitability reasons;
- `summary.json` overview.

An actual image preview is **not** certified as crown-facing merely because
the generation job succeeded. Check the cut-corner outer boundary, full stone,
correct *crown* table rather than pavilion diagonals, and whether a 128px
icon is recognizable. Reject/rework rather than approving an ambiguous image.

## Explicit approval after visual validation

After merge, the repository Actions workflow
`catalogue-faceup-thumbnail-approve` requires all of:

1. exact diamond id;
2. WebP SHA-256 from reviewed JSON;
3. original selected source frame SHA-256 from reviewed JSON;
4. literal `I_REVIEWED_THE_CROWN_VIEW` acknowledgement.

The workflow checks out **updated master**, regenerates the image from its
unchanged original source frame, compares both hashes and source identity,
publishes the content-addressed WebP through the existing
`GitHubReleaseStorage` storage contract, then atomically commits an optional
`derived_media.face_up_thumbnail` reference plus the rebuilt
`data/catalog.json`. It invokes the reusable Pages workflow after commit.
The publication fails closed on any mismatch or attempt to replace a different
reviewed thumbnail, so a changed algorithm or upstream image cannot silently
relabel a pose.

No public site's stored derivative is promoted by automatic CI. Because
the source views are not physically calibrated, `face_up_thumbnail_url`
means **human-confirmed crown-looking thumbnail**, not a measured physical
angle or an optical quality score.

## Tests

```sh
python -m unittest tests.test_faceup_thumbnail tests.test_faceup_publish tests.test_diamond_catalogue -v
```

The tests use synthetic outlines, source SHA mismatches, missing observations,
repository publishing fake, idempotent object storage, index rebuild, source
preservation and explicit approval gates. Network preview is separate and may
expose genuine upstream unavailability without rewriting original evidence.
