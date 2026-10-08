# Diyona exact-SKU catalogue ingestion (HTTP-only)

Diyona's `/pages/diamond-detail?sku=...` is client-rendered. The initial
Shopify HTML is **not** an authoritative source for the diamond record;
attempting to parse visible `SKU: ... · IGI ...` from its raw HTML fails
even for a live, purchasable stone.

## Default retrieval (no Chromium)

1. Parse and validate the exact SKU supplied in the original retailer URL.
2. Read the public Shopify page **only to discover** the retailer-published
   `SUPABASE_URL` and `SUPABASE_ANON` API configuration. This is not
   an attempt to parse certificate details from the page.
3. Perform the exact same read-only public query as Diyona's JavaScript:

   `GET https://ofjwrrqzzbcnmkkmlawl.supabase.co/rest/v1/public_diamonds?select=*&sku=eq.<SKU>&limit=1`

   The public anonymous token from the page is passed as `apikey` and
   `Authorization: Bearer` for this one trusted host and is **never logged,
   persisted, or committed to Git**. No private cookie, login, browser, proxy,
   or headless Chromium is required.
4. Reject missing, duplicate, different-SKU or missing-IGI results. Use the
   returned `certificate_number`, `lab`, `shape`, `carat`, grades,
   geometry and source URLs as retailer-attributed, exact-SKU data.
5. Keep exact PDF (public CloudFront), still-image and certificate-bound
   Loupe references where valid. Fetch and independently validate evidence
   as before; preserve any blocked/missing certificate as **partial**.

For a page that does **not** advertise that API, the existing historic
fully-rendered HTML parser remains supported for old fixtures or static
retailer layouts. No attempt to read HTML identity precedes the API path
when Diyona advertises its public lookup.

The two-source boundary is important: the Shopify page supplies only the
public **connection configuration**, while the certificate-bound row
supplies the actual diamond data. The original JSON row is retained as
a sanitized, source-attributed response; the public anon credential is not.

## Verified live observation — 2026-10-08

Exact user-supplied URL:
`https://diyona.com/pages/diamond-detail?sku=A69835AA4`

A live public HTTP-only GitHub Actions probe returned HTTP 200 and exactly
one row, with:

- `sku=A69835AA4`
- `lab=IGI`
- `certificate_number=LG816611062`
- `shape=Asscher`, `carat=2.69`
- a still URL from `assets-images-saas.nivoda.com`
- a certificate PDF URL from `dnyvsyhu34v1w.cloudfront.net`
- a `loupe360.com/diamond/LG816611062/video/500/500` reference

The public row also contained `price_usd=749.77`, but no populated
`markup_price`. We explicitly label price sourced from the public API
and its tax/storefront display basis **unverified**, not a confirmed user
checkout price.

Test fixture coverage is not proof that the current original assets remain
downloadable; that is verified separately by live ingestion. The optional
`igi_report` workflow field from #120 remains an exceptional manual fallback
when the retailer public API is unavailable, never the default.
