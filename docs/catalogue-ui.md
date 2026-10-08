# Static diamond catalogue UI — C1 and C2 (#136, #137)

This is a **research contact sheet** at `/catalogue/`. It is deliberately separate from the existing Sparkles homepage. The Pages build keeps the existing root `index.html`, historical `evaluations/`, `resources/`, and `data/` alongside it.

## Data boundary

- Load `../data/catalog.json` only. The index is the generated `sparkles-diamond-index/1` from #106/#107; no hard-coded production diamonds.
- Use `thumbnail_url` for a representative original evidence image. This is **not** an independently calibrated face-up view or an optical score.
- No GitHub REST API calls, release discovery, or runtime ingestion from the browser.
- Prices and tax bases remain observations, in original currency; the price sorter groups currencies before comparing values.
- Explicit Unknown / partial / unavailable states; no fabricated certificate PDF or price.
- Selection uses `?selected=igi-xxx,igi-yyy&compare=1` as a shareable URL. C2 retrieves the selected full manifests on demand and renders an aligned comparison with stills and expandable evidence provenance; C3 adds synchronized original media.

The real saved records used for smoke validation are `igi-lg756520111` (partial PDF retrieval, original 256-frame rotation) and `igi-lg816611062` (complete certificate and 256-frame rotation).

## GitHub Pages setup and deployment

**One-time maintainer setting:** go to repository **Settings → Pages → Build and deployment**, and select **GitHub Actions**. Repository settings cannot be changed by the C1 pull request.

- On a normal `master` push affecting website files, `.github/workflows/catalogue-pages.yml` assembles and publishes the Pages site.
- The `diamond-catalogue-ingest` action calls the **same reusable Pages workflow** only after its publisher job succeeds.
- A commit authored with `GITHUB_TOKEN` does *not* trigger an ordinary downstream `push` workflow. The explicit call is therefore essential.
- The deploy job checks out latest `master` **after** the catalogue publisher committed its manifest and index, not the old ingestion workflow checkout.
- The curated staging script copies only public static assets, checks that index rows correspond to real manifests, and validates relative links from the two entry pages.
- Page deployment is serialized with the dedicated Pages concurrency group.

**Expected URL when Pages is enabled and deployed:** https://choonkiatlee.github.io/sparkles/catalogue/ . Do not claim a live site until a successful Pages workflow run and browser smoke test confirm it.

## Reproducible tests

Run from repository root (Python 3.11+, Node 22+):

```sh
node --check catalogue/core.mjs
node --check catalogue/app.mjs
node --test tests/catalogue-core.test.mjs
python -m unittest tests.test_catalogue_pages_site -v
```

The new `catalogue-ui-contract` CI checks these on every relevant PR. Browser smoke after merge: open the expected Pages URL and verify two published diamonds and real thumbnails, all metadata, selection deep links, partial/complete labels, existing homepage links, and a subsequent ingestion's updated index.

## C2: selected manifest comparison

Selecting two to five stones and pressing **Compare selected** opens an
aligned table, with a single row label shared across all selected diamonds.
On narrow screens it scrolls horizontally instead of squeezing facts into
misaligned cards. Selection order and compare state survive URL reload
(`selected=id1,id2&compare=1`); catalogue search and filtering remain independent.

Only the selected per-diamond manifests are downloaded, at canonical
`../data/diamonds/<index-id>.json` paths. Cached successful loads are reused
while transient failures can be retried *per column*. Every response is
validated against the certified lab/report identity in the compact index.
A failed or unavailable manifest does not prevent the other stone from loading.

- Comparison values are taken from the authoritative manifest, including
  optional reported proportions. Missing values remain **Unknown**.
- The most recent listing observation is displayed in the aligned price
  and source rows; expand provenance to review all saved retailer observations
  with their **original price, currency, tax basis and dates**.
- A recovered certificate PDF is labeled separately from an upstream
  certificate **verification link**. A partial IGI-403 record must not
  display the verification link as a downloaded PDF.
- All evidence kinds/statuses, ordered frame counts, retrieval timestamps,
  completion reasons and failed attempts appear behind `details`.
- Prefer one recovered still, else one validated first rotation frame. No
  frame prefetch, animation or calibrated face-up angle is implied. A
  video-only record shows its video link in provenance, not a fake still.
- Media rendering only reads resolved HTTP(S) `asset.storage.url`;
  an R2 fixture renders the same way as the GitHub Release backend.
