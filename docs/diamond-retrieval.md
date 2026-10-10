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

If an upstream IGI PDF returns HTTP 403 (or is unavailable), retrieval retains the original retailer-supplied IGI verification link when present, otherwise the attempted exact-report PDF URL. Consumers can use `result.certificate_link` to offer a manual link; the failed certificate attempt also retains its `locator`, provenance and HTTP error. This is a link only, not a downloaded/identity-validated certificate: `result.certificates` remains empty and the standard-policy result remains `partial`.

```python
result = retrieve_diamond(url)
if not result.certificates and result.certificate_link:
    print("Certificate unavailable for automatic validation:", result.certificate_link)
```

## Identity reconciliation

The production validator compares report number, lab, origin, shape, carat, colour, clarity and dimensions wherever both listing and evidence provide them. Normalization is intentionally narrow:

- IGI and International Gemological Institute are equivalent.
- Laboratory-grown/lab-grown/lab-created labels are equivalent.
- Common report shape labels such as Oval vs Oval Brilliant and Round vs Round Brilliant are equivalent.
- Numeric formatting such as 3.32 vs 3.320 is equivalent.
- Missing values remain `missing`; they are not agreement.

A real disagreement raises `IdentityConflictError` with source-linked comparisons before result assembly.

## Supplier motion and Loupe360 resolution

The default factory registers Diajewel, Workshop/Core360, V360 4.0 (including Loupe360-linked remote-media viewers), D360 and direct public video downloaders. Progressive rotations are decoded and validated as complete ordered 256-frame sequences, preserving original JPEG bytes, dimensions, hashes and source positions; video bytes are retained without frame decoding. Unknown valid source IDs do not require registration or a hardcoded allowlist.

All distinct supported rotation/viewer and direct video URLs advertised on the exact listing are retained as independent evidence references. The certificate-bound Loupe360/Nivoda public resolver can find a supported supplier viewer **and** a supported direct video in one lookup (rather than choosing only one) using the full report identity. It does not search unrelated records or guess supplier IDs. Both direct listing links and Loupe360-resolved sources work through the same default `retrieve_diamond(url)` API. Duplicate asset URLs are downloaded once and their listing/lookup provenance is combined in the retained evidence record; each discovered reference still has an explicit attempt status. One unsuccessful selected asset makes standard-policy completion `partial` even if another rotation or video succeeded. Video and rotation kinds can be excluded independently by an injected policy.

The default completion policy still requires a successfully downloaded and identity-matched certificate plus validated motion. A certificate URL alone is not sufficient for `complete`. Callers can supply an injected certificate-only policy if appropriate.

### Vision360 4.0 remote media

Loupe360 exact-certificate resolution can return an external Vision360 4.0 viewer like
`https://v360.in/viewer4.0/vision360.html?d=VDC-32-50&surl=https://s10.v360.in/images/company/1546/`.
The `RemoteV360RotationDownloader` uses the **supplied exact** `d` and `surl`
to locate the progressive JSON sequence below
`https://s10.v360.in/images/company/1546/imaged/VDC-32-50/`.
It requires a public HTTPS V360 CDN root of the form
`s<digits>.v360.in/images/company/<digits>/` (or the documented same-origin
viewer default without `surl`), rejects arbitrary external hosts and path
traversal, and keeps original source bytes and frame ordering through the
existing `ProgressiveRotationProcessor`. No inventory search or guessed
supplier movie identifier is involved.

A simulated regression uses the viewer returned for IGI LG781646632.
The real supplier endpoint must still be exercised by rerunning that diamond
after merge; simulated 256-frame fixtures are not proof of live availability.

## Public HTTP safety

The default HTTP client uses finite timeouts, rejects non-HTTP(S), credential-bearing, local/private/reserved destinations and validates redirect destinations under the same rule. Components receive this client through constructor injection; processors perform no network reads.

## Bounded live verification on 2026-10-07 and 2026-10-08

- Quality Diamonds: the exact `d=133/F74D0EF67` listing route was publicly readable and exposed LG713574578, 3.32ct Oval D/VVS1, measurements, an inc-VAT GBP price, an IGI verification link and a Nivoda still. The public listing price changed between crawls, so fixtures intentionally test structure and attribution rather than asserting a live price.
- Diyona: the exact `sku=B934F4533` route remained reachable but the stone had become unavailable by the live check. A recent public snapshot had exposed the full LG800667394 identity and displayed specifications; that sanitized snapshot is the reproducible parser fixture.
- IGI: on 2026-10-08 Quality Diamonds' exact-linked PDF request returned HTTP 403, so the one-call result was correctly `partial` while retaining the human verification URL; the blocked download is not considered a matched PDF.
- Supplier motion (2026-10-08 GitHub Actions diagnostic): Quality Diamonds/Core360, direct Diajewel and direct D360 each recovered 256 original ordered frames. Quality Diamonds also returned metadata and a still. The Diyona sample was no longer publicly certificate-bound, so current live Diyona retrieval is unverified; its stored fixture covers the parser and end-to-end behavior.

## Extension contract

Providers, resolvers, policy, downloaders, processors, validator and assembler remain explicitly injected. Evidence kinds remain extensible string identifiers, registration is unambiguous, resolution is bounded and policy is reapplied to every resolved reference. Supplier-media downloaders register against these contracts without retailer/viewer branches in `DiamondRetriever`.

## Listing-independent expert reference lookup (#196)

Use this entry point when an external agent has already curated a reference, **not**
a retailer detail page. It uses the same in-memory evidence classes, downloader,
processor, SHA-256 metadata and per-source attempts as normal ingestion:

```python
from diamond_retrieval import retrieve_reference_media

result = retrieve_reference_media(
    "ps285166-r07",
    media_sources=[{
        "kind": "viewer", "provider": "v360.diamonds",
        "status": "linked_unverified",
        "url": "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i",
    }],
)
# result.attempts contains an UNSUPPORTED viewer URL; nothing is fabricated.

igi = retrieve_reference_media(
    "ps285166-r02", lab="IGI", report_number="LG634479985",
    media_sources=[], include_igi_pdf=False,
)
# Best-effort exact report -> Nivoda/Loupe360 candidate motion/video/still.
```

Inputs are the stable unprefixed reference ID, optional source-claimed lab and full
report number, and zero or more curator-provided `viewer`, `still` and `video`
links. Explicit URLs are attempted first. The default pipeline validates public
HTTPS destinations and redirect hops; it does not fetch arbitrary listings or
run any LLM. A Loupe UUID or numeric viewer ID is **not** interpreted as a
certificate number. Only existing supported v360.in/Diajewel/Workshop/Core360/
D360 patterns are decoded; `v360.diamonds` and unrecognized Loupe viewer pages
remain explicit `unsupported` attempts with the original link intact.

The returned `DiamondResult` uses a synthetic `reference:<id>` locator, never
a fake certified listing. `result.evidence` holds validated original bytes and
`result.attempts` holds successes, failures, duplicate links and unsupported
sources. Exact-report lookup failures do not suppress unrelated direct media.
The resolver opts into the Loupe record's image candidate on this path only;
normal retailer ingestion keeps its original set of candidates. An extracted
certificate identity conflict raises `IdentityConflictError`, preventing a
result from being published until reviewed. No evidence is stored on disk here:
publication/Actions are separate issue #197.

Run the deterministic suite with:

```sh
python -m unittest tests.test_reference_media_lookup -v
```
