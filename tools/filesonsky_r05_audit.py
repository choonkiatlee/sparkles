"""Read-only transport audit for R05's exact identity-backed FilesOnSky Vision360 viewer.

This is a diagnostic, NOT a downloader or license to publish media.
Only one exact trusted viewer and two established Vision360 bootstrap shapes are
requested. Do not follow outbound script references or accept user URLs.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.motion_sources import _bootstrap_contract
from diamond_retrieval.reference_media import _safe_source_url

ROOT = Path(__file__).resolve().parents[1]
REF = "ps285166-r05"
REPORT = "LG644442866"
HOST = "www.filesonsky.com"
VIEWER = "https://www.filesonsky.com/v360/Vision360.HTML?d=659844"
# Known same-origin Vision360 transport layouts, not arbitrary domain exploration.
ROOTS = (
    "https://www.filesonsky.com/imaged/659844",
    "https://www.filesonsky.com/v360/imaged/659844",
)


class ScriptList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        src = dict(attrs).get("src")
        if src:
            self.sources.append(src)


def describe_html(data: bytes) -> dict:
    """List only script host/path shapes; never expose query credentials."""
    html = data.decode("utf-8", "replace")
    parser = ScriptList()
    parser.feed(html)
    scripts = []
    for item in parser.sources[:12]:
        parsed = urlsplit(urljoin(VIEWER, item))
        scripts.append({
            "host": parsed.hostname if parsed.hostname in {
                HOST, "filesonsky.com", "cdnjs.cloudflare.com", "code.jquery.com"
            } else "<other>",
            "path_suffix": Path(parsed.path).name[:72],
            "has_query": bool(parsed.query),
        })
    lowered = html.lower()
    return {
        "html_sha256": hashlib.sha256(data).hexdigest(),
        "html_bytes": len(data),
        "scripts": scripts,
        "inline_script": "<script" in lowered and len(scripts) == 0,
        "mentions_imaged": "imaged" in lowered,
        "mentions_json": ".json" in lowered,
        "mentions_mp4": ".mp4" in lowered,
        "mentions_vision360": "vision360" in lowered,
        "mentions_surl": "surl" in lowered,
    }


def valid_trusted_source() -> None:
    ref = json.loads((ROOT / "data/references/ps285166-r05.json").read_text("utf-8"))
    assert ref["id"] == REF and ref["identity"] == {
        "lab": "IGI", "report_number": REPORT, "status": "reported"
    }, "R05 source/identity changed"
    attempts = ref.get("enrichment_attempts", [])
    assert any(
        a.get("reference_identifier") == REF + ":loupe-report:supplier-rotation"
        and a.get("locator") == VIEWER
        and a.get("status") == "unsupported"
        for a in attempts
    ), "Exact provider source not verified by trusted publication"
    assert _safe_source_url(VIEWER) == VIEWER


def status_for_bootstrap(data: bytes) -> dict:
    """No raw media, scripts, tokens or JSON bodies in CI logs."""
    try:
        obj = json.loads(data)
        dims, scramble, version = _bootstrap_contract(obj, source="r05-audit")
        return {
            "wire": "progressive-bootstrap-valid",
            "dimensions": list(dims),
            "version": version,
            "scramble_len": len(scramble),
        }
    except Exception:
        return {"wire": "not-progressive-bootstrap"}


def run() -> None:
    valid_trusted_source()
    client = UrllibHttpClient(max_bytes=400_000)
    response = client.get(VIEWER, timeout=12)
    viewer = {"source": "r05-exact-viewer", "http": response.status_code}
    if response.status_code == 200:
        viewer.update(describe_html(response.content))
    print("FILESONSKY_AUDIT " + json.dumps(viewer, sort_keys=True), flush=True)
    if response.status_code != 200:
        return
    # Read-only bounded probes of just two existing Vision360 source layouts.
    # A 200 response does not prove frames are available; validate JSON contract.
    for index, root in enumerate(ROOTS):
        for suffix in ("/0.json?version=", "/0.json"):
            url = _safe_source_url(root + suffix)
            assert urlsplit(url).hostname == HOST
            result = {"source": "bootstrap-" + str(index), "variant": suffix}
            try:
                fetch = client.get(url, timeout=12)
                result["http"] = fetch.status_code
                if fetch.status_code == 200:
                    result.update(status_for_bootstrap(fetch.content))
                    result["sha256"] = hashlib.sha256(fetch.content).hexdigest()
            except Exception:
                result["status"] = "transport-failure-or-blocked"
            print("FILESONSKY_AUDIT " + json.dumps(result, sort_keys=True), flush=True)


def full_original_audit() -> None:
    """Validate all 256 source originals without writes or supplier HTML parsing."""
    from diamond_retrieval.models import EvidenceReference, ROTATION
    from diamond_retrieval.motion import ProgressiveRotationProcessor
    from diamond_retrieval.motion_sources import FilesOnSkyRotationDownloader

    valid_trusted_source()
    ref = EvidenceReference(
        identifier=REF + ":source-audit",
        kind=ROTATION,
        retrieval_key=VIEWER,
        locator=VIEWER,
        provenance=(),
        metadata={"lab": "IGI", "report_number": REPORT},
    )
    try:
        raw = FilesOnSkyRotationDownloader(UrllibHttpClient(), timeout=25).download(ref)
        rotations = ProgressiveRotationProcessor().process(raw)
        assert len(rotations) == 1, "not a single complete rotation"
        frames = rotations[0].frames
        assert len(frames) == 256
        assert [frame.source_index for frame in frames] == list(range(256))
        assert rotations[0].metadata.get("sequence_complete") is True
        print("FILESONSKY_FULL " + json.dumps({
            "status": "validated",
            "reference": REF,
            "frame_count": len(frames),
            "dimensions": list(rotations[0].metadata["dimensions"]),
            "first_source_sha256": hashlib.sha256(frames[0].payload).hexdigest(),
            "last_source_sha256": hashlib.sha256(frames[-1].payload).hexdigest(),
            "source_responses": len(raw.source_responses),
        }, sort_keys=True), flush=True)
    except Exception as exc:
        print("FILESONSKY_FULL " + json.dumps({
            "status": "not_validated", "reason_class": type(exc).__name__,
        }, sort_keys=True), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--full"]:
        full_original_audit()
    elif sys.argv[1:] == []:
        run()
    else:
        raise SystemExit("Only --full is supported")
