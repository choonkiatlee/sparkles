"""Temporary one-run public-http-only Diyona frontend probe.

Deliberately logs only structural diagnostics and public script URLs,
not raw HTML, response bodies, customer data, API credentials or tokens.
"""
import html.parser
import re
import urllib.parse
from diamond_retrieval.http import UrllibHttpClient

URL = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"

class Collector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.inline = []
        self.active = False
        self.current = []
        self.tags = []
    def handle_starttag(self, tag, attrs):
        attr=dict(attrs)
        if tag=="script":
            if "src" in attr:
                self.scripts.append(urllib.parse.urljoin(URL, attr["src"]))
            else:
                self.active=True
                self.current=[]
            self.tags.append({"type":attr.get("type"),"id":attr.get("id")})
    def handle_data(self, data):
        if self.active: self.current.append(data)
    def handle_endtag(self,tag):
        if tag=="script" and self.active:
            self.inline.append("".join(self.current))
            self.active=False

def safe_name(url):
    parsed=urllib.parse.urlsplit(url)
    return parsed.hostname + parsed.path if parsed.hostname else parsed.path

def print_hits(label,text):
    keys=["LG816611062","A69835AA4","graphql","/api/","diamond","nivoda","getDiamond","fetch(","shopify","endpoint"]
    for term in keys:
        print("      ",term, len(re.findall(re.escape(term),text,re.I)))
    # Print only public endpoint paths and hostnames, not query/parameter values.
    out=set()
    for match in re.finditer(r"""https?://[a-zA-Z0-9.-]+/[a-zA-Z0-9/_-]{3,100}""",text):
        val=match.group(0)
        if any(w in val.lower() for w in ("api","diamond","graphql","nivoda","fetch","cdn.shopify")):
            out.add(val)
    print("      endpoint candidates",list(sorted(out))[:35])

def main():
    client=UrllibHttpClient(max_bytes=8_000_000)
    r=client.get(URL,timeout=25)
    print("URL status",r.status_code,"bytes",len(r.content),"type",r.headers.get("Content-Type"))
    if r.status_code!=200: return
    text=r.content.decode("utf-8","replace")
    print_hits("page",text)
    parsed=Collector()
    parsed.feed(text)
    print("scripts external",len(parsed.scripts),"inline",len(parsed.inline))
    print("script URLs", [safe_name(s) for s in parsed.scripts[:35]])
    print("script tags",parsed.tags[:25])
    for i,s in enumerate(parsed.inline):
        if any(k in s.lower() for k in ("diamond","api","graphql","nivoda","report")):
            print("Inline candidate",i,"bytes",len(s))
            print_hits("inline",s)
    # Diagnose public page frontend request shapes without logging API credentials.
    # Show a small bounded code window around the selected query functions.
    for i in (45, 46, 50):
        if i >= len(parsed.inline): continue
        body = parsed.inline[i]
        print("inline request trace",i)
        patterns = ("getDiamond", "get-diamond", "diamond-by", "diamond-ring-builder-flax", ".from(", "supabase", "fetch(", "API_BASE", "api/diamond")
        for term in patterns:
            positions=[m.start() for m in re.finditer(re.escape(term),body,re.I)]
            for pos in positions[:5]:
                # Never display credentials, full URL query parameters or secrets.
                snippet=body[max(0,pos-100):min(len(body),pos+210)].replace("\\n"," ")
                snippet=re.sub(r"""(?i)(?:apikey|access_token|authorization|anon_key|password)\\s*[:=]\\s*["'][^"']+["']""","[redacted]",snippet)
                print("    ",term,repr(snippet[:310]))
    # A handful of scripts only, bounded by total response size.
    for i,s in enumerate(parsed.scripts[:24]):
        if s.startswith("https://") and urllib.parse.urlsplit(s).hostname in {"diyona.com","www.diyona.com","cdn.shopify.com"}:
            try:
                resp=client.get(s,timeout=18)
                content=resp.content.decode("utf-8","replace") if resp.status_code==200 else ""
                print("script",i,safe_name(s),"status",resp.status_code,"bytes",len(content))
                if any(x in content.lower() for x in ("diamond","nivoda","api/")):
                    print_hits("script",content)
            except Exception as e:
                print("script",i,"failed",type(e).__name__)
if __name__=="__main__":
    main()
