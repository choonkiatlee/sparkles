"""Bounded, read-only audits of exactly two curated missing-motion sources.

R07: request only the buyer-linked v360.diamonds page; never crawl its scripts,
guess the underlying data API or bypass a paywall / 402 response.
R23: check only the exact source-backed d360.tech original media URLs derived by
the already-reviewed D360 adapter. Full rotation attempted only if preflight
checks pass; existing original 256-JPEG validator owns acceptance.

Neither action publishes bytes or edits any manifest. Output is sanitized.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.models import EvidenceReference, ROTATION
from diamond_retrieval.motion import (
    ProgressiveRotationProcessor, decode_vision360_scramble,
    validate_jpeg_bytes,
)
from diamond_retrieval.motion_sources import D360RotationDownloader
from diamond_retrieval.reference_media import _safe_source_url

ROOT = Path(__file__).resolve().parents[1]
R07_ID = "ps285166-r07"
R07_VIEWER = "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i"
R23_ID = "ps281114-r23"
R23_VIEWER = "https://d360.tech/view.html?d=89-AY-8102"
R23_ROOT = "https://media.d360.us/imaged/89-AY-8102"


def verified_record(ref_id: str) -> dict:
    """Check trust anchors against current reviewed master; refuse drift."""
    if ref_id not in {R07_ID, R23_ID}:
        raise ValueError("out-of-scope reference")
    record = json.loads(
        (ROOT / "data" / "references" / (ref_id + ".json")).read_text("utf-8")
    )
    expected = (
        ("IGI", "LG625406458", R07_VIEWER)
        if ref_id == R07_ID else ("GIA", "13534682", R23_VIEWER)
    )
    assert record["id"] == ref_id
    assert record["identity"] == {
        "lab": expected[0], "report_number": expected[1], "status": "reported"
    }
    assert any(e.get("kind") == "still" and e.get("status") == "success"
               for e in record["evidence"]), "published still anchor missing"
    if ref_id == R07_ID:
        assert any(src.get("url") == R07_VIEWER
                   for src in record["media_sources"])
    else:
        assert any(a.get("locator") == R23_VIEWER and
                   a.get("kind") == "rotation" and
                   a.get("status") == "invalid_payload"
                   for a in record["enrichment_attempts"])
    _safe_source_url(expected[2])
    return record


def reference(ref_id: str, viewer: str) -> EvidenceReference:
    return EvidenceReference(
        identifier=ref_id + ":exact-original-audit", kind=ROTATION,
        retrieval_key=viewer, locator=viewer,
    )


def response_shape(response) -> dict:
    data = response.content
    typ = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    try:
        host = urlsplit(response.url).hostname
    except ValueError:
        host = None
    return {
        "http": response.status_code,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mime": typ[:70],
        "final_host": host if host in {"v360.diamonds", "media.d360.us"} else "<other>",
        "magic": (
            "mp4" if len(data) > 8 and data[4:8] == b"ftyp" else
            "jpeg" if data[:3] == b"\xff\xd8\xff" else
            "html" if b"<html" in data[:1000].lower() or
            b"<!doctype html" in data[:1000].lower() else "other"
        ),
    }


def classify_d360_preflight(responses: dict) -> dict:
    """Explain why an exact D360 source is not valid, with no source bytes logged."""
    result = {}
    for name in ("metadata.json", "0.json", "still.jpg"):
        response = responses.get(name)
        result[name] = "not_read" if response is None else str(response.status_code)
        if response is None or response.status_code != 200:
            return {"preflight": "missing_source", "first_blocker": name, "status": result}

    try:
        metadata = json.loads(responses["metadata.json"].content)
    except (ValueError, UnicodeDecodeError):
        return {"preflight": "invalid_metadata_json"}
    if metadata is None:
        return {"preflight": "invalid_metadata_shape"}
    try:
        bootstrap = json.loads(responses["0.json"].content)
    except (ValueError, UnicodeDecodeError):
        return {"preflight": "invalid_bootstrap_json"}
    if not isinstance(bootstrap, dict):
        return {"preflight": "invalid_bootstrap_shape"}
    # Match the production D360 downloader: numeric-string dimensions are
    # accepted through int(), rather than requiring JSON integer types.
    try:
        dims = [int(bootstrap["width"]), int(bootstrap["height"])]
    except (KeyError, TypeError, ValueError):
        return {"preflight": "invalid_dimensions", "dimension_types": [
            type(bootstrap.get(k)).__name__ for k in ("width", "height")
        ]}
    if not all(0 < x <= 8000 for x in dims):
        return {"preflight": "invalid_dimensions_range"}
    if not isinstance(bootstrap.get("scramble"), str):
        return {"preflight": "missing_scramble", "dimensions": dims}
    try:
        scramble = decode_vision360_scramble(bootstrap["scramble"])
    except ValueError:
        return {"preflight": "invalid_scramble", "dimensions": dims}
    preview = bootstrap.get("image")
    if not isinstance(preview, str):
        return {"preflight": "missing_image", "dimensions": dims}
    try:
        image = base64.b64decode("".join(preview.split()), validate=True)
    except Exception:
        return {"preflight": "invalid_preview_base64", "dimensions": dims}
    still = responses["still.jpg"].content
    if image != still:
        return {"preflight": "preview_still_mismatch", "dimensions": dims,
                "preview_sha256": hashlib.sha256(image).hexdigest(),
                "still_sha256": hashlib.sha256(still).hexdigest()}
    try:
        still_dims = validate_jpeg_bytes(still)
    except Exception:
        return {"preflight": "invalid_still_jpeg", "dimensions": dims}
    if tuple(dims) != still_dims:
        return {"preflight": "still_dimension_mismatch", "dimensions": dims,
                "still_dimensions": list(still_dims)}
    return {
        "preflight": "valid_original_bootstrap",
        "dimensions": dims,
        "scramble_levels": len(scramble),
    }


def audit_r07(http) -> list[dict]:
    verified_record(R07_ID)
    url = _safe_source_url(R07_VIEWER)
    assert urlsplit(url).hostname == "v360.diamonds"
    try:
        response = http.get(url, timeout=15)
        shape = response_shape(response)
        state = (
            "http_402_blocked" if response.status_code == 402 else
            "http_other_blocked" if response.status_code != 200 else
            "page_not_original_media" if shape["magic"] == "html" else
            "unexpected_direct_content"
        )
        return [{"reference": R07_ID, "source": "exact_buyer_viewer",
                 "state": state, **shape}]
    except Exception as exc:
        return [{"reference": R07_ID, "source": "exact_buyer_viewer",
                 "state": "transport_failure", "error_class": type(exc).__name__}]


def audit_r23(http) -> list[dict]:
    verified_record(R23_ID)
    ref = reference(R23_ID, R23_VIEWER)
    item, root = D360RotationDownloader._source(ref)
    assert item == "89-AY-8102" and root == R23_ROOT
    outputs = []
    replies = {}
    for filename in ("metadata.json", "0.json", "still.jpg"):
        url = _safe_source_url(root + "/" + filename)
        assert urlsplit(url).hostname == "media.d360.us"
        try:
            response = http.get(url, timeout=15)
            replies[filename] = response
            outputs.append({"reference": R23_ID, "source": filename, **response_shape(response)})
        except Exception as exc:
            outputs.append({"reference": R23_ID, "source": filename,
                            "state": "transport_failure", "error_class": type(exc).__name__})
            break

    preflight = classify_d360_preflight(replies)
    outputs.append({"reference": R23_ID, "source": "contract", **preflight})
    if preflight.get("preflight") != "valid_original_bootstrap":
        return outputs

    try:
        raw = D360RotationDownloader(http, timeout=15).download(ref)
        rotations = ProgressiveRotationProcessor().process(raw)
        assert len(rotations) == 1
        rotation = rotations[0]
        frames = rotation.frames
        assert len(frames) == 256
        assert [f.source_index for f in frames] == list(range(256))
        assert rotation.metadata.get("sequence_complete") is True
        outputs.append({
            "reference": R23_ID, "source": "complete_originals", "state": "validated",
            "frame_count": len(frames), "source_responses": len(raw.source_responses),
            "first_frame_sha256": hashlib.sha256(frames[0].payload).hexdigest(),
            "last_frame_sha256": hashlib.sha256(frames[-1].payload).hexdigest(),
        })
    except Exception as exc:
        outputs.append({"reference": R23_ID, "source": "complete_originals",
                        "state": "not_validated", "error_class": type(exc).__name__})
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", choices=("r07", "r23"))
    args = parser.parse_args()
    client = UrllibHttpClient(max_bytes=2_000_000)
    records = audit_r07(client) if args.reference == "r07" else audit_r23(client)
    for record in records:
        print("REFERENCE_ORIGINAL_AUDIT " + json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
