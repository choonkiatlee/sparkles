"""Two independently browser-audited PriceScope Loupe numeric-viewer transports.

Only R03 and R09 exact *curated viewer* -> *pinned proxy* associations may
use this resolver. Neither numeric viewer token is an independently certified
lab report. Preserve both reference identities as unverified.

R03 has 256 ordered proxy-returned JPEGs; R09's native cache genuinely has
255 distinct indexed JPEGs (0..254, index 255 = HTTP 404). Do not fabricate
a 256th frame or mislabel proxy bytes as supplier originals.
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
R09_REFERENCE_ID = "ps285166-r09"
R09_VIEWER = "https://loupe360.com/diamond/1498922544"
R09_PROXY_ROOT = (
    "https://assets-images.pixorac.com/"
    "aHR0cHM6Ly92aWV3LmdlbTM2MC5pbi9nZW0zNjAuaHRtbD9kPTI1MDcyNDExMzYtVTYwLTMxMUE="
)
PINNED_VIEWERS = {
    R03_REFERENCE_ID: {
        "viewer": R03_VIEWER,
        "proxy": R03_PROXY_ROOT,
        "source_viewer": "https://labgrowns3.s3.ap-southeast-1.amazonaws.com/stoneimages360.html?d=1146555_B2C",
        "frame_count": 256,
        "source_audit": "https://github.com/choonkiatlee/sparkles/actions/runs/38077622287",
    },
    R09_REFERENCE_ID: {
        "viewer": R09_VIEWER,
        "proxy": R09_PROXY_ROOT,
        "source_viewer": "https://view.gem360.in/gem360.html?d=2507241136-U60-311A",
        "frame_count": 255,
        "source_audit": "https://github.com/choonkiatlee/sparkles/actions/runs/38077937306",
    },
}


class PinnedOpaqueLoupeViewerResolver:
    """Only the two reviewed exact viewer links, without certification claims."""

    def __init__(self, http_client: HttpClient, *, timeout: float = 15.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        reference_id = reference.metadata.get("reference_id")
        pin = PINNED_VIEWERS.get(reference_id)
        return bool(
            pin is not None
            and reference.kind == ROTATION
            and reference.locator == pin["viewer"]
            and reference.retrieval_key == pin["viewer"]
            and not reference.metadata.get("report_number")
            and any(
                step.source == "reference_media_source"
                and step.locator == pin["viewer"]
                and step.details.get("provider") == "loupe360"
                for step in reference.provenance
            )
        )

    def resolve(self, listing: ListingRecord, reference: EvidenceReference) -> tuple[EvidenceReference, ...]:
        if not self.supports(reference):
            raise ValueError("Unreviewed numeric Loupe viewer")
        reference_id = reference.metadata["reference_id"]
        pin = PINNED_VIEWERS[reference_id]
        if (
            listing.url != "reference:" + reference_id
            or listing.metadata.lab is not None
            or listing.metadata.report_number is not None
        ):
            raise ValueError("Pinned numeric Loupe viewer cannot become a certificate association")
        token = urlsplit(pin["viewer"]).path.rsplit("/", 1)[-1]
        request = json.dumps({
            "query": Loupe360CertificateResolver._query,
            "variables": {"cert": token},
        }, separators=(",", ":")).encode()
        response = self.http_client.post(
            Loupe360CertificateResolver.endpoint, timeout=self.timeout,
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
        if not isinstance(v360, dict) or v360.get("url") != pin["proxy"]:
            raise ValueError("Pinned exact viewer returned another media source")
        count = v360.get("frame_count")
        if isinstance(count, bool) or count != pin["frame_count"]:
            raise ValueError("Pinned exact viewer changed its source-native frame count")
        raw_top = v360.get("top_index")
        top = None
        if isinstance(raw_top, (int, str)) and not isinstance(raw_top, bool):
            value = str(raw_top)
            if value.isdigit() and int(value) < count:
                top = int(value)
        return (EvidenceReference(
            identifier=reference.identifier + ":pinned-proxy", kind=ROTATION,
            retrieval_key=pin["proxy"], locator=pin["proxy"],
            provenance=(ProvenanceStep(
                "loupe360_pinned_exact_viewer_proxy", pin["viewer"],
                {"reference_id": reference_id, "source_audit": pin["source_audit"],
                 "supplier_original_bytes_verified": False,
                 "independent_certificate_verified": False},
            ),),
            metadata={
                "reference_id": reference_id,
                "loupe360_proxy_exact_viewer": True,
                "loupe360_viewer_source": pin["viewer"],
                "supplier_frame_count": count,
                "supplier_top_index": top,
                "identity_status": "unverified",
            },
        ),)
