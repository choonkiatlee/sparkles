# LG756580087 · complete 360 sequence

[Visual walkthrough](index.html) · [issue #15](https://github.com/choonkiatlee/sparkles/issues/15) · [PR #16](https://github.com/choonkiatlee/sparkles/pull/16)

The full sequence adds **observed consecutive-frame switching and dark-run lengths**, which the 12-frame sparse sample cannot measure. It does not turn the vendor recording into a calibrated light-return or sparkle test.

## Extraction and unchanged baseline

Reused the research skill's `scripts/extract_diajewel360.py`, with the certificate-bound [Diajewel viewer](https://vision.diajewel360.com/Vision360.html?d=VL-131355) and its exact-stone saved batches. Quality 4, version 1: seven batches contain 4/4/8/16/32/64/128 frames. Inverse permutation followed by odd-position interleaving produces 256 ordered original 704×704 JPEGs, totalling 9,088,577 bytes. All 256 SHA-256/order pairs match the prior verified recovery; all 16 originals in #14 match this sequence. No missing/repeated indices or byte/pixel duplicates. Batch URLs, hashes and stored positions remain in [source-manifest.json](source-manifest.json).

This is a vendor display loop showing face-up, tilted and profile views. Continuity at 255→0 is visually consistent. Physical rotation axis, calibrated angles, capture cadence and constant angular sampling are unknown. Source index 128 is not asserted to mean 180°. Original bytes are untouched; raw stacks are excluded from Git and reproducible from the manifest's versioned public batch URLs.

Before code changes, master `8509365` processed the entire sequence: 256 valid images, 256 accepted outlines. No threshold was loosened. The subsequent versioned-contract run reproduces all 256 segmentation/registration decisions and photometry/region NPZ bytes exactly. All output camera originals match source hashes. Segmentation QC was inspected at 21 representative indices across the loop, including profiles; every primary-interval registered view was inspected. Acceptance is **outline acceptance, not face-up acceptance**. Candidate silhouettes generally follow the stone, although shadows and pale edges remain segmentation uncertainty. The full raw QC sheets remain generated working outputs, not committed giant contact sheets.

Full preprocessing produces large per-frame derived stacks and contact sheets; it completed without an observed processing failure. This run is a functional validation, not a measured runtime/peak-memory benchmark. Use the compact build script for publication; streaming/downsampled preprocessing QC is a useful future optimisation.

## Continuous intervals and support

Primary: **248–255 → 0–8**, 17 consecutive frames. The table and concentric step layout remain visible around the closest face-up views; mild pose/azimuth changes remain. Selection is a visually chosen near-face-up window, not a calibrated angular gate.

Sensitivity: **240–255 → 0–16**, 33 consecutive frames, with more tilt at each end. It matches the endpoints of #14's sparse diagnostics. Profile frames elsewhere are excluded from these optical-scene traces.

Measurements use identical image-aligned regions and the intersection of valid support across the interval; no per-frame intensity matching or facet tracking. The centre/inner/middle retain 100% of the reference region in the primary window; outer retains **82.4%**. The wider window retains 100%/100%/99.7%/**57.9%** respectively. Outer results describe that surviving subset and are especially sensitive to pose and support. Reference-region fractions use the first selected frame's silhouette-clipped regions, not anatomical facet areas.

## What the primary interval measures

Brightness is encoded-sRGB Rec.709 weighted brightness, 0–1. Amplitude is p90 minus p10 of each region's median. A pixel is relatively dark when below 0.65 × that frame's global median on common support. The region-median state uses the same threshold. These definitions are exploratory measurements, not cut-quality categories.

| Region | Median amplitude | Mean dark-pixel occupancy | Pixels with ≥1 switch | Pixel transitions p90 | Longest dark run p90 / max |
|---|---:|---:|---:|---:|---:|
| Centre | 0.077 | 4.8% | 36.4% | 3 | 2 / 9 frames |
| Inner | 0.035 | 7.8% | 43.2% | 3 | 4 / 12 frames |
| Middle | 0.034 | 11.2% | 56.0% | 4 | 4 / 11 frames |
| Outer | 0.008 | 11.9% | 52.1% | 4 | 5 / 15 frames |

All four **regional medians** remain above the dark threshold: zero region-wide dark transitions, zero median-dark occupancy, 17-frame observed bright runs. This does not mean all facets stay bright. Pixel-level states uncover contrast activity hidden by regional medians. Runs use source-frame counts only; gaps and excluded duplicates break runs, endpoints censor them, and the end of the selected interval is not joined back to its beginning.

The centre's median varies while its local pixels alternate: the recording does not show a wholly inactive/dark centre during this interval. Some fixed pixels remain dark for longer spans, especially nearer the outer region; these can reflect a moving step image, pose, obstruction or lighting. They are not evidence of physical leakage or dead facets.

The rings do not brighten/darken as one synchronous system: the centre dips near index 6, inner dark occupancy rises around the wrap, middle darkness increases after the wrap, and outer darkness peaks nearer 255. This is consistent with different coarse areas changing at different points, but does not establish physical tier correspondence or hall-of-mirrors quality. The trace granularity is too coarse to infer facet activation cadence directly.

## Sparse versus continuous, on identical support

We resampled the same 33-frame processed interval at #14's exact 12 indices: 240,244,248,250,252,254,0,2,4,8,12,16. Both comparisons use the **same full-interval support and per-frame thresholds** so sampling is isolated from support changes. [comparison.json](comparison.json) retains numeric results. The separate occupancy preview shows #14's changing-support convention alongside the full/common-support map; those two images intentionally include a methodological difference.

| Region | Sparse dark-pixel occupancy | Full 33-frame occupancy | Change |
|---|---:|---:|---:|
| Centre | 5.04% | 5.53% | +0.48 percentage points |
| Inner | 7.30% | 7.29% | −0.01 pp |
| Middle | 9.48% | 10.23% | +0.75 pp |
| Outer | 14.06% | 12.16% | −1.90 pp |

The sparse sample captured broad regional brightness/relative-dark occupancy reasonably well in this recording. The outer estimate shifts most, though by less than 2 percentage points on fixed support. No universal materiality threshold is implied.

It missed intervening states and cannot establish transitions or consecutive-source-frame run lengths: adjacent sparse samples are 2–4 source steps apart. In the full 33-frame window the centre/inner/middle/outer pixel-transition p90 is 4/4/7/7, and longest-dark-run p90 is 4.7/4/5/6 source frames. Such results distinguish long blocks from repeated switching at fixed image pixels; synthetic tests explicitly verify equal occupancy with different run patterns. They do not establish flash counts or optical quality.

## Confident conclusions / inference limits

- **Established:** full ordered provenance, no detected omissions/duplicates, unchanged preprocessing behavior, consecutive region/pixel traces, support loss, observed switching and source-frame run statistics.
- **Reasonable scene-level inference:** the centre repeatedly changes; region medians alone conceal contrast mobility; the sparse sample understates temporal detail despite similar average occupancy.
- **Unanswered:** calibrated speed/angles, physical facet tracking, absolute light return, ASET leakage, absolute fire/body colour, fluorescence, sparkle rate and purchase recommendation.

## Reproduce

With Python 3.10+, NumPy, Pillow, SciPy and the installed research extractor dependencies (`curl`, `cryptography`):

```bash
python <research-skill-root>/scripts/extract_diajewel360.py \
  --viewer-url 'https://vision.diajewel360.com/Vision360.html?d=VL-131355' \
  --certificate IGI-LG756580087 --output /tmp/lg756580087-source
# Optional --reuse-source-dir <exact-stone-cache>; never another stone's cache.
# Copy the committed contract after checking recovered index/hash pairs agree:
python - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/lg756580087-source/manifest.json')
a=json.loads(p.read_text()); b=json.loads(Path('docs/360/full-sequence/IGI-LG756580087/source-manifest.json').read_text())
assert [(r['index'],r['sha256']) for r in a['frames']] == [(r['index'],r['sha256']) for r in b['frames']]
p.write_text(json.dumps(b,indent=2)+'\n')
PY
python -m diamond360.cli /tmp/lg756580087-source \
  --order-manifest /tmp/lg756580087-source/manifest.json --output /tmp/lg756580087-processed
PYTHONPATH=. python docs/360/full-sequence/build_example.py \
  /tmp/lg756580087-processed /tmp/lg756580087-compact-qc
python -m unittest discover -q
```

Use fresh output directories. The preprocessor consumes decoded paths/indices/hashes; it knows nothing about Diajewel. The exact extractor is maintained in the research skill, not copied here. If public retrieval changes or blocks, stop that route; do not guess IDs, change hosts or silently drop frames. For later runs with a different source revision, compare the hashes and record a new provenance snapshot rather than relabelling it this recovery.
