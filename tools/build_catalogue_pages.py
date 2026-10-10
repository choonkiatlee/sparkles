"""Build and validate a static Pages deployment without Python sources or .git."""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC_PATHS = ("index.html", ".nojekyll", "catalogue", "learning", "data/catalog.json", "data/diamonds", "data/reference-index.json", "data/references", "evaluations", "resources")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.urls.append(value)

def validate_site(directory: Path) -> None:
    catalogue = json.loads((directory / "data/catalog.json").read_text(encoding="utf-8"))
    if catalogue.get("schema") != "sparkles-diamond-index/1":
        raise ValueError("Unsupported catalogue index schema")
    rows = catalogue.get("diamonds")
    if not isinstance(rows, list):
        raise ValueError("Catalogue index missing diamonds array")
    seen = set()
    for row in rows:
        identifier, path = row.get("id"), row.get("manifest_path")
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier) or identifier in seen:
            raise ValueError("Invalid or duplicate published diamond id")
        seen.add(identifier)
        if path != f"data/diamonds/{identifier}.json":
            raise ValueError("Unsafe/noncanonical diamond manifest path")
        manifest = json.loads((directory / path).read_text(encoding="utf-8"))
        if manifest.get("id") != identifier:
            raise ValueError("Index and manifest identity mismatch")
    references = json.loads((directory / "data/reference-index.json").read_text(encoding="utf-8"))
    if references.get("schema") != "sparkles-reference-index/1" or not isinstance(references.get("references"), list):
        raise ValueError("Invalid static reference index")
    reference_ids = set()
    for row in references["references"]:
        identifier = row.get("id")
        if (not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier)
                or identifier in reference_ids or row.get("selection_id") != f"ref-{identifier}"):
            raise ValueError("Invalid/duplicate reference or comparison selection ID")
        reference_ids.add(identifier)
        path = row.get("manifest_path")
        if path != f"data/references/{identifier}.json":
            raise ValueError("Unsafe/noncanonical reference path")
        manifest = json.loads((directory / path).read_text(encoding="utf-8"))
        if manifest.get("schema") != "sparkles-reference/1" or manifest.get("id") != identifier:
            raise ValueError("Reference index/manifest mismatch")
        if row["selection_id"] in seen:
            raise ValueError("Shared basket selection ID collision")
    for rel in ("index.html", "catalogue/index.html", "learning/index.html"):
        doc = directory / rel
        parser = Links()
        parser.feed(doc.read_text(encoding="utf-8"))
        for href in parser.urls:
            if href.startswith(("#", "//")):
                continue
            parsed = urlsplit(href)
            if parsed.scheme or not parsed.path:
                continue
            resolved = (doc.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(directory.resolve()) or not resolved.exists():
                raise ValueError(f"Broken or unsafe local link from {rel}: {href[:160]}")

def build(destination: Path) -> None:
    destination = destination.resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("Destination must not contain the repository root")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for rel in STATIC_PATHS:
        source = ROOT / rel
        if not source.exists():
            raise FileNotFoundError(source)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    validate_site(destination)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.dest)
    print(f"Validated static Pages bundle at {args.dest}")
