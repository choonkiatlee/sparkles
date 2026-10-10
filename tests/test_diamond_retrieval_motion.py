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
    HttpResponse,
    InvalidPayloadError,
    ProvenanceStep,
    RawEvidence,
)
from diamond_retrieval.motion_sources import (
    Core360RotationDownloader,
    D360RotationDownloader,
    DiajewelRotationDownloader,
    FilesOnSkyRotationDownloader,
    Gem360RotationDownloader,
    Labgrowns3RotationDownloader,
    RemoteV360RotationDownloader,
    WorkshopRotationDownloader,
)
from diamond_retrieval.motion import (
    ProgressiveRotationProcessor,
    canonical_progressive_positions,
    decode_vision360_scramble,
    ordered_positions,
    validate_scramble,
)


FIXTURES = Path(__file__).parent / "fixtures" / "diamond_retrieval"
_MOTION_FIXTURE = json.loads((FIXTURES / "motion-audits.json").read_text())
AUDITS = _MOTION_FIXTURE["audits"]
D360_AUDITS = _MOTION_FIXTURE["d360_audits"]


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
        "dimensions": [8, 8],
        "scramble": scramble if scramble is not None else audit["scramble"],
        "batches": batches,
    }
    return RawEvidence(
        reference=_reference(audit["source_pipeline"], audit["viewer"]),
        payload=json.dumps(bundle, separators=(",", ":")).encode(),
        media_type="application/json",
        format="progressive-rotation-json",
    )






def _d360_source_responses(d360_audit, *, item_id="NEW-D360-1", still_matches=True):
    from diamond360.d360_source import KNOWN_SOURCES, PACK_COUNTS, PACK_START_SERIALS

    scramble = KNOWN_SOURCES[d360_audit["item_id"]]["scramble"]
    targets = ordered_positions(scramble)
    root = f"https://media.d360.us/imaged/{item_id}"
    still = _jpeg(0)
    bootstrap = {
        "width": 8,
        "height": 8,
        "quality": 4,
        "scramble": d360_audit["encrypted_scramble"],
        "image": base64.b64encode(still if still_matches else _jpeg(1)).decode("ascii"),
    }
    responses = {
        root + "/metadata.json": (b'{"fixture":true}', "application/json"),
        root + "/0.json": (
            json.dumps(bootstrap, separators=(",", ":")).encode(),
            "application/json",
        ),
        root + "/still.jpg": (still, "image/jpeg"),
    }
    for batch, (count, start_serial) in enumerate(
        zip(PACK_COUNTS, PACK_START_SERIALS), 1
    ):
        payload = []
        for stored_position in range(count):
            serial = start_serial + stored_position
            source_index = targets[serial - 1]
            payload.append(base64.b64encode(_jpeg(source_index)).decode("ascii"))
        responses[f"{root}/{batch}.json"] = (
            json.dumps(payload, separators=(",", ":")).encode(),
            "application/json",
        )
    return responses


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(url)
        value = self.responses.get(url)
        if value is None:
            return HttpResponse(404, url, {"Content-Type": "text/plain"}, b"missing")
        content, media_type = value
        return HttpResponse(200, url, {"Content-Type": media_type}, content)


