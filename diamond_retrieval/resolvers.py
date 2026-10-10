"""Deterministic exact-report resolvers used by retailer adapters."""
from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import parse_qs, quote, urlsplit

from .protocols import HttpClient
from .models import (
    CERTIFICATE,
    ROTATION,
    STILL,
    VIDEO,
    EvidenceReference,
    ListingRecord,
    ProvenanceStep,
)


def _report_number(reference: EvidenceReference) -> str | None:
    value = reference.metadata.get("report_number")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    if reference.locator:
        parts = urlsplit(reference.locator)
        query = parse_qs(parts.query)
        value = query.get("r", [None])[0]
        if value:
            return value.strip().upper()
        if reference.locator.startswith("igi-report:"):
            return reference.locator.split(":", 1)[1].strip().upper()
        if reference.locator.startswith("loupe360-report:"):
            return reference.locator.split(":", 1)[1].strip().upper()
    return None


class IgiReportPdfResolver:
    """Resolve an exact IGI report number to IGI's public report-PDF endpoint."""

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind != CERTIFICATE:
            return False
        if reference.metadata.get("resolver") == "igi_exact_report":
            return True
        if not reference.locator:
            return False
        parts = urlsplit(reference.locator)
        return (
            parts.netloc.lower() in {"igi.org", "www.igi.org"}
            and "verify-your-report" in parts.path
        )

    def resolve(
        self, listing: ListingRecord, reference: EvidenceReference
    ) -> tuple[EvidenceReference, ...]:
        report = _report_number(reference)
        if not report:
            raise ValueError("IGI exact-report resolver requires a report number")
        metadata = dict(reference.metadata)
        metadata.pop("resolver", None)
        metadata["format"] = "pdf"
        metadata["report_number"] = report
        locator = f"https://api.igi.org/viewpdf.php?r={quote(report, safe='')}"
        return (
            EvidenceReference(
                identifier=f"{reference.identifier}:pdf",
                kind=CERTIFICATE,
                retrieval_key=f"igi-pdf:{report}",
                locator=locator,
                provenance=(
                    ProvenanceStep(
                        "igi_exact_report",
                        locator,
                        {"report_number": report},
                    ),
                ),
                metadata=metadata,
            ),
        )


