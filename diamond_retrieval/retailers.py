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
    return _SECRET_PATTERN.sub(r"\1[redacted]\3", text)


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


def _motion_reference(source: str, url: str, report_number: str, parsed: _ParsedHtml) -> EvidenceReference | None:
    values = (*parsed.hrefs, *parsed.media)
    direct_rotation = next(
        (value for value in values if _direct_rotation_locator(value)),
        None,
    )
    if direct_rotation:
        return EvidenceReference(
            identifier=f"{source}:{report_number}:rotation",
            kind=ROTATION,
            retrieval_key=direct_rotation,
            locator=direct_rotation,
            provenance=(ProvenanceStep(source, url),),
            metadata={"lab": "IGI", "report_number": report_number},
        )

    direct_video = next(
        (value for value in values if _direct_video_locator(value)),
        None,
    )
    if direct_video:
        return EvidenceReference(
            identifier=f"{source}:{report_number}:video",
            kind=VIDEO,
            retrieval_key=direct_video,
            locator=direct_video,
            provenance=(ProvenanceStep(source, url),),
            metadata={
                "lab": "IGI",
                "report_number": report_number,
                "format": "video",
            },
        )

    candidates = [
        value
        for value in values
        if "loupe360.com" in urlsplit(value).netloc.lower()
    ]
    if candidates:
        locator = candidates[0]
        return EvidenceReference(
            identifier=f"{source}:{report_number}:rotation",
            kind=ROTATION,
            retrieval_key=locator,
            locator=locator,
            provenance=(ProvenanceStep(source, url),),
            metadata={
                "lab": "IGI",
                "report_number": report_number,
                "resolver": "loupe360_certificate",
            },
        )
    if "360°" in parsed.text or "Loading 360" in parsed.text or "360 View" in parsed.text:
        return EvidenceReference(
            identifier=f"{source}:{report_number}:rotation",
            kind=ROTATION,
            retrieval_key=f"loupe360-report:{report_number}",
            locator=f"loupe360-report:{report_number}",
            provenance=(ProvenanceStep(source, url),),
            metadata={
                "lab": "IGI",
                "report_number": report_number,
                "resolver": "loupe360_certificate",
            },
        )
    return None


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
        if not header or not identity:
            raise RetrievalError("Diyona exact listing no longer exposes certificate-bound diamond data")
        sku, report_number = identity.group(1), identity.group(2).upper()
        if sku.upper() != expected_sku.upper():
            raise RetrievalError("Diyona listing SKU does not match the requested exact URL")

        carat = Decimal(header.group(1))
        shape = header.group(2).strip()
        colour = _field(parsed.text, "Color")
        clarity = _field(parsed.text, "Clarity")
        dimensions = _dimensions(parsed.text)
        price_match = re.search(
            r"Diamond Price\s*\$\s*([0-9,]+(?:\.[0-9]+)?)",
            parsed.text,
            re.I,
        )
        price = _decimal(price_match.group(1)) if price_match else None

        fields = ["report_number", "lab", "retailer_sku", "origin", "shape", "carat"]
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
        motion = _motion_reference("diyona_listing", url, report_number, parsed)
        if motion:
            references.append(motion)

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
        motion = _motion_reference(
            "quality_diamonds_listing", url, report_number, parsed
        )
        if motion:
            references.append(motion)

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
