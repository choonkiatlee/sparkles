"""Optional, exact-URL browser fallback for JavaScript-rendered Diyona listings.

Only the initial public listing is browser-rendered, never supplier media or
certificate verification. The normal injectable HTTP retrieval path remains
unchanged for any static HTML that already establishes certified identity.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qs, urlsplit

from diamond_retrieval.errors import RetrievalError
from diamond_retrieval.http import validate_public_http_url
from diamond_retrieval.protocols import HttpResponse
from diamond_retrieval.retailers import DiyonaListingProvider

_RENDER_REQUIRED = (
    "Diyona exact listing no longer exposes certificate-bound diamond data"
)
_NO_IDENTITY = "Diyona rendered listing did not expose certificate-bound diamond data"
_RENDER_FAILED = "Diyona browser rendering failed"
_MAX_HTML_BYTES = 12 * 1024 * 1024


def _safe_browser_target(url: str) -> None:
    """Keep the browser on the exact public retailer entry point."""
    if not DiyonaListingProvider(None).supports(url):
        raise ValueError("Browser rendering requires an exact Diyona listing URL")
    validate_public_http_url(url)


def _is_safe_request(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        return False
    if parts.username is not None or parts.password is not None:
        return False
    if parts.hostname.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return not parts.hostname.lower().endswith((".local", ".internal"))
    return ip.is_global


def render_diyona_html(url: str, *, timeout: float = 30.0) -> bytes:
    """Render the public page and wait for its actual certificate-bound DOM.

    No separate ID search or guessed source endpoint. Browser automation merely
    observes the exact link supplied by the user as a human shopper would.
    """
    _safe_browser_target(url)
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 1360, "height": 900},
                    service_workers="block",
                )
                try:
                    page = context.new_page()
                    def guard(route):
                        if _is_safe_request(route.request.url):
                            route.continue_()
                        else:
                            route.abort()
                    page.route("**/*", guard)
                    page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                    # Require the requested SKU plus an actual human-visible
                    # report line, not arbitrary window globals/script JSON.
                    sku = parse_qs(urlsplit(url).query)["sku"][0]
                    page.wait_for_function(
                        """sku => {
                          const t = document.body?.innerText || "";
                          const label = /SKU:\\s*([A-Za-z0-9]+)\\s*(?:·|\\||-)\\s*IGI\\s+([A-Za-z]*\\d+)/i.exec(t);
                          return label && label[1].toUpperCase() === sku.toUpperCase();
                        }""",
                        arg=sku, timeout=int(timeout * 1000),
                    )
                    # Ensure that a redirect didn't swap out the exact stone.
                    final = urlsplit(page.url)
                    expected = urlsplit(url)
                    if final.hostname not in {"diyona.com", "www.diyona.com"} or (
                        parse_qs(final.query).get("sku", [""])[0].upper()
                        != parse_qs(expected.query)["sku"][0].upper()
                    ):
                        raise RetrievalError("Diyona browser navigation changed the exact listing")
                    markup = page.content().encode("utf-8")
                    if len(markup) > _MAX_HTML_BYTES:
                        raise RetrievalError("Diyona rendered HTML exceeded safe size limit")
                    return markup
                finally:
                    context.close()
            finally:
                browser.close()
    except PlaywrightTimeout:
        raise RetrievalError(_NO_IDENTITY) from None
    except RetrievalError:
        raise
    except Exception:
        # Do not expose arbitrary browser/network messages and URLs in Action logs.
        raise RetrievalError(_RENDER_FAILED) from None


class RenderedDiyonaListingProvider(DiyonaListingProvider):
    """Retry only missing-identity HTML with an exact public browser rendering."""

    def __init__(self, http_client, *, renderer=render_diyona_html, timeout=30.0):
        super().__init__(http_client, timeout=timeout)
        self.renderer = renderer

    def fetch(self, url: str):
        try:
            return super().fetch(url)
        except RetrievalError as error:
            if str(error) != _RENDER_REQUIRED:
                raise

        html = self.renderer(url, timeout=self.timeout)
        if not isinstance(html, bytes) or len(html) > _MAX_HTML_BYTES:
            raise RetrievalError(_RENDER_FAILED)

        outer = self.http_client

        class SingleSnapshot:
            def get(self, requested, *, timeout):
                if requested != url:
                    return outer.get(requested, timeout=timeout)
                return HttpResponse(
                    status_code=200, url=url,
                    headers={"Content-Type": "text/html; charset=utf-8"},
                    content=html,
                )

        # Normal retailer parser still verifies the exact requested SKU, full
        # IGI report number and all available grades/dimensions.
        return DiyonaListingProvider(SingleSnapshot(), timeout=self.timeout).fetch(url)
