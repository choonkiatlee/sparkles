# PriceScope external benchmark archive

This directory contains provenance for the PriceScope examples tracked by #64.

## Scope of this slice

Archive first, analysis later.

- preserve source URLs and source-provided interpretations;
- fetch original public media without altering bytes;
- record SHA-256, byte count and content type;
- discover the six primary corner/windmill images from their original forum posts;
- keep downloaded third-party media out of Git and in a short-lived CI artifact;
- do **not** run Sparkles descriptors or tune any metric in this slice.

The committed `source-catalog.json` contains the benchmark semantics. The
archive job emits `archive-manifest.json` with retrieval results and hashes.

Source labels are provenance, not objective ground truth. In particular, the
corner/windmill sequence is a controlled geometry/character sweep rather than
a monotonic quality scale.

## Reproduce

```bash
python tools/archive_pricescope_external.py \
  --catalog docs/360/external-benchmark/pricescope/source-catalog.json \
  --out /tmp/pricescope-archive
```

Raw media are intentionally not committed. The CI artifact is for verification
and downstream experimentation; the durable repository record is the compact
URL/hash manifest.
