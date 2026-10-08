"""One-time public live Diyona certificate field comparison diagnostic.

Do not print public anon key, URLs, HTTP bodies or arbitrary exception text.
"""
import re
from decimal import Decimal
from diamond_retrieval import retrieve_diamond
from diamond_retrieval.errors import IdentityConflictError

URL = "https://diyona.com/pages/diamond-detail?sku=A69835AA4"

def safe_value(value):
    if isinstance(value,(int,float,Decimal)):
        return str(value)
    if isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9 -]{1,45}",value):
        return value
    if isinstance(value,tuple) and len(value)<=4:
        return "(" + ",".join(safe_value(v) for v in value) + ")"
    return "[redacted]"

try:
    r=retrieve_diamond(URL)
    print("Live Diyona identity: successful",r.metadata.report_number, "status",r.status)
    print("evidence types",[(x.kind,len(getattr(x,"frames",[]))) for x in r.evidence])
except IdentityConflictError as exc:
    print("Live Diyona identity conflicts",len(exc.comparisons))
    for c in exc.comparisons:
        print("FIELD",c.field,"VALUES",[safe_value(v) for v in c.values])
        print("SOURCES",[p.source for p in c.provenance][:6])
except Exception as exc:
    print("Live Diyona error type",type(exc).__name__)
