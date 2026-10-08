# Exact Diyona listings: browser-rendered fallback

Diyona's diamond detail page can display a valid certified stone after
JavaScript loads while a plain HTTP response contains only a generic page shell.
Do not equate missing initial-server HTML with a sold or unidentified stone.

The checkout workflow invokes the public retrieval interface using a
`RenderedDiyonaListingProvider` *only* for exact public Diyona listing URLs:

1. Attempt the existing lightweight HTTP and HTML parser.
2. If the **sole** failure is missing certificate-bound details, open that
   same URL in headless Chromium; wait for a visible SKU and IGI report line.
3. Feed the rendered DOM back through the unchanged verified parsing, SKU
   matching and certificate-validation path. Do not infer identity from a URL,
   guessed certificate number or a search-result snippet.
4. Keep other errors (HTTP 403, 404, SKU mismatch, identity conflict)
   fail-closed; browser fallback never bypasses explicit access denial.

The certified `SKU · IGI` line is enough to form a truthful diamond
identity even if the display carat/shape heading is absent. In that case,
carat and shape remain null rather than guessed.

The optional `catalogue-browser` dependency installs Playwright only in
the GitHub ingestion workflow, not the core retrieval CI environment.
The workflow installs Chromium (including Linux prerequisites). This adds
startup time but doesn't require any private authentication or proxy.
The renderer only observes the explicitly requested public URL and fails if
a redirect changes the SKU. Response size is bounded, browser errors are
reported using safe static reason codes, and actual HTML/URLs are not logged.

## Verification

The `test_diyona_rendered_listing` fixture suite exercises the exact
shape of a JS-only HTML shell and an after-load DOM, with a synthetic
public-example identity (A69835AA4 / LG816611062). It tests that the
normal parser accepts explicit certificate-bound identity without an
optional display heading, doesn't launch the browser for sufficient
static HTML, and fails closed on redirected/different SKU, access denial
and missing rendered identity.

These fixtures are **synthetic examples**, not purported copies of Diyona's
live HTML. A real post-merge Action retry is still necessary to verify
live browser rendering and any later Release/Git publication. The original
diagnostics-only run #37756051809 established that the initial HTML did not
satisfy the parser, not that the browser listing was unavailable.
