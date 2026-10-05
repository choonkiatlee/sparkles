"""Validated image discovery without changing source pixels or bytes."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}


def natural_key(value):
    return tuple((1, int(s)) if s.isdigit() else (0, s.lower())
                 for s in re.split(r'(\d+)', str(value)))


def source_index(path):
    match = re.search(r'(\d+)$', Path(path).stem)
    return int(match.group(1)) if match else None


def load_rgb(path):
    with Image.open(path) as image:
        if image.mode not in {'RGB', 'L'}:
            raise ValueError(f'Unsupported image mode {image.mode}; expected 8-bit RGB/L')
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Animated/multipage image is not an extracted frame')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('EXIF orientation must be applied explicitly upstream')
        image.load()
        return np.asarray(image.convert('RGB')).copy()


def ingest(directory, order_manifest=None):
    directory = Path(directory).resolve()
    frame_root = directory / 'frames' if (directory / 'frames').is_dir() else directory
    paths = sorted((p for p in frame_root.iterdir() if p.is_file() and
                    p.suffix.lower() in EXTENSIONS), key=lambda p: natural_key(p.name))
    if not paths:
        raise ValueError('No image frames found')
    metadata = json.loads(Path(order_manifest).read_text()) if order_manifest else {}
    order = next((metadata[k] for k in ('reading_order', 'reading_order_zero_based',
                  'selected_reading_order') if k in metadata), None)
    if order is None and 'faceup_reading_order' in metadata:
        order = metadata['faceup_reading_order'] + metadata.get('context_reading_order', [])
    entries = metadata.get('frames', metadata.get('selected_frames', []))
    expected = {}
    for entry in entries:
        idx = entry.get('index', entry.get('frame_index_zero_based'))
        if idx is not None:
            expected[idx] = entry
    if order is not None:
        ids = [source_index(p) for p in paths]
        if None in ids or len(set(ids)) != len(ids):
            raise ValueError('Manifest order requires unique numeric frame indices')
        lookup = dict(zip(ids, paths))
        if len(set(order)) != len(order):
            raise ValueError('Repeated index in manifest order')
        missing = set(order) - set(ids)
        if missing:
            raise ValueError(f'Manifest frames missing: {sorted(missing)}')
        if set(ids) - set(order):
            raise ValueError('Unlisted frames present; use a separate input directory')
        paths = [lookup[i] for i in order]
    records, byte_seen, pixel_seen, dimensions = [], {}, {}, set()
    for position, path in enumerate(paths):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        idx = source_index(path)
        if expected.get(idx, {}).get('sha256', digest) != digest:
            raise ValueError(f'Source hash mismatch: {path.name}')
        r = dict(position=position, name=path.name, path=str(path.relative_to(directory)),
                 source_index=idx, bytes=len(raw), sha256=digest, status='valid')
        try:
            rgb = load_rgb(path)
            height, width = rgb.shape[:2]
            brightness = (rgb.astype(np.float32) / 255) @ np.array([.2126, .7152, .0722])
            r.update(width=width, height=height, brightness={
                'mean': float(brightness.mean()), 'std': float(brightness.std()),
                'p05': float(np.quantile(brightness, .05)),
                'p95': float(np.quantile(brightness, .95))})
            dimensions.add((width, height))
            pixel_hash = hashlib.sha256(f'{width}x{height}:'.encode() + rgb.tobytes()).hexdigest()
            r['pixel_sha256'] = pixel_hash
            if digest in byte_seen:
                r['duplicate_of'] = byte_seen[digest]
            elif pixel_hash in pixel_seen:
                r['pixel_duplicate_of'] = pixel_seen[pixel_hash]
            byte_seen.setdefault(digest, path.name)
            pixel_seen.setdefault(pixel_hash, path.name)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            r.update(status='invalid', error=str(error))
        records.append(r)
    valid = sum(r['status'] == 'valid' for r in records)
    total = metadata.get('source_frame_count', metadata.get('advertised_frame_count'))
    warnings = []
    if valid != len(records):
        warnings.append('Invalid images retained in manifest and excluded from processing')
    if len(dimensions) != 1:
        warnings.append('Mixed image dimensions: inspect camera-space comparisons')
    if total is not None and len(records) != total:
        warnings.append('Sparse selection; source indices are not elapsed time or calibrated angles')
    return dict(schema_version='1.0', frame_count=len(records), valid_count=valid,
                dimensions=[list(d) for d in sorted(dimensions)], frames=records,
                ordering='explicit_manifest' if order is not None else 'natural_filename',
                sparse=total is not None and len(records) != total,
                source_frame_count=total, source_manifest=metadata, warnings=warnings,
                brightness_definition='Rec.709 weighted encoded sRGB, range 0..1; not linear luminance')
