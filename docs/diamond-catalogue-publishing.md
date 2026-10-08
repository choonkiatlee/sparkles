# GitHub catalogue publishing (issue #107)

This is the publishing layer for the versioned catalogue contract (#106). It invokes
the existing single-listing diamond_retrieval.retrieve_diamond function, rather
than re-implementing retailer and source retrieval.

## Using the workflow

After merge into master: Actions > diamond-catalogue-ingest > Run workflow.
Supply one publicly accessible exact Diyona or Quality Diamonds listing URL.

The workflow uses GITHUB_TOKEN with contents:write and one repo-wide concurrency
group. The URL is passed through an environment variable rather than interpolated
into a shell command. No additional token, queue, cloud database, or worker is
required. Pages deployment is explicitly outside scope (#108): GITHUB_TOKEN
commits do not trigger another push workflow automatically.

## Publication ordering and failure policy

1. Retrieve a DiamondResult, establish the certified identity, check
   identity-comparison conflicts and validate every source payload SHA-256
   before any GitHub mutation. A partial result with established identity is
   allowed; unresolved or conflicting identity is rejected.
2. Load or create an immutable GitHub Release with tag
   sparkles-diamond-<stable-id>. Upload original source bytes under flat
   content-hashed filenames, one addressable JPEG per motion frame. Deduplicate
   identical assets. Confirm every uploaded or existing asset's exact size and
   SHA-256 (GitHub digest if present; otherwise download and check original bytes).
   A Release may contain at most 1,000 assets; reject a plan that exceeds this
   limit instead of silently publishing an incomplete series. A later sharded
   Release backend or R2 can use the same manifest schema.
3. Finalize the manifest only when every needed original asset is verified.
   Incomplete uploads may leave orphaned immutable assets, never committed
   pointers to non-existent media. A retry verifies and reuses existing media.
4. Snapshot master at one Git commit and enumerate existing diamond manifests,
   merge the new certified observation, regenerate the entire catalogue index,
   and create one Git commit containing both the manifest and index. A normal
   non-force ref update enforces optimistic concurrency. On a stale branch head,
   re-read and retry (up to three attempts). Never force-push master.

Only compact JSON is committed to Git:
- data/diamonds/<stable-id>.json
- data/catalog.json

Original source PDFs, JPEGs, and videos live in Releases. The resolved storage
URL in each manifest is browser-addressable; no GitHub API discovery is required
by the future UI.

## Safety and upstream limitations

- GitHub's built-in GITHUB_TOKEN is the sole workflow secret. Raw response
  bodies, unsanitized upstream data and secret-bearing query strings must not
  appear in logs; CLI errors print safe exception class names only.
- Upstream HTTP 403 from IGI is not bypassed. Store the linked certificate
  verification URL and a partial/failed attempt status; do not claim a PDF
  was recovered or a certificate comparison succeeded.
- The existing retail input adapter already enforces exact public routes.
  No guessing of other certificate URLs or bypassing site controls.
- Running a workflow from master is required. Serial Action workflow runs
  and non-fast-forward Git update detection protect the shared catalogue index.

## Acceptance tests and live smoke

CI uses an in-memory fake of the GitHub Release and Git trees API for
idempotency, multi-retailer updates, original-byte integrity, partial results,
hash mismatch, failed upload, stale Git head, release capacity, missing digest,
deterministic index and binary exclusion. One test uses the actual #104 public
retriever + 256-frame Core360 fixture end-to-end. Existing catalogue and
retrieval test suites also run.

After merging, perform a bounded real workflow_dispatch using one supported
live exact listing URL. Confirm the certificate identity, Release assets,
SHA-256 of downloaded evidence, committed manifest/index, and re-run idempotency.
If access is blocked, record the precise limitation; do not invent success.

No production Release or workflow smoke is claimed solely by passing fake tests.
The live smoke remains an explicit acceptance gate before closing #107.

Local focused verification:
- python -m unittest tests.test_diamond_catalogue_publisher -v
- python -m unittest tests.test_diamond_catalogue_integration -v

The repository-wide geometry validation has an unrelated known frozen-method
mismatch after PR #96; this does not change catalogue contract tests.


## Diyona default ingestion: public Supabase API (no Chromium)

The normal Diyona adapter now retrieves the stone record from the same
public PostgREST endpoint used by the retailer's own browser:

1. Get the exact SKU from `?sku=A69835AA4`.
2. Perform a *bootstrap-only* HTTP GET of Diyona's Shopify shell to read its
   current `SUPABASE_URL` and public `SUPABASE_ANON` configuration. No
   diamond facts are parsed from that shell, no JavaScript is executed, and
   the shell/anonymous browser key are **not persisted in evidence**.
3. Call the pinned public Supabase host's
   `/rest/v1/public_diamonds?sku=eq.<SKU>&select=...&limit=2`
   with the publicly advertised browser API key.
4. Require **exactly one** returned stone, a matching SKU, IGI lab and a
   complete IGI report number. `certificate_number` determines the canonical
   catalogue identity; grades, dimensions, public image/video and certificate
   URLs are retained with their API attribution.
5. Continue using the existing verified certificate/media retrieval and
   immutable GitHub Release publication pipeline.

The live no-browser probe on 2026-10-08 returned a single public API row
for SKU `A69835AA4` with `certificate_number=LG816611062`. The
API result—not a user claim or a guessed URL—is the primary identity source.

The optional workflow `igi_report` remains a backward-compatible manual
fallback for cases where the retailer's public API is genuinely unavailable,
but it is **not required** when the API is working. Manual identity retains
explicit attribution and requires independent corroboration before publication.

No Playwright, Chromium or headless browser is installed or invoked.

The two requests are lightweight HTTP and the first exists *only* to
bootstrap the rotating public API configuration, never to parse a
JavaScript-rendered diamond detail screen. A future pinned public anonymous
key can eliminate that bootstrap GET if desired, at the cost of managing
public-key rotation.
