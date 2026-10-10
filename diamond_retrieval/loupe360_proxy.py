"""Exact-certificate Loupe360/Pixorac indexed JPEG fallback.

Loupe360's public V360Info can return an assets-images.pixorac.com/<encoded
viewer> URL. Its visible player requests /<index>.webp and (as observed in
the #221 bounded source audit) all 256 corresponding /<index>.jpg resources
are also available. This is an independently hosted *proxy*, not proof of
byte identity with the original supplier's Vision360 transport.

The downloader is never enabled for a bare user-supplied Pixorac URL:
a successfully matched Loupe360 certificate resolver must create the
candidate and annotate it as an exact-report source.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from urllib.parse import urlsplit

from .errors import InvalidPayloadError, MissingEvidenceError
from .models import (
    ROTATION, EvidenceReference, ProvenanceStep, RawEvidence,
    RotationEvidence, RotationFrame,
)
from .motion import validate_jpeg_bytes
from .protocols import HttpClient
from .resolvers import Loupe360CertificateResolver

FRAME_COUNT = 256
FRAME_LIMIT_BYTES = 1024 * 1024
TOTAL_LIMIT_BYTES = 25 * 1024 * 1024
_TOKEN = re.compile(r"/[A-Za-z0-9_-]{20,1024}={0,2}\Z")


def validated_proxy_root(reference: EvidenceReference) -> str:
    """Accept only a URL from a successful exact-lab-and-report resolver."""
    if (
        reference.kind != ROTATION
        or reference.metadata.get("loupe360_proxy_exact_certificate") is not True
        or not reference.metadata.get("report_number")
        or not reference.metadata.get("lab")
        or not any(step.source == "loupe360_exact_certificate" for step in reference.provenance)
    ):
        raise ValueError("Pixorac source requires an exact-certificate Loupe360 resolution")

    locator = reference.locator or ""
    if len(locator) > 1600:
        raise ValueError("Pixorac source URL too long")
    parts = urlsplit(locator)
    if (
        parts.scheme != "https" or parts.netloc != "assets-images.pixorac.com"
        or parts.query or parts.fragment or not _TOKEN.fullmatch(parts.path)
    ):
        raise ValueError("Untrusted Pixorac indexed-image root")
    # Exact encoded viewer comes from the matched V360Info; do not infer one
    # from a report, inventory ID or arbitrary CDN path.
    try:
        decoded = Loupe360CertificateResolver._unwrap_v360(locator)
    except ValueError as exc:
        raise ValueError("Pixorac encoded viewer invalid") from exc
    if (urlsplit(decoded).scheme != "https"
            or not Loupe360CertificateResolver._is_supported_rotation_url(decoded)):
        raise ValueError("Pixorac wrapper does not name a supported supplier viewer")
    frame_count = reference.metadata.get("supplier_frame_count")
    top_index = reference.metadata.get("supplier_top_index")
    if frame_count != FRAME_COUNT or isinstance(frame_count, bool):
        raise ValueError("Pixorac V360Info must advertise exactly 256 frames")
    try:
        index = int(top_index)
    except (ValueError, TypeError) as exc:
        raise ValueError("Pixorac top_index missing") from exc
    if isinstance(top_index, bool) or not 0 <= index < FRAME_COUNT:
        raise ValueError("Pixorac top_index out of range")
    return locator


class Loupe360ProxyRotationDownloader:
    """Read exact indexed JPEG assets from the certificate-matched proxy."""

    def __init__(self, http_client: HttpClient, *, timeout: float = 15.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        try:
            validated_proxy_root(reference)
            return True
        except ValueError:
            return False

    def download(self, reference: EvidenceReference) -> RawEvidence:
        root = validated_proxy_root(reference)
        frames: list[str] = []
        hashes: set[str] = set()
        dimensions: tuple[int, int] | None = None
        total = 0
        for index in range(FRAME_COUNT):
            url = f"{root}/{index}.jpg"
            response = self.http_client.get(url, timeout=self.timeout)
            if response.status_code == 404:
                raise MissingEvidenceError(f"Pixorac indexed frame {index} returned 404")
            if response.status_code != 200:
                raise InvalidPayloadError(
                    f"Pixorac indexed frame {index} returned HTTP {response.status_code}"
                )
            # Prevent cross-domain redirects. The shared HTTP client separately
            # rejects private/non-public DNS and validates every redirect hop.
            if response.url != url:
                raise InvalidPayloadError("Pixorac indexed frame redirected from exact source")
            payload = response.content
            if len(payload) > FRAME_LIMIT_BYTES:
                raise InvalidPayloadError(f"Pixorac indexed frame {index} exceeds size limit")
            total += len(payload)
            if total > TOTAL_LIMIT_BYTES:
                raise InvalidPayloadError("Pixorac complete rotation exceeds size limit")
            size = validate_jpeg_bytes(payload)
            if dimensions is None:
                dimensions = size
            elif dimensions != size:
                raise InvalidPayloadError("Pixorac rotation frame dimensions changed")
            digest = hashlib.sha256(payload).hexdigest()
            hashes.add(digest)
            frames.append(base64.b64encode(payload).decode("ascii"))

        # Reject static placeholders masquerading as 256 images; do not assume
        # any one frame is an entire rotation.
        if len(hashes) < 240:
            raise InvalidPayloadError("Pixorac proxy frames do not show a complete varying rotation")

        metadata = {
            **reference.metadata,
            "supplier": "loupe360-pixorac-proxy",
            "frame_count": FRAME_COUNT,
            "dimensions": dimensions,
            "source_root": root,
            "source_transport": "certificate_matched_indexed_proxy_jpeg",
            "supplier_original_bytes_verified": False,
            "source_frame_sha256_distinct": len(hashes),
        }
        bundle = {
            "schema_version": "sparkles-indexed-proxy-rotation/1",
            "source": "loupe360-pixorac-proxy",
            "source_root": root,
            "dimensions": list(dimensions),
            "face_up_hint": int(reference.metadata["supplier_top_index"]),
            "frames": frames,
        }
        return RawEvidence(
            reference=reference,
            payload=json.dumps(bundle, separators=(",", ":")).encode("utf-8"),
            format="indexed-proxy-rotation-json",
            media_type="application/json",
            metadata=metadata,
        )


class IndexedProxyRotationProcessor:
    """Network-free validation of a complete, already-indexed rotation."""

    def supports(self, raw: RawEvidence) -> bool:
        return raw.reference.kind == ROTATION and raw.format == "indexed-proxy-rotation-json"

    def process(self, raw: RawEvidence) -> tuple[RotationEvidence, ...]:
        try:
            bundle = json.loads(raw.payload)
        except Exception as exc:
            raise InvalidPayloadError("Pixorac indexed rotation payload is invalid JSON") from exc
        if not isinstance(bundle, dict) or bundle.get("schema_version") != "sparkles-indexed-proxy-rotation/1":
            raise InvalidPayloadError("Unsupported indexed rotation bundle")
        frames_encoded = bundle.get("frames")
        declared_dimensions = bundle.get("dimensions")
        if not isinstance(frames_encoded, list) or len(frames_encoded) != FRAME_COUNT:
            raise InvalidPayloadError("Indexed proxy rotation requires exactly 256 frames")
        if (
            not isinstance(declared_dimensions, list)
            or len(declared_dimensions) != 2
            or not all(isinstance(x, int) and not isinstance(x, bool) and 0 < x < 10000
                       for x in declared_dimensions)
        ):
            raise InvalidPayloadError("Invalid indexed rotation dimensions")

        frames = []
        hashes = set()
        for index, encoded in enumerate(frames_encoded):
            if not isinstance(encoded, str):
                raise InvalidPayloadError(f"Indexed proxy frame {index} is not base64")
            try:
                jpeg = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise InvalidPayloadError(f"Indexed proxy frame {index} is invalid base64") from exc
            if len(jpeg) > FRAME_LIMIT_BYTES:
                raise InvalidPayloadError("Indexed proxy frame exceeds size limit")
            size = validate_jpeg_bytes(jpeg)
            if list(size) != declared_dimensions:
                raise InvalidPayloadError("Indexed proxy frame dimensions mismatch")
            sha = hashlib.sha256(jpeg).hexdigest()
            hashes.add(sha)
            frames.append(RotationFrame(
                source_index=index,
                payload=jpeg,
                dimensions=size,
                sha256=sha,
                stored_position=index,
                source_batch="indexed-proxy",
            ))
        if len(hashes) < 240:
            raise InvalidPayloadError("Indexed proxy rotation is effectively static")
        hint = bundle.get("face_up_hint")
        if isinstance(hint, bool) or not isinstance(hint, int) or not 0 <= hint < FRAME_COUNT:
            raise InvalidPayloadError("Indexed proxy face-up hint out of range")
        metadata = {
            **raw.metadata,
            "supplier": "loupe360-pixorac-proxy",
            "frame_count": FRAME_COUNT,
            "dimensions": tuple(declared_dimensions),
            "sequence_complete": True,
            "ordering": "proxy indexed source positions 0..255",
            "physical_angle_calibrated": False,
            "supplier_original_bytes_verified": False,
        }
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                "loupe360_pixorac_proxy_indexed_jpeg",
                raw.reference.locator,
                {"frame_count": FRAME_COUNT, "supplier_original_bytes_verified": False},
            ),
        )
        return (RotationEvidence(
            identifier=raw.reference.identifier,
            kind=ROTATION,
            provenance=provenance,
            payload=raw.payload,
            metadata=metadata,
            frames=tuple(frames),
            face_up_hint=hint,
        ),)
