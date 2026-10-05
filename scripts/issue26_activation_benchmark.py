#!/usr/bin/env python3
"""Temporary issue #26 benchmark runner using authoritative committed source hashes."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from diamond360 import asscher_steps
from diamond360 import benchmark
from diamond360 import activation_benchmark
from diamond360.pipeline import run as preprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "360" / "activation"
BENCHMARK = ROOT / "docs" / "360" / "benchmark" / "benchmark.json"
CERTS = ("IGI-LG756580087", "IGI-LG756520111", "IGI-LG818659722", "IGI-LG836619414")
CORE = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]
WIDE = [240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def image_candidates(value, base_url: str):
    if isinstance(value, dict):
        for child in value.values():
            yield from image_candidates(child, base_url)
    elif isinstance(value, list):
        for child in value:
            yield from image_candidates(child, base_url)
    elif isinstance(value, str):
        text = value.strip()
        raw = None
        if text.startswith("data:image/") and ";base64," in text:
            try:
                raw = base64.b64decode(text.split(",", 1)[1], validate=False)
            except Exception:
                raw = None
        elif text.startswith("/9j/") or text.startswith("iVBOR"):
            try:
                raw = base64.b64decode(text, validate=False)
            except Exception:
                raw = None
        elif text.startswith(("http://", "https://")):
            lowered = urllib.parse.urlparse(text).path.lower()
            if lowered.endswith((".jpg", ".jpeg", ".png", ".webp")):
                try:
                    raw = fetch(text)
                except Exception:
                    raw = None
        elif any(text.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            try:
                raw = fetch(urllib.parse.urljoin(base_url, text))
            except Exception:
                raw = None
        if raw and (raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"\x89PNG") or raw.startswith(b"RIFF")):
            yield raw


def recover_subset(full_manifest: Path, indices: list[int], destination: Path) -> Path:
    manifest = json.loads(full_manifest.read_text())
    wanted = {int(i) for i in indices}
    records = [record for record in manifest["frames"] if record["source_index"] in wanted]
    if {record["source_index"] for record in records} != wanted:
        raise RuntimeError(f"{manifest['certificate']}: complete manifest does not cover requested indices")

    destination.mkdir(parents=True, exist_ok=True)
    (destination / "frames").mkdir(exist_ok=True)
    by_batch = {}
    for record in records:
        by_batch.setdefault(record["source_url"], []).append(record)

    for url, batch_records in by_batch.items():
        payload = fetch(url)
        batch_meta = next((b for b in manifest["batches"] if b["url"] == url), None)
        if batch_meta and hashlib.sha256(payload).hexdigest() != batch_meta["sha256"]:
            raise RuntimeError(f"{manifest['certificate']}: batch hash mismatch for {url}")
        parsed = json.loads(payload)
        candidates = {}
        for raw in image_candidates(parsed, url):
            candidates.setdefault(hashlib.sha256(raw).hexdigest(), raw)
        for record in batch_records:
            raw = candidates.get(record["sha256"])
            if raw is None:
                raise RuntimeError(
                    f"{manifest['certificate']}: frame {record['source_index']} hash not found "
                    f"in {url}; extracted {len(candidates)} image candidates"
                )
            target = destination / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

    subset = dict(manifest)
    subset["sequence_complete"] = False
    subset["frames"] = sorted(records, key=lambda r: indices.index(r["source_index"]))
    subset["recovery_note"] = "issue #26 temporary runner; bytes verified against committed frame SHA-256"
    subset_path = destination / "source-manifest.json"
    subset_path.write_text(json.dumps(subset, indent=2) + "\n")
    return subset_path


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    scratch = ROOT / ".issue26-benchmark"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir()

    benchmark_manifest = json.loads(BENCHMARK.read_text())
    stones = []
    rows = []

    for cert in CERTS:
        print(f"=== {cert} ===", flush=True)
        full_manifest = ROOT / "docs" / "360" / "benchmark" / "per-stone" / cert / "source-manifest.json"
        source = scratch / cert / "source"
        subset_manifest = recover_subset(full_manifest, WIDE, source)
        processed = scratch / cert / "processed"
        preprocess(
            source,
            processed,
            order_manifest=subset_manifest,
            gain=1.0,
            diagnostic_indices=WIDE,
            accept_review=True,
        )

        stone_entry = {"certificate": cert, "windows": {}}
        for window, indices in (("core", CORE), ("wide", WIDE)):
            step_out = scratch / cert / f"steps-{window}"
            asscher_steps.run(processed, step_out, indices, wrap=True)
            result = activation_benchmark.measure_stone(processed, step_out, indices, wrap=True)
            result["certificate"] = cert
            destination = OUT / "per-stone" / cert / window
            activation_benchmark.write_stone_outputs(result, destination, processed)
            stone_entry["windows"][window] = {
                "activation": str((destination / "activation.json").relative_to(OUT)),
                "template_status": result["representations"]["semantic"]["qc"]["template_status"],
                "upstream_status": result["upstream_validity"]["status"],
            }
            for representation, rep in result["representations"].items():
                for region, modes in rep.get("regions", {}).items():
                    for support_mode, cell in modes.items():
                        for trace_type, summary, validity in (
                            ("raw", cell["raw_summary"], cell["raw_validity"]),
                            ("relative", cell["relative_summary"], cell["relative_validity"]),
                        ):
                            rows.append({
                                "certificate": cert,
                                "window": window,
                                "representation": representation,
                                "region": region,
                                "support_mode": support_mode,
                                "trace_type": trace_type,
                                "status": validity["status"],
                                "total_excursion": summary["total_excursion"],
                                "mad_scale": summary["mad_scale"],
                                "persistent_support_fraction": cell["persistent_support_fraction"],
                            })
        stones.append(stone_entry)

    summary = {
        "schema_version": "diamond360-activation-benchmark/1",
        "benchmark_manifest": str(BENCHMARK.relative_to(ROOT)),
        "core_indices": CORE,
        "wide_indices": WIDE,
        "stones": stones,
        "interpretation": "descriptive recorded-image activation benchmark; no quality score",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")

    import csv
    fields = ["certificate","window","representation","region","support_mode","trace_type","status","total_excursion","mad_scale","persistent_support_fraction"]
    with (OUT / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
