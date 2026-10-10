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
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.models import EvidenceReference, ROTATION
from diamond_retrieval.motion import (
    ProgressiveRotationProcessor, decode_vision360_scramble,
    validate_jpeg_bytes,
)
from diamond_retrieval.motion_sources import D360RotationDownloader
from diamond360.d360_source import PACK_COUNTS
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


class _ScriptSources(HTMLParser):
    """Collect ordinary script-src references, never execute vendor code."""
    def __init__(self):
        super().__init__()
        self.sources = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        url = dict(attrs).get("src")
        if isinstance(url, str):
            self.sources.append(url)


def audit_r23_viewer_scripts(http) -> list[dict]:
    """Inspect only exact D360 viewer and a few same-origin static JS assets."""
    outputs = []
    viewer = _safe_source_url(R23_VIEWER)
    try:
        response = http.get(viewer, timeout=15)
        outputs.append({
            "reference": R23_ID, "source": "exact_viewer",
            **response_shape(response),
        })
        if response.status_code != 200 or len(response.content) > 500_000:
            return outputs
        scripts = _ScriptSources()
        scripts.feed(response.content.decode("utf-8", "replace"))
        count = 0
        for source in scripts.sources:
            parsed = urlsplit(urljoin(viewer, source))
            if (parsed.scheme != "https" or parsed.hostname != "d360.tech"
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or not parsed.path.endswith(".js") or ".." in parsed.path
                or len(parsed.path) > 180):
                continue
            if count == 4:
                break
            count += 1
            url = _safe_source_url(parsed.geturl())
            try:
                js = http.get(url, timeout=15)
                plain = js.content.decode("utf-8", "replace").lower()
                outputs.append({
                    "reference": R23_ID, "source": "script-" + str(count),
                    "path_basename": Path(parsed.path).name[:65],
                    **response_shape(js),
                    "contains_scramble": "scramble" in plain,
                    "contains_0json": "0.json" in plain,
                    "contains_version": "version" in plain,
                    "contains_imaged": "imaged" in plain,
                    "contains_shuffle": "shuffle" in plain,
                })
            except Exception as exc:
                outputs.append({
                    "reference": R23_ID, "source": "script-" + str(count),
                    "state": "transport_failure", "error_class": type(exc).__name__,
                })
    except Exception as exc:
        outputs.append({
            "reference": R23_ID, "source": "exact_viewer",
            "state": "transport_failure", "error_class": type(exc).__name__,
        })
    return outputs