def _progressive_source_responses(audit, source_root, *, version):
    by_batch = {}
    for frame in audit["frames"]:
        by_batch.setdefault(frame["batch"], []).append(frame)
    bootstrap = {
        "width": 8,
        "height": 8,
        "quality": 4,
        "version": version,
        "scramble": audit["encrypted_scramble"],
        "image": base64.b64encode(_jpeg(0)).decode("ascii"),
    }
    responses = {}
    metadata_url = source_root + "/0.json" + ("?version=" if audit["source_pipeline"] == "workshop" else "")
    responses[metadata_url] = (
        json.dumps(bootstrap, separators=(",", ":")).encode(),
        "application/json",
    )
    for batch in range(1, 8):
        frames = sorted(by_batch[batch], key=lambda item: item["stored_position"])
        encoded = [
            base64.b64encode(_jpeg(frame["source_index"])).decode("ascii")
            for frame in frames
        ]
        responses[f"{source_root}/{batch}.json?version={version}"] = (
            json.dumps(encoded, separators=(",", ":")).encode(),
            "application/json",
        )
    return responses


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



    def test_d360_public_scramble_decodes_to_legacy_audited_maps(self):
        from diamond360.d360_source import KNOWN_SOURCES

        for audit in D360_AUDITS:
            with self.subTest(item_id=audit["item_id"]):
                self.assertEqual(
                    decode_vision360_scramble(audit["encrypted_scramble"]),
                    KNOWN_SOURCES[audit["item_id"]]["scramble"],
                )

    def test_d360_downloader_accepts_new_item_id_without_allowlist(self):
        audit = D360_AUDITS[0]
        item_id = "NEW-D360-1"
        viewer = f"https://d360.tech/view.html?d={item_id}"
        http = FakeHttpClient(_d360_source_responses(audit, item_id=item_id))
        downloader = D360RotationDownloader(http)
        ref = _reference("d360-tech", viewer)

        self.assertTrue(downloader.supports(ref))
        raw = downloader.download(ref)
        rotation = ProgressiveRotationProcessor().process(raw)[0]
        self.assertEqual([frame.source_index for frame in rotation.frames], list(range(256)))
        self.assertEqual(rotation.frames[0].payload, _jpeg(0))
        root = f"https://media.d360.us/imaged/{item_id}"
        self.assertEqual(
            http.calls,
            [root + "/metadata.json", root + "/0.json", root + "/still.jpg"]
            + [f"{root}/{batch}.json" for batch in range(1, 8)],
        )

    def test_d360_preview_must_match_still(self):
        audit = D360_AUDITS[0]
        item_id = "NEW-D360-1"
        viewer = f"https://d360.tech/view.html?d={item_id}"
        http = FakeHttpClient(
            _d360_source_responses(audit, item_id=item_id, still_matches=False)
        )
        with self.assertRaises(InvalidPayloadError):
            D360RotationDownloader(http).download(_reference("d360-tech", viewer))

    def test_diajewel_downloader_accepts_new_exact_item_id_and_uses_public_version(self):
        audit = AUDITS[0]
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-NEW123"
        root = "https://vision.diajewel360.com/imaged/VL-NEW123"
        http = FakeHttpClient(_progressive_source_responses(audit, root, version=1))
        downloader = DiajewelRotationDownloader(http)
        ref = _reference("diajewel", viewer)

        self.assertTrue(downloader.supports(ref))
        raw = downloader.download(ref)
        self.assertEqual(raw.format, "progressive-rotation-json")
        rotation = ProgressiveRotationProcessor().process(raw)[0]
        self.assertEqual([frame.source_index for frame in rotation.frames], list(range(256)))
        self.assertEqual(
            http.calls,
            [root + "/0.json"] + [f"{root}/{batch}.json?version=1" for batch in range(1, 8)],
        )
        self.assertEqual(len(raw.source_responses), 8)

    def test_workshop_downloader_accepts_new_exact_item_id_and_core360_alias(self):
        audit = AUDITS[1]
        viewers = (
            "https://workshop.360view.link/view/NEW-ABC-42",
            "https://workshop.360view.link/360viewer/360view.html?d=NEW-ABC-42",
        )
        root = "https://data1.360view.link/data/1/imaged/NEW-ABC-42"
        for viewer in viewers:
            with self.subTest(viewer=viewer):
                http = FakeHttpClient(_progressive_source_responses(audit, root, version=2))
                downloader = WorkshopRotationDownloader(http)
                ref = _reference("workshop", viewer)
                self.assertTrue(downloader.supports(ref))
                raw = downloader.download(ref)
                rotation = ProgressiveRotationProcessor().process(raw)[0]
                self.assertEqual(len(rotation.frames), 256)
                self.assertEqual(
                    http.calls,
                    [root + "/0.json?version="]
                    + [f"{root}/{batch}.json?version=2" for batch in range(1, 8)],
                )

    def test_core360_downloader_uses_same_origin_progressive_transport(self):
        audit = AUDITS[0]
        viewer = "https://v3603703.v360.in/vision360.html?d=NGS-05-413"
        root = "https://v3603703.v360.in/imaged/NGS-05-413"
        responses = _progressive_source_responses(audit, root, version=1)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        http = FakeHttpClient(responses)
        downloader = Core360RotationDownloader(http)
        ref = _reference("core360", viewer)

        self.assertTrue(downloader.supports(ref))
        raw = downloader.download(ref)
        rotation = ProgressiveRotationProcessor().process(raw)[0]
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual(rotation.metadata["supplier"], "core360")
        self.assertEqual(rotation.metadata["dimensions"], (8, 8))
        self.assertFalse(rotation.metadata["physical_angle_calibrated"])
        self.assertEqual(
            http.calls,
            [root + "/0.json?version="]
            + [f"{root}/{batch}.json?version=1" for batch in range(1, 8)],
        )

        wrong = _reference(
            "core360",
            "https://example.com/vision360.html?d=NGS-05-413",
        )
        self.assertFalse(downloader.supports(wrong))


    def test_loupe_v360_remote_media_root_downloads_original_ordered_frames(self):
        # IGI LG781646632 was resolved by Loupe360 to this exact viewer,
        # but previously returned "no downloader supports reference".
        viewer = (
            "https://v360.in/viewer4.0/vision360.html?"
            "d=VDC-32-50&surl=https://s10.v360.in/images/company/1546/"
        )
        root = "https://s10.v360.in/images/company/1546/imaged/VDC-32-50"
        responses = _progressive_source_responses(AUDITS[0], root, version=1)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        http = FakeHttpClient(responses)
        downloader = RemoteV360RotationDownloader(http)
        ref = _reference("loupe360", viewer)

        self.assertTrue(downloader.supports(ref))
        raw = downloader.download(ref)
        frames = ProgressiveRotationProcessor().process(raw)[0].frames
        self.assertEqual(len(frames), 256)
        self.assertEqual([f.source_index for f in frames], list(range(256)))
        self.assertEqual(frames[0].payload, _jpeg(0))
        self.assertEqual(raw.metadata["supplier"], "v360-remote")
        self.assertEqual(
            http.calls,
            [root + "/0.json?version="]
            + [f"{root}/{n}.json?version=1" for n in range(1, 8)],
        )

    def test_default_composition_registers_remote_v360_downloader(self):
        from diamond_retrieval import default_config
        viewer = (
            "https://v360.in/viewer4.0/vision360.html?"
            "d=VDC-32-50&surl=https://s10.v360.in/images/company/1546/"
        )
        config = default_config(FakeHttpClient({}))
        supporting = [
            downloader for downloader in config.downloaders
            if downloader.supports(_reference("loupe360", viewer))
        ]
        self.assertEqual(len(supporting), 1)
        self.assertIsInstance(supporting[0], RemoteV360RotationDownloader)

    def test_gem360_lg833634461_original_progressive_transport(self):
        from diamond_retrieval import default_config
        from diamond_retrieval.resolvers import Loupe360CertificateResolver

        item = "2208261115-MV25-13A"
        viewer = f"https://view.gem360.in/gem360.html?d={item}"
        root = f"https://videos.gem360.in/imaged/{item}"
        responses = _progressive_source_responses(AUDITS[0], root, version=1)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        client = FakeHttpClient(responses)
        reference = _reference("gem360", viewer)
        downloader = Gem360RotationDownloader(client)

        self.assertTrue(Loupe360CertificateResolver._is_supported_rotation_url(viewer))
        self.assertTrue(downloader.supports(reference))
        raw = downloader.download(reference)
        rotations = ProgressiveRotationProcessor().process(raw)
        self.assertEqual(len(rotations), 1)
        self.assertEqual(len(rotations[0].frames), 256)
        self.assertEqual([f.source_index for f in rotations[0].frames], list(range(256)))
        self.assertEqual(rotations[0].metadata["supplier"], "gem360")
        self.assertTrue(rotations[0].metadata["sequence_complete"])
        self.assertEqual(
            client.calls,
            [root + "/0.json?version="] +
            [f"{root}/{n}.json?version=1" for n in range(1, 8)],
        )
        registered = [
            item for item in default_config(FakeHttpClient({})).downloaders
            if item.supports(reference)
        ]
        self.assertEqual(len(registered), 1)
        self.assertIsInstance(registered[0], Gem360RotationDownloader)

    def test_gem360_accepts_legacy_exact_path_and_benign_display_flags(self):
        item = "2302241224-VR-536"
        downloader = Gem360RotationDownloader(FakeHttpClient({}))
        for viewer in (
            f"https://view.gem360.in/gem360/{item}/gem360-{item}.html",
            f"https://view.gem360.in/gem360.html?controls=0&d={item}",
            f"https://view.gem360.in/gem360.html?btn=0&controls=0&d={item}&sv=0&v=0",
        ):
            with self.subTest(viewer=viewer):
                self.assertTrue(downloader.supports(_reference("gem360", viewer)))

    def test_gem360_rejects_lookalikes_and_unsafe_or_ambiguous_urls(self):
        item = "2208261115-MV25-13A"
        good = f"https://view.gem360.in/gem360.html?d={item}"
        client = FakeHttpClient({})
        downloader = Gem360RotationDownloader(client)
        for bad in (
            good.replace("https://", "http://"),
            good.replace("view.gem360.in", "view.gem360.in.evil.test"),
            good.replace("view.gem360.in", "127.0.0.1"),
            good.replace(item, "../other"),
            good.replace(item, "%2Fetc"),
            good + "&d=OTHER",
            good + "&surl=https://127.0.0.1",
            good + "#fragment",
            good.replace("gem360.html", "other.html"),
            good.replace("view.gem360.in/", "view.gem360.in:443/"),
            good + "&controls=2",
        ):
            with self.subTest(url=bad):
                self.assertFalse(downloader.supports(_reference("gem360", bad)))
        self.assertEqual(client.calls, [])


    def test_filesonsky_r05_original_vision360_transport(self):
        from diamond_retrieval import default_config
        from diamond_retrieval.resolvers import Loupe360CertificateResolver

        viewer = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
        root = "https://www.filesonsky.com/v360/imaged/659844"
        responses = _progressive_source_responses(AUDITS[0], root, version=1)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        client = FakeHttpClient(responses)
        reference = _reference("filesonsky", viewer)
        downloader = FilesOnSkyRotationDownloader(client)
        self.assertTrue(Loupe360CertificateResolver._is_supported_rotation_url(viewer))
        self.assertTrue(downloader.supports(reference))
        rotations = ProgressiveRotationProcessor().process(downloader.download(reference))
        self.assertEqual(len(rotations), 1)
        self.assertEqual(len(rotations[0].frames), 256)
        self.assertEqual([f.source_index for f in rotations[0].frames], list(range(256)))
        self.assertEqual(rotations[0].frames[0].payload, _jpeg(0))
        self.assertEqual(rotations[0].metadata["supplier"], "filesonsky")
        self.assertTrue(rotations[0].metadata["sequence_complete"])
        self.assertEqual(
            client.calls,
            [root + "/0.json?version="] +
            [f"{root}/{n}.json?version=1" for n in range(1, 8)],
        )
        registered = [
            item for item in default_config(FakeHttpClient({})).downloaders
            if item.supports(reference)
        ]
        self.assertEqual(len(registered), 1)
        self.assertIsInstance(registered[0], FilesOnSkyRotationDownloader)

    def test_filesonsky_rejects_unsafe_or_ambiguous_urls_without_network(self):
        from diamond_retrieval.resolvers import Loupe360CertificateResolver
        viewer = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
        client = FakeHttpClient({})
        downloader = FilesOnSkyRotationDownloader(client)
        for bad in (
            viewer.replace("https://", "http://"),
            viewer.replace("www.filesonsky.com", "www.filesonsky.com.evil.test"),
            viewer.replace("www.filesonsky.com", "127.0.0.1"),
            viewer.replace("659844", "..%2fother"),
            viewer.replace("659844", ""),
            viewer + "&d=OTHER",
            viewer + "&surl=https://127.0.0.1",
            viewer + "#fragment",
            viewer.replace("Vision360.HTML", "other.html"),
            viewer.replace("www.filesonsky.com/", "www.filesonsky.com:443/"),
        ):
            with self.subTest(url=bad):
                self.assertFalse(downloader.supports(_reference("filesonsky", bad)))
                self.assertFalse(Loupe360CertificateResolver._is_supported_rotation_url(bad))
        self.assertEqual(client.calls, [])

    def test_filesonsky_incomplete_original_frames_fail_closed(self):
        viewer = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
        root = "https://www.filesonsky.com/v360/imaged/659844"
        responses = _progressive_source_responses(AUDITS[0], root, version=1)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        responses[root + "/5.json?version=1"] = (b"[]", "application/json")
        with self.assertRaises(InvalidPayloadError):
            FilesOnSkyRotationDownloader(
                FakeHttpClient(responses)
            ).download(_reference("filesonsky", viewer))

    def test_labgrowns3_s3_recovers_exact_complete_original_frames(self):
        # The public KVideo player for R06/R10 requests imaged/<id>/0.json
        # and 1..7.json; the actual audited bootstraps use v2 / v1.
        for item, version in (
            ("1210811_B2C", 2),
            ("1165252_B2C", 1),
        ):
            with self.subTest(item=item):
                host = "https://labgrowns3.s3.ap-southeast-1.amazonaws.com"
                viewer = f"{host}/stoneimages360.html?d={item}"
                root = f"{host}/imaged/{item}"
                responses = _progressive_source_responses(
                    AUDITS[0], root, version=version,
                )
                responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
                client = FakeHttpClient(responses)
                downloader = Labgrowns3RotationDownloader(client)
                self.assertTrue(downloader.supports(_reference("labgrowns3", viewer)))
                raw = downloader.download(_reference("labgrowns3", viewer))
                rotations = ProgressiveRotationProcessor().process(raw)
                self.assertEqual(len(rotations), 1)
                motion = rotations[0]
                self.assertEqual(len(motion.frames), 256)
                self.assertEqual(
                    [frame.source_index for frame in motion.frames],
                    list(range(256)),
                )
                self.assertEqual(motion.frames[0].payload, _jpeg(0))
                self.assertEqual(motion.metadata["supplier"], "labgrowns3")
                self.assertTrue(motion.metadata["sequence_complete"])
                self.assertEqual(
                    client.calls,
                    [root + "/0.json?version="] +
                    [f"{root}/{n}.json?version={version}" for n in range(1, 8)],
                )
                from diamond_retrieval import default_config
                config = default_config(FakeHttpClient({}))
                self.assertEqual(
                    sum(d.supports(_reference("labgrowns3", viewer))
                        for d in config.downloaders), 1,
                )

    def test_labgrowns3_rejects_lookalikes_and_invalid_ids_without_network(self):
        host = "https://labgrowns3.s3.ap-southeast-1.amazonaws.com"
        good = f"{host}/stoneimages360.html?d=1210811_B2C"
        http = FakeHttpClient({})
        downloader = Labgrowns3RotationDownloader(http)
        self.assertTrue(downloader.supports(_reference("labgrowns3", good)))
        for bad in (
            good.replace("https://", "http://"),
            good.replace(host, "https://evil.test"),
            good.replace(host, host + ".evil.test"),
            good.replace("1210811_B2C", "../1210811_B2C"),
            good.replace("1210811_B2C", "%2Fetc"),
            good + "&surl=https://127.0.0.1",
            good + "&d=1165252_B2C",
            good + "#other",
            good.replace("stoneimages360.html", "other.html"),
            good.replace("1210811_B2C", ""),
        ):
            with self.subTest(url=bad):
                self.assertFalse(downloader.supports(_reference("labgrowns3", bad)))
        self.assertEqual(http.calls, [])

    def test_labgrowns3_missing_or_invalid_frame_batch_is_not_motion(self):
        host = "https://labgrowns3.s3.ap-southeast-1.amazonaws.com"
        item = "1210811_B2C"
        root = f"{host}/imaged/{item}"
        viewer = f"{host}/stoneimages360.html?d={item}"
        responses = _progressive_source_responses(AUDITS[0], root, version=2)
        responses[root + "/0.json?version="] = responses.pop(root + "/0.json")
        responses[f"{root}/5.json?version=2"] = (b"[]", "application/json")
        with self.assertRaises(InvalidPayloadError):
            Labgrowns3RotationDownloader(
                FakeHttpClient(responses)
            ).download(_reference("labgrowns3", viewer))

    def test_remote_v360_requires_exact_public_media_root(self):
        valid = (
            "https://v360.in/viewer4.0/vision360.html?"
            "d=VDC-32-50&surl=https://s10.v360.in/images/company/1546/"
        )
        downloader = RemoteV360RotationDownloader(FakeHttpClient({}))
        self.assertTrue(downloader.supports(_reference("v360", valid)))
        for url in (
            valid.replace("s10.v360.in", "127.0.0.1"),
            valid.replace("s10.v360.in", "s10.v360.in.attacker.test"),
            valid.replace("/images/company/1546/", "/private/"),
            valid.replace("d=VDC-32-50", "d=../other"),
            valid.replace("surl=https://", "surl=http://"),
            valid + "&surl=https://s11.v360.in/images/company/1546/",
            valid.replace("v360.in/viewer4.0/", "other.test/viewer4.0/"),
        ):
            with self.subTest(url=url):
                self.assertFalse(downloader.supports(_reference("v360", url)))
        self.assertEqual(downloader.http_client.calls, [])

    def test_progressive_downloader_rejects_incomplete_public_batch(self):
        audit = AUDITS[0]
        viewer = "https://vision.diajewel360.com/Vision360.html?d=VL-NEW123"
        root = "https://vision.diajewel360.com/imaged/VL-NEW123"
        responses = _progressive_source_responses(audit, root, version=1)
        responses[root + "/4.json?version=1"] = (b"[]", "application/json")
        downloader = DiajewelRotationDownloader(FakeHttpClient(responses))
        with self.assertRaises(InvalidPayloadError):
            downloader.download(_reference("diajewel", viewer))

    def test_ordered_positions_is_a_complete_permutation(self):
        positions = ordered_positions(AUDITS[0]["scramble"])
        self.assertEqual(len(positions), 256)
        self.assertEqual(set(positions), set(range(256)))


if __name__ == "__main__":
    unittest.main()
