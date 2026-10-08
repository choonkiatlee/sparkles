"""Diyona's actual public exact-SKU lookup, read-only and browser-free.

The retailer embeds its public Supabase URL and public *anon* API key in
the first-party diamond-detail page's JavaScript, which calls:
    public_diamonds.select("*").eq("sku", sku).limit(1)
We reproduce that specific request, not arbitrary storefront API discovery.
Never expose or persist the anonymous token or use privileged credentials.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from .errors import RetrievalError
from .models import ProvenanceStep, SourceResponse
from .protocols import HttpClient

_PUBLIC_PROJECT = "https://ofjwrrqzzbcnmkkmlawl.supabase.co"
_URL_RE = re.compile(
    r"""\bSUPABASE_URL\s*=\s*['"](https://[a-z0-9-]+\.supabase\.co)['"]"""
)
_ANON_RE = re.compile(
    r"""\bSUPABASE_ANON\s*=\s*['"]([a-zA-Z0-9._-]{32,2048})['"]"""
)
_SKU_RE = re.compile(r"[A-Za-z0-9]{5,40}")
_REPORT_RE = re.compile(r"LG[0-9]{8,12}")
_FIELDS = frozenset({
    "sku", "lab", "certificate_number", "certificate_url",
    "shape", "carat", "color", "clarity", "cut", "polish", "symmetry",
    "fluorescence", "length", "width", "depth_mm", "depth_percent",
    "table_percent", "ratio", "price_usd", "markup_price",
    "image_url", "video_url", "min_delivery_days", "max_delivery_days",
})


@dataclass(frozen=True)
class PublicDiyonaRecord:
    data: dict
    url: str
    provenance: ProvenanceStep
    source_response: SourceResponse


def query_public_diyona_record(
    client: HttpClient, *, page_html: str, sku: str, timeout: float,
) -> PublicDiyonaRecord:
    """Return only an exact certificate-bound row or refuse the lookup."""
    if not _SKU_RE.fullmatch(sku):
        raise RetrievalError("Diyona SKU is not a valid exact public lookup key")

    match_host = _URL_RE.search(page_html)
    match_key = _ANON_RE.search(page_html)
    if not match_host or not match_key:
        raise RetrievalError("Diyona page does not advertise its public diamond lookup")
    if match_host.group(1) != _PUBLIC_PROJECT:
        raise RetrievalError("Diyona page advertises an unexpected diamond data source")

    # The anon key is explicitly distributed by the public retailer frontend.
    # It is used only for an exact row read on this pinned Supabase host.
    anon_key = match_key.group(1)
    api_url = _PUBLIC_PROJECT + "/rest/v1/public_diamonds?" + urlencode(
        {"select": "*", "sku": "eq." + sku, "limit": "1"}
    )
    response = client.get(
        api_url, timeout=timeout,
        headers={"apikey": anon_key, "Authorization": "Bearer " + anon_key,
                 "Accept": "application/json"},
    )
    if response.status_code != 200:
        raise RetrievalError(
            "Diyona public diamond lookup returned HTTP " + str(response.status_code)
        )
    if len(response.content) > 256 * 1024:
        raise RetrievalError("Diyona public lookup result exceeds size limit")
    try:
        rows = json.loads(response.content)
    except (ValueError, UnicodeError):
        raise RetrievalError("Diyona public diamond lookup returned invalid JSON") from None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RetrievalError("Diyona public diamond lookup has no unique exact SKU record")
    row = rows[0]
    if row.get("sku") != sku:
        raise RetrievalError("Diyona public diamond lookup SKU mismatch")
    report = str(row.get("certificate_number") or "").upper().strip()
    if str(row.get("lab") or "").upper().strip() != "IGI" or not _REPORT_RE.fullmatch(report):
        raise RetrievalError("Diyona public diamond lookup lacks a valid IGI certificate")
    row = {key: row[key] for key in sorted(_FIELDS) if key in row}
    source = ProvenanceStep(
        "diyona_public_supabase", api_url,
        {"retailer_sku": sku, "report_number": report,
         "response_sha256": hashlib.sha256(response.content).hexdigest()},
    )
    return PublicDiyonaRecord(
        data=row, url=api_url, provenance=source,
        source_response=SourceResponse(
            "diyona_public_supabase",
            json.dumps(row, sort_keys=True, ensure_ascii=False),
            api_url, "application/json", True,
        ),
    )
