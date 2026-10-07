import base64
import hashlib
import io
import json
import unittest
from pathlib import Path

from PIL import Image

from diamond_retrieval import (
    ROTATION,
    EvidenceReference,
    InvalidPayloadError,
    ProvenanceStep,
    RawEvidence,
)
from diamond_retrieval.motion import (
    ProgressiveRotationProcessor,
    canonical_progressive_positions,
    decode_vision360_scramble,
    ordered_positions,
    validate_scramble,
)


FIXTURES = Path(__file__).parent / "fixtures" / "diamond_retrieval"
AUDITS = json.loads((FIXTURES / "motion-audits.json").read_text())["audits"]


def _jpeg(index: int) -> bytes:
    image = Image.new("RGB", (8, 8), (index % 251, (index * 7) % 251, (index * 13) % 251))
    image.putpixel((index % 8, (index // 8) % 8), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _reference(source: str, viewer: str) -> EvidenceReference:
    return EvidenceReference(
        identifier=f"{source}:rotation",
        kind=ROTATION,
        retrieval_key=viewer,
        locator=viewer,
        provenance=(ProvenanceStep(source, viewer),),
        metadata={"supplier": source},
    )


def _raw_from_audit(audit, *, corrupt_index=None, omit_batch=None, scramble=None):
    batches = []
    by_batch = {}
    for frame in audit["frames"]:
        by_batch.setdefault(frame["batch"], []).append(frame)

    for batch_number in range(1, 8):
        if batch_number == omit_batch:
            continue
        frames = sorted(
            by_batch[batch_number],
            key=lambda item: item["stored_position"],
        )
        payloads = []
        for frame in frames:
            payload = (
                b"not-a-jpeg"
                if frame["source_index"] == corrupt_index
                else _jpeg(frame["source_index"])
            )
            payloads.append(base64.b64encode(payload).decode("ascii"))
        batches.append(
            {
                "batch": batch_number,
                "source_url": f"https://supplier.test/{batch_number}.json",
                "frames": payloads,
            }
        )

    bundle = {
        "schema_version": "sparkles-progressive-motion/1",
        "source": audit["source_pipeline"],
        "viewer_url": audit["viewer"],
        "dimensions": audit["dimensions"],
        "scramble": scramble if scramble is not None else audit["scramble"],
        "batches": batches,
    }
    return RawEvidence(
        reference=_reference(audit["source_pipeline"], audit["viewer"]),
        payload=json.dumps(bundle, separators=(",", ":")).encode(),
        media_type="application/json",
        format="progressive-rotation-json",
    )


class ProgressiveMotionContractTests(unittest.TestCase):
    def test_canonical_progressive_positions_match_legacy_d360_contract(self):
        from diamond360.d360_source import canonical_progressive_positions as legacy

        self.assertEqual(
            canonical_progressive_positions(),
            legacy(),
        )

    def test_public_player_aes_scramble_decodes_to_audited_maps(self):
        for audit in AUDITS:
            decoded = decode_vision360_scramble(audit["encrypted_scramble"])
            self.assertEqual(decoded, audit["scramble"])

    def test_diajewel_full_audit_mapping_is_reproduced(self):
        self._assert_full_audit(AUDITS[0])

    def test_workshop_full_audit_mapping_is_reproduced(self):
        self._assert_full_audit(AUDITS[1])

    def _assert_full_audit(self, audit):
        raw = _raw_from_audit(audit)
        evidence = ProgressiveRotationProcessor().process(raw)
        self.assertEqual(len(evidence), 1)
        rotation = evidence[0]
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual(
            [frame.source_index for frame in rotation.frames],
            list(range(256)),
        )

        expected = {frame["source_index"]: frame for frame in audit["frames"]}
        for frame in rotation.frames:
            contract = expected[frame.source_index]
            self.assertEqual(frame.source_batch, str(contract["batch"]))
            self.assertEqual(frame.stored_position, contract["stored_position"])
            self.assertEqual(frame.dimensions, (8, 8))
            self.assertEqual(frame.sha256, hashlib.sha256(frame.payload).hexdigest())

    def test_invalid_scramble_fails_closed(self):
        audit = AUDITS[0]
        bad = [list(level) for level in audit["scramble"]]
        bad[0] = [0, 0, 2, 3]
        with self.assertRaises(ValueError):
            validate_scramble(bad)
        with self.assertRaises(InvalidPayloadError):
            ProgressiveRotationProcessor().process(
                _raw_from_audit(audit, scramble=bad)
            )

    def test_incomplete_batches_fail_closed(self):
        with self.assertRaises(InvalidPayloadError):
            ProgressiveRotationProcessor().process(
                _raw_from_audit(AUDITS[0], omit_batch=6)
            )

    def test_corrupt_jpeg_fails_entire_sequence(self):
        with self.assertRaises(InvalidPayloadError):
            ProgressiveRotationProcessor().process(
                _raw_from_audit(AUDITS[0], corrupt_index=137)
            )

    def test_ordered_positions_is_a_complete_permutation(self):
        positions = ordered_positions(AUDITS[0]["scramble"])
        self.assertEqual(len(positions), 256)
        self.assertEqual(set(positions), set(range(256)))


if __name__ == "__main__":
    unittest.main()
