"""Download original immutable catalogue frames, render auditable thumbnail previews.

Usage: python tools/build_faceup_previews.py --output out igi-lg756520111 ...
Never writes data/catalog.json or marks any candidate verified.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from diamond_catalogue.faceup_thumbnail import preview_manifest

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("diamond_ids",nargs="+")
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=True)
    results={}
    failures=0
    for identifier in args.diamond_ids:
        if not identifier.startswith("igi-") or not identifier.replace("-","").isalnum():
            parser.error("Only explicitly named stable IGI IDs are supported")
        source=ROOT / "data" / "diamonds" / f"{identifier}.json"
        if not source.is_file():
            print(f"Missing catalogued manifest: {identifier}",file=sys.stderr)
            failures+=1
            continue
        manifest=json.loads(source.read_text(encoding="utf-8"))
        if manifest["id"] != identifier:
            print(f"Identity mismatch: {identifier}",file=sys.stderr)
            failures+=1
            continue
        try:
            result=preview_manifest(manifest,args.output)
            results[identifier]={
                "status":result["status"],
                "selected":result.get("source",{}).get("source_index"),
                "derivative_sha256":result.get("derivative",{}).get("sha256"),
            }
            if not (args.output / f"{identifier}.webp").is_file():
                failures+=1
        except (ValueError, OSError, RuntimeError) as exc:
            # Public CI: avoid printing full credentialed upstream URLs.
            (args.output / f"{identifier}-error.txt").write_text(
                "Unable to generate candidate: "+type(exc).__name__+"\n",
                encoding="utf-8",
            )
            print(f"{identifier}: {type(exc).__name__} while downloading/processing saved frames",
                  file=sys.stderr)
            failures+=1
    (args.output / "summary.json").write_text(
        json.dumps(results,sort_keys=True,indent=2)+"\n",encoding="utf-8",
    )
    print(json.dumps(results,sort_keys=True,indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
