"""Exact-certificate Loupe360/Pixorac indexed JPEG fallback.

Loupe360's public V360Info can return an assets-images.pixorac.com/<encoded
viewer> URL. Its visible player requests /<index>.webp and (as observed in
the #221 bounded source audit) all 256 corresponding /<index>.jpg resources
are also available. This is an independently hosted *proxy*, not proof of
byte identity with the original supplier's Vision360 transport.

The downloader is never enabled for a bare user-supplied Pixorac URL.
It normally requires a certificate-matched resolver; a single explicitly
pinned, independently browser-audited R03/R09 direct viewer may also create
an unverified-identity proxy candidate. No other numeric viewers qualify.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import os
from pathlib import Path
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
CERTIFICATE_FRAME_COUNTS = frozenset({128, 256})
FRAME_LIMIT_BYTES = 1024 * 1024
TOTAL_LIMIT_BYTES = 25 * 1024 * 1024
_TOKEN = re.compile(r"/[A-Za-z0-9_-]{20,1024}={0,2}\Z")


def validated_proxy_root(reference: EvidenceReference) -> str:
    """Accept an exact certificate or one of two individually source-pinned viewers."""
    from .opaque_loupe_viewer import PINNED_VIEWERS
    if reference.metadata.get("r02_browser_observed_cache") is True:
        from .r02_browser_cache import CACHE_REF, REFERENCE_ID, REPORT, validate_root
        if not (
            reference.kind == ROTATION
            and reference.identifier == "ps285166-r02:loupe-report:r02-browser-cache"
            and reference.locator == CACHE_REF
            and reference.retrieval_key == CACHE_REF
            and reference.metadata.get("reference_id") == REFERENCE_ID
            and reference.metadata.get("lab") == "IGI"
            and reference.metadata.get("report_number") == REPORT
            and reference.metadata.get("supplier_frame_count") == FRAME_COUNT
            and reference.metadata.get("supplier_top_index") == 213
            and any(step.source == "loupe360_exact_certificate"
                    and step.locator == Loupe360CertificateResolver.endpoint
                    for step in reference.provenance)
        ):
            raise ValueError("R02 proxy source lacks the exact report/source provenance")
        runner_temp = os.environ.get("RUNNER_TEMP")
        if not runner_temp:
            raise ValueError("R02 cache requires the trusted runner temporary directory")
        cache_file = Path(runner_temp) / "r02-pixorac-root"
        try:
            root = cache_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("R02 audited browser source file is unavailable") from exc
        return validate_root(root)

    unverified_viewer = reference.metadata.get("loupe360_proxy_exact_viewer") is True
    pin = PINNED_VIEWERS.get(reference.metadata.get("reference_id")) if unverified_viewer else None
    if unverified_viewer:
        # Only actual browser-audited direct viewer -> proxy correspondences.
        # Neither numeric viewer identifier is promoted to an IGI/GIA report.
        if not (
            pin is not None
            and reference.kind == ROTATION
            and reference.metadata.get("loupe360_viewer_source") == pin["viewer"]
            and reference.metadata.get("identity_status") == "unverified"
            and reference.locator == pin["proxy"]
            and reference.retrieval_key == pin["proxy"]
            and any(step.source == "loupe360_pinned_exact_viewer_proxy"
                    and step.locator == pin["viewer"] for step in reference.provenance)
            and not reference.metadata.get("report_number")
            and not reference.metadata.get("lab")
        ):
            raise ValueError("Pixorac source does not match any pinned viewer provenance")
    elif (
        reference.kind != ROTATION
        or reference.metadata.get("loupe360_proxy_exact_certificate") is not True
        or not reference.metadata.get("report_number")
        or not reference.metadata.get("lab")
        or not any(step.source == "loupe360_exact_certificate" for step in reference.provenance)
    ):
        raise ValueError("Pixorac source requires a certified or pinned-viewer resolution")

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
    if urlsplit(decoded).scheme != "https" or (
        decoded != pin["source_viewer"] if unverified_viewer
        else not Loupe360CertificateResolver._is_supported_rotation_url(decoded)
    ):
        raise ValueError("Pixorac wrapper does not name the exact trusted supplier viewer")
    frame_count = reference.metadata.get("supplier_frame_count")
    top_index = reference.metadata.get("supplier_top_index")
    if unverified_viewer:
        expected_count = pin["frame_count"]
        if frame_count != expected_count or isinstance(frame_count, bool):
            raise ValueError("Pixorac frame count does not match source-specific contract")
    else:
        if (
            isinstance(frame_count, bool)
            or not isinstance(frame_count, int)
            or frame_count not in CERTIFICATE_FRAME_COUNTS
        ):
            raise ValueError("Pixorac frame count does not match certificate contract")
        expected_count = frame_count
    if unverified_viewer and top_index is None:
        # No known face-up hint: keep it absent rather than fabricating zero.
        return locator
    try:
        index = int(top_index)
    except (ValueError, TypeError) as exc:
        raise ValueError("Pixorac top_index missing") from exc
    if isinstance(top_index, bool) or not 0 <= index < expected_count:
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
        count = reference.metadata["supplier_frame_count"]
        frames: list[str] = []
        hashes: set[str] = set()
        hashes_by_index: list[str] = []
        dimensions: tuple[int, int] | None = None
        total = 0
        for index in range(count):
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
            hashes_by_index.append(digest)
            frames.append(base64.b64encode(payload).decode("ascii"))

        # Reject static placeholders masquerading as a complete indexed rotation; do not assume
        # any one frame is an entire rotation.
        minimum_distinct = (count * 15 + 15) // 16
        if len(hashes) < minimum_distinct:
            raise InvalidPayloadError("Pixorac proxy frames do not show a complete varying rotation")

        is_r02 = reference.metadata.get("r02_browser_observed_cache") is True
        if is_r02:
            # Original read-only R02 audit independently verified these 3
            # ordered byte anchors, plus all 256 distinct 819x819 JPEGs.
            anchors = {
                0: "93bc22d267a879e68589a115fbebadf3bfa338503bf9b47ad4d8d5e86418ad1d",
                213: "33b0d2848058db1c360fe212536a09e3dafd68b3857d150264b02b1f99455185",
                255: "b2eb1257e78889824338e9ffd0ac164e001723b9ae1b0366d062303500b2673c",
            }
            if (len(hashes) != FRAME_COUNT or dimensions != (819, 819)
                    or any(hashes_by_index[i] != digest for i, digest in anchors.items())):
                raise InvalidPayloadError("R02 proxy JPEG source failed audited hash anchors")

        # Do not persist the opaque browser-observed cache path in the public
        # reference manifest, evidence payload, or Actions logs.
        safe_root = reference.locator if is_r02 else root
        metadata = {
            **reference.metadata,
            "supplier": "loupe360-pixorac-proxy",
            "frame_count": count,
            "dimensions": dimensions,
            "source_root": safe_root,
            "source_transport": ("r02_exact_browser_sha_pinned_indexed_proxy_jpeg"
                                 if is_r02 else
                                 "pinned_unverified_viewer_indexed_proxy_jpeg"
                                 if reference.metadata.get("loupe360_proxy_exact_viewer") is True
                                 else "certificate_matched_indexed_proxy_jpeg"),
            "supplier_original_bytes_verified": False,
            "source_frame_sha256_distinct": len(hashes),
        }
        bundle = {
            "schema_version": "sparkles-indexed-proxy-rotation/1",
            "source": "loupe360-pixorac-proxy",
            "source_root": safe_root,
            "frame_count": count,
            "dimensions": list(dimensions),
            "face_up_hint": (int(reference.metadata["supplier_top_index"])
                             if reference.metadata["supplier_top_index"] is not None else None),
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
        count = bundle.get("frame_count", FRAME_COUNT)
        if isinstance(count, bool) or count not in (128, 255, 256):
            raise InvalidPayloadError("Unexpected indexed proxy frame count")
        if count in CERTIFICATE_FRAME_COUNTS:
            try:
                validated_proxy_root(raw.reference)
            except ValueError as exc:
                raise InvalidPayloadError("Indexed proxy certificate provenance invalid") from exc
        if count == 255:
            # The ONLY accepted 255-image contract is native R09: actual 0..254
            # verified; original viewer advertised 255 and index 255 was 404.
            from .opaque_loupe_viewer import R09_REFERENCE_ID
            if not (
                raw.reference.metadata.get("loupe360_proxy_exact_viewer") is True
                and raw.reference.metadata.get("reference_id") == R09_REFERENCE_ID
                and raw.reference.metadata.get("supplier_frame_count") == 255
                and raw.metadata.get("frame_count") == 255
            ):
                raise InvalidPayloadError("255-position proxy is not the pinned R09 source")
            try:
                validated_proxy_root(raw.reference)
            except ValueError as exc:
                raise InvalidPayloadError("R09 indexed proxy provenance invalid") from exc
        if not isinstance(frames_encoded, list) or len(frames_encoded) != count:
            raise InvalidPayloadError("Indexed proxy rotation has incomplete source-declared frames")
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
        minimum_distinct = (count * 15 + 15) // 16
        if len(hashes) < minimum_distinct:
            raise InvalidPayloadError("Indexed proxy rotation is effectively static")
        hint = bundle.get("face_up_hint")
        if hint is None and raw.reference.metadata.get("loupe360_proxy_exact_viewer") is True:
            pass  # Reviewer-visible orientation is unknown, not guessed.
        elif isinstance(hint, bool) or not isinstance(hint, int) or not 0 <= hint < count:
            raise InvalidPayloadError("Indexed proxy face-up hint out of range")
        metadata = {
            **raw.metadata,
            "supplier": "loupe360-pixorac-proxy",
            "frame_count": count,
            "dimensions": tuple(declared_dimensions),
            "sequence_complete": True,
            "ordering": f"proxy indexed source positions 0..{count - 1}",
            "physical_angle_calibrated": False,
            "supplier_original_bytes_verified": False,
        }
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                "loupe360_pixorac_proxy_indexed_jpeg",
                raw.reference.locator,
                {"frame_count": count, "supplier_original_bytes_verified": False},
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
