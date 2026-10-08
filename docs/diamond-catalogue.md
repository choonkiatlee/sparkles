# Persistent diamond catalogue — schema v1

`diamond_catalogue` is a storage-neutral, side-effect-free persistence boundary for
`diamond_retrieval.models.DiamondResult`. See #105 / #106. It does not call GitHub,
write files, or depend on the unfinished supplier motion adapter in #104.

## Stable identity

- The certified logical identity is `(normalized lab, full report number)`; for
  example `IGI` + `LG800667394` → `igi-lg800667394`.
- Lab aliases are explicit (`IGI`, `GIA`), whitespace/hyphen formatting is normalized
  for report numbers, and unsupported punctuation is rejected rather than guessed.
- Retailer SKUs and URLs **never** determine identity.
- The public `DiamondResult` must have an established certified identity. A returned
  partial result is still publishable if it has that identity and no comparison
  conflict; conflicts and unresolved identities fail closed.

## Pure API and publication order

```python
from diamond_catalogue import (
    InMemoryStorage, plan_publication, finalize_manifest,
    merge_manifest, build_index, json_document,
)

plan = plan_publication(result)  # result: existing DiamondResult from #97
storage = InMemoryStorage()      # swap for GitHub Release publisher in #107
resolved = storage.publish(plan.assets)
published = finalize_manifest(plan, resolved)
merged = merge_manifest(existing_manifest_or_none, published)
index = build_index([merged, *other_diamond_manifests])

manifest_bytes = json_document(merged).encode("utf-8")
index_bytes = json_document(index).encode("utf-8")
```

**Write after uploads/verification only.** `plan_publication` yields an in-memory
manifest draft with unresolved `asset_id`s and a tuple of `PlannedAsset` objects
holding source bytes. `finalize_manifest` verifies that every planned asset has
been resolved with matching SHA-256, byte count, backend, locator and public HTTPS
URL. An unresolved draft cannot pass `merge_manifest` for persistence.

Nothing persists until the real #107 publisher commits the final JSON. If a
binary upload fails, an unreferenced uploaded immutable asset is acceptable;
a committed manifest with broken/missing references is not.

## Persisted layout

```text
data/diamonds/igi-lg800667394.json  # one authoritative manifest per certificate
data/catalog.json                  # regenerated from manifests; small UI index
```

Never commit original PDFs, JPEGs, videos, or the
`PublicationPlan.assets` byte payloads into Git history.

`schema = "sparkles-diamond-catalogue/1"` manifest fields:

| Field | Purpose |
| --- | --- |
| `id`, `identity` | Normalized primary key, lab, full report number |
| `diamond_metadata` | Shape, origin, carat, grades, dimensions, reported proportions, field attribution |
| `listings[]` | Retailer host, listing URL/SKU, observed price/currency/tax basis/time |
| `retrievals[]` | Retrieval status, completion reasons, attempts and identity comparisons with source links and original unverified certificate link (including IGI 403) |
| `evidence[]` | Kind, ID, status, provenance, observations, source metadata, resolved original assets |

Rotation sources that supply 256 original frame payloads may also contain a synthetic in-memory progressive JSON bundle; only the original frames are published, not this redundant generated bundle. Rotation frame order, supplier, ordering, completeness and physical-angle-calibration flags survive in the catalogue.\n\nEach evidence record has `record_key`, an identifier derived from its logical
source reference and content. Every rotation retains its own ordered `frames[]`
array with **original** source index, stored position, source batch, pixel
width/height and an immutable asset reference. Two logically distinct positions
can intentionally refer to the same byte-identical uploaded asset.

Asset references have this shape **after** publication:

```json
{
  "sha256": "<64 lowercase hex characters>",
  "byte_count": 12345,
  "media_type": "image/jpeg",
  "storage": {
    "backend": "github_release",
    "locator": "<opaque backend-native asset locator>",
    "url": "https://<public media host>/asset.jpg"
  }
}
```

The UI reads only `storage.url`, not GitHub Release APIs. A test backend using
`backend = "r2"` works with the exact same schema and rendering contract.
The contract does not force a one-Release-per-diamond physical layout. Hashed,
flat filenames avoid collision and caching ambiguity; Release namespace selection,
limits and upload transport belong to #107.

`schema = "sparkles-diamond-index/1"` contains sorted `diamonds[]` rows with:
`id`, `manifest_path`, lab/report, last-observed retailer/listing and price,
carat/shape/grades/dimensions, latest retrieval status, motion availability,
and representative `thumbnail_url`. The index has no binary data and is not
authoritative. The UI can fetch a full manifest only for selected diamonds.

## Upsert policy

- Same certificate and same retrieval observation: idempotent; no duplicate rows.
- Same certificate through another retailer: preserve both listing observations
  and their dated prices, and keep source-specific evidence/provenance.
- Subsequent partial retrieval: append the failure/attempt; never delete earlier
  valid evidence or silently mark it absent.
- Known, conflicting certified attributes in two manifests: fail closed for
  manual investigation rather than silently preferring one retailer.
- Asset content-hash naming allows byte-identical evidence within a publication
  plan to be stored once, without losing separate frame positions or source links.

No arbitrary sanitized raw HTTP responses, source `metadata.extra`, or
unfiltered provenance `details` are persisted by default. We keep explicit
field attribution, source links, retrieval attempts, completion reasons, and
original evidence descriptors instead.

## Testing and boundaries

Run `python -m unittest tests.test_diamond_catalogue -v`. Tests construct typed
`DiamondResult` fixtures against the merged #97 models, without network access.
The fake storage backend validates hashes and publication behavior for both
GitHub Release and R2 labels. #107 adds real GitHub uploads, Actions, concurrency
and commit safety; #108 adds the static Pages UI. This contract adds neither.

The #104 compatibility gate uses real public `retrieve_diamond` composition with the\narchive-backed Quality Diamonds and Diyona fixtures, verifies all 256 individual\nrotation frames, and checks the expected partial/linked-certificate semantics when\nIGI returns 403.
