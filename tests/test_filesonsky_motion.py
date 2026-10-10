"""Network-free exact FilesOnSky original-motion contract tests."""
import unittest

from diamond_retrieval import (
    FilesOnSkyRotationDownloader, ProgressiveRotationProcessor, InvalidPayloadError,
    MissingEvidenceError, default_config,
)
from tests.test_diamond_retrieval_motion import (
    AUDITS, FakeHttpClient, _reference, _progressive_source_responses,
)

VIEWER = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
ROOT = "https://www.filesonsky.com/v360/imaged/659844"


def fake_responses(*, missing_batch=None, corrupt_batch=None):
    responses = _progressive_source_responses(AUDITS[0], ROOT, version=1)
    responses[ROOT + "/0.json?version="] = responses.pop(ROOT + "/0.json")
    if missing_batch is not None:
        responses.pop(f"{ROOT}/{missing_batch}.json?version=1")
    if corrupt_batch is not None:
        responses[f"{ROOT}/{corrupt_batch}.json?version=1"] = (
            b"[]", "application/json",
        )
    return responses


class FilesOnSkyMotionTests(unittest.TestCase):
    def test_exact_r05_viewer_recovers_all_original_ordered_frames(self):
        http = FakeHttpClient(fake_responses())
        adapter = FilesOnSkyRotationDownloader(http)
        reference = _reference("filesonsky", VIEWER)
        self.assertTrue(adapter.supports(reference))
        raw = adapter.download(reference)
        rotation = ProgressiveRotationProcessor().process(raw)[0]
        self.assertEqual(rotation.metadata["supplier"], "filesonsky")
        self.assertEqual(len(rotation.frames), 256)
        self.assertEqual([frame.source_index for frame in rotation.frames],
                         list(range(256)))
        self.assertEqual(
            http.calls,
            [ROOT + "/0.json?version="] +
            [f"{ROOT}/{i}.json?version=1" for i in range(1, 8)],
        )
        self.assertEqual(len(raw.source_responses), 8)
        self.assertFalse(rotation.metadata["physical_angle_calibrated"])

    def test_trusted_viewer_acceptance_is_exact_and_non_generic(self):
        adapter = FilesOnSkyRotationDownloader(None)
        self.assertTrue(adapter.supports(_reference("filesonsky", VIEWER)))
        for invalid in (
            VIEWER.replace("https://", "http://"),
            VIEWER.replace("www.filesonsky.com", "filesonsky.com"),
            VIEWER.replace("www.filesonsky.com", "www.filesonsky.com.evil.test"),
            VIEWER + "&surl=https://evil.test/",
            VIEWER + "&d=OTHER",
            VIEWER + "#fragment",
            VIEWER.replace("659844", "../../etc/passwd"),
            VIEWER.replace("659844", "R05"),
            VIEWER.replace("/v360/", "/other/"),
            VIEWER.replace("Vision360.HTML", "Video.html"),
            "https://www.filesonsky.com/v360/Vision360.HTML",
        ):
            with self.subTest(url=invalid):
                self.assertFalse(adapter.supports(_reference("filesonsky", invalid)))

    def test_missing_or_corrupt_batch_never_claims_motion(self):
        for missing in (1, 7):
            with self.subTest(missing=missing):
                adapter = FilesOnSkyRotationDownloader(
                    FakeHttpClient(fake_responses(missing_batch=missing))
                )
                with self.assertRaises(MissingEvidenceError):
                    adapter.download(_reference("filesonsky", VIEWER))
        adapter = FilesOnSkyRotationDownloader(
            FakeHttpClient(fake_responses(corrupt_batch=5))
        )
        with self.assertRaises(InvalidPayloadError):
            adapter.download(_reference("filesonsky", VIEWER))

    def test_default_retrieval_registers_filesonsky(self):
        self.assertTrue(any(
            isinstance(adapter, FilesOnSkyRotationDownloader)
            for adapter in default_config(FakeHttpClient({})).downloaders
        ))


if __name__ == "__main__":
    unittest.main()
