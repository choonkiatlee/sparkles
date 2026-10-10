"""Single reviewed unverified R03 Loupe numeric-viewer source contract.

This is NOT an IGI/GIA certificate lookup or proof of certified identity.
The original PriceScope-linked exact Loupe viewer loaded the pinned Pixorac
proxy in the read-only browser audit #253, and all 256 indexed JPEG bytes
were checked in the independent read-only source validation.

Never generalize this resolver to arbitrary numeric/UUID Loupe URLs.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from .models import ROTATION, EvidenceReference, ListingRecord, ProvenanceStep
from .protocols import HttpClient
from .resolvers import Loupe360CertificateResolver

R03_REFERENCE_ID = "ps285166-r03"
R03_VIEWER = "https://loupe360.com/diamond/636493231"
R03_PROXY_ROOT = (
    "https://assets-images.pixorac.com/"
    "aHR0cHM6Ly9sYWJncm93bnMzLnMzLmFwLXNvdXRoZWFzdC0xLmFtYXpvbmF3cy5jb20v"
    "c3RvbmVpbWFnZXMzNjAuaHRtbD9kPTExNDY1NTVfQjJD"
)
SOURCE_EVIDENCE = "https://github.com/choonkiatlee/sparkles/actions/runs/38077622287"


class PinnedOpaqueLoupeViewerResolver:
    """Only R03's reviewed exact numeric viewer, preserving unverified identity."""

    def __init__(self, http_client: HttpClient, *, timeout: float = 15.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        return (
            reference.kind == ROTATION
            and reference.locator == R03_VIEWER
            and reference.retrieval_key == R03_VIEWER
            and reference.metadata.get("reference_id") == R03_REFERENCE_ID
            and not reference.metadata.get("report_number")
            and any(
                step.source == "reference_media_source"
                and step.locator == R03_VIEWER
                and step.metadata.get("provider") == "loupe360"
                for step in reference.provenance
            )
        )

    def resolve(self, listing: ListingRecord, reference: EvidenceReference) -> tuple[EvidenceReference, ...]:
        if not self.supports(reference) or (
            listing.url != "reference:" + R03_REFERENCE_ID
            or listing.metadata.lab is not None
            or listing.metadata.report_number is not None
        ):
            raise ValueError("Pinned numeric Loupe source may not become a certificate association")
        token = urlsplit(R03_VIEWER).path.rsplit("/", 1)[-1]
        request = json.dumps({
            "query": Loupe360CertificateResolver._query,
            "variables": {"cert": token},
        }, separators=(",", ":")).encode()
        response = self.http_client.post(
            Loupe360CertificateResolver.endpoint,
            timeout=self.timeout,
            content=request,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise ValueError("Pinned exact viewer metadata unavailable")
        try:
            payload = json.loads(response.content)
            record = (payload.get("data") or {}).get("certificate_by_cert_number")
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("Pinned exact viewer metadata invalid") from exc
        if payload.get("errors") or not isinstance(record, dict):
            raise ValueError("Pinned exact viewer metadata missing")
        v360 = record.get("v360")
        if not isinstance(v360, dict) or v360.get("url") != R03_PROXY_ROOT:
            raise ValueError("Pinned exact viewer returned another media source")
        count = v360.get("frame_count")
        if count != 256 or isinstance(count, bool):
            raise ValueError("Pinned exact viewer does not advertise 256 indexed frames")
        # Top orientation not reported for this viewer. Never invent an angle.
        raw_top = v360.get("top_index")
        top = None
        if isinstance(raw_top, (int, str)) and not isinstance(raw_top, bool):
            value = str(raw_top)
            if value.isdigit() and int(value) < 256:
                top = int(value)
        return (EvidenceReference(
            identifier=reference.identifier + ":pinned-proxy",
            kind=ROTATION,
            retrieval_key=R03_PROXY_ROOT,
            locator=R03_PROXY_ROOT,
            provenance=(ProvenanceStep(
                "loupe360_pinned_exact_viewer_proxy", R03_VIEWER,
                {"reference_id": R03_REFERENCE_ID, "source_audit": SOURCE_EVIDENCE,
                 "supplier_original_bytes_verified": False,
                 "independent_certificate_verified": False},
            ),),
            metadata={
                "reference_id": R03_REFERENCE_ID,
                "loupe360_proxy_exact_viewer": True,
                "loupe360_viewer_source": R03_VIEWER,
                "supplier_frame_count": 256,
                "supplier_top_index": top,
                "identity_status": "unverified",
            },
        ),)
