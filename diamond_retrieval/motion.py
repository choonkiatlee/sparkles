"""Network-free ordering and validation for progressive 256-frame rotations."""
from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from PIL import Image

from diamond360.d360_source import (
    FRAME_COUNT,
    PACK_COUNTS,
    PACK_START_SERIALS,
    canonical_progressive_positions as _legacy_canonical_progressive_positions,
    ordered_positions as _legacy_ordered_positions,
    validate_scramble as _legacy_validate_scramble,
)

from .errors import InvalidPayloadError
from .models import (
    ROTATION,
    ProvenanceStep,
    RawEvidence,
    RotationEvidence,
    RotationFrame,
)


def canonical_progressive_positions(bits: int = 8) -> dict[int, int]:
    """Return the audited progressive serial -> 1-based viewer-slot mapping."""
    return _legacy_canonical_progressive_positions(bits)


def validate_scramble(scramble: list[list[int]]) -> None:
    """Validate the seven audited progressive permutation levels."""
    _legacy_validate_scramble(scramble)


def ordered_positions(scramble: list[list[int]]) -> tuple[int, ...]:
    """Return progressive serial order as zero-based final source indices."""
    mapping = _legacy_ordered_positions(scramble)
    return tuple(mapping[serial] - 1 for serial in range(1, FRAME_COUNT + 1))


_VISION360_AES_KEY = b"2606198511121984"


def decode_vision360_scramble(ciphertext: str) -> list[list[int]]:
    """Decode the public Vision360 AES-CBC/PKCS#7 scramble payload.

    The public player parses the same UTF-8 literal as both AES key and IV,
    decrypts the Base64 string in CBC mode, removes PKCS#7 padding, then parses
    the resulting JSON. Validation remains fail-closed through validate_scramble.
    """
    if not isinstance(ciphertext, str) or not ciphertext:
        raise ValueError("Vision360 scramble must be non-empty Base64 text")
    try:
        encrypted = base64.b64decode(ciphertext, validate=True)
    except Exception as exc:
        raise ValueError("Vision360 scramble is not valid Base64") from exc
    if not encrypted or len(encrypted) % 16:
        raise ValueError("Vision360 scramble ciphertext is not AES block-aligned")
    try:
        decryptor = Cipher(
            algorithms.AES(_VISION360_AES_KEY),
            modes.CBC(_VISION360_AES_KEY),
        ).decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        decoded = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Vision360 scramble decryption failed") from exc
    if not isinstance(decoded, list):
        raise ValueError("Vision360 scramble plaintext must be a JSON array")
    validate_scramble(decoded)
    return decoded


def validate_jpeg_bytes(payload: bytes) -> tuple[int, int]:
    """Validate one complete original JPEG and return its decoded dimensions."""
    if not isinstance(payload, bytes) or not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise InvalidPayloadError("frame is not a complete JPEG")
    try:
        with Image.open(BytesIO(payload)) as image:
            image.load()
            if image.format != "JPEG":
                raise InvalidPayloadError("decoded frame is not JPEG")
            return tuple(image.size)
    except InvalidPayloadError:
        raise
    except Exception as exc:
        raise InvalidPayloadError(f"invalid JPEG: {exc}") from exc


def _decode_jpeg(encoded: str, *, batch: int, stored_position: int) -> tuple[bytes, tuple[int, int]]:
    if not isinstance(encoded, str):
        raise InvalidPayloadError(
            f"progressive batch {batch} position {stored_position} is not base64 text"
        )
    try:
        payload = base64.b64decode("".join(encoded.split()), validate=True)
    except Exception as exc:
        raise InvalidPayloadError(
            f"invalid base64 JPEG in progressive batch {batch} position {stored_position}"
        ) from exc
    try:
        dimensions = validate_jpeg_bytes(payload)
    except InvalidPayloadError as exc:
        raise InvalidPayloadError(
            f"invalid JPEG in progressive batch {batch} position {stored_position}: {exc}"
        ) from exc
    return payload, dimensions


