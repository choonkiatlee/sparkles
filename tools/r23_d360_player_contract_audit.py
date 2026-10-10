"""Read-only bounded player-code audit of the exact R23 D360 viewer.

Inspect only the public exact viewer HTML and up to six first-party script-src
assets explicitly included by that page. Never eval JS, follow arbitrary links,
or output full source/URL tokens. Report bounded contextual code windows around
frame-order semantics to inform source-specific contract investigation.
"""
from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit

from diamond_retrieval.http import UrllibHttpClient
from diamond_retrieval.reference_media import _safe_source_url

VIEWER = "https://d360.tech/view.html?d=89-AY-8102"
HOST = "d360.tech"
_TERMS = re.compile(
    r"scramble|shuffle|frame|rotate|rotation|progressive|imaged|"
    r"0[.]json|kvideo|array|index|order|angle|step|"
    r"video|loader|surl|baseurl",
    re.IGNORECASE,
)
_CLEAN = re.compile(r"[^a-zA-Z0-9_\[\](){};:=+.\-/*?,<> \t\n]")


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.externals = []
        self.inlines = []
        self._inside = False
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        self._inside = True
        self._buffer = []
        source = dict(attrs).get("src")
        if source:
            self.externals.append(source)

    def handle_data(self, data):
        if self._inside:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._inside:
            code = "".join(self._buffer)
            if code.strip():
                self.inlines.append(code)
            self._inside = False
            self._buffer = []


def code_windows(content: str, *, max_windows: int = 24, radius: int = 115) -> dict:
    """Bounded printable contexts with URL/base64/identifiers redacted."""
    intervals = []
    for match in _TERMS.finditer(content):
        start = max(0, match.start()-radius)
        end = min(len(content), match.end()+radius)
        if any(start <= b and end >= a for a, b in intervals):
            # For high-density keywords, retain disjoint windows only.
            continue
        intervals.append((start, end))
        if len(intervals) >= max_windows:
            break
    contexts = []
    for start,end in intervals:
        snippet = content[start:end]
        snippet = re.sub(r"https?://[^\\s\"'<>]+", "<redacted-url>", snippet)
        snippet = re.sub(r"[A-Za-z0-9+/]{90,}={0,2}", "<redacted-large-token>", snippet)
        snippet = _CLEAN.sub(" ", snippet)
        contexts.append(" ".join(snippet.split())[:260])
    return {
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "bytes": len(content.encode()),
        "terms": sorted(set(x.group(0).lower() for x in _TERMS.finditer(content)))[:35],
        "windows": contexts,
    }


def run() -> None:
    client = UrllibHttpClient(max_bytes=800_000)
    url = _safe_source_url(VIEWER)
    response = client.get(url, timeout=15)
    print("R23_PLAYER "+json.dumps({"source":"viewer","http":response.status_code,
            "sha256":hashlib.sha256(response.content).hexdigest(),
            "bytes":len(response.content)},sort_keys=True),flush=True)
    if response.status_code != 200:
        return
    parser = Scripts()
    parser.feed(response.content.decode("utf-8","replace"))
    print("R23_PLAYER "+json.dumps({"source":"html_structure",
        "inline_script_count":len(parser.inlines),
        "external_script_count":len(parser.externals),
        "external_basenames":[urlsplit(urljoin(VIEWER,x)).path.rsplit("/",1)[-1][:60]
            for x in parser.externals][:20]},sort_keys=True),flush=True)
    for index, code in enumerate(parser.inlines[:12],1):
        print("R23_PLAYER "+json.dumps({"source":f"inline-{index}",
            **code_windows(code,max_windows=18)},sort_keys=True),flush=True)
    # Fixed bounded excerpts from the actual public, inlined (obfuscated)
    # D360 player. No runtime JS, vendor requests or string-table eval.
    if len(parser.inlines) >= 2:
        code = parser.inlines[1]
        anchors = (
            "new Array(0x100)", "await fetch(", "fetch(",
            "subtle", "atob(", "0x100", "0x80", "rotate",
            "recordRotation", "frameContainer", "function _0x",
        )
        for label in anchors:
            match = code.find(label)
            if match < 0:
                continue
            start = max(0, match - 650)
            snippet = code[start : min(len(code), match + 1700)]
            snippet = re.sub(r"https?://[^\s\"'<>]+", "<redacted-url>", snippet)
            snippet = re.sub(r"[A-Za-z0-9+/]{120,}={0,2}", "<redacted-token>", snippet)
            # Public program code only: bounded excerpt, not supplier data or
            # arbitrary media links.
            print("R23_PLAYER_FOCUS "+json.dumps({
                "anchor":label, "offset":match,
                "snippet":" ".join(snippet.split())[:2200]
            },sort_keys=True),flush=True)
    count=0
    for source in parser.externals:
        parsed=urlsplit(urljoin(VIEWER,source))
        if (parsed.scheme!="https" or parsed.hostname!=HOST or parsed.port not in (None,443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.endswith(".js") or ".." in parsed.path or len(parsed.path)>160):
            continue
        if count>=6:
            break
        count+=1
        url=_safe_source_url(parsed.geturl())
        try:
            js=client.get(url,timeout=15)
            if js.status_code!=200:
                payload={"status":js.status_code}
            else:
                payload=code_windows(js.content.decode("utf-8","replace"),max_windows=40)
            print("R23_PLAYER "+json.dumps({"source":f"same-origin-script-{count}",
                "basename":parsed.path.rsplit("/",1)[-1],**payload},
                sort_keys=True),flush=True)
        except Exception as exc:
            print("R23_PLAYER "+json.dumps({"source":f"same-origin-script-{count}",
                    "error_class":type(exc).__name__},sort_keys=True),flush=True)


if __name__ == "__main__":
    run()
