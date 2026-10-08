# Supplier Motion Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Complete #100 by adding reusable, certificate-bound supplier motion retrieval for audited Diajewel, Workshop/Core360 and D360 formats plus direct public video bytes, without changing the public retrieval interface or legacy `diamond360` behavior.

**Architecture:** Keep network access in source-specific downloaders and ordering/validation in network-free processors. Diajewel and Workshop share the audited 4/4/8/16/32/64/128 progressive-batch processor; D360 reuses the same ordering primitives where its wire format agrees but keeps its D360-specific bootstrap checks. Loupe360 resolution returns the exact supplier viewer association before any supplier downloader runs.

**Tech Stack:** Python 3.10+, stdlib JSON/base64/hashlib/io, Pillow, existing `diamond_retrieval` protocols, unittest, GitHub Actions.

**Spec:** GitHub issue #100 (parent #97); builds on merged #98/#99.

## Global Constraints

- One public call remains `retrieve_diamond(url, config=None) -> DiamondResult`.
- No saving, cache, batch retrieval, publication or purchase verdict.
- Only exact listing/certificate-linked public sources; no guessed IDs or alternate/private APIs.
- Preserve original media bytes; no resizing/re-encoding.
- Preserve source index, batch/stored position, dimensions, SHA-256, supplier hint and provenance.
- Ordering checks stay fail-closed; invalid/incomplete/corrupt sources become structured partial failures.
- Processors perform no network reads.
- Existing `diamond360` behavior and tests must remain unchanged.

## Review Focus

- Unknown but syntactically valid viewer IDs must not be rejected merely because they are absent from a source-ID allowlist.
- Incomplete batch sets, duplicate/missing ordering positions and malformed scramble maps must fail before a `RotationEvidence` is emitted.
- A corrupt JPEG hidden inside an otherwise valid 256-frame sequence must fail the sequence.
- Two references resolving to the same supplier asset must download once per invocation while preserving provenance attempts.
- Supplier access blocks must leave matched listing/certificate/still evidence usable and make standard-policy completion partial.

---

### Task 1: Shared audited progressive-order processor

**Files:**
- Create: `diamond_retrieval/motion.py`
- Create: `tests/fixtures/diamond_retrieval/motion-audits.json`
- Create: `tests/test_diamond_retrieval_motion.py`

**Interfaces:**
- Produces `canonical_progressive_positions(bits=8)`, `validate_scramble(scramble)`, `ordered_positions(scramble)`, and `ProgressiveRotationProcessor.process(raw) -> tuple[RotationEvidence, ...]`.
- Raw progressive bundle metadata contains seven batch records with decoded scramble permutations and original JPEG bytes.

- [ ] Write archive-oracle tests first: Diajewel LG756580087 and Workshop LG756520111 ordering must reproduce committed manifest source-index → batch/stored-position samples; malformed permutations/incomplete batches/corrupt JPEG fail.
- [ ] Run focused tests and confirm RED because motion module does not exist.
- [ ] Implement shared ordering/JPEG validation with no source-ID conditions.
- [ ] Run focused tests and confirm GREEN.
- [ ] Commit.

### Task 2: Exact Diajewel and Workshop/Core360 downloaders

**Files:**
- Create: `diamond_retrieval/motion_sources.py`
- Modify: `tests/test_diamond_retrieval_motion.py`

**Interfaces:**
- Produces `DiajewelRotationDownloader` and `WorkshopRotationDownloader`, both implementing `EvidenceDownloader`.
- Each accepts an injected HTTP client and exact viewer reference, fetches source metadata/batches with bounded requests, and returns one raw progressive bundle for Task 1's processor.

- [ ] Add failing fake-HTTP tests for exact URL parsing, arbitrary safe item IDs, expected source URLs/version semantics, incomplete batches, and no writes.
- [ ] Confirm RED.
- [ ] Implement only exact audited host/path recipes; do not hardcode known item IDs.
- [ ] Confirm GREEN.
- [ ] Commit.

### Task 3: D360 generic downloader with legacy regression contract

**Files:**
- Modify: `diamond_retrieval/motion_sources.py`
- Modify: `tests/test_diamond_retrieval_motion.py`
- Do not modify: `diamond360/d360_source.py` unless a regression test proves a necessary compatibility-only extraction.

**Interfaces:**
- Produces `D360RotationDownloader` using exact `d360.tech` viewer IDs and `media.d360.us/imaged/<id>` public resources.
- Consumes Task 1 ordering primitives rather than duplicating them.

- [ ] Add failing tests proving both audited D360 maps reproduce legacy first-target/order contracts and a new valid ID is accepted from metadata without an ID allowlist.
- [ ] Add failure tests for bootstrap/still mismatch, invalid scramble, missing pack and corrupt JPEG.
- [ ] Confirm RED.
- [ ] Implement D360 download path while retaining byte-identical frame-zero/still validation.
- [ ] Run new tests plus `tests.test_d360_source`; confirm GREEN.
- [ ] Commit.

### Task 4: Loupe360 exact-certificate supplier resolution and direct video

**Files:**
- Modify: `diamond_retrieval/resolvers.py`
- Modify: `diamond_retrieval/protocols.py`, `diamond_retrieval/http.py` only if the public Loupe360 certificate route requires POST.
- Create or modify: `diamond_retrieval/video.py`
- Modify: `tests/test_diamond_retrieval_motion.py`

**Interfaces:**
- `Loupe360CertificateResolver` returns the exact supplier viewer URL from certificate-bound public media data when present, carrying supplier identity observations/provenance; it does not infer a supplier ID.
- `DirectVideoDownloader` + `DirectVideoProcessor` preserve original public video bytes and validate recognizable media/container signatures without decoding frames.

- [ ] Add failing fixture tests for certificate → Diajewel/Workshop/D360/direct-video references and missing/mismatched certificate data.
- [ ] Add failing tests for valid/invalid direct video bytes.
- [ ] Confirm RED, implement minimal public resolver/request support and direct video components, confirm GREEN.
- [ ] Commit.

### Task 5: Default composition and two-retailer single-call completion

**Files:**
- Modify: `diamond_retrieval/composition.py`
- Modify: `diamond_retrieval/__init__.py`
- Modify: `tests/test_diamond_retrieval_retailers.py`
- Modify: `docs/diamond-retrieval.md`
- Modify: `.github/workflows/diamond-retrieval-contract.yml`

**Interfaces:**
- Default factory registers supplier resolvers/downloaders/processors; orchestrator API remains unchanged.

- [ ] Add failing end-to-end fixtures where Diyona and Quality Diamonds each return listing metadata + matched PDF + ordered motion in one call; test one direct listing media path and one Loupe360-resolved path, invocation dedupe and certificate-only policy zero motion calls.
- [ ] Confirm RED.
- [ ] Register components and update fixtures/docs.
- [ ] Run retrieval framework + retailer + motion suites and legacy D360 tests; confirm GREEN.
- [ ] Commit.

### Task 6: Verification and issue checklist

- [ ] Run the focused GitHub Actions retrieval contract including legacy D360 regression.
- [ ] Run repository-wide unittest discovery.
- [ ] Perform bounded live smoke checks for one Diajewel/Workshop and one D360 exact viewer; record explicit upstream blocks without bypassing them.
- [ ] Review #97/#100 acceptance checklist and update PR body with exact passes/known access limits.
- [ ] Open the PR; leave unmerged.