def audit_r23_original_pack_set(http, root: str, dimensions: tuple[int, int]) -> dict:
    """Read exactly 1..7.json and verify all frame bytes, without inventing order.

    A set of 256 valid source JPEGs is *not* a reconstructed 360 rotation:
    D360 stores them in progressive batches with a vendor-specific scramble.
    The immutable per-frame SHA collection is summarized here without
    displaying image contents or adding any motion evidence.
    """
    assert root == R23_ROOT and dimensions == (600, 600)
    sha_set: set[str] = set()
    counts: list[int] = []
    total = 0
    for batch_number, expected in enumerate(PACK_COUNTS, 1):
        url = _safe_source_url(root + f"/{batch_number}.json")
        assert urlsplit(url).hostname == "media.d360.us"
        try:
            response = http.get(url, timeout=25)
            if response.status_code != 200:
                return {
                    "reference": R23_ID, "source": "full_unordered_frame_set",
                    "status": "missing_batch", "batch": batch_number,
                    "http": response.status_code,
                }
            entries = json.loads(response.content)
            if not isinstance(entries, list) or len(entries) != expected:
                return {
                    "reference": R23_ID, "source": "full_unordered_frame_set",
                    "status": "invalid_batch_count", "batch": batch_number,
                    "expected": expected,
                    "actual": len(entries) if isinstance(entries, list) else None,
                }
            for entry in entries:
                if not isinstance(entry, str):
                    raise ValueError("non-text frame payload")
                frame = base64.b64decode("".join(entry.split()), validate=True)
                if validate_jpeg_bytes(frame) != dimensions:
                    raise ValueError("original frame resolution mismatch")
                sha_set.add(hashlib.sha256(frame).hexdigest())
            counts.append(len(entries))
            total += len(entries)
        except Exception as exc:
            return {
                "reference": R23_ID, "source": "full_unordered_frame_set",
                "status": "invalid_or_unavailable_batch", "batch": batch_number,
                "error_class": type(exc).__name__,
            }
    return {
        "reference": R23_ID, "source": "full_unordered_frame_set",
        "status": "verified_original_jpeg_set" if total == 256 and
        len(sha_set) == 256 else "duplicate_or_missing_frames",
        "counts": counts, "frame_count": total,
        "unique_frame_hashes": len(sha_set),
        "dimensions": list(dimensions),
        "ordered_rotation_verified": False,
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

    # Read structural keys (never values) for the known D360 metadata and
    # bootstrap; missing scramble may be an older/alternative source format.
    for filename in ("metadata.json", "0.json"):
        response = replies.get(filename)
        if response is not None and response.status_code == 200:
            try:
                obj = json.loads(response.content)
            except (ValueError, UnicodeDecodeError):
                continue
            outputs.append({
                "reference": R23_ID,
                "source": filename + ":structure",
                "json_type": type(obj).__name__,
                "keys": sorted(
                    k for k in obj if isinstance(k, str)
                    and len(k) <= 40 and k.isascii()
                    and all(ch.isalnum() or ch in "_-" for ch in k)
                )[:35] if isinstance(obj, dict) else [],
                "field_types": {
                    k: type(obj[k]).__name__
                    for k in ("width", "height", "scramble", "image", "frames", "version")
                    if isinstance(obj, dict) and k in obj
                },
            })
    if preflight.get("preflight") == "missing_scramble":
        # Summarize source preview vs vendor still and the MEDIA/PROPERTIES
        # *schema only*: do not log supplier metadata values or images.
        try:
            bootstrap = json.loads(replies["0.json"].content)
            preview_bytes = base64.b64decode(
                "".join(bootstrap["image"].split()), validate=True
            )
            preview_dims = validate_jpeg_bytes(preview_bytes)
            vendor_still = replies["still.jpg"].content
            still_dims = validate_jpeg_bytes(vendor_still)
            outputs.append({
                "reference": R23_ID, "source": "preview_still_relation",
                "exact_byte_match": preview_bytes == vendor_still,
                "preview_dimensions": list(preview_dims),
                "vendor_still_dimensions": list(still_dims),
                "preview_sha256": hashlib.sha256(preview_bytes).hexdigest(),
                "vendor_still_sha256": hashlib.sha256(vendor_still).hexdigest(),
            })
        except Exception as exc:
            outputs.append({"reference": R23_ID, "source": "preview_still_relation",
                            "state": "invalid_or_unavailable",
                            "error_class": type(exc).__name__})
        try:
            metadata = json.loads(replies["metadata.json"].content)
            if isinstance(metadata, dict):
                for field in ("MEDIA", "PROPERTIES"):
                    child = metadata.get(field)
                    outputs.append({
                        "reference": R23_ID, "source": "metadata:" + field,
                        "value_type": type(child).__name__,
                        "keys": sorted(
                            k for k in child if isinstance(k, str)
                            and len(k) <= 40 and k.isascii()
                            and all(ch.isalnum() or ch in "_-" for ch in k)
                        )[:35] if isinstance(child, dict) else [],
                    })
        except Exception:
            pass
        # Probe the two established, same-item frame pack names only. This
        # confirms whether the underlying source frames still exist, but does
        # NOT assert a trustworthy ordered rotation without a scramble map.
        for n in (1, 2):
            path = f"{n}.json"
            url = _safe_source_url(root + "/" + path)
            assert urlsplit(url).hostname == "media.d360.us"
            try:
                response = http.get(url, timeout=15)
                item = {"reference": R23_ID, "source": path,
                        **response_shape(response)}
                if response.status_code == 200:
                    try:
                        batch = json.loads(response.content)
                        item["json_type"] = type(batch).__name__
                        item["frame_strings"] = (
                            len(batch) if isinstance(batch, list)
                            and all(isinstance(x, str) for x in batch) else None
                        )
                    except (ValueError, UnicodeDecodeError):
                        item["json_type"] = "invalid_json"
                outputs.append(item)
            except Exception as exc:
                outputs.append({"reference": R23_ID, "source": path,
                                "state": "transport_failure",
                                "error_class": type(exc).__name__})
    if preflight.get("preflight") == "missing_scramble":
        # Valid-looking progressive packs do not imply an authenticated viewer
        # order. Probe all original JPEGs to distinguish missing bytes from
        # an unsupported unscrambled/legacy transport.
        outputs.append(audit_r23_original_pack_set(http, root, (600, 600)))
        outputs.extend(audit_r23_viewer_scripts(http))
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
    client = UrllibHttpClient(max_bytes=12_000_000)
    records = audit_r07(client) if args.reference == "r07" else audit_r23(client)
    for record in records:
        print("REFERENCE_ORIGINAL_AUDIT " + json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
