# Static diamond catalogue UI — C1 (#136)

This is a **research contact sheet** at `/catalogue/`. It is deliberately separate from the existing Sparkles homepage. The Pages build keeps the existing root `index.html`, historical `evaluations/`, `resources/`, and `data/` alongside it.

## Data boundary

- Load `../data/catalog.json` only. The index is the generated `sparkles-diamond-index/1` from #106/#107; no hard-coded production diamonds.
- Use `thumbnail_url` for a representative original evidence image. This is **not** an independently calibrated face-up view or an optical score.
- No GitHub REST API calls, release discovery, or runtime ingestion from the browser.
- Prices and tax bases remain observations, in original currency; the price sorter groups currencies before comparing values.
- Explicit Unknown / partial / unavailable states; no fabricated certificate PDF or price.
- Selection uses `?selected=igi-xxx,igi-yyy&compare=1` as a shareable URL. The C1 index-only overview is intentionally modest; C2 adds full manifest-backed comparison and C3 adds synchronized original media.

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

## Follow-ups

- C2 #137: full per-diamond manifests, side-by-side metadata and expandable provenance.
- C3 #138: ordinal (not physically calibrated) synchronized 360 player, bounded prefetch and storage-neutral `asset.storage.url` for both GitHub Release and R2 fixtures.

No database, user accounts, ranking system, new optical analysis or browser ingestion controls are introduced.
