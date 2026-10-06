"""Extract exact ordered JPEG frames from audited d360.tech viewers.

The adapter intentionally supports only source IDs whose d360 scramble map has
been independently audited. Unknown IDs fail closed instead of assuming frame
order. Raw JPEG bytes are decoded from vendor JSON and written unchanged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from PIL import Image

FRAME_COUNT = 256
PACK_COUNTS = (4, 4, 8, 16, 32, 64, 128)
PACK_START_SERIALS = (1, 5, 9, 17, 33, 65, 129)
DEFAULT_MEDIA_BASE = "https://media.d360.us"
ID_RE = re.compile(r"^(?!.*\.\.)(?=.*[A-Za-z0-9])[A-Za-z0-9_.-]+$")
USER_AGENT = "Mozilla/5.0 SparklesD360Extractor/1"

# Decrypted from each viewer's 0.json `scramble` field using the current d360
# player algorithm. The corresponding 0.json SHA-256 pins the audited source
# contract so a changed bootstrap cannot silently reuse an old ordering map.
KNOWN_SOURCES = {
    "79-BB-5159600": {
        "bootstrap_sha256": "19adfa45f5e47ec670bc0cb25c2b9057315585bde9518b0062db5f2f472eab9f",
        "scramble": [
            [3,2,1,0],
            [1,3,2,0],
            [5,6,7,0,2,3,1,4],
            [9,12,14,1,7,5,0,8,6,10,2,4,13,15,11,3],
            [0,3,16,12,8,14,26,4,29,23,17,25,22,31,10,28,24,1,30,21,15,9,5,7,2,13,19,27,6,18,11,20],
            [39,62,29,49,41,53,12,21,1,54,56,47,50,45,11,23,18,58,25,7,15,63,31,55,16,5,36,26,57,6,20,43,60,52,35,51,2,48,42,28,46,30,13,8,34,33,40,24,44,9,37,10,27,32,14,3,61,38,22,19,17,59,4,0],
            [10,62,102,16,74,18,87,83,91,58,101,64,106,50,1,89,98,114,20,71,19,57,23,45,24,69,109,113,97,9,51,5,13,26,111,117,88,118,27,49,3,7,103,122,120,59,112,80,66,53,61,0,115,124,44,108,15,40,65,68,47,52,123,56,76,6,82,67,28,100,75,119,4,14,35,127,55,81,93,31,33,99,110,34,90,60,48,96,73,92,105,70,54,72,121,36,38,12,63,17,125,43,25,21,8,41,79,126,86,107,46,78,116,84,94,85,37,42,29,39,32,77,30,2,22,95,11,104],
        ],
    },
    "79-BT-5165227": {
        "bootstrap_sha256": "513c2a7308907b76b79201de61a992c54bda5f7522d29adad80132789318c8f0",
        "scramble": [
            [2,1,0,3],
            [1,2,0,3],
            [1,0,4,6,3,7,2,5],
            [2,15,13,10,14,4,8,12,6,0,7,1,5,3,9,11],
            [24,12,19,23,28,3,9,15,11,22,26,6,27,8,10,0,31,1,13,17,30,7,25,29,20,5,21,14,16,2,18,4],
            [34,7,2,25,13,27,15,33,52,36,1,5,17,46,53,42,58,60,16,61,30,56,40,6,3,18,24,9,12,43,29,57,48,35,0,55,50,4,32,54,8,28,41,11,19,45,21,20,44,22,38,51,31,39,26,47,10,23,59,49,62,63,37,14],
            [14,80,100,6,85,17,11,73,74,39,57,10,12,20,84,5,45,89,61,94,83,60,21,63,95,54,28,127,29,37,40,91,22,75,3,56,58,88,86,105,55,66,81,59,9,16,104,24,120,72,53,118,31,117,113,109,33,0,42,34,65,64,97,93,7,114,49,2,116,92,115,110,78,108,101,90,123,4,71,112,107,8,77,70,38,19,35,46,25,18,126,122,67,98,68,99,48,62,47,43,125,44,52,13,82,26,102,69,32,51,1,79,76,106,41,111,27,15,36,87,50,96,119,124,121,30,23,103],
        ],
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_viewer(value: str) -> tuple[str, str]:
    """Return (viewer_url, item_id) from a d360 viewer URL or bare item id."""
    if ID_RE.fullmatch(value):
        return f"https://d360.tech/view.html?d={value}", value
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "d360.tech":
        raise ValueError("Expected https://d360.tech viewer URL or a bare d360 item id")
    values = parse_qs(parsed.query).get("d", [])
    if len(values) != 1 or not ID_RE.fullmatch(values[0]):
        raise ValueError("d360 viewer URL requires one valid d= item id")
    item_id = values[0]
    return f"https://d360.tech/view.html?d={item_id}", item_id


def canonical_progressive_positions(bits: int = 8) -> dict[int, int]:
    """Map progressive serial number (1-based) to final viewer slot (1-based)."""
    total = 2 ** bits
    out = {
        1: 1,
        2: total // 4 + 1,
        3: (total // 4) * 2 + 1,
        4: (total // 4) * 3 + 1,
    }
    interval_count = 4
    serial = 5
    for _ in range(bits - 2):
        interval_count *= 2
        for j in range(interval_count // 2):
            out[serial] = int(total / interval_count * (2 * j + 1) + 1)
            serial += 1
    if set(out) != set(range(1, total + 1)):
        raise ValueError("Internal progressive map is incomplete")
    if set(out.values()) != set(range(1, total + 1)):
        raise ValueError("Internal progressive map is not a permutation")
    return out


def validate_scramble(scramble: list[list[int]]) -> None:
    if len(scramble) != len(PACK_COUNTS):
        raise ValueError("d360 scramble must have seven progressive levels")
    for level, (values, expected) in enumerate(zip(scramble, PACK_COUNTS), 1):
        if len(values) != expected or set(values) != set(range(expected)):
            raise ValueError(f"Invalid d360 scramble permutation at level {level}")


def ordered_positions(scramble: list[list[int]]) -> dict[int, int]:
    """Port the d360 player scramble + progressive insertion mapping."""
    validate_scramble(scramble)
    base = canonical_progressive_positions(8)
    remap: dict[int, int] = {}
    serial = 1
    offset = 4
    for x in scramble[0]:
        remap[serial] = x + 1
        serial += 1
    for values in scramble[1:]:
        for x in values:
            remap[serial] = x + offset + 1
            serial += 1
        offset *= 2
    result = {serial: base[progressive_serial] for serial, progressive_serial in remap.items()}
    if set(result) != set(range(1, FRAME_COUNT + 1)):
        raise ValueError("d360 ordered map is incomplete")
    if set(result.values()) != set(range(1, FRAME_COUNT + 1)):
        raise ValueError("d360 ordered map is not a permutation")
    return result


def _fetch(url: str) -> tuple[bytes, dict[str, str]]:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Referer": "https://d360.tech/"},
    )
    with urlopen(request, timeout=45) as response:
        return response.read(), {k.lower(): v for k, v in response.headers.items()}


def _jpeg_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
        raise ValueError("d360 frame is not a complete JPEG")
    with Image.open(BytesIO(raw)) as image:
        image.load()
        if image.format != "JPEG":
            raise ValueError("d360 frame did not decode as JPEG")
        return image.size


def extract(viewer_or_id: str, output: str | Path, *, media_base: str = DEFAULT_MEDIA_BASE) -> dict:
    viewer, item_id = parse_viewer(viewer_or_id)
    known = KNOWN_SOURCES.get(item_id)
    if known is None:
        raise ValueError(
            f"Unsupported d360 item {item_id}: no audited scramble map is bundled; "
            "add an audited map before declaring source order"
        )
    media_base = media_base.rstrip("/")
    source_root = f"{media_base}/imaged/{item_id}"
    output = Path(output)
    frame_dir = output / "frames"
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty or absent")
    frame_dir.mkdir(parents=True, exist_ok=True)

    metadata_url = f"{source_root}/metadata.json"
    bootstrap_url = f"{source_root}/0.json"
    still_url = f"{source_root}/still.jpg"
    metadata_raw, _ = _fetch(metadata_url)
    bootstrap_raw, _ = _fetch(bootstrap_url)
    still_raw, _ = _fetch(still_url)
    if sha256(bootstrap_raw) != known["bootstrap_sha256"]:
        raise ValueError(
            "d360 bootstrap changed since ordering audit; refuse to reuse stale scramble map"
        )
    bootstrap = json.loads(bootstrap_raw)
    if not isinstance(bootstrap.get("image"), str) or not isinstance(bootstrap.get("scramble"), str):
        raise ValueError("Unexpected d360 0.json structure")
    preview_raw = base64.b64decode("".join(bootstrap["image"].split()), validate=True)
    if preview_raw != still_raw:
        raise ValueError("d360 0.json preview and still.jpg disagree")
    expected_dimensions = (int(bootstrap["width"]), int(bootstrap["height"]))
    if _jpeg_dimensions(still_raw) != expected_dimensions:
        raise ValueError("d360 still.jpg dimensions disagree with 0.json")
    positions = ordered_positions(known["scramble"])

    batches = []
    frame_records: list[dict | None] = [None] * FRAME_COUNT
    for batch, (count, start_serial) in enumerate(zip(PACK_COUNTS, PACK_START_SERIALS), 1):
        url = f"{source_root}/{batch}.json"
        raw, _ = _fetch(url)
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) != count or not all(isinstance(x, str) for x in payload):
            raise ValueError(f"Unexpected d360 pack {batch}: expected {count} base64 JPEGs")
        batches.append({"batch": batch, "url": url, "sha256": sha256(raw), "count": count})
        for stored_position, encoded in enumerate(payload):
            try:
                jpeg = base64.b64decode("".join(encoded.split()), validate=True)
            except Exception as exc:
                raise ValueError(f"Invalid base64 JPEG in pack {batch} position {stored_position}") from exc
            dims = _jpeg_dimensions(jpeg)
            if dims != expected_dimensions:
                raise ValueError(
                    f"d360 frame dimensions {dims} disagree with 0.json {expected_dimensions}"
                )
            serial = start_serial + stored_position
            source_index = positions[serial] - 1
            if frame_records[source_index] is not None:
                raise ValueError(f"Repeated d360 target source index {source_index}")
            filename = f"d360-{item_id}-frame-{source_index:03d}.jpg"
            path = frame_dir / filename
            path.write_bytes(jpeg)
            frame_records[source_index] = {
                "source_index": source_index,
                "path": f"frames/{filename}",
                "sha256": sha256(jpeg),
                "bytes": len(jpeg),
                "batch": batch,
                "stored_position": stored_position,
                "progressive_serial": serial,
                "source_url": url,
            }

    if any(x is None for x in frame_records):
        missing = [i for i, x in enumerate(frame_records) if x is None]
        raise ValueError(f"Incomplete d360 extraction; missing source indices {missing}")
    if frame_records[0]["sha256"] != sha256(still_raw):
        raise ValueError("d360 reconstructed source frame 0 does not match still.jpg")

    manifest = {
        "schema_version": "diamond360-source/1",
        "source_pipeline": "d360-tech",
        "item_id": item_id,
        "viewer": viewer,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "metadata_url": metadata_url,
        "metadata_sha256": sha256(metadata_raw),
        "bootstrap_url": bootstrap_url,
        "bootstrap_sha256": sha256(bootstrap_raw),
        "still_url": still_url,
        "still_sha256": sha256(still_raw),
        "source_frame_count": FRAME_COUNT,
        "sequence_complete": True,
        "dimensions": list(expected_dimensions),
        "ordering": "d360 audited scramble map over canonical progressive odd-position interleave",
        "ordering_validation": (
            "bootstrap SHA-256 pinned to audited viewer; seven scramble levels are exact "
            "permutations; 256 progressive images map one-to-one onto source indices 0..255; "
            "reconstructed source frame 0 matches vendor still.jpg byte-for-byte"
        ),
        "scramble_provenance": (
            "decrypted from the vendor 0.json scramble field using the vendor viewer algorithm "
            "during issue #64 audit; decrypted map is bundled, encrypted bytes remain source-pinned"
        ),
        "batches": batches,
        "frames": frame_records,
    }
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("viewer", help="d360.tech viewer URL or audited d360 item id")
    parser.add_argument("output", help="empty/absent output directory")
    args = parser.parse_args(argv)
    manifest = extract(args.viewer, args.output)
    print(
        json.dumps(
            {
                "item_id": manifest["item_id"],
                "frame_count": len(manifest["frames"]),
                "dimensions": manifest["dimensions"],
                "manifest": str(Path(args.output) / "source-manifest.json"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
