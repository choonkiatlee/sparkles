"""Retrieve a certified Diyona SKU via its publicly used Supabase PostgREST table.

Diyona's page is a Shopify HTML shell. It fetches the certified stone from
Supabase public_diamonds using the exact `sku`; Playwright is unnecessary.
Read the public API URL / anonymous browser key from the retailer's current
HTML (never retain the key), query only expected public columns, and verify
the returned SKU and certificate before creating references.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlsplit

from .errors import RetrievalError
from .models import (
    CERTIFICATE, STILL, DiamondMetadata, EvidenceReference,
    FieldAttribution, ListingRecord, ProvenanceStep, SourceResponse,
)
from .retailers import (
    _ParsedHtml, _igi_certificate_reference, _motion_references,
    _still_references,
)

_URL = re.compile(r"""\bSUPABASE_URL\s*=\s*['"](https://[a-z0-9.-]+\.supabase\.co)['"]""", re.I)
_ANON = re.compile(r"""\bSUPABASE_ANON\s*=\s*['"]([a-zA-Z0-9_+./=-]{40,2000})['"]""")
_CERT = re.compile(r"LG[0-9]{7,12}", re.I)
_SELECT = (
    "sku,certificate_number,certificate_url,lab,carat,shape,color,clarity,"
    "cut,polish,symmetry,fluorescence,length,width,depth_mm,depth_percent,"
    "table_percent,ratio,markup_price,image_url,video_url"
)


def _number(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
        if not result.is_finite():
            return None
        return result
    except (InvalidOperation, ValueError):
        return None


def _public_api_config(html: str) -> tuple[str, str] | None:
    """No fixed/bundled tokens; discover current public settings in source."""
    url = _URL.search(html)
    anon = _ANON.search(html)
    if not url or not anon:
        return None
    base = url.group(1)
    parsed = urlsplit(base)
    # Pin to Supabase-managed HTTPS hosts (no arbitrary storefront-supplied URL).
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.hostname != "ofjwrrqzzbcnmkkmlawl.supabase.co"):
        raise RetrievalError("Diyona public data endpoint is not a safe Supabase host")
    return base, anon.group(1)


