"""Original #64 PriceScope archive -> standard reference publisher, entirely offline."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from diamond_catalogue.models import CatalogueError
from diamond_catalogue.reference_archive_publish import (
    APPROVED, _checked_relative, publish_archived_reference,
)
from tests.test_reference_publication import ReferenceFakeGitHub, ref


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path, reference_id: str):
    sample, kind, url = APPROVED[reference_id]
    home = root / "archive"
    home.mkdir()
    if kind == "rotation":
        source = home / "d360" / sample
        frames_dir = source / "frames"
        frames_dir.mkdir(parents=True)
        rows = []
        for index in range(256):
            payload = BytesIO()
            Image.new("RGB", (758, 597),
                      (index, index // 3, (index * 17) % 256)).save(
                          payload, format="JPEG")
            data = payload.getvalue()
            name = f"frames/frame-{index:03d}.jpg"
            (source / name).write_bytes(data)
            rows.append({"index": index, "path": name,
                         "sha256": sha(data), "bytes": len(data)})
        raw = json.dumps({"frames": rows}, separators=(",", ":")).encode()
        (source / "manifest.json").write_bytes(raw)
        media = {"full_original_verified": True,
                 "locator": {"sample_id": sample, "url": url},
                 "sequence": {
                     "manifest_path": f"d360/{sample}/manifest.json",
                     "manifest_sha256": sha(raw), "manifest_bytes": len(raw),
                     "frame_count": 256, "frame_index_field": "index",
                     "dimensions": [758, 597]}}
    else:
        directory = home / "media"
        directory.mkdir(parents=True)
        payload = b"\x00\x00\x00\x18ftypisom" + b"original source video bytes"
        relative = f"media/{sample}.mp4"
        (home / relative).write_bytes(payload)
        media = {"full_original_verified": True,
                 "assets": [{"media_url": url, "media_type": "mp4",
                             "byte_archive_status": "archived_original",
                             "artifact_path": relative, "sha256": sha(payload),
                             "bytes": len(payload)}]}
    manifest = {"schema_version": "sparkles-external-benchmark/1",
                "samples": [{"sample_id": sample, "media": media}]}
    bench_path = root / "benchmark.json"
    bench_path.write_text(json.dumps(manifest))
    doc = ref(reference_id, media=[{
        "kind": "viewer" if kind == "rotation" else "video",
        "provider": "d360.tech" if kind == "rotation" else "kashiimports",
        "status": "linked_unverified", "url": url,
    }])
    api = ReferenceFakeGitHub()
    api.seed([doc])
    return api, home, bench_path, doc


class ArchiveImportTests(unittest.TestCase):
    def test_complete_original_256_frames_publish_and_rerun_without_changes(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r17")
            receipt = publish_archived_reference(
                doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertTrue(receipt.changed)
            self.assertEqual(receipt.asset_count, 256)
            saved = api.reference(doc["id"])
            self.assertEqual(saved["commentary"], doc["commentary"])
            self.assertEqual(saved["media_sources"], doc["media_sources"])
            self.assertEqual(saved["identity"]["status"], "unverified")
            rotation = saved["evidence"][0]
            self.assertEqual(rotation["kind"], "rotation")
            self.assertTrue(rotation["metadata"]["sequence_complete"])
            self.assertEqual(len(rotation["frames"]), 256)
            self.assertEqual(
                [r["source_index"] for r in rotation["frames"]], list(range(256)))
            self.assertTrue(api.reference_index()["references"][0]["has_motion"])
            self.assertEqual(api.uploads, 256)
            self.assertEqual(api.commits_created, 1)
            repeat = publish_archived_reference(
                doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertFalse(repeat.changed)
            self.assertEqual(api.uploads, 256)
            self.assertEqual(api.commits_created, 1)

    def test_bad_original_frame_hash_fails_closed_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r17")
            path = root / "d360/asscher-eval-glittery/frames/frame-032.jpg"
            path.write_bytes(b"corrupted original")
            with self.assertRaises(ValueError):
                publish_archived_reference(
                    doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertEqual(api.uploads, 0)
            self.assertEqual(api.commits_created, 0)
            self.assertFalse(api.reference_index()["references"][0]["has_motion"])

    def test_video_is_exact_original_not_fake_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r20")
            receipt = publish_archived_reference(
                doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertEqual(receipt.asset_count, 1)
            saved = api.reference(doc["id"])
            self.assertEqual(len(saved["evidence"]), 1)
            self.assertEqual(saved["evidence"][0]["kind"], "video")
            self.assertNotIn("frames", saved["evidence"][0])
            self.assertEqual(saved["evidence"][0]["media_type"], "video/mp4")
            self.assertTrue(api.reference_index()["references"][0]["has_motion"])
            self.assertEqual(api.uploads, 1)

    def test_curated_source_mismatch_and_cert_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r20")
            current = api.reference(doc["id"])
            current["media_sources"][0]["url"] = "https://www.kashiimports.com/video/99999.mp4"
            api.blobs["changed-curation"] = json.dumps(current)
            api.trees["t0"]["data/references/" + doc["id"] + ".json"] = "changed-curation"
            with self.assertRaisesRegex(CatalogueError, "does not match"):
                publish_archived_reference(
                    doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertEqual(api.uploads, 0)
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r20")
            current = api.reference(doc["id"])
            current["identity"] = {"status": "reported", "lab": "IGI",
                                   "report_number": "LG800667394"}
            api.blobs["changed-id"] = json.dumps(current)
            api.trees["t0"]["data/references/" + doc["id"] + ".json"] = "changed-id"
            with self.assertRaisesRegex(CatalogueError, "cannot be assigned"):
                publish_archived_reference(
                    doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertEqual(api.uploads, 0)

    def test_bad_video_hash_and_untrusted_path_fail_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, doc = fixture(Path(td), "ps281114-r22")
            bad = root / "media/asscher-eval-nice-dance.mp4"
            bad.write_bytes(b"bad")
            with self.assertRaisesRegex(CatalogueError, "hash or byte"):
                publish_archived_reference(
                    doc["id"], api=api, archive_root=root, benchmark_path=bench)
            self.assertEqual(api.uploads, 0)
            for path in ("../escape.mp4", "/etc/passwd", "d360/../../secret"):
                with self.assertRaises(CatalogueError):
                    _checked_relative(root, path)

    def test_reject_unapproved_reference(self):
        with tempfile.TemporaryDirectory() as td:
            api, root, bench, _ = fixture(Path(td), "ps281114-r20")
            with self.assertRaisesRegex(CatalogueError, "not allowlisted"):
                publish_archived_reference(
                    "ps281114-r19", api=api, archive_root=root,
                    benchmark_path=bench)


if __name__ == "__main__":
    unittest.main()
