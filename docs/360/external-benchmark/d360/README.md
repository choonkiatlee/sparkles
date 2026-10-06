# d360.tech external-source adapter

Issue #64 includes two Karl_K / strmrdr-labelled Asscher examples whose d360
viewers remain live:

- `79-BB-5159600` — the “Glittery” case
- `79-BT-5165227` — the “Crispest” case

The extractor in `diamond360/d360_source.py` downloads the vendor's original
progressive JPEG packs from `media.d360.us`, reconstructs the viewer's
authoritative 256-frame order, and writes a normal `diamond360-source/1`
directory.

## Usage

```bash
python -m diamond360.d360_source \
  'https://d360.tech/view.html?d=79-BB-5159600' \
  /tmp/79-BB-5159600
```

The output contains:

```text
source-manifest.json
frames/
  d360-79-BB-5159600-frame-000.jpg
  ...
  d360-79-BB-5159600-frame-255.jpg
```

Raw third-party frames are intentionally not committed to Git.

## Ordering contract

d360 serves seven progressive packs containing
`4 + 4 + 8 + 16 + 32 + 64 + 128 = 256` JPEGs. The viewer places these into
the final sequence using a per-item encrypted `scramble` map layered over its
canonical progressive odd-position interleave.

For this deliberately small first adapter:

- the scramble maps for the two issue-64 viewers were independently decoded
  from their current `0.json` bootstrap;
- each map is bundled with the extractor;
- each bootstrap is SHA-256 pinned;
- unknown d360 item IDs fail closed rather than assuming an order;
- all seven scramble levels must be exact permutations;
- the resulting mapping must cover source indices 0..255 exactly once;
- reconstructed source frame 0 must match the vendor's `still.jpg`
  byte-for-byte.

That final check is independent of the permutation implementation and passed for
both audited viewers.

## Verified source contracts

| d360 item | frames | dimensions | bootstrap SHA-256 | frame 0 / still SHA-256 |
|---|---:|---:|---|---|
| `79-BB-5159600` | 256 | 758×597 | `19adfa45f5e47ec670bc0cb25c2b9057315585bde9518b0062db5f2f472eab9f` | `0168b10051d7cdf52011c52ffbec20cfe8b2f26b2f3d91a9ac9480cb19c87a18` |
| `79-BT-5165227` | 256 | 648×511 | `513c2a7308907b76b79201de61a992c54bda5f7522d29adad80132789318c8f0` | `f8fa831797275f7cb647f5f7baaf9ef2c30bc631ab38d0634fe75c76c8d01574` |

The integration workflow additionally passes each generated source directory
through `diamond360.ingestion.ingest` and requires 256/256 valid frames,
non-sparse ordering, and the explicit source manifest contract.

## Scope boundary

This PR intentionally does **not** implement a generic d360 scramble decryptor.
That would add code/dependencies unrelated to the two external benchmark stones.
A future d360 source can be added only after its ordering map is audited (or a
generic decryptor is separately reviewed).
