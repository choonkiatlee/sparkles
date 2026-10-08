# #76 follow-up: compare frozen #75 and #96 geometry methods

This is a **new, target-blind method-revision experiment**, not a retroactive edit
to the original #88/#89/#90 evidence.

## Predeclared identities

| | Original (#75) | Outer-octagon-first (#96) |
|---|---|---|
| Method name | `initial_v1` | `outer_octagon_v2` |
| Estimator revision | `8bbbbf64754f2bcbb48ab435b731bdf95f7722bc` | `6334cc9d0c7e2c9a26854bfaeec7a8ebbb6fc668` |
| Frozen specification SHA256 | `5805a26f468a8b25664556747576075901e36d46401a41182c9d1469f1f68065` | `aaf8a885efe039b203330f9592dcccdb41ba11f3a731eb31143fa6de06b4e42e` |

- Historical contract **unchanged**: `validation-contract.json`.
- New version **separately frozen**: `validation-contract-outer-v2.json`.
- Same four hash-pinned benchmark sources, semantic topology, #80 gauge and
  #88 displacement/provenance/identity metrics.
- Same #89 leave-one-out and fixed-ruler transfer questions.
- Same #90 two representative stones, seven image perturbations and poor-view bins.
- No new numeric displacement pass/fail threshold and no per-stone retuning.

## Adaptation necessary to avoid an invalid comparison

The old #89 stability code manually reconstructed #75's `_median_outer_vertices`
and chose at most seven pose-ranked frames. Merely executing that code in a #96
checkout would **not** validate #96.

For `outer_octagon_v2` specifically, the stability and stress runners now:
1. Collect the entire #73-compatible crown-lobe candidate pool.
2. Apply #96's unchanged `outer_octagon.select_records` quality/medoid gates.
3. Fit #96's median fitted-octagon consensus with its confidence.
4. Run the unchanged inner-boundary inference.
5. Leave-one-out only the selected primary frames, without selecting replacement
   ones or changing thresholds. Every subset runs the #96 consensus again.

The original historical runner/output stays unchanged. Because #96 can choose a
**different number and set of primary frames**, leave-one-out counts and transfer
intervals may differ; report those differences rather than silently aligning
subsets or treating unavailable results as zero displacement.

## Historical comparators

- #89 original run: https://github.com/choonkiatlee/sparkles/actions/runs/37683160270
- #90 original run: https://github.com/choonkiatlee/sparkles/actions/runs/37687610094

The workflows retrieve the original frozen artifacts by explicit GitHub run ID,
read both JSON summaries, check the source-manifest fingerprint and frozen
method revision, and write `method-comparison.json`. New outputs and
side-by-side comparison are uploaded together.

Review **both** the raw candidate wireframes and the comparison summary. Do
not infer that lower displacement alone establishes greater physical accuracy.
If either source pipeline or semantic gauge becomes unavailable, report it.
The DiaGem/Sergey targets are out of scope for these experiments and must not
be consumed or used to tune an estimator.

## Research handoff

These reruns are additional evidence for #92's KEEP / REVISE / REJECT decision.
The previous #89/#90 failures remain part of the record. #91's independent
profile-photo comparison proceeds independently, without being recast as a
3D calibration of the face-up 360 image-plane wireframe.
