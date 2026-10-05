# Issue 15 implementation plan and resume ledger

Goal/spec: https://github.com/choonkiatlee/sparkles/issues/15
Architecture: existing research extractor → vendor-neutral ordered source manifest → unchanged preprocessing → separate temporal measurement. Python/NumPy/Pillow/SciPy; no new runtime dependency.

## Ordered tasks
- [x] Recover all original frames using existing helper and exact-stone cached batches; match all prior recovery hashes.
- [ ] Run baseline preprocessing unchanged, inspect whole-sequence QC before choosing a continuous interval.
- [ ] Extend ingestion for versioned ordered paths/source indices/hashes, independent of filename indices. Test shuffled filenames, hashes, duplicate indices, missing/unlisted paths, completeness declarations and legacy compatibility.
- [ ] Add separate `diamond360.region_traces` command consuming sequence outputs and an explicit ordered contiguous interval. Median encoded brightness; fixed common-support regions; per-frame relative-dark pixel occupancy plus region-median dark/bright states. Gap/exclusion breaks runs; no loop closure unless explicitly traversed; source-step units only. Test alternating versus block darkness, missing frames, wraparound, sparse refusal, unsupported regions and duplicates.
- [ ] Save compact overview, acceptance summary, registration/support QC, traces/states, manifests and #14 comparison. Keep raw/full derived stacks out of Git; document reproducible retrieval.
- [ ] Full suite, visual QC, link/hash validation; checkpoint commits and concise PR.

## Decisions / progress
2026-10-05: user requested execution of fully specified issue; implement inline in isolated clone/feature branch. Issue is the design authority. Baseline master 8509365; 28 tests pass. All 256 recovered 704×704 JPEG hashes/order match earlier validated recovery (9,088,577 bytes), no repeated hashes. Source VL-131355, quality 4, batches 1–7/version=1; inverse permutation/interleave, unknown angles/timing. No segmentation threshold changes.

Next: inspect unchanged full run and near-face-up frames around source wrap.
