import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from diamond360 import external_benchmark as eb
from diamond360 import video_source


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ExternalBenchmarkPolicyTests(unittest.TestCase):
    def test_vendor_360_uses_frozen_core_and_wide_windows(self):
        window = eb._window_for_source(
            {"source_frame_count":256, "sequence_complete":True},
            "vendor_360",
        )
        self.assertEqual(window["analysis_indices"], eb.CORE_INDICES)
        self.assertEqual(window["geometry_indices"], eb.WIDE_INDICES)
        self.assertTrue(window["wrap"])
        self.assertTrue(window["profile_compatible"])

    def test_video_window_is_centered_label_blind_and_not_profile_compatible(self):
        window = eb._window_for_source(
            {"source_frame_count":120, "sequence_complete":True},
            "direct_mp4",
        )
        self.assertEqual(len(window["analysis_indices"]), 97)
        self.assertEqual(window["analysis_indices"][0], 11)
        self.assertEqual(window["analysis_indices"][-1], 107)
        self.assertEqual(window["geometry_indices"], window["analysis_indices"])
        self.assertFalse(window["wrap"])
        self.assertFalse(window["profile_compatible"])

    def test_short_motion_is_not_padded_or_duplicated(self):
        with self.assertRaisesRegex(ValueError, "need at least 17"):
            eb._window_for_source(
                {"source_frame_count":16, "sequence_complete":True},
                "direct_mp4",
            )

    def test_retained_projection_has_exact_declared_profile_vocabulary(self):
        self.assertEqual(len(eb.PROFILE_FIELDS), 21)
        self.assertIn(
            "dark_state.persistence.inner_dark_q90_window_fraction",
            eb.PROFILE_FIELDS,
        )
        self.assertIn(
            "directional.corner_NW_SE_pearson",
            eb.PROFILE_FIELDS,
        )
        self.assertIn(
            "flash_morphology.active_frame_fraction",
            eb.PROFILE_FIELDS,
        )

    def test_archived_sequence_materializer_preserves_order_and_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            source_dir = archive / "d360" / "example"
            frames = source_dir / "frames"
            frames.mkdir(parents=True)
            rows = []
            for index in range(3):
                path = frames / f"x-{index}.jpg"
                path.write_bytes(f"frame-{index}".encode())
                rows.append({
                    "index":index,
                    "path":f"frames/{path.name}",
                    "sha256":_digest(path),
                })
            manifest = source_dir / "manifest.json"
            manifest.write_text(json.dumps({"frames":rows}) + "\n")
            sample = {
                "sample_id":"example",
                "media":{"sequence":{
                    "manifest_path":"d360/example/manifest.json",
                    "frame_index_field":"index",
                    "frame_count":3,
                    "ordering":"test order",
                }},
            }
            destination = root / "out"
            result = eb.materialize_archived_sequence(
                sample, archive, destination
            )
            self.assertEqual(result["schema_version"], "diamond360-source/1")
            self.assertEqual(
                [row["source_index"] for row in result["frames"]],
                [0, 1, 2],
            )
            self.assertEqual(
                json.loads((destination / "source-manifest.json").read_text())[
                    "source_frame_count"
                ],
                3,
            )

    def test_static_sample_is_not_manufactured_into_motion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            (archive / "media").mkdir(parents=True)
            still = archive / "media" / "still.jpg"
            still.write_bytes(b"not actually decoded in this policy test")
            manifest = {"samples":[{
                "sample_id":"still",
                "evidence_type":"still",
                "media":{"sequence":None,"assets":[{
                    "artifact_path":"media/still.jpg",
                    "sha256":_digest(still),
                }]},
            }]}
            status = eb.prepare_archive_sources(
                manifest, archive, root / "sources"
            )
            self.assertEqual(status["still"]["status"], "not_applicable")
            self.assertFalse((root / "sources" / "still").exists())


class VideoSourceAdapterTests(unittest.TestCase):
    def test_extract_records_derived_frame_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "sample.mp4"
            media.write_bytes(b"archived bytes")
            output = root / "out"
            calls = []

            def fake_run(command):
                calls.append(command)
                if command[0] == "ffprobe":
                    return SimpleNamespace(stdout=json.dumps({"streams":[{
                        "codec_name":"h264",
                        "width":100,
                        "height":80,
                        "avg_frame_rate":"25/1",
                        "r_frame_rate":"25/1",
                        "nb_frames":"2",
                        "duration":"0.08",
                    }]}))
                frames = output / "frames"
                frames.mkdir(parents=True, exist_ok=True)
                for index in range(2):
                    (frames / f"frame-{index:06d}.png").write_bytes(
                        f"png-{index}".encode()
                    )
                return SimpleNamespace(stdout="")

            with mock.patch.object(video_source, "_run", side_effect=fake_run):
                result = video_source.extract(
                    media,
                    output,
                    sample_id="sample",
                )
            self.assertEqual(result["source_frame_count"], 2)
            self.assertTrue(result["sequence_complete"])
            self.assertEqual(
                result["frames"][1]["derived_from_video_frame_index"], 1
            )
            self.assertEqual(
                result["adapter"]["archived_media_sha256"], _digest(media)
            )
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
