---
type: source
status: active
tags: [sparkles, diamond, asscher]
aliases: []
certificate_lab: IGI
certificate_number: LG756580087
researched_at: "2026-10-04T20:42:34+01:00"
last_saved_at: "2026-10-04T20:53:00+01:00"
research_pass: 2
research_status: partial
---

# Sparkles IGI-LG756580087 research

Pass 2 adds a correctly ordered supplier sequence and 16 curated original frames. Geometry/proportions and sampled changes through rotation are documented; leakage remains unresolved. Independent IGI verification is deferred by user preference.

## Sources and identity

- [Diyona exact SKU 268F4881D](https://diyona.com/pages/diamond-detail?sku=268F4881D): public exact-SKU listing supplies LG756580087, report and media links.
- [Retailer-hosted IGI report PDF](https://dnyvsyhu34v1w.cloudfront.net/pdf/LG756580087.pdf): downloaded, text extracted and page visually inspected; certificate, origin, carat, colour, clarity and all dimensions match.
- [Loupe360](https://loupe360.com/diamond/LG756580087/video/500/500): opened; currently renders a static photograph, not inspected motion.
- [Supplier 360 lead](https://vision.diajewel360.com/Vision360.html?d=VL-131355): returned by the exact-certificate public Loupe media record, decoded from its returned v360 URL; public page/player retrieved in Pass 2; original ordered sequence recovered and sampled visually.
- [IGI verification link](https://www.igi.org/verify-your-report/?r=LG756580087): retained as an untested official reference, not independent verification.

Loupe public certificate metadata also matches laboratory-grown status, Asscher, 2.52 ct D/VVS1 and 7.58 × 7.56 × 4.84 mm. Shared supplier records are not independent verification. No material identity mismatch found in inspected sources.

## Report facts

All below come from the inspected retailer-hosted report unless noted.

| Field | Reported value |
|---|---|
| Number / date | LG756580087 / January 6, 2026 |
| Origin / shape | Laboratory grown / square emerald cut (retailer: Asscher) |
| Carat / colour / clarity | 2.52 / D / VVS1 |
| Dimensions | 7.58 × 7.56 × 4.84 mm |
| Table / total depth | 63% / 64% |
| Crown height / pavilion depth | 14% / 46.5% (diagram) |
| Girdle / culet | Slightly thick / pointed |
| Polish / symmetry | Excellent / excellent |
| Fluorescence | None |
| Inscription | IGI LG756580087 |
| Growth / comments | HPHT; as grown, no indication of post-growth treatment; Type II |
| Crown / pavilion angles | Not reported |

No optical cut grade is given. Height percentages do not describe individual pavilion tiers. The inscription photograph is explicitly labelled “Sample Image Used”; it is not an inspected photograph of this stone's inscription. Price omitted: the public feed's price_usd does not establish displayed retail price or tax basis.

## Saved evidence

Derived evidence bundles used during evaluation are intentionally not committed; source provenance and retained original artifacts remain documented here.

| Asset | Source / association | Access and inspection | Use / limitation |
|---|---|---|---|
| Report PDF | Retailer-hosted PDF above; exact full certificate and six identity fields match | Saved and inspected | Grades and diagram proportions; no optical assessment |
| Face-up original | [Direct JPEG](https://assets-images.pixorac.com/eb276a35-777b-4fc5-b788-1fd94e903476.jpg); exact-certificate media record and Loupe DOM show this asset | Saved via supported browser media download and inspected; 704 × 704 | Outline and visible facet pattern in one lighting/view; no motion or leakage diagnosis |
| Supplier image-frame 360 | Exact-certificate Loupe record → VL-131355 viewer → page-linked player/batches | All 256 unique original 704 × 704 JPEGs downloaded, ordered and decode/hash verified; overview and selected transitions visually inspected; 16 originals archived | Sampled rotational changes, centre/steps/corners and profile; single supplier setup, unknown angles/timing, not ASET |
| ASET / Ideal-Scope | No linked item in listing/media record; bounded full/numeric certificate searches | Not found in searched sources | Decisive missing evidence for leakage/angular return |
| Side / crown imagery | Same supplier rotation; selected frames 32, 80, 128, 208 | Original oblique/profile images saved and inspected | Profile/crown context; does not calibrate angles or measure tiers |

Direct shell photograph requests returned HTTP 403; browser displayed and downloaded the exact DOM-linked original successfully. Loupe page displayed only its static fallback. No claim that upstream motion is absent.

Saved-member SHA-256:
- PDF: 289b38d653f423d7330e737de54773410f5311d995bf6ed135a9ea72e941982e
- JPEG: 2d868ebd8c18877c30e2c5f0b72ea07d041df15df23a9cc5a3a6f5fbaf4db7e2
- Media record: 6eed80839c4172344efeaef3692c4d67c8e95c176175ff95b685bed66a4b38f7
- Listing record: 314b035b52cd65aa528a39aa210c8f44656608be9dd5c086f2faedc376356493

## Pass 2 recovery and curation


- Source: [supplier viewer](https://vision.diajewel360.com/Vision360.html?d=VL-131355), its actual [player](https://vision.diajewel360.com/js/vision360.js) and [metadata](https://vision.diajewel360.com/imaged/VL-131355/0.json).
- Metadata quality 4 leads to final batch 7; public player requests `imaged/VL-131355/1.json?version=1` through `7.json?version=1`. Preserve the actual version query. Unversioned/Python requests returned HTTP 403; ordinary curl reads of the player-requested URLs succeeded. No confirmed bot challenge observed.
- Decode the public player's scramble map using its raw AES-CBC/PKCS7 routine; validate each permutation. Reorder each batch by inverse permutation and interleave each new batch at odd positions. Batch counts: 4, 4, 8, 16, 32, 64, 128.
- All **256** JPEGs fully decode at **704 × 704**, have unique SHA-256, and total **9,088,577 bytes**. This describes recovery completeness, not individual visual inspection of every frame.
- Visual inspection: ordered 32-frame whole-loop overview, 12 near-face-up previews, full-size selected-image composition and individual frame 250. The 16 archived originals are byte-identical to recovery; manifest records original indices, batch/stored position, byte size, SHA-256, source-batch URLs/hashes and explicit reading order.
- **Face-up order:** 240 → 244 → 248 → 250 → 252 → 254 → 0 → 2 → 4 → 8 → 12 → 16. The sequence wraps through 255 → 0. It samples both sides of near-face-up, including dark/asymmetric band states and changing centre/step/corner appearances. Near-square-on is around 254/0; supplier top_index "250" is a lead, not a calibrated face-up angle.
- **Context frames:** 32, 80, 128, 208 provide broader oblique/profile compositions, selected for distinct useful views.
- Supplier `createdDate` is **2026-01-12T06:37:13Z**, after the 6 January 2026 report; no analogous earlier-date discrepancy found. Metadata is supplier-provided, not independent proof.
- Original report and still remain in the Pass 1 ZIP. Full sequence, duplicate Base64 batches, player and selection contact sheets are deliberately excluded from the compact archive. Full recovery remains temporary working evidence, reproducible from recorded source URLs; it is **not** a durably saved full-frame archive.
- ZIP CRC and every archived JPEG's original-byte hash/dimensions checked. Ordinary supplier lighting and grey background; image processing metadata includes sharpness/background levels. No calibrated spectral lighting, original timing or additional rotation axes established. Ordered-frame sampling supports dynamic assessment but is not a watched continuous video or a leakage test.

## Remaining useful work

1. Exact-stone ASET/Ideal-Scope is the highest-value missing asset for leakage/angular return. Bounded full/numeric certificate searches using two search engines found no matching complementary stone result; only unrelated results. It is not evidence of poor cut. No need to repeat identical searches.
2. Complementary lighting or additional tilt axes would improve confidence if supplied or discoverable. Current original sequence and report are ready for a separate Asscher evaluation; no optical verdict is made here.
3. Independent IGI verification remains deferred by preference. No retailer contact made.

All Pass 1 assets preserved. No source upload failure remains for the curated evidence.

Navigation: [[Sparkles home|Sparkles]].
