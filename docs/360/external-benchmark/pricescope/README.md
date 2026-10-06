# PriceScope external benchmark archive

This directory contains the source/provenance archive for the PriceScope
examples tracked by #64.

## Scope of this slice

Archive first, analysis later.

- preserve source URLs and source-provided interpretations;
- prefer exact original public media;
- record SHA-256, byte count and content type only when exact bytes are recovered;
- keep downloaded third-party media out of Git;
- do **not** run Sparkles descriptors or tune any metric in this slice.

`source-catalog.json` records the intended benchmark examples and their source
semantics. `archive-manifest.json` records what was actually recoverable.

## Current retrieval status — 2026-10-06

The PriceScope article and forum text are publicly accessible and the article's
original GIF/MP4 URLs are preserved in the catalog. However PriceScope returns
HTTP 403 to direct media and forum-page requests from GitHub-hosted archive
jobs.

Two independent Actions probes confirmed the block. The expanded probe found:

- 14 explicit article media URLs catalogued;
- 14/14 direct byte requests blocked with HTTP 403;
- 10 target forum-post examples catalogued;
- 0 original forum attachment URLs recoverable through the blocked runner
  request/current text rendering.

Accordingly the durable manifest deliberately contains **no invented hashes or
byte counts**. Forum post text/labels and article media locators are archived;
the media-byte archive remains incomplete.

Do not replace the missing originals with screenshots, thumbnails or
recompressed copies while calling them originals.

## Reproduce the probe

```bash
python tools/archive_pricescope_external.py \
  --catalog docs/360/external-benchmark/pricescope/source-catalog.json \
  --out /tmp/pricescope-archive
```

The workflow is manual-only because the source currently blocks GitHub runner
traffic. If PriceScope access changes, rerun it and update
`archive-manifest.json` only from successfully recovered exact bytes.

## Interpretation boundary

PriceScope descriptions are external expert/forum evidence, not objective ground
truth. The six corner/windmill cases are a controlled geometry/character sweep,
not a monotonic quality scale.
