# Automated compact catalogue thumbnails — issue #143

The small browse-table icons are **fully automated**. The larger C2 comparison
continues to display the original published media; generated assets do not
replace original stills, videos, ordered 360 frames, or the report PDFs.

## How generation works

`diamond_catalogue.faceup_thumbnail` reads 32 stratified positions from a
published complete ordered 360 cycle, verifying every original downloaded
image's SHA-256 against the immutable catalogue manifest. It reuses the existing:

- `diamond360.segmentation.segment` background/foreground mask;
- `diamond360.asscher_pose.assess_frame` and `face_orientation_cues`;
- `diamond360.asscher_pose_sequence.resolve_face_lobes` for likely crown
  vs pavilion lobe identification when the evidence resolves it;
- `diamond360.asscher_outer_octagon.assess_record` for outer-silhouette checks;
- `diamond360.geometry.fit_asscher_outline` for observed exterior crop corners.

Select the best usable outer-octagon view, preferring a resolved crown lobe.
If the crown is ambiguous or the octagon strict gate fails, make a
**generic overview crop** from the segmented outer foreground where available.
Never crop around a bright internal facet. If no complete rotation exists,
attempt a verified original still crop. If the image/crop isn't usable,
retain the original `thumbnail_url` fallback in the index.

Cropping preserves **original RGB pixels**, a square padded presentation, and
downsamples deterministically to a 128px WebP. There is no new invented
physical camera angle, no quality score, no manual verification requirement.

## Publisher & data contract

The automatic publisher (`diamond_catalogue.faceup_publish`) constructs one
hashed `PlannedAsset` and uploads through the existing
`GitHubReleaseStorage` storage-neutral interface. The catalogue publisher
atomically appends optional `derived_media.overview_thumbnail` containing:

- original source asset SHA-256 and stored frame index (or still hash);
- derived WebP SHA-256, byte count and resolved storage URL;
- source crop bounding box, algorithm, pose-selection status and
  `human_verified: false`.

The generated index adds optional `overview_thumbnail_url`, while
`thumbnail_url` still points to the original saved retailer representative.
The table chooses the generated icon when available and otherwise uses the
original. C2's `representativeAsset` is intentionally unchanged.

Each existing successful generated derivative is stable across re-ingestion.
The publisher is idempotent and won't re-upload the same icon on subsequent
runs. Strict source hash or media-URL failures skip that icon and do not corrupt
the catalogue. No human-in-the-loop approval or upload workflow exists.

## Automatic triggering

- On first merge of #143 to `master`, the `catalogue-thumbnail-auto` workflow
  backfills saved diamonds, up to 100 missing icons per run, then invokes the
  Pages reusable deployment workflow explicitly.
- Each future `diamond-catalogue-ingest` publication executes the same
  bounded backfill step after publishing evidence and before Pages deployment.
- A manual `workflow_dispatch` rerun exists **only** for transient storage
  failures; it is not an approval or per-diamond review step.

Source fetching is network-bounded with safety checks and original SHA-256
verification. Failures log a warning, not a bogus icon. The existing
read-only `asscher-thumbnail-preview` workflow records reproducibility/QC
sample crops for LG756520111 and LG816611062; its artifacts never need approval.

## Tests

```sh
python -m unittest tests.test_faceup_thumbnail tests.test_faceup_publish tests.test_diamond_catalogue -v
```

Tests cover original SHA rejection, outer-crop correctness, generic unverified
views, absent motion/stills, idempotent atomic Git index updates, unchanged
original comparison evidence and storage-neutral URL resolution.
