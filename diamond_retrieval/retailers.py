"""Exact-listing providers for the first supported retailers."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import parse_qs, urlsplit

from .errors import RetrievalError
from .diyona_public import query_public_diyona_record
from .models import (
    CERTIFICATE,
    ROTATION,
    STILL,
    VIDEO,
    DiamondMetadata,
    EvidenceReference,
    FieldAttribution,
    ListingRecord,
    ProvenanceStep,
    SourceResponse,
)
from .protocols import HttpClient


_SECRET_PATTERN = re.compile(
    r"""(?ix)
    (
      ["']?(?:api[_-]?key|apikey|access[_-]?token|client[_-]?secret|authorization)["']?
      \s*[:=]\s*["']
    )
    ([^"']+)
    (["'])
    """
)


def _sanitize_retained_html(text: str) -> str:
    clean = _SECRET_PATTERN.sub(r"\1[redacted]\3", text)
    # Shopify's public page embeds a Supabase anonymous JWT. It is public
    # and needed only for the live read, never in persisted source HTML.
    return re.sub(
        r"""(?i)(\bSUPABASE_ANON\s*=\s*['"])[^'"]+(['"])""",
        r"\1[redacted]\2", clean,
    )


class _SnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hrefs: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.media: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "a" and values.get("href"):
            self.hrefs.append(html.unescape(values["href"]))
        if tag.lower() == "img" and values.get("src"):
            self.images.append(
                (html.unescape(values["src"]), html.unescape(values.get("alt", "")))
            )
        if tag.lower() in {"iframe", "source", "video"} and values.get("src"):
            self.media.append(html.unescape(values["src"]))

    @property
    def text(self) -> str:
        return " ".join(self.parts)


@dataclass(frozen=True)
class _ParsedHtml:
    text: str
    hrefs: tuple[str, ...]
    images: tuple[tuple[str, str], ...]
    media: tuple[str, ...]


def _parse_html(content: bytes) -> tuple[str, _ParsedHtml]:
    raw = content.decode("utf-8", "replace")
    parser = _SnapshotParser()
    parser.feed(raw)
    return raw, _ParsedHtml(
        text=re.sub(r"\s+", " ", parser.text).strip(),
        hrefs=tuple(parser.hrefs),
        images=tuple(parser.images),
        media=tuple(parser.media),
    )


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _dimensions(text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"(?:Dimensions|Measurements)\s*:?[ ]*"
        r"([0-9.]+)\s*(?:mm)?\s*[xX×]\s*"
        r"([0-9.]+)\s*(?:mm)?\s*[xX×]\s*"
        r"([0-9.]+)",
        text,
        re.I,
    )
    if not match:
        return None
    return tuple(float(match.group(i)) for i in range(1, 4))


def _field(text: str, label: str) -> str | None:
    match = re.search(rf"\b{re.escape(label)}\s*:?[ ]*([^\s<]+)", text, re.I)
    return match.group(1).strip() if match else None


def _proportions(text: str) -> dict[str, str | float]:
    result: dict[str, str | float] = {}
    numeric_patterns = {
        "table_percent": r"\bTable\s*%?\s*:?[ ]*([0-9.]+)\s*%",
        "depth_percent": r"\bDepth\s*%?\s*:?[ ]*([0-9.]+)\s*%",
        "length_width_ratio": r"\b(?:L/W Ratio|Ratio)\s*:?[ ]*([0-9.]+)",
    }
    for key, pattern in numeric_patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            result[key] = float(match.group(1))
    for label, key in (
        ("Cut", "cut"),
        ("Polish", "polish"),
        ("Symmetry", "symmetry"),
        ("Fluorescence", "fluorescence"),
        ("Girdle", "girdle"),
        ("Culet", "culet"),
    ):
        value = _field(text, label)
        if value and value != "-":
            result[key] = value
    return result


def _attribution(source: str, url: str, fields: Iterable[str]) -> dict[str, FieldAttribution]:
    return {field: FieldAttribution(source, url) for field in fields}


def _igi_certificate_reference(
    *,
    source: str,
    url: str,
    report_number: str,
    hrefs: Iterable[str],
) -> EvidenceReference:
    igi_href = next(
        (
            href
            for href in hrefs
            if "igi.org" in urlsplit(href).netloc.lower()
            and ("verify-your-report" in urlsplit(href).path or "viewpdf.php" in urlsplit(href).path)
        ),
        None,
    )
    direct_pdf = bool(igi_href and "viewpdf.php" in urlsplit(igi_href).path)
    return EvidenceReference(
        identifier=f"{source}:{report_number}:certificate",
        kind=CERTIFICATE,
        retrieval_key=(
            f"igi-pdf:{report_number}" if direct_pdf else f"igi-report:{report_number}"
        ),
        locator=igi_href or f"igi-report:{report_number}",
        provenance=(ProvenanceStep(source, url),),
        metadata={
            "lab": "IGI",
            "report_number": report_number,
            "format": "pdf" if direct_pdf else "report",
            **({} if direct_pdf else {"resolver": "igi_exact_report"}),
        },
    )


def _direct_rotation_locator(value: str) -> bool:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        return False
    host = parts.netloc.lower()
    query = parse_qs(parts.query)
    if (
        host == "vision.diajewel360.com"
        and parts.path.lower().rstrip("/") == "/vision360.html"
        and bool(query.get("d", [""])[0])
    ):
        return True
    if host == "workshop.360view.link":
        if parts.path.startswith("/view/") and len(parts.path.rstrip("/").split("/")) >= 3:
            return True
        return (
            parts.path.lower().rstrip("/") == "/360viewer/360view.html"
            and bool(query.get("d", [""])[0])
        )
    core_prefix = host.removesuffix(".v360.in")
    if (
        host.endswith(".v360.in")
        and core_prefix.startswith("v360")
        and core_prefix[4:].isdigit()
        and parts.path.lower().rstrip("/") == "/vision360.html"
        and bool(query.get("d", [""])[0])
    ):
        return True
    return (
        host == "d360.tech"
        and parts.path.lower().rstrip("/") == "/view.html"
        and bool(query.get("d", [""])[0])
    )


def _direct_video_locator(value: str) -> bool:
    parts = urlsplit(value)
    return (
        parts.scheme in {"http", "https"}
        and bool(parts.netloc)
        and parts.path.lower().endswith((".mp4", ".m4v", ".mov", ".webm"))
    )


def _motion_references(
    source: str, url: str, report_number: str, parsed: _ParsedHtml
) -> tuple[EvidenceReference, ...]:
    """Retain all distinct exact-stone media advertised by the listing.

    Loupe links are resolved in addition to direct media, but an unlinked
    "360 View" label prompts a lookup only if no concrete source was found.
    """
    values = (*parsed.hrefs, *parsed.media)
    references: list[EvidenceReference] = []
    seen: set[tuple[str, str]] = set()

    for value in values:
        if _direct_rotation_locator(value):
            kind = ROTATION
        elif _direct_video_locator(value):
            kind = VIDEO
        else:
            continue
        key = (str(kind), value)
        if key in seen:
            continue
        seen.add(key)
        references.append(
            EvidenceReference(
                identifier=f"{source}:{report_number}:{kind}:{len(references)}",
                kind=kind,
                retrieval_key=value,
                locator=value,
                provenance=(ProvenanceStep(source, url, {"media_url": value}),),
                metadata={
                    "lab": "IGI",
                    "report_number": report_number,
                    **({"format": "video"} if kind == VIDEO else {}),
                },
            )
        )

    # One certificate-bound lookup can yield either evidence kind or both.
    # Two policy-selectable references share a retrieval key so that only
    # one lookup occurs when both rotation and video are requested.
    loupe_links = tuple(dict.fromkeys(
        value
        for value in values
        if urlsplit(value).netloc.lower() in {"loupe360.com", "www.loupe360.com"}
        and urlsplit(value).scheme in {"http", "https"}
    ))
    has_unlinked_motion = (
        "360°" in parsed.text or "Loading 360" in parsed.text or "360 View" in parsed.text
    )
    if loupe_links or (not references and has_unlinked_motion):
        locator = loupe_links[0] if loupe_links else f"loupe360-report:{report_number}"
        provenance = (
            ProvenanceStep(source, url, {"loupe360_links": loupe_links}),
        )
        for kind in (ROTATION, VIDEO):
            references.append(
                EvidenceReference(
                    identifier=f"{source}:{report_number}:loupe360:{kind}",
                    kind=kind,
                    retrieval_key=f"loupe360-report:{report_number}",
                    locator=locator,
                    provenance=provenance,
                    metadata={
                        "lab": "IGI",
                        "report_number": report_number,
                        "resolver": "loupe360_certificate",
                    },
                )
            )
    return tuple(references)


def _still_references(
    *,
    source: str,
    url: str,
    sku: str,
    parsed: _ParsedHtml,
    hosts: set[str] | None = None,
) -> tuple[EvidenceReference, ...]:
    refs: list[EvidenceReference] = []
    seen: set[str] = set()
    for src, alt in parsed.images:
        parts = urlsplit(src)
        host = parts.netloc.lower()
        if hosts is not None and host not in hosts:
            continue
        if hosts is None and "diamond" not in alt.lower():
            continue
        if parts.scheme not in {"http", "https"}:
            continue
        if src in seen:
            continue
        path = parts.path.lower()
        if not path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        seen.add(src)
        refs.append(
            EvidenceReference(
                identifier=f"{source}:{sku}:still:{len(refs)}",
                kind=STILL,
                retrieval_key=src,
                locator=src,
                provenance=(ProvenanceStep(source, url),),
                metadata={"format": "image"},
            )
        )
    return tuple(refs)


def _diyona_public_record_as_listing(
    http_client: HttpClient, *, url: str, expected_sku: str,
    raw_html: str, response, timeout: float,
) -> ListingRecord:
    """Build an exact certificate-bound listing from Diyona's own public API."""
    record = query_public_diyona_record(
        http_client, page_html=raw_html, sku=expected_sku, timeout=timeout,
    )
    data = record.data
    report = str(data["certificate_number"]).strip().upper()

    def as_decimal(name):
        value = data.get(name)
        return Decimal(str(value)) if value is not None and str(value).strip() else None

    def as_text(name):
        value = data.get(name)
        return str(value).strip() if value is not None and str(value).strip() else None

    carat = as_decimal("carat")
    shape = as_text("shape")
    colour = as_text("color")
    clarity = as_text("clarity")
    dimensions = None
    dims = [as_decimal(k) for k in ("length", "width", "depth_mm")]
    if all(x is not None and x > 0 for x in dims):
        dimensions = tuple(float(x) for x in dims)
    price = as_decimal("markup_price")
    if price is None:
        price = as_decimal("price_usd")

    proportion_names = {
        "ratio": "length_width_ratio", "depth_percent": "depth_percent",
        "table_percent": "table_percent", "cut": "cut",
        "polish": "polish", "symmetry": "symmetry",
        "fluorescence": "fluorescence",
    }
    proportions = {}
    for key, name in proportion_names.items():
        value = data.get(key)
        if value is not None and str(value).strip():
            proportions[name] = float(value) if key in {
                "ratio", "depth_percent", "table_percent"
            } else str(value)

    fields = ["report_number", "lab", "retailer_sku"]
    if shape:
        fields.append("shape")
    if carat is not None:
        fields.append("carat")
    if colour:
        fields.append("colour")
    if clarity:
        fields.append("clarity")
    if dimensions:
        fields.append("dimensions")
    if proportions:
        fields.append("reported_proportions")
    if price is not None:
        fields.extend(("price", "currency", "tax_basis"))
    attribution = _attribution("diyona_public_supabase", record.url, fields)
    attribution["origin"] = FieldAttribution("diyona_listing", url)
    metadata = DiamondMetadata(
        report_number=report,
        lab="IGI",
        retailer_sku=expected_sku,
        origin="lab-grown",
        shape=shape, carat=carat,
        colour=colour.upper() if colour else None,
        clarity=clarity.upper() if clarity else None,
        dimensions=dimensions,
        reported_proportions=proportions,
        price=price, currency="USD" if price is not None else None,
        tax_basis="displayed USD price; tax basis not stated" if price is not None else None,
        attribution=attribution,
    )
    source = "diyona_public_supabase"
    certificate_url = as_text("certificate_url")
    cert_parts = urlsplit(certificate_url or "")
    # Retailer's exact PDF URL is a public CloudFront PDF with a matching
    # report in the filename. Retain as original evidence; validate PDF identity.
    trusted_pdf = (
        cert_parts.scheme == "https"
        and cert_parts.hostname == "dnyvsyhu34v1w.cloudfront.net"
        and cert_parts.path.lower() == f"/pdf/{report.lower()}.pdf"
        and not cert_parts.username and not cert_parts.password
    )
    if trusted_pdf:
        references = [EvidenceReference(
            identifier=f"{source}:{report}:certificate",
            kind=CERTIFICATE, retrieval_key=certificate_url, locator=certificate_url,
            provenance=(record.provenance,),
            metadata={"lab": "IGI", "report_number": report, "format": "pdf"},
        )]
    else:
        references = [_igi_certificate_reference(
            source=source, url=record.url,
            report_number=report, hrefs=(),
        )]

    image_url = as_text("image_url")
    video_url = as_text("video_url")
    parsed_media = _ParsedHtml(
        text="360° View",
        hrefs=(video_url,) if video_url else (),
        images=((image_url, "Diamond"),) if image_url else (),
        media=(),
    )
    references.extend(_still_references(
        source=source, url=record.url, sku=expected_sku, parsed=parsed_media,
    ))
    references.extend(_motion_references(
        source, record.url, report, parsed_media,
    ))
    # Never persist the publicly embedded anonymous API key in the raw HTML.
    return ListingRecord(
        url=url,
        metadata=metadata,
        references=tuple(references),
        provenance=(ProvenanceStep("diyona_listing", url), record.provenance),
        raw_responses=(
            SourceResponse(
                "diyona_listing", _sanitize_retained_html(raw_html),
                response.url, response.headers.get("Content-Type"), True,
            ),
            record.source_response,
        ),
    )


class DiyonaListingProvider:
    """Parse Diyona's exact public /pages/diamond-detail?sku=... route."""

    _hosts = {"diyona.com", "www.diyona.com"}

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, url: str) -> bool:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        return (
            parts.scheme in {"http", "https"}
            and parts.netloc.lower() in self._hosts
            and parts.path.rstrip("/") == "/pages/diamond-detail"
            and bool(query.get("sku", [""])[0])
        )

    def fetch(self, url: str) -> ListingRecord:
        expected_sku = parse_qs(urlsplit(url).query)["sku"][0]
        response = self.http_client.get(url, timeout=self.timeout)
        if response.status_code < 200 or response.status_code >= 300:
            raise RetrievalError(f"Diyona listing returned HTTP {response.status_code}")
        raw, parsed = _parse_html(response.content)

        header = re.search(
            r"([0-9]+(?:\.[0-9]+)?)ct\s+([A-Za-z][A-Za-z -]+?)\s+Lab Diamond",
            parsed.text,
            re.I,
        )
        identity = re.search(
            r"SKU:\s*([A-Za-z0-9]+)\s*(?:·|\||-)\s*IGI\s+([A-Za-z]*\d+)",
            parsed.text,
            re.I,
        )
        # The certified SKU + IGI report is the publishability-critical fact.
        # A carat/shape display heading is useful but not an identity check:
        # live storefront layouts can omit it while showing the certificate.
        if not identity:
            return _diyona_public_record_as_listing(
                self.http_client, url=url, expected_sku=expected_sku,
                raw_html=raw, response=response, timeout=self.timeout,
            )
        sku, report_number = identity.group(1), identity.group(2).upper()
        if sku.upper() != expected_sku.upper():
            raise RetrievalError("Diyona listing SKU does not match the requested exact URL")

        carat = Decimal(header.group(1)) if header else None
        shape = header.group(2).strip() if header else None
        colour = _field(parsed.text, "Color")
        clarity = _field(parsed.text, "Clarity")
        dimensions = _dimensions(parsed.text)
        price_match = re.search(
            r"Diamond Price\s*\$\s*([0-9,]+(?:\.[0-9]+)?)",
            parsed.text,
            re.I,
        )
        price = _decimal(price_match.group(1)) if price_match else None

        fields = ["report_number", "lab", "retailer_sku", "origin"]
        if shape:
            fields.append("shape")
        if carat is not None:
            fields.append("carat")
        if colour:
            fields.append("colour")
        if clarity:
            fields.append("clarity")
        if dimensions:
            fields.append("dimensions")
        if price is not None:
            fields.extend(("price", "currency", "tax_basis"))

        metadata = DiamondMetadata(
            report_number=report_number,
            lab="IGI",
            retailer_sku=sku,
            origin="lab-grown",
            shape=shape,
            carat=carat,
            colour=colour.upper() if colour else None,
            clarity=clarity.upper() if clarity else None,
            dimensions=dimensions,
            reported_proportions=_proportions(parsed.text),
            price=price,
            currency="USD" if price is not None else None,
            tax_basis="displayed price; tax basis not stated" if price is not None else None,
            attribution=_attribution("diyona_listing", url, fields),
        )

        references: list[EvidenceReference] = [
            _igi_certificate_reference(
                source="diyona_listing",
                url=url,
                report_number=report_number,
                hrefs=parsed.hrefs,
            )
        ]
        references.extend(
            _still_references(
                source="diyona_listing",
                url=url,
                sku=sku,
                parsed=parsed,
            )
        )
        references.extend(_motion_references("diyona_listing", url, report_number, parsed))

        sanitized = _sanitize_retained_html(raw)
        return ListingRecord(
            url=url,
            metadata=metadata,
            references=tuple(references),
            provenance=(ProvenanceStep("diyona_listing", url),),
            raw_responses=(
                SourceResponse(
                    "diyona_listing",
                    sanitized,
                    response.url,
                    response.headers.get("Content-Type"),
                    True,
                ),
            ),
        )


class QualityDiamondsListingProvider:
    """Parse Quality Diamonds' exact public buy-loose-diamonds?d=... route."""

    _hosts = {"qualitydiamonds.co.uk", "www.qualitydiamonds.co.uk"}
    _still_hosts = {"assets-images-saas.nivoda.com"}

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, url: str) -> bool:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        return (
            parts.scheme in {"http", "https"}
            and parts.netloc.lower() in self._hosts
            and parts.path.rstrip("/") == "/loose-diamonds/buy-loose-diamonds"
            and bool(query.get("d", [""])[0])
        )

    def fetch(self, url: str) -> ListingRecord:
        expected_id = parse_qs(urlsplit(url).query)["d"][0]
        response = self.http_client.get(url, timeout=self.timeout)
        if response.status_code < 200 or response.status_code >= 300:
            raise RetrievalError(
                f"Quality Diamonds listing returned HTTP {response.status_code}"
            )
        raw, parsed = _parse_html(response.content)

        report = re.search(
            r"Certificate Number:\s*([A-Za-z]*\d+)", parsed.text, re.I
        )
        sku_match = re.search(r"\bID:\s*([0-9]+/[A-Za-z0-9]+)", parsed.text, re.I)
        header = re.search(
            r"([A-Za-z][A-Za-z -]+?),\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s+Carat,\s*"
            r"([A-Z]+),\s*"
            r"(FL|IF|VVS1|VVS2|VS1|VS2|SI1|SI2)\s+"
            r"IGI(?:\s+Lab Grown)?\s+Diamond",
            parsed.text,
            re.I,
        )
        if not report or not sku_match or not header:
            raise RetrievalError(
                "Quality Diamonds exact listing does not expose certificate-bound diamond data"
            )
        sku = sku_match.group(1)
        if sku.lower() != expected_id.lower():
            raise RetrievalError(
                "Quality Diamonds listing ID does not match the requested exact URL"
            )
        report_number = report.group(1).upper()
        shape = header.group(1).strip()
        carat = Decimal(header.group(2))
        colour = header.group(3).upper()
        clarity = header.group(4).upper()
        dimensions = _dimensions(parsed.text)

        inc_vat = re.search(
            r"£\s*([0-9,]+(?:\.[0-9]+)?)\s*\(inc\.\s*VAT\)",
            parsed.text,
            re.I,
        )
        ex_vat = re.search(
            r"£\s*([0-9,]+(?:\.[0-9]+)?)\s*\(ex\.\s*VAT\)",
            parsed.text,
            re.I,
        )
        price = _decimal(inc_vat.group(1)) if inc_vat else None
        origin = "lab-grown" if re.search(r"\bLab Grown Diamond\b", parsed.text, re.I) else None

        fields = [
            "report_number",
            "lab",
            "retailer_sku",
            "shape",
            "carat",
            "colour",
            "clarity",
        ]
        if origin:
            fields.append("origin")
        if dimensions:
            fields.append("dimensions")
        if price is not None:
            fields.extend(("price", "currency", "tax_basis"))

        extra = {}
        if ex_vat:
            extra["price_ex_vat_gbp"] = _decimal(ex_vat.group(1))

        metadata = DiamondMetadata(
            report_number=report_number,
            lab="IGI",
            retailer_sku=sku,
            origin=origin,
            shape=shape,
            carat=carat,
            colour=colour,
            clarity=clarity,
            dimensions=dimensions,
            reported_proportions=_proportions(parsed.text),
            price=price,
            currency="GBP" if price is not None else None,
            tax_basis="inc. VAT" if price is not None else None,
            attribution=_attribution("quality_diamonds_listing", url, fields),
            extra=extra,
        )

        references: list[EvidenceReference] = [
            _igi_certificate_reference(
                source="quality_diamonds_listing",
                url=url,
                report_number=report_number,
                hrefs=parsed.hrefs,
            )
        ]
        references.extend(
            _still_references(
                source="quality_diamonds_listing",
                url=url,
                sku=sku.replace("/", "-"),
                parsed=parsed,
                hosts=self._still_hosts,
            )
        )
        references.extend(
            _motion_references("quality_diamonds_listing", url, report_number, parsed)
        )

        sanitized = _sanitize_retained_html(raw)
        return ListingRecord(
            url=url,
            metadata=metadata,
            references=tuple(references),
            provenance=(ProvenanceStep("quality_diamonds_listing", url),),
            raw_responses=(
                SourceResponse(
                    "quality_diamonds_listing",
                    sanitized,
                    response.url,
                    response.headers.get("Content-Type"),
                    True,
                ),
            ),
        )
