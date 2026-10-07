# Diamond retrieval

`diamond_retrieval` provides one in-memory retrieval call for one exact diamond listing URL:

```python
from diamond_retrieval import retrieve_diamond

result = retrieve_diamond(url)
```

The result owns recovered evidence bytes and provenance. The retrieval layer creates no output directory, persistent cache or publication artifact.

## Supported retailer routes

The default composition now registers two exact-listing providers:

- Diyona: `https://diyona.com/pages/diamond-detail?sku=...`
- Quality Diamonds: `https://www.qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=...`

Search pages, inventory discovery and guessed stock identifiers are deliberately unsupported.

The Diyona provider reads the exact public detail page and records its displayed USD price without inventing a tax treatment when the page does not state one. The Quality Diamonds provider reads the exact `d=...` page and preserves the displayed GBP inc-VAT price separately from the observed ex-VAT amount. Retailer fields retain field-level attribution.

Quality Diamonds' current public extraction recipe is deliberately page-based rather than dependent on a private client API: the exact page exposes its retailer ID, certificate number, shape/carat/grades, measurements, price/tax basis, IGI verification link and Nivoda still URL. Sanitized saved page snapshots cover both retailer parsers.

## Certificate and still evidence

An IGI verification link or certificate-bound report reference is resolved only through the exact report number already established by the retailer listing. The resolver produces IGI's public exact-report PDF URL; it never searches broadly or guesses a stock ID.

Certificate PDFs are retained byte-for-byte. The network-free PDF processor extracts recognizable report identity and grading fields and records SHA-256. A valid PDF whose text cannot establish the report identity is still retained with `extraction_failed` status, making the result partial instead of discarding the source.

Linked still images are downloaded without resizing. Pillow validates the original bytes in memory and records original dimensions and SHA-256.

## Identity reconciliation

The production validator compares report number, lab, origin, shape, carat, colour, clarity and dimensions wherever both listing and evidence provide them. Normalization is intentionally narrow:

- IGI and International Gemological Institute are equivalent.
- Laboratory-grown/lab-grown/lab-created labels are equivalent.
- Common report shape labels such as Oval vs Oval Brilliant and Round vs Round Brilliant are equivalent.
- Numeric formatting such as 3.32 vs 3.320 is equivalent.
- Missing values remain `missing`; they are not agreement.

A real disagreement raises `IdentityConflictError` with source-linked comparisons before result assembly.

## Loupe360 and the PR B limitation

When an exact listing advertises motion but does not expose a concrete supported viewer URL, the framework may create an exact-certificate Loupe360 reference using the already established full report number. This is resolution only. PR B does **not** download or decode supplier motion.

Accordingly, under the standard policy, Diyona and Quality Diamonds can return useful metadata + matched certificate + available still evidence but remain `partial` while the selected motion reference is unsupported. A certificate-only injected policy can complete without making a motion request. Diajewel, Workshop/Core360 and D360 motion download/processing belong to #100.

## Public HTTP safety

The default HTTP client uses finite timeouts, rejects non-HTTP(S), credential-bearing, local/private/reserved destinations and validates redirect destinations under the same rule. Components receive this client through constructor injection; processors perform no network reads.

## Bounded live verification on 2026-10-07

- Quality Diamonds: the exact `d=133/F74D0EF67` listing route was publicly readable and exposed LG713574578, 3.32ct Oval D/VVS1, measurements, an inc-VAT GBP price, an IGI verification link and a Nivoda still. The public listing price changed between crawls, so fixtures intentionally test structure and attribution rather than asserting a live price.
- Diyona: the exact `sku=B934F4533` route remained reachable but the stone had become unavailable by the live check. A recent public snapshot had exposed the full LG800667394 identity and displayed specifications; that sanitized snapshot is the reproducible parser fixture.
- IGI: the public verification link was visible from the retailer page. Automated access to the IGI verification/PDF endpoint may be refused by the upstream service; such access failures are returned as explicit partial evidence status rather than retried through alternate hosts or credentials.

## Extension contract

Providers, resolvers, policy, downloaders, processors, validator and assembler remain explicitly injected. Evidence kinds remain extensible string identifiers, registration is unambiguous, resolution is bounded and policy is reapplied to every resolved reference. Supplier-media work in #100 should register against these contracts rather than add retailer/viewer branches to `DiamondRetriever`.
