"""Convert archived motion media into an explicit diamond360-source/1 source.

This adapter is for external falsification benchmarks. Decoded frames are derived
evidence, not original still-image bytes, and their indices are video-frame order,
not calibrated viewing angles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

SOURCE_SCHEMA = "diamond360-source/1"
ADAPTER_SCHEMA = "diamond360-video-source-adapter/1"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command):
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


def _probe(media, ffprobe):
    completed = _run([
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration",
        "-of", "json",
        str(media),
    ])
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if len(streams) != 1:
        raise ValueError("expected exactly one primary video stream")
    return streams[0]


def extract(media, output, *, sample_id=None, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    media = Path(media).resolve()
    output = Path(output).resolve()
    if not media.is_file():
        raise ValueError(f"media file missing: {media}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be a new or empty directory")
    if output == media.parent or output in media.parents:
        raise ValueError("output must not contain the archived source media")

    probe = _probe(media, ffprobe)
    frames = output / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    pattern = frames / "frame-%06d.png"
    _run([
        ffmpeg,
        "-v", "error",
        "-i", str(media),
        "-vsync", "0",
        "-start_number", "0",
        str(pattern),
    ])

    paths = sorted(frames.glob("frame-*.png"))
    if not paths:
        raise ValueError("ffmpeg decoded no frames")
    entries = []
    for source_index, path in enumerate(paths):
        expected_name = f"frame-{source_index:06d}.png"
        if path.name != expected_name:
            raise ValueError(
                f"decoded frame sequence is not contiguous at {source_index}: {path.name}"
            )
        entries.append({
            "source_index": source_index,
            "path": str(path.relative_to(output)),
            "sha256": _sha256(path),
            "derived_from_video_frame_index": source_index,
        })

    payload = {
        "schema_version": SOURCE_SCHEMA,
        "source_type": "decoded_video_frames",
        "source_id": sample_id or media.stem,
        "source_frame_count": len(entries),
        "sequence_complete": True,
        "ordering": "decoded_video_frame_order",
        "frames": entries,
        "adapter": {
            "schema_version": ADAPTER_SCHEMA,
            "archived_media_name": media.name,
            "archived_media_sha256": _sha256(media),
            "archived_media_bytes": media.stat().st_size,
            "decode": "ffmpeg every decoded video frame, vsync=0, lossless PNG",
            "frame_index_semantics": (
                "decoded video frame order; neither elapsed source steps nor "
                "calibrated viewing angles are inferred"
            ),
            "probe": probe,
        },
    }
    (output / "source-manifest.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sample-id")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    try:
        result = extract(
            args.media,
            args.output,
            sample_id=args.sample_id,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
        )
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"{result['source_id']}: {result['source_frame_count']} decoded frames -> {args.output}")


if __name__ == "__main__":
    main()
