"""Explicit adapters from archived external media into diamond360-source/1.

These adapters are benchmark-only provenance boundaries. They do not relax the
normal source contract: every decoded/extracted frame is hashed, ordered and
declared in an explicit source manifest before the production preprocessing
pipeline can consume it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image

SOURCE_SCHEMA = "diamond360-source/1"
ADAPTER_SCHEMA = "sparkles-external-media-adapter/1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_info(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.load()
        if image.mode not in {"RGB", "L"}:
            raise ValueError(f"{path}: unsupported extracted image mode {image.mode}")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError(f"{path}: extracted frame must be a single image")
        if image.getexif().get(274, 1) != 1:
            raise ValueError(f"{path}: EXIF orientation must be applied upstream")
        return image.size


def build_source(
    frame_paths,
    output,
    *,
    provenance,
    source_media_path=None,
    copy_frames=True,
):
    """Write a complete ordered source contract from already ordered image frames."""
    frames = [Path(path).resolve() for path in frame_paths]
    if not frames:
        raise ValueError("external source requires at least one frame")
    if len(set(frames)) != len(frames):
        raise ValueError("external source frames must be unique paths")

    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty or absent")
    frame_dir = output / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    records = []
    dimensions = set()
    for index, source in enumerate(frames):
        if not source.is_file():
            raise ValueError(f"external frame missing: {source}")
        suffix = source.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            raise ValueError(f"unsupported external frame type: {source.name}")
        destination = frame_dir / f"external-frame-{index:06d}{suffix}"
        if copy_frames:
            shutil.copyfile(source, destination)
        else:
            if source.parent != frame_dir:
                raise ValueError("copy_frames=False requires frames already in output/frames")
            destination = source
        width, height = _image_info(destination)
        dimensions.add((width, height))
        records.append(
            {
                "source_index": index,
                "path": str(destination.relative_to(output)),
                "sha256": _sha256(destination),
                "bytes": destination.stat().st_size,
                "width": width,
                "height": height,
            }
        )

    source_media = None
    if source_media_path is not None:
        media = Path(source_media_path).resolve()
        if not media.is_file():
            raise ValueError(f"external source media missing: {media}")
        source_media = {
            "path": str(media),
            "sha256": _sha256(media),
            "bytes": media.stat().st_size,
        }

    manifest = {
        "schema_version": SOURCE_SCHEMA,
        "source_kind": "external_benchmark_adapter",
        "adapter_schema": ADAPTER_SCHEMA,
        "sequence_complete": True,
        "source_frame_count": len(records),
        "dimensions": [list(item) for item in sorted(dimensions)],
        "provenance": provenance,
        "source_media": source_media,
        "frames": records,
    }
    (output / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )
    return manifest


def extract_video(media_path, output, *, provenance, ffmpeg="ffmpeg"):
    """Decode every video/GIF frame in source order to lossless PNGs via ffmpeg."""
    media_path = Path(media_path).resolve()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty or absent")
    frame_dir = output / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    pattern = frame_dir / "decoded-%06d.png"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media_path),
        "-vsync",
        "0",
        str(pattern),
    ]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise ValueError("ffmpeg is required for external video adaptation") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ffmpeg failed to decode {media_path.name}") from exc

    frames = sorted(frame_dir.glob("decoded-*.png"))
    if not frames:
        raise ValueError(f"ffmpeg decoded no frames from {media_path.name}")
    return build_source(
        frames,
        output,
        provenance=provenance,
        source_media_path=media_path,
        copy_frames=False,
    )


def adapt_still(image_path, output, *, provenance):
    """Wrap one original still as a one-frame source for static-only descriptors."""
    return build_source(
        [Path(image_path)],
        output,
        provenance=provenance,
        source_media_path=image_path,
        copy_frames=True,
    )