class ProgressiveRotationProcessor:
    """Decode a canonical in-memory 4/4/8/16/32/64/128 source bundle."""

    format_name = "progressive-rotation-json"

    def supports(self, raw: RawEvidence) -> bool:
        return raw.reference.kind == ROTATION and raw.format == self.format_name

    def process(self, raw: RawEvidence) -> tuple[RotationEvidence, ...]:
        try:
            bundle = json.loads(raw.payload)
        except Exception as exc:
            raise InvalidPayloadError("progressive rotation bundle is not valid JSON") from exc
        if not isinstance(bundle, dict):
            raise InvalidPayloadError("progressive rotation bundle must be an object")
        if bundle.get("schema_version") != "sparkles-progressive-motion/1":
            raise InvalidPayloadError("unsupported progressive rotation bundle schema")

        scramble = bundle.get("scramble")
        if not isinstance(scramble, list):
            raise InvalidPayloadError("progressive rotation bundle is missing scramble levels")
        try:
            validate_scramble(scramble)
            targets = ordered_positions(scramble)
        except ValueError as exc:
            raise InvalidPayloadError(str(exc)) from exc

        batches = bundle.get("batches")
        if not isinstance(batches, list):
            raise InvalidPayloadError("progressive rotation bundle is missing batches")
        by_number: dict[int, dict[str, Any]] = {}
        for batch in batches:
            if not isinstance(batch, dict) or not isinstance(batch.get("batch"), int):
                raise InvalidPayloadError("invalid progressive batch record")
            number = batch["batch"]
            if number in by_number:
                raise InvalidPayloadError(f"duplicate progressive batch {number}")
            by_number[number] = batch
        if set(by_number) != set(range(1, len(PACK_COUNTS) + 1)):
            raise InvalidPayloadError("progressive rotation requires exactly batches 1..7")

        declared_dimensions = bundle.get("dimensions")
        expected_dimensions: tuple[int, int] | None = None
        if declared_dimensions is not None:
            if (
                not isinstance(declared_dimensions, list)
                or len(declared_dimensions) != 2
                or not all(isinstance(value, int) and value > 0 for value in declared_dimensions)
            ):
                raise InvalidPayloadError("invalid declared progressive frame dimensions")
            expected_dimensions = tuple(declared_dimensions)

        frame_records: list[RotationFrame | None] = [None] * FRAME_COUNT
        for batch_number, (expected_count, start_serial) in enumerate(
            zip(PACK_COUNTS, PACK_START_SERIALS), 1
        ):
            record = by_number[batch_number]
            frames = record.get("frames")
            if (
                not isinstance(frames, list)
                or len(frames) != expected_count
            ):
                raise InvalidPayloadError(
                    f"progressive batch {batch_number} expected {expected_count} frames"
                )
            for stored_position, encoded in enumerate(frames):
                jpeg, dimensions = _decode_jpeg(
                    encoded,
                    batch=batch_number,
                    stored_position=stored_position,
                )
                if expected_dimensions is not None and dimensions != expected_dimensions:
                    raise InvalidPayloadError(
                        f"frame dimensions {dimensions} disagree with declared {expected_dimensions}"
                    )
                serial = start_serial + stored_position
                source_index = targets[serial - 1]
                if frame_records[source_index] is not None:
                    raise InvalidPayloadError(
                        f"progressive order repeats source index {source_index}"
                    )
                frame_records[source_index] = RotationFrame(
                    source_index=source_index,
                    payload=jpeg,
                    dimensions=dimensions,
                    sha256=hashlib.sha256(jpeg).hexdigest(),
                    stored_position=stored_position,
                    source_batch=str(batch_number),
                )

        if any(frame is None for frame in frame_records):
            missing = [index for index, frame in enumerate(frame_records) if frame is None]
            raise InvalidPayloadError(
                f"incomplete progressive rotation; missing source indices {missing}"
            )
        frames = tuple(frame for frame in frame_records if frame is not None)
        if len(frames) != FRAME_COUNT:
            raise InvalidPayloadError("progressive rotation did not produce 256 frames")

        source = str(bundle.get("source") or "progressive-rotation")
        viewer_url = bundle.get("viewer_url")
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                source,
                viewer_url if isinstance(viewer_url, str) else raw.reference.locator,
                {
                    "ordering": "scramble inverse permutation + progressive odd-position interleave",
                    "frame_count": FRAME_COUNT,
                },
            ),
        )
        metadata = dict(raw.metadata)
        metadata.update(
            {
                "supplier": source,
                "frame_count": FRAME_COUNT,
                "dimensions": expected_dimensions or frames[0].dimensions,
                "sequence_complete": True,
                "physical_angle_calibrated": False,
                "ordering": "scramble inverse permutation + progressive odd-position interleave",
            }
        )
        return (
            RotationEvidence(
                identifier=raw.reference.identifier,
                kind=ROTATION,
                provenance=provenance,
                payload=raw.payload,
                metadata=metadata,
                source_responses=raw.source_responses,
                frames=frames,
                face_up_hint=bundle.get("face_up_hint"),
            ),
        )
