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

All 14 article originals (11 GIFs and 3 MP4s) were recovered in a Work session.
Images and complete videos decode successfully; exact byte counts and SHA-256
are recorded. Earlier GitHub runner 403 probes remain as retrieval history.
The three article MP4s have limited original resolution: 80 × 176, 98 frames,
4.9 seconds.

### Old corner/windmill forum thread

Public inline JPEG previews were recovered for all 10 forum examples. Full
attachment endpoints return login HTML, so previews are explicitly distinguished
from unverified full originals. Post #58's positive comment refers to the tilted
image at post #56. Post mappings use displayed numbers, excluding inserted adverts.

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

The **Glittery** d360 sequence is now archived: 256 unique original 758 × 597
JPEGs, imported from the saved verified source bundle. Every image decodes and
matches its recorded byte count, SHA-256 and contiguous frame index. Source
manifest and labelled derived previews are included in release bundle v3.
Visual inspection was sampled; timing and calibrated viewing angles are unknown.

**Crispest** is also archived: 256 unique original 648 × 511 JPEGs, recovered
from the saved exact-viewer artifact in [Actions run 37536103420](https://github.com/choonkiatlee/sparkles/actions/runs/37536103420).
A new live extraction stopped at batch 1 HTTP 403. The saved sequence was checked
for image decoding, dimensions, contiguous indices, byte counts, unique hashes
and frame 0/still agreement. Its original source manifest and recovery provenance
are retained in v3. Visual inspection covered the ordered 16-frame overview and
original frames 252, 0 and 4; it did not cover every frame.
Historical partial-recovery evidence is retained separately in the bundle.

## Persistent recovered bundle

[Download recovery bundle v3](https://github.com/choonkiatlee/sparkles/releases/download/pricescope-research-2026-10-06-v1/pricescope-media-recovery-2026-10-06-v3.zip):
14 article originals, 2 Kashi original videos, 10 public forum inline previews,
and both complete d360 sequences: Glittery and Crispest, 512 original frames total.
The ZIP includes source URLs, SHA-256, byte counts and post associations.
It is preserved as a [GitHub release asset](https://github.com/choonkiatlee/sparkles/releases/tag/pricescope-research-2026-10-06-v1)
for future agents and research workflows. Raw
media remain out of Git. All images and complete MP4s were decoded; archive
integrity and per-file hashes were verified. Release v3 is 36,567,890 bytes;
SHA-256: `379f411098e4d96df78d7c00fea5bb9fd18d5f37d890b873928c4003ba126da5`.

## Normalized external benchmark

[`benchmark-manifest.json`](benchmark-manifest.json) completes normalization for
issue #64 step 2 using schema `sparkles-external-benchmark/1`. It joins all 32
catalogued examples to their labels, relations and archived evidence:

- 16 original standalone GIF/MP4 samples, 10 forum inline previews and two
  complete D360 sequences (512 original frames);
- four locator-only examples with explicit media gaps;
- source performance progressions, paired views, the corner/windmill geometry
  sweep and reviewer-specific comparison relationships;
- per-label reviewer type, performance / geometry/style / personal-preference
  categories, explicit label strength and separate inferred classifications;
- three general expert principles kept outside per-stone labels.

Read `samples` for normalized records, `groups` and `relations` for source
comparisons, and `general_principles` for context. Each sample retains its complete
`source_catalog_record`; label text preserves catalog paraphrases rather than
claiming verbatim transcription. Missing reviewer/post provenance remains unknown
or ambiguous. Post #58's label retains the separate media post #56.

`media.assets` records ZIP-relative paths, exact source URLs, hashes and byte
counts. `media.sequence` references an ordered source manifest in the pinned v3
release, including its hash, frame index field, dimensions and total original
JPEG bytes. Frame paths are relative to that manifest's directory. Simulation
and real-stone domains stay explicit; previews are not full originals, and archived
motion has not yet been validated against Sparkles preprocessing requirements.
Source ordering carries no numerical quality score.

Validation preserved every catalog sample and label, checked all 26 standalone
asset hashes and all 512 ordered frame hashes against the published ZIP, and
verified release bytes/SHA-256. Steps 3–5 (blind runs, comparison and disposition)
remain pending; every sample's `analysis_status` is `not_run`. The normalized
manifest is versioned in Git alongside the catalog and archive manifest; release
v3 remains the unchanged raw-media bundle.

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


## Blind benchmark runner

Issue #64 steps 3–5 are executed by `diamond360.external_benchmark`. The runner
uses the normalized manifest above plus the pinned v3 release archive; it does
not change any Sparkles production threshold or descriptor definition.

Media are handled by explicit source class:

- complete vendor 360 sequences -> normal 256-frame `diamond360-source/1` and
  the frozen wrapped face-up core `248..255,0..8`;
- MP4/GIF -> decoded in source order through a benchmark-only adapter; clips
  up to 99 frames keep every frame, while longer clips use a fixed uniform
  full-clip sample capped at 99 frames. The original decoded indices are
  preserved in provenance and no face-up index is invented;
- JPEG/PNG preview -> one-frame static geometry only; no synthetic motion;
- missing/unsupported media -> `pipeline_source_mismatch`.

The predeclared falsification directions are deliberately narrow. The P3
progression tests grouped/persistent darkness and research tier readability;
the Kashi pair tests inner dark persistence and switching; Glittery vs Crispest
uses research tier readability because the expert criticism is P3/tier-related.
Activation, mobility, flash scale and coordination remain descriptive unless a
source label directly claims the corresponding percept.

Reproduce from an unpacked v3 archive:

```bash
python -m diamond360.external_benchmark \
  --archive-root /path/to/pricescope-media-recovery-2026-10-06-v3 \
  --output /tmp/pricescope-external-results
```

CI workflow `.github/workflows/pricescope-external-benchmark.yml` downloads the
pinned release asset, runs the adapter tests and blind benchmark, and uploads
the detailed per-sample evidence as an artifact. Compact comparison findings
are intended to be versioned here after the run has been inspected.


## Structured expert observations

Issue #82 normalizes the existing Karl_K / strmrdr evidence into a separate,
provenance-preserving corpus:

- `expert-observation.schema.json` — versioned record contract;
- `expert-observations.json` — normalized observations and validation-use partition;
- `expert-observations.md` — interpretation and anti-leakage rules.

The original #64 catalog/manifest remains the source/media record of truth. The
new corpus does not add subjective labels and does not map textual locality to
#72 facet IDs yet. In v1, `source_wording` is explicitly the existing catalog
paraphrase rather than a claimed verbatim transcription.
