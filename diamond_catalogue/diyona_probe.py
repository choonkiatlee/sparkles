"""Ephemeral, public non-browser Diyona listing diagnostics for CI investigation.

Only emits HTTP metadata, *names* of HTML structural fields, and safe path
patterns from public front-end scripts. Never log HTML, cookies, headers,
query values, source JS, inline scripts or authentication tokens.
"""
from __future__ import annotations

import hashlib
import html.parser
import json
import re
from urllib.parse import urljoin, urlsplit

from diamond_retrieval.http import UrllibHttpClient

URL = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"


class Tags(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.inline = []
        self._script = False
        self.scratch = ""
        self.meta = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "script":
            src = d.get("src")
            self._script = not bool(src)
            self.scratch = ""
            if src:
                self.scripts.append(src)
        if tag == "meta":
            self.meta.append((d.get("name") or d.get("property") or "", d.get("content") or ""))
        if tag == "link":
            self.links.append((d.get("rel") or "", d.get("href") or ""))

    def handle_data(self, data):
        if self._script:
            self.scratch += data[:150000]

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self.inline.append(self.scratch)
            self._script = False


def show_path(v: str):
    p = urlsplit(v)
    # Only route path; never print query, fragment, credentials or tokens.
    return (p.hostname or "") + p.path[:190]


def run():
    c = UrllibHttpClient(max_bytes=10*1024*1024)
    r = c.get(URL, timeout=22)
    body = r.content.decode("utf-8", "replace")
    parsed = Tags()
    parsed.feed(body)
    print("HTML status", r.status_code, "bytes", len(r.content), "final_host", urlsplit(r.url).hostname)
    print("HTML sha256", hashlib.sha256(r.content).hexdigest())
    for label, pattern in [
        ("target SKU", "A69835AA4"),
        ("target IGI", "LG816611062"),
        ("certificate label", "Certificate Number"),
        ("IGI cert number", "IGI"),
        ("identity section", "SKU:"),
        ("loading text", "Loading"),
        ("next data", "__NEXT_DATA__"),
        ("shopify", "shopify"),
        ("script JSON", "application/ld+json"),
        ("script fetch", "fetch("),
    ]:
        print("HTML has",label,pattern.lower() in body.lower())
    print("script count",len(parsed.scripts),"inline count",len(parsed.inline))
    print("script paths",json.dumps([show_path(urljoin(URL,x)) for x in parsed.scripts[:35]]))
    print("meta names",[k[:60] for k,v in parsed.meta if k][:25])
    print("inline lengths",[len(x) for x in parsed.inline[:12]])
    print("inline clues",{
        label:sum(label.lower() in x.lower() for x in parsed.inline)
        for label in ["A69835AA4","LG816611062","certificate","api/","fetch(","diamond","graphql"]
    })
    # Limit front-end JS to same-host or CDN-origin scripts advertised by the
    # public HTML and do not execute JS. Log only regex-discovered generic API
    # route literals and external API hostnames, never query parameters.
    for script in parsed.scripts[:20]:
        full = urljoin(URL,script)
        try:
            resp=c.get(full,timeout=16)
            js=resp.content.decode("utf-8","replace")
            paths=sorted(set(re.findall(r'(?:(?:"|\\\\")|\\x27)(/(?:api|apps|pages|products|graphql|diamonds|search)[A-Za-z0-9_./-]{1,100})',js,re.I)))
            hosts=sorted(set(re.findall(r'https?://([a-z0-9._-]{5,95})/(?:api|graphql|diamond)',js,re.I)))
            print("JS",show_path(full),"status",resp.status_code,"bytes",len(resp.content),
                  "diamond_term",("diamond" in js.lower()),"api_paths",paths[:18],
                  "api_hosts",hosts[:16])
        except Exception as exc:
            print("JS",show_path(full),"failure_type",type(exc).__name__)


if __name__ == "__main__":
    run()
