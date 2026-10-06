# Crispness evidence

The #50 runner automatically generates source-first evidence panels for every benchmark stone. The complete generated set is stored as the `crispness-benchmark` artifact on [Actions run 37511719011](https://github.com/choonkiatlee/sparkles/actions/runs/37511719011).

We intentionally do **not** commit the full image set. This repository recently moved large/repetitive generated assets out of Git history; `manifest.json` therefore pins a four-panel representative subset by source index, selection role, byte size and SHA-256.

Each panel contains:

1. the unaltered camera-space source frame first;
2. a registered diagnostic second;
3. the expected #19-compatible boundary in white;
4. supported local edge peaks in black.

The four pinned examples cover the Workshop continuity failure, Diajewel pipeline-sensitivity case, a strong boundary in an explicit #22 crispness stone, and the LG836619414 human counterexample where the review remains geometrically crisp even though one outer boundary is incomplete.

To regenerate the complete evidence set, use the command in the parent [README](../README.md) with the versioned #18 source bundles.
