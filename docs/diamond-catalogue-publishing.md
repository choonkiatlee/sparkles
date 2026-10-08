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


## JavaScript-only Diyona listings (no browser dependency)

The URL already gives the exact SKU. The critical identifier is the IGI report.
When the server-side HTML contains the SKU/report pairing, no extra input
is needed. If the public retailer HTML omits its client-rendered identity,
the optional `igi_report` workflow input accepts the full `LG...` number
visible on the user-facing page; it does NOT infer that number from the SKU.

The resulting record explicitly states that the SKU/report association was
supplied by the user, not independently verified from retailer HTML. The
publisher only proceeds if an independently retrieved IGI PDF has a matching
parsed report or a successful rotation/video has provenance from Loupe360's
exact certificate-bound lookup for that report. If upstream evidence fails
or the input conflicts with the static listing, publication stops and no
manifest is written. Original access controls are respected.

For the first smoke test use:
- `diamond_url=https://diyona.com/pages/diamond-detail?sku=A69835AA4`
- `igi_report=LG816611062`

Neither Playwright nor Chromium is needed or installed. Media remain
retrievable using the public exact-report resolver and supplier downloader.
A manual claim is not silently presented as independently established
retailer metadata.