def fetch_diyona_public_record(url: str, response, http_client, *, timeout: float):
    """Use the exact URL SKU, not a guessed SKU-to-certificate relationship.

    Return None only if the returned HTML has no recognizable public
    Supabase config. Otherwise refuse mismatches, empty/ambiguous rows and
    invalid public responses rather than guessing.
    """
    html = response.content.decode("utf-8", "replace")
    config = _public_api_config(html)
    if config is None:
        return None
    base, anon = config
    sku = parse_qs(urlsplit(url).query).get("sku", [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sku):
        raise RetrievalError("Diyona exact URL has invalid public SKU")

    api_url = base + "/rest/v1/public_diamonds?" + urlencode({
        "select": _SELECT, "sku": "eq." + sku, "limit": "2"
    })
    headers = {
        "apikey": anon,
        "Authorization": "Bearer " + anon,
        "Accept": "application/json",
    }
    # All of this information is publicly retrievable by the storefront's JS.
    # Only our production client needs the optional header-bearing GET.
    api = http_client.get(api_url, timeout=timeout, headers=headers)
    if api.status_code < 200 or api.status_code >= 300:
        raise RetrievalError(f"Diyona public stone lookup returned HTTP {api.status_code}")
    try:
        rows = json.loads(api.content)
    except (ValueError, UnicodeDecodeError):
        raise RetrievalError("Diyona public stone lookup returned invalid JSON") from None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RetrievalError("Diyona public stone lookup did not return exactly one stone")
    stone = rows[0]
    if str(stone.get("sku") or "").upper() != sku.upper():
        raise RetrievalError("Diyona public stone SKU does not match exact URL")
    report = str(stone.get("certificate_number") or "").strip().upper()
    if not _CERT.fullmatch(report):
        raise RetrievalError("Diyona public stone has no full IGI report number")
    lab = str(stone.get("lab") or "").strip().upper()
    if lab and lab != "IGI":
        raise RetrievalError("Diyona public stone has incompatible certificate lab")

    source = "diyona_public_diamonds"
    attribution_url = api_url  # Has only SKU, fixed column list; no credentials.
    fields = ["report_number", "lab", "retailer_sku"]
    carat = _number(stone.get("carat"))
    price = _number(stone.get("markup_price"))
    length = _number(stone.get("length"))
    width = _number(stone.get("width"))
    depth = _number(stone.get("depth_mm"))
    dimensions = (
        (float(length), float(width), float(depth))
        if all(v is not None and v > 0 for v in (length, width, depth))
        else None
    )
    shape = str(stone.get("shape") or "").strip() or None
    colour = str(stone.get("color") or "").strip().upper() or None
    clarity = str(stone.get("clarity") or "").strip().upper() or None
    props = {}
    for key, target in [
        ("depth_percent", "depth_percent"),
        ("table_percent", "table_percent"),
        ("ratio", "length_width_ratio"),
    ]:
        value = _number(stone.get(key))
        if value is not None:
            props[target] = float(value)
    for key in ("cut", "polish", "symmetry", "fluorescence"):
        value = str(stone.get(key) or "").strip()
        if value:
            props[key] = value

    for field, present in [
        ("shape", shape is not None), ("carat", carat is not None),
        ("colour", colour is not None), ("clarity", clarity is not None),
        ("dimensions", dimensions is not None), ("reported_proportions", bool(props)),
        ("price", price is not None), ("currency", price is not None),
        ("tax_basis", price is not None),
    ]:
        if present:
            fields.append(field)
    metadata = DiamondMetadata(
        report_number=report, lab="IGI", retailer_sku=sku,
        origin=None,  # Public row provides no independent mined/lab-grown field.
        shape=shape, carat=carat, colour=colour, clarity=clarity,
        dimensions=dimensions, reported_proportions=props, price=price,
        currency="USD" if price is not None else None,
        tax_basis="displayed retailer markup; tax basis not stated" if price is not None else None,
        attribution={
            k: FieldAttribution(source, attribution_url) for k in fields
        },
    )

    certificate_url = str(stone.get("certificate_url") or "").strip()
    if (urlsplit(certificate_url).scheme == "https"
            and report in urlsplit(certificate_url).path.upper()
            and urlsplit(certificate_url).path.lower().endswith(".pdf")):
        certificate = EvidenceReference(
            identifier=f"{source}:{report}:certificate",
            kind=CERTIFICATE,
            retrieval_key=f"igi-pdf:{report}", locator=certificate_url,
            provenance=(ProvenanceStep(source, attribution_url),),
            metadata={"lab": "IGI", "report_number": report, "format": "pdf"},
        )
    else:
        certificate = _igi_certificate_reference(
            source=source, url=attribution_url, report_number=report, hrefs=()
        )

    references = [certificate]
    image_url = str(stone.get("image_url") or "").strip()
    if image_url:
        references.extend(_still_references(
            source=source, url=attribution_url, sku=sku,
            parsed=_ParsedHtml(text="", hrefs=(), images=((image_url, "Diamond"),), media=()),
        ))
    video_url = str(stone.get("video_url") or "").strip()
    references.extend(_motion_references(
        source, attribution_url, report,
        _ParsedHtml(text="360 View", hrefs=(video_url,) if video_url else (),
                    images=(), media=()),
    ))

    # Never retain public JS bootstrap configuration or its anonymous API key.
    # An HTML digest gives provenance without persisting any tokens or scripts.
    import hashlib
    bootstrap_digest = hashlib.sha256(response.content).hexdigest()
    # The PostgREST JSON consists only of the explicitly selected public columns.
    return ListingRecord(
        url=url, metadata=metadata, references=tuple(references),
        provenance=(
            ProvenanceStep("diyona_listing", url),
            ProvenanceStep(source, attribution_url, {"sku": sku, "report_number": report}),
        ),
        raw_responses=(
            SourceResponse("diyona_html_bootstrap", "sha256:" + bootstrap_digest,
                           response.url, "text/plain", True),
            SourceResponse(source, api.content.decode("utf-8", "replace"),
                           api_url, "application/json", True),
        ),
    )