class Loupe360CertificateResolver:
    """Resolve an exact certificate to its public Loupe/Nivoda media record."""

    endpoint = "https://g.nivoda.com/graphql-public-loupe360"
    _query = """query($cert:String!){
      certificate_by_cert_number(cert_number:$cert) {
        id certNumber lab image video pdfUrl
        v360 { url frame_count top_index id }
      }
    }"""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        timeout: float = 20.0,
        include_image: bool = False,
    ) -> None:
        self.http_client = http_client
        self.timeout = timeout
        self.include_image = include_image

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind not in {ROTATION, VIDEO}:
            return False
        if reference.metadata.get("resolver") == "loupe360_certificate":
            return True
        if self.http_client is None:
            return False
        if not reference.locator or not _report_number(reference):
            return False
        return urlsplit(reference.locator).netloc.lower() in {
            "loupe360.com",
            "www.loupe360.com",
        }

    @staticmethod
    def _unwrap_v360(value: str) -> str:
        parts = urlsplit(value)
        if parts.netloc.lower() != "assets-images.pixorac.com":
            return value
        token = parts.path.strip("/").split("/", 1)[0]
        if not token:
            raise ValueError("Loupe360 v360 wrapper has no encoded supplier URL")
        try:
            decoded = base64.urlsafe_b64decode(
                token + "=" * (-len(token) % 4)
            ).decode("utf-8")
        except Exception as exc:
            raise ValueError("Loupe360 v360 wrapper is not valid URL-safe Base64") from exc
        return decoded

    @staticmethod
    def _is_supported_rotation_url(value: str) -> bool:
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
        if (
            host in {"v360.in", "www.v360.in"}
            and parts.path.lower().rstrip("/") == "/viewer4.0/vision360.html"
            and bool(query.get("d", [""])[0])
        ):
            return True
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

    @staticmethod
    def _is_direct_video_url(value: str) -> bool:
        parts = urlsplit(value)
        return (
            parts.scheme in {"http", "https"}
            and bool(parts.netloc)
            and parts.path.lower().endswith((".mp4", ".m4v", ".mov", ".webm"))
        )

    def _fallback_reference(
        self, reference: EvidenceReference, report: str
    ) -> tuple[EvidenceReference, ...]:
        metadata = dict(reference.metadata)
        metadata.pop("resolver", None)
        metadata["report_number"] = report
        metadata["lab"] = metadata.get("lab") or "IGI"
        locator = (
            "https://loupe360.com/diamond/"
            f"{quote(report, safe='')}/video/500/500"
        )
        return (
            EvidenceReference(
                identifier=f"{reference.identifier}:loupe360",
                kind=reference.kind,
                retrieval_key=f"loupe360:{report}:video",
                locator=locator,
                provenance=(
                    ProvenanceStep(
                        "loupe360_exact_certificate",
                        locator,
                        {"report_number": report, "lab": metadata["lab"]},
                    ),
                ),
                metadata=metadata,
            ),
        )

    def resolve(
        self, listing: ListingRecord, reference: EvidenceReference
    ) -> tuple[EvidenceReference, ...]:
        report = _report_number(reference)
        if not report:
            raise ValueError("Loupe360 exact-certificate resolver requires a report number")
        if self.http_client is None:
            # Backward-compatible unresolved viewer reference. The default factory
            # injects HTTP when supplier media support is enabled.
            return self._fallback_reference(reference, report)

        request_body = json.dumps(
            {"query": self._query, "variables": {"cert": report}},
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.http_client.post(
            self.endpoint,
            timeout=self.timeout,
            content=request_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(
                f"Loupe360 certificate lookup returned HTTP {response.status_code}"
            )
        try:
            payload = json.loads(response.content)
        except Exception as exc:
            raise ValueError("Loupe360 certificate lookup returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Loupe360 certificate lookup returned a non-object response")
        if payload.get("errors"):
            raise ValueError("Loupe360 certificate lookup returned GraphQL errors")
        record = (payload.get("data") or {}).get("certificate_by_cert_number")
        if not isinstance(record, dict):
            raise ValueError("Loupe360 certificate lookup returned no certificate record")

        returned_report = str(record.get("certNumber") or "").strip().upper()
        if returned_report != report:
            raise ValueError(
                f"Loupe360 certificate mismatch: requested {report}, returned "
                f"{returned_report or 'missing'}"
            )
        expected_lab = str(reference.metadata.get("lab") or listing.metadata.lab or "").strip().upper()
        returned_lab = str(record.get("lab") or "").strip().upper()
        if expected_lab and returned_lab and returned_lab != expected_lab:
            raise ValueError(
                f"Loupe360 lab mismatch: expected {expected_lab}, returned {returned_lab}"
            )

        metadata = dict(reference.metadata)
        metadata.pop("resolver", None)
        metadata.update(
            {
                "report_number": report,
                "lab": returned_lab or expected_lab or "IGI",
                "loupe360_certificate_id": record.get("id"),
                "loupe360_lookup_sha256": hashlib.sha256(response.content).hexdigest(),
            }
        )
        references: list[EvidenceReference] = []
        v360 = record.get("v360")
        if isinstance(v360, dict):
            wrapped = v360.get("url")
            if isinstance(wrapped, str) and wrapped:
                try:
                    locator = self._unwrap_v360(wrapped)
                except ValueError:
                    # Preserve malformed/unknown viewer references for a
                    # structured unsupported attempt; never block a separately
                    # supported video asset from the same certificate record.
                    locator = wrapped
                rotation_metadata = {
                    **metadata,
                    "supplier_frame_count": v360.get("frame_count"),
                    "supplier_top_index": v360.get("top_index"),
                    "loupe360_v360_id": v360.get("id"),
                    "loupe360_v360_url": wrapped,
                }
                references.append(
                    EvidenceReference(
                        identifier=f"{reference.identifier}:supplier-rotation",
                        kind=ROTATION,
                        retrieval_key=locator,
                        locator=locator,
                        provenance=(
                            ProvenanceStep(
                                "loupe360_exact_certificate",
                                self.endpoint,
                                {
                                    "report_number": report,
                                    "certificate_id": record.get("id"),
                                    "frame_count": v360.get("frame_count"),
                                    "top_index": v360.get("top_index"),
                                },
                            ),
                        ),
                        metadata=rotation_metadata,
                    )
                )

        video = record.get("video")
        if isinstance(video, str) and self._is_direct_video_url(video):
            video_metadata = {
                **metadata,
                "format": "video",
                "loupe360_video_url": video,
            }
            references.append(
                EvidenceReference(
                    identifier=f"{reference.identifier}:direct-video",
                    kind=VIDEO,
                    retrieval_key=video,
                    locator=video,
                    provenance=(
                        ProvenanceStep(
                            "loupe360_exact_certificate",
                            self.endpoint,
                            {
                                "report_number": report,
                                "certificate_id": record.get("id"),
                            },
                        ),
                    ),
                    metadata=video_metadata,
                )
            )

        # Reference-only enrichment opts in to the returned still; regular
        # retailer ingestion retains its existing candidate set by default.
        image_url = record.get("image")
        if self.include_image and isinstance(image_url, str):
            image_parts = urlsplit(image_url)
            if (image_parts.scheme == "https" and image_parts.hostname
                    and image_parts.username is None and image_parts.password is None
                    and image_parts.port in (None, 443)):
                references.append(
                    EvidenceReference(
                        identifier=f"{reference.identifier}:supplier-still",
                        kind=STILL,
                        retrieval_key=image_url,
                        locator=image_url,
                        provenance=(
                            ProvenanceStep(
                                "loupe360_exact_certificate",
                                self.endpoint,
                                {"report_number": report, "certificate_id": record.get("id")},
                            ),
                        ),
                        metadata={**metadata, "loupe360_image_url": image_url},
                    )
                )

        if references:
            return tuple(references)

        raise ValueError(
            "Loupe360 certificate record exposes no supported exact rotation or direct video"
        )

