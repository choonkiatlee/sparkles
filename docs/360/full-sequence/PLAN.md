# Issue 15 implementation plan and resume ledger

Goal/spec: https://github.com/choonkiatlee/sparkles/issues/15
Architecture: existing research extractor → vendor-neutral ordered source manifest → unchanged preprocessing → separate temporal measurement. Python/NumPy/Pillow/SciPy; no new runtime dependency.

## Ordered tasks
- [x] Recover all original frames using existing helper and exact-stone cached batches; match all prior recovery hashes.
- [x] Run baseline preprocessing unchanged, inspect whole-sequence QC before choosing a continuous interval.
- [x] Extend ingestion for versioned ordered paths/source indices/hashes, independent of filename indices. Test shuffled filenames, hashes, duplicate indices, missing/unlisted paths, completeness declarations and legacy compatibility.
- [x] Add separate `diamond360.region_traces` command consuming sequence outputs and an explicit ordered contiguous interval. Median encoded brightness; fixed common-support regions; per-frame relative-dark pixel occupancy plus region-median dark/bright states. Gap/exclusion breaks runs; no loop closure unless explicitly traversed; source-step units only. Test alternating versus block darkness, missing frames, wraparound, sparse refusal, unsupported regions and duplicates.
- [x] Save compact overview, acceptance summary, registration/support QC, traces/states, manifests and #14 comparison. Keep raw/full derived stacks out of Git; document reproducible retrieval.
- [x] Full suite, visual QC, link/hash validation; checkpoint commits and concise PR.

## Decisions / progress
2026-10-05: user requested execution of fully specified issue; implement inline in isolated clone/feature branch. Issue is the design authority. Baseline master 8509365; 28 tests pass. All 256 recovered 704×704 JPEG hashes/order match earlier validated recovery (9,088,577 bytes), no repeated hashes. Source VL-131355, quality 4, batches 1–7/version=1; inverse permutation/interleave, unknown angles/timing. No segmentation threshold changes.

Next: inspect unchanged full run and near-face-up frames around source wrap.

2026-10-05 completion checkpoint: all 256 hashes/order and camera copies verified. Baseline/current 256 segmentation/registration decisions and derived photometry/region bytes identical. Primary 248–255→0–8; wider 240–255→0–16. Compact QC/walkthrough and controlled sparse comparison pushed in PR #16 (8ca7f27, 4794341). 37 tests pass; JSON and local report links validated; representative segmentation and all primary registered frames inspected. Independent final review complete; two manifest findings fixed. Raw frames/derived stack intentionally reproducible outside Git.

Ruling: supplement region-median states with per-pixel switching/run distributions — all coarse medians remain bright and would otherwise hide changing local contrast. Cost if misunderstood: image-pixel switching could be mistaken for facet flashes; explicit limitations and spatial maps are included.

Next action: address important review findings, run full suite, verify remote tree/blob hashes, mark PR ready; leave issue open until merge. Follow-up: validate another supported source and benchmark/downsample whole-sequence QC; do not generalise quality scores from this recording.

Final review: independent reviewer reproduced core/wide JSON exactly; README numbers agree. Fixed authoritative frame order overridden by legacy fields and unsupported source-schema integrity bypass. Both reproduced RED→GREEN; missing-path error also made explicit. Full suite: 40 tests pass. No deferred minor findings. Final tree/hash verification and ready transition remain delivery steps.
