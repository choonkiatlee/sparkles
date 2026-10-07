# Source media recovery — 7 October 2026

Recovery completed: after the user signed in to PriceScope, the three full attachment endpoints served native JPEG objects. These exact downloaded bytes now replace the previews. The original historical upload identity cannot be independently proven beyond the verifiable full attachment objects.

## Full attachment recovery

Authenticated full attachment navigation and image-document download succeeded for all three targets on 7 October 2026. MIME type was image/jpeg. HTTP response status was not exposed by the browser API.

| Post | Dimensions | Bytes | SHA-256 |
|---|---|---|---|
| 151 | 410 × 319 | 9889 | `0d0d87dfd9d4090dc21d03173b9260abe00556b40c6df05e19fad310fa0bd3a3` |
| 157 | 421 × 277 | 14797 | `4993dfcd3521d800c7b7751f38e23eeba3fc8962682e35ee5001708f87207acb` |
| 158 | 414 × 281 | 15779 | `7ea46e6bf93eceb23d83d86c50e3d27cf07160392f7adc14c68b7573d49f2d86` |

All objects decode and were visually checked against their expected contents. Both original and inline-preview URLs remain in ground-truth.json. No numeric values were transcribed.

## Earlier unauthenticated inventory and results

The live page-6 DOM exposes linked `img` elements with `src`, `alt`, and `title`. For the three targets, `srcset` was empty; no extra `data-src` / `data-url` or full data/CDN URL was present on those elements. Full attachment IDs and original filenames are therefore known, but the original upload dimensions and byte counts are not.

### Post 151 — profileNewA.JPG

- Full attachment: https://www.pricescope.com/community/attachments/profilenewa-jpg.120620/ — browser navigation returned `Log in | PriceScope`, with `You must be logged-in to do that.` No image bytes; HTTP status not exposed by the browser API.
- Inline preview: https://www.pricescope.com/community/data/attachments/116/116998-234bd483c8c2b28449a166b9399c6ba0.jpg?hash=I0vUg8jCso — loaded as an image/jpeg document and downloaded successfully. 6968 bytes; 300 × 233 pixels. HTTP status not exposed by the browser API.
- SHA-256: `efa466418fb993196029685c703e220a1a1b766d82e2617748eea58763d1885d`.
- Local file: [profile-photo.JPG](profile-photo.JPG).
- Visual identity: Post 151 explicitly introduces a better photograph for Sergey. Visual inspection confirms a horizontal-table profile with visible step boundaries. Post 154 is a different attachment, morepics.JPG (120622), and is not substituted. The association with the post-156 estimates follows thread sequence, not an explicit image citation in post 156.
- Most promising full-resolution route: authenticated download of attachment 120620 through the linked PriceScope attachment endpoint, then compare against the archived preview and record full-object metadata.

### Post 157 — manualMeasurements.JPG

- Full attachment: https://www.pricescope.com/community/attachments/manualmeasurements-jpg.120629/ — browser navigation returned `Log in | PriceScope`, with `You must be logged-in to do that.` No image bytes; HTTP status not exposed by the browser API.
- Inline preview: https://www.pricescope.com/community/data/attachments/117/117007-5422cf26c73fa4730ad74512a90e36bf.jpg?hash=VCLPJsc_pH — loaded as an image/jpeg document and downloaded successfully. 9284 bytes; 300 × 197 pixels. HTTP status not exposed by the browser API.
- SHA-256: `f81e4c9bb3e9b5666ba70ad5849f42ec0d202f29f243ce393f80774076d09c4d`.
- Local file: [manual-measurements.JPG](manual-measurements.JPG).
- Visual identity: Visual inspection confirms the dated personal/manual measurements table for a 0.79 carat Asscher, with C1/C2/C3 and P1/P2/P3 columns. No numbers transcribed from the preview.
- Most promising full-resolution route: authenticated download of attachment 120629 through the linked PriceScope attachment endpoint, then compare against the archived preview and record full-object metadata.

### Post 158 — manualMeasurementsFull.JPG

- Full attachment: https://www.pricescope.com/community/attachments/manualmeasurementsfull-jpg.120630/ — browser navigation returned `Log in | PriceScope`, with `You must be logged-in to do that.` No image bytes; HTTP status not exposed by the browser API.
- Inline preview: https://www.pricescope.com/community/data/attachments/117/117008-d50b687ee48e01c4f24c63ce7a9954bc.jpg?hash=1QtofuSOAc — loaded as an image/jpeg document and downloaded successfully. 10505 bytes; 300 × 203 pixels. HTTP status not exposed by the browser API.
- SHA-256: `0100b93cddc422dc8787f0d360b1240fa2854cda4c3deec9cbf301acae92ab9f`.
- Local file: [manual-measurements-last-line.JPG](manual-measurements-last-line.JPG).
- Visual identity: Distinct attachment and bytes; visual inspection shows the same measurement table extended to include a fourth pavilion row. This is a corrected complete table, not a standalone last-line crop.
- Most promising full-resolution route: authenticated download of attachment 120630 through the linked PriceScope attachment endpoint, then compare against the archived preview and record full-object metadata.

## Additional candidate around post 154

The separate post-154 image is `morepics.JPG`, attachment 120622:

- Full link discovered: https://www.pricescope.com/community/attachments/morepics-jpg.120622/ — not fetched; not selected as the better profile photograph.
- Inline source discovered: https://www.pricescope.com/community/data/attachments/117/117000-55d75d800d378653c5542ba7a529d9a2.jpg?hash=VdddgA03hl — not fetched; markup declares 233 × 292.

Post 151 names its image `profileNewA.JPG` and introduces a better photograph for Sergey. Post 156 does not explicitly name the image it uses; the attribution to post 151 follows this contextual evidence and visual profile suitability. Do not claim a stronger citation than the thread provides.

## Other recovery routes checked

- Initial cloud-browser downloads from the thread's full-profile link and inline `img` both timed out (20 seconds). Navigating directly to the observed preview URL and downloading the resulting image document succeeded. This is the useful recovery technique, not a screenshot operation.
- Local Python urllib requests to the profile full link, profile preview and both full measurement links timed out (12 seconds each). A preliminary page HEAD request also timed out. These are network failures, not proof of unavailable attachments.
- Downloaded and inspected `pricescope-media-recovery-2026-10-06-v3.zip` from the existing release (554 entries): no target original filename, attachment ID or target reference in JSON/Markdown/HTML, and no matching filename. No full-resolution candidate found.
- Reviewed temporary recovery workflow at commit `195f28a6a2af779863d839a8a82e49f5f89ef0f0`: it attempted the page before media and wrote results to logs, without an artifact-upload step. Inspected run 37585754394, job 112675358314: HTTP 403 occurred at `page, _ = fetch(THREAD)` before parsing or requesting any image. The run has no artifacts. Thus the earlier CI failure says nothing about attachment availability. Run: https://github.com/choonkiatlee/sparkles/actions/runs/37585754394
- Exact-filename public search with two search engines found no independently hosted original object; one engine returned the same source thread. No archive/cache object with verifiable provenance was found. Archive CDX enumeration was not performed.

## Earlier limits (resolved by authenticated attachment recovery)

Before authentication, only previews were available. Never promote their dimensions or byte counts to full-attachment metadata. No measurement values were transcribed or inferred from the images. Post 158 is a distinct corrected complete table, rather than a standalone last-line image.

PR #71 was already merged before this work. Changes belong in a focused follow-up PR using the existing fixture directory.
