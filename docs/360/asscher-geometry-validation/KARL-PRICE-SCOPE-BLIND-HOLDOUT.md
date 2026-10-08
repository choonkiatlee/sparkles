# #92 external holdout: Karl_K Crispest and Glittery

## Why this is **holdout** and not a calibration set

The PriceScope Asscher evaluation thread supplies two identifiable,
independently archived real-stone sequences with a source-specific expert
technical comparison: **Crispest** (D360 \`79-BT-5165227\`) and **Glittery**
(D360 \`79-BB-5159600\`). The [#64 normalized benchmark](../../external-benchmark/pricescope/benchmark-manifest.json)
records the original interpretations and their provenance, including
Karl_K / strmrdr's criticism of Crispest's face-up P3 leakage. This
report does **not** load those expert labels or the pairwise preference
into fitting, sampling, or metric selection. They may only be inspected
after all source-only results have been frozen.

These stones are independent of the four main geometry source bundles
used by #89 and of the DiaGem/Sergey profile. The original media exist
in the verified PriceScope archive v3 (36,567,890 bytes, SHA-256
\`379f411098e4d96df78d7c00fea5bb9fd18d5f37d890b873928c4003ba126da5\`),
with all **512** exact JPEG frames (256 per stone). Both D360 frame
manifest hashes are fixed in the code; \`external_media.adapt_archived_sequence\`
also checks each original JPEG member's recorded hash.

## What is genuinely held fixed

1. Source choice **predeclared**: exactly Crispest and Glittery, no
   selection based on later brightness or expert score.
2. Geometry algorithm **predeclared**: existing frozen #96
   \`outer_octagon_v2\` and its existing #73/#80 pose / source processing.
   This external stone has *no* previous #89 fitted scaffold. Therefore
   we fit the unchanged #96 model **once per stone** from its geometry
   candidate views. Claiming that we reused a #89 scaffold from a
   different diamond would be false.
3. If pose/gauge/scaffold is unavailable, output \`unavailable\` and
   preserve the reason. Do not loosen thresholds or manually pick nicer
   frames based on the Karl labels.
4. Once that stone-level scaffold is built, fix it. Choose the crown
   window via **the existing #73 face selection**; when unresolved,
   use the existing #89 primary medoid fallback, clearly labelled.
   Sample 11 predeclared normalized lobe positions (fractions
   \`-1,-.8,...,0,...,.8,1\`) using the existing registered frames.
   No per-view fits; original missing frames stay missing.
5. Apply the merged #166 per-ID, non-exclusive image-polygon
   brightness sampler and the #184 fixed-footprint/relative-percentile
   sensitivity probe. Both consume the same pixels, no geometric
   re-optimization.
6. Output each \`sample_id\`, original viewer provenance, source/index,
   nominal brightness, fixed support/status/confidence, exposure rank
   sensitivity and selected-source figure. Do not output any arbitrary
   good/bad label, weighted score or 3D facet angle.

### Important scientific distinction

**This is a held-out *method application*, not a byte-frozen held-out
stone-level scaffold.** The #89 method parameters are fixed and never
fitted to these examples; the stone-specific scaffold must be estimated
once because each diamond has distinct dimensions and geometry. Only
per-frame *transfer* is truly fixed. Report failures, don't silently
adjust the camera frame selection until these two pass.

- Face-up 360 images can contain true optical virtual facets and
  reflections that do not follow an exclusive physical C3/table ring.
- Fixed semantics allow repeatable **image-plane optical support**
  observations, but cannot directly prove P3 leakage or polished
  P1/P2/P3/C3 facets.
- #70's blind external descriptor benchmark already falsified the
  idea that simple tier-readability and relative-darkness are generic
  scores. A new brightness trace must *not* be used to reverse that
  conclusion without independent method-locked validation.
- Vendor capture exposure/gamma/illumination and sequence orientation
  are uncalibrated; between-stone absolute brightness is not
  comparable physical light return.
- A successful holdout establishes an operational handoff under the
  frozen geometry method, **not** agreement with Karl_K's performance
  judgement or #92 universal KEEP.

## Reproducible run

The new CI downloads and hashes the original v3 PriceScope ZIP, then
calls:

\`\`\`bash
python -m diamond360.asscher_semantic_optical_karl_holdout \
  --archive-root /tmp/karl-original-media/<verified-root> \
  --catalog docs/360/external-benchmark/pricescope/benchmark-manifest.json \
  --output outputs/asscher-karl-blind-holdout
\`\`\`

Each stone has \`blind-92-holdout.json\` and, if there is a supported
scaffold and usable views, \`blind-92-holdout.png\`. Source JPEG/pose
arrays are not uploaded. The manifest-driven outputs remain blind to
expert labels, and any remaining missing support is documented.

This external test feeds [#92](https://github.com/choonkiatlee/sparkles/issues/92)
and [#64](https://github.com/choonkiatlee/sparkles/issues/64)
without changing #75/#88 or tuning the existing image-only geometry.