- Link URLs are scheme-checked and all evidence/source labels are rendered
  as text nodes (not untrusted HTML).

Run `node --test tests/catalogue-core.test.mjs tests/catalogue-compare.test.mjs`
for deterministic index/manifest fixture checks; the latter exercises the
two live-published JSON manifests and null/partial/video/R2 cases.

## Follow-ups

- C2 #137: included on this branch; merge/review before starting C3.
- C3 #138: ordinal (not physically calibrated) synchronized 360 player, bounded prefetch and storage-neutral `asset.storage.url` for both GitHub Release and R2 fixtures.

No database, user accounts, ranking system, new optical analysis or browser ingestion controls are introduced.


## Compact overview table — #142

The default catalogue browse view is a **dense selectable table** rather than the original large card grid. Scannable columns are: choose, representative evidence thumbnail, report/retailer and dimensions, carat, colour, clarity, original-currency price with tax basis, retrieval status, and a **Not scored** placeholder for a future, separately validated optical-quality score. No fictitious score or FX comparison is created. The dropdown offers certified colour and clarity grade sorting as well as carat, report and currency-bucketed price.

The row prefers the automatically generated `overview_thumbnail_url` (128px source-hash-verified WebP) if available and falls back to the original `thumbnail_url` otherwise. The crop is generated with existing Asscher silhouette/pose code but does not assert a physically calibrated face-up viewing angle. The detailed C2 comparison still uses full original media unchanged. See `docs/catalogue-thumbnails.md`.

Keyboard-accessible checkboxes and the C1 2–5 selection/shareable URL behavior are preserved; C2 manifest-backed detail remains below the table. On narrow screens the table scrolls horizontally, with selection and report/thumbnail columns sticky to maintain identity while scanning metrics.


## C3a: shared ordinal original 360 comparison (#154)

Open a selected 2–5-stone comparison to display a **shared player toolbar** and an
aligned **360 rotation** row for each column with a recovered successful,
complete ordered frame sequence. Full original stills remain in each column
header; C2 metadata, original PDFs and provenance remain unchanged. The
compact overview has no 360 loading.

The same normalized position p in [0,1) drives each sequence with
\`index=floor(p*frame_count)\`, wrapping at 1.0. A 256-frame stone and a
64-frame stone therefore traverse each saved cycle over the same relative
time, without claiming equivalent physical camera angles, phase alignment, or
identical frame 0 across suppliers. Prev/next use the finest selected
sequence's ordinal step; playback advances at 8 ticks/second over an
approximately 15-second normalized cycle. Browser range keyboard navigation
works via the native range input.

For missing, failed, incomplete or video-only motion, the rotation cell
explains the limitation; any original video has an explicit source link.
A missing individual JPEG shows a retry button. Per-column manifest retry
and stale-selection guards are retained.

### Optional prefetch policy (disabled by default)

\`catalogue/rotation.mjs\` exports \`PREFETCH_ALL_DEFAULT = false\` and the
pure \`prefetchURLs(rotation,p,mode)\` function. The player exposes
**Prefetch every frame (more data)** as an unchecked checkbox. When off, only
the current displayed frame and neighboring ±2 frame URLs are requested.
When explicitly checked, all frames for **selected** complete rotations are
queued for loading, with global \`PREFETCH_CONCURRENCY = 3\`, rather than
opening hundreds of simultaneous image requests. Unselected diamonds and the
overview never prefetch any frames. Changing selection/hiding the player drops
pending work; active browser requests may finish. Detailed queue caching,
progress display, advanced cancellation and mobile tuning belong to C3b #155.

Changing \`PREFETCH_ALL_DEFAULT\` to \`true\` changes the initial behavior in a
single place if a future deployment decides that unlimited prefetch should be
the default. The frontend reads resolved \`asset.storage.url\` (GitHub Release,
R2, etc.) and does not call GitHub REST. Successful manifests are cached,
but there is no full media manifest preloading.

### C3a verification

\`\`\`sh
node --check catalogue/rotation.mjs
node --check catalogue/comparison-view.mjs
node --test tests/catalogue-core.test.mjs tests/catalogue-compare.test.mjs tests/catalogue-rotation.test.mjs
python -m unittest tests.test_catalogue_pages_site -v
\`\`\`

The rotation tests exercise the two real 256-frame saved stones, simulated mixed
frame counts, unsafe/incomplete/media-only cases, and the concurrency-limited
prefetch-all policy. Follow with a visual smoke of the published static Pages
comparison link once the PR is merged.
