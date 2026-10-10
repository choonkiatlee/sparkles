#!/usr/bin/env python3
"""Read-only R07 Pixorac cache probe using ONLY the already-curated exact viewer.

An absent Nivoda v360.url does not establish that Pixorac has no cache.
Test the reversible base64url encoding of the buyer's precise V360 viewer,
plus its query-key-order-equivalent spelling. Neither URL is provider-supplied:
results remain source *research*, never automatically trusted publication.

No alternative diamond IDs, supplier searches, authentication, paywall bypass,
or persistent JPEG storage. Bounded public HTTPS, no redirects off exact root.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.motion import validate_jpeg_bytes

ROOT = Path(__file__).resolve().parents[1]
REF = "ps285166-r07"
REPORT = "LG625406458"
VIEWER = "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i"
PIXORAC_HOST = "assets-images.pixorac.com"
FRAME_COUNT = 256
MAX_FRAME_BYTES = 1024 * 1024
MAX_ROTATION_BYTES = 25 * 1024 * 1024


def pinned_source():
    record = json.loads((ROOT / "data/references" / (REF + ".json")).read_text("utf-8"))
    if (record.get("id") != REF
        or record.get("identity") != {
            "lab": "IGI", "report_number": REPORT, "status": "reported"
        }
        or record.get("media_sources") != [{
            "kind": "viewer", "provider": "v360.diamonds",
            "status": "linked_unverified", "url": VIEWER
        }]
        or not any(
            e.get("kind") == "still" and e.get("status") == "success"
            for e in record.get("evidence", [])
        )):
        raise ValueError("R07 curated reference, original viewer or still changed")
    return VIEWER


def exact_serializations():
    """Only two presentations of the same exact buyer-provided URL."""
    viewer = pinned_source()
    parts = urlsplit(viewer)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    assert (parts.scheme, parts.hostname, parts.path, parts.fragment) == (
        "https", "v360.diamonds",
        "/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b", ""
    )
    assert sorted(pairs) == [("a", "625406458"), ("m", "i")]
    canonical = urlunsplit(parts._replace(query=urlencode([("m", "i"), ("a", "625406458")])))
    assert sorted(parse_qsl(urlsplit(canonical).query)) == sorted(pairs)
    return (("buyer_exact", viewer), ("query_order_equivalent", canonical))


def encoded_root(viewer):
    # A deterministic hypothesis for a public proxy cache, NOT a source
    # authorized by the Nivoda exact-certificate record.
    token = base64.urlsafe_b64encode(viewer.encode("utf-8")).decode("ascii").rstrip("=")
    return f"https://{PIXORAC_HOST}/{token}"


def check_rotation(http, *, variant, viewer):
    root = encoded_root(viewer)
    output = {
        "candidate": variant,
        "root_sha256": hashlib.sha256(root.encode("utf-8")).hexdigest(),
        "source_from_verified_provider": False,
        "outcome": "not_checked",
    }
    hashes = []
    dims = None
    total = 0
    for index in range(FRAME_COUNT):
        url = f"{root}/{index}.jpg"
        try:
            response = http.get(url, timeout=12)
        except Exception as exc:
            output.update(outcome="request_error", failed_index=index,
                          error_type=type(exc).__name__)
            return output
        if index == 0:
            output["first_http"] = response.status_code
        if response.status_code != 200:
            output.update(outcome="frame_unavailable", failed_index=index,
                          frame_http=response.status_code)
            return output
        if response.url != url:
            output.update(outcome="redirect_refused", failed_index=index)
            return output
        content = response.content
        if not content or len(content) > MAX_FRAME_BYTES:
            output.update(outcome="invalid_frame_size", failed_index=index)
            return output
        total += len(content)
        if total > MAX_ROTATION_BYTES:
            output.update(outcome="rotation_oversized", failed_index=index)
            return output
        try:
            size = validate_jpeg_bytes(content)
        except Exception:
            output.update(outcome="invalid_jpeg", failed_index=index)
            return output
        if dims is None:
            dims = size
        elif size != dims:
            output.update(outcome="dimensions_changed", failed_index=index)
            return output
        hashes.append(hashlib.sha256(content).hexdigest())
    n_unique = len(set(hashes))
    output.update(
        outcome=("complete_unattributed_proxy_rotation" if n_unique == FRAME_COUNT
                 else "insufficient_distinct_frames"),
        frame_count=FRAME_COUNT,
        distinct_frame_sha256=n_unique,
        dimensions=dims,
        byte_total=total,
        first_frame_sha256=hashes[0],
        last_frame_sha256=hashes[-1],
        ordered_sha_chain=hashlib.sha256("".join(hashes).encode()).hexdigest(),
    )
    return output


def probe(http):
    result = {
        "schema": "sparkles-r07-direct-pixorac-cache-audit/1",
        "reference": REF, "report": REPORT,
        "identity_status": "reported",
        "source": "buyer_viewer_base64url_derivation_not_provider_authorized",
        "mode": "read_only_no_media_publishing",
        "candidates": [],
    }
    for variant, viewer in exact_serializations():
        result["candidates"].append(check_rotation(http, variant=variant, viewer=viewer))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Fail closed if the reference was edited or no longer has a valid anchor.
    pinned_source()
    result = probe(UrllibHttpClient(max_bytes=MAX_FRAME_BYTES))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
