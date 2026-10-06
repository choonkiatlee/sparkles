# PriceScope external benchmark archive

This directory contains source/provenance material for the PriceScope examples
tracked by #64.

## Scope

Archive first, analysis later.

- preserve source URLs and source-provided interpretations;
- distinguish expert review from community/purchaser preference;
- prefer exact original public media;
- record SHA-256 and byte counts only after exact bytes are recovered;
- keep raw third-party media out of Git;
- do **not** tune Sparkles metrics to these examples.

`source-catalog.json` records benchmark semantics and reviewer provenance.
`archive-manifest.json` records what is actually recoverable.

## Current archive status — 2026-10-06

### PriceScope-hosted P3/article media

The article/media locators remain known, but PriceScope returns HTTP 403 to
GitHub-hosted archival fetches. The durable manifest therefore records the
URLs and blocked state without inventing hashes.

### Old corner/windmill forum thread

Post text and labels are preserved. The migrated forum rendering does not expose
the old inline-media URLs to the archive tooling, and GitHub runner page fetches
are blocked by PriceScope.

### 2023–24 Asscher evaluation thread

This source is materially more useful for Sparkles:

- Karl_K / strmrdr supplies direct technical labels on individual real stones;
- two primary candidates still have live `d360.tech` viewers;
- exact Whiteflash/GIA identities survive for several later comparison stones;
- two Kashi sources are direct original MP4s and **are downloadable**.

Verified raw-video records:

| sample | bytes | SHA-256 |
|---|---:|---|
| `asscher-eval-messy-arrows` | 5,886,312 | `ec4a17f8c89ce710dd5a9b8e4e8d08b8e398d99692e583e4f63f970bfd4f487a` |
| `asscher-eval-nice-dance` | 4,840,046 | `f69e6e8e429665246becc6121621fe4d92955383cb7e2163cd6b91aa010a5b27` |

Those bytes were retrieved in Actions run `37533954460`. They are not committed
to Git; the manifest preserves exact source URLs, sizes and hashes.

The d360 cases are **viewer-live but not yet frame-archived**. They need a small
d360-specific extraction adapter rather than weakening the existing Sparkles
source contracts.

## Reproduce the byte probe

```bash
python tools/archive_pricescope_external.py \
  --catalog docs/360/external-benchmark/pricescope/source-catalog.json \
  --out /tmp/pricescope-archive
```

The workflow is manual-only. Re-run it when testing source availability or after
adding a direct-media candidate.

## Interpretation boundary

PriceScope commentary is external evidence, not objective ground truth.
Reviewer type matters:

- Karl_K / strmrdr: expert technical label;
- experienced forum member: informed perceptual/preference label;
- purchaser/thread author: useful observation or preference, not expert ground truth.

Keep these layers separate during downstream calibration.
