"""R02-only, read-only discovery of the exact Pixorac indexed cache.

The public exact-report Loupe viewer loads an opaque Pixorac subdirectory.
We accept only the byte-for-byte source root previously audited in Actions
#38078719770, not a guessed inventory ID. The root stays in the job environment,
never in public Actions logs or a reference manifest.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

REFERENCE_ID = "ps285166-r02"
REPORT = "LG634479985"
VIEWER = "https://loupe360.com/diamond/" + REPORT
SUPPLIER_VIEWER = "https://mediassests.s3.amazonaws.com/V360/Vision360.html"
EXPECTED_ROOT_SHA256 = "1b5dff721515cf0cb5cb38f2ed228a1c0ea1f806f0396862c52140c5b2d13dc8"
CACHE_REF = "r02-browser-observed-pixorac-sha256:" + EXPECTED_ROOT_SHA256
# Only source-observed public indexed image URLs from the exact certificate's viewer.
_INDEXED = re.compile(
    r"^/([A-Za-z0-9_-]{20,1024}={0,2})/([A-Za-z0-9._~+=:-]{1,24})/"
    r"([0-9]{1,3})\.(?:jpg|webp)$"
)


def validate_root(root: str) -> str:
    if not isinstance(root, str) or len(root) > 1600:
        raise ValueError("R02 Pixorac browser root missing or too long")
    parsed = urlsplit(root)
    if (parsed.scheme != "https" or parsed.netloc != "assets-images.pixorac.com"
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("R02 browser root is not the audited HTTPS host")
    pieces = parsed.path.split("/")
    if len(pieces) != 3 or not pieces[1] or not re.fullmatch(
        r"[A-Za-z0-9_-]{20,1024}={0,2}", pieces[1]
    ) or not re.fullmatch(r"[A-Za-z0-9._~+=:-]{1,24}", pieces[2]) or ".." in pieces[2]:
        raise ValueError("R02 Pixorac path does not match observed source shape")
    try:
        supplier = base64.urlsafe_b64decode(
            pieces[1] + "=" * (-len(pieces[1]) % 4)
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("R02 browser cache source token invalid") from exc
    if supplier != SUPPLIER_VIEWER:
        raise ValueError("R02 browser cache wraps an untrusted supplier")
    if hashlib.sha256(root.encode("utf-8")).hexdigest() != EXPECTED_ROOT_SHA256:
        raise ValueError("R02 source does not match independently audited fingerprint")
    return root


def observed_root_from_browser_events(messages: list[dict]) -> str:
    """Reconcile CDP request IDs with HTTP 200 responses; never infer endpoints."""
    requests: dict[str, str] = {}
    accepted: set[str] = set()
    for row in messages:
        method = row.get("method")
        params = row.get("params") or {}
        ident = params.get("requestId")
        if method == "Network.requestWillBeSent":
            url = (params.get("request") or {}).get("url")
            if isinstance(ident, str) and isinstance(url, str):
                requests[ident] = url
        elif method == "Network.responseReceived" and params.get("response", {}).get("status") == 200:
            url = requests.get(ident)
            if url:
                parts = urlsplit(url)
                if (parts.scheme == "https" and parts.netloc == "assets-images.pixorac.com"
                        and not parts.query and not parts.fragment):
                    match = _INDEXED.fullmatch(parts.path)
                    if match and int(match.group(3)) < 256:
                        accepted.add("https://assets-images.pixorac.com/" +
                                     match.group(1) + "/" + match.group(2))
    if len(accepted) != 1:
        raise ValueError("R02 browser observed no unique successful indexed source")
    return validate_root(next(iter(accepted)))


def discover_root() -> str:
    """Open only exact Loupe certificate views in a token-free headless browser."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                "--window-size=1280,900"):
        options.add_argument(arg)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    observed: list[dict] = []
    try:
        driver.set_page_load_timeout(25)
        driver.execute_cdp_cmd("Network.enable", {})
        for suffix in ("", "/video/500/500"):
            driver.get(VIEWER + suffix)
            time.sleep(6)
            for entry in driver.get_log("performance"):
                try:
                    observed.append(json.loads(entry["message"])["message"])
                except (ValueError, TypeError, KeyError):
                    pass
        return observed_root_from_browser_events(observed)
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    root = discover_root()
    # GitHub env file belongs to this run; no URL or tokenized root in stdout.
    with args.github_env.open("a", encoding="utf-8") as output:
        output.write("R02_PIXORAC_ROOT=" + root + "\n")
    print("R02 exact public browser cache: verified SHA-256 " + EXPECTED_ROOT_SHA256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
