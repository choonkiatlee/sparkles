# Asscher sequence gauge

Issue: #80  
Builds on: #73  
Consumed by: #75, #76

This layer turns the per-frame image-plane pose from #73 into one stable
sequence coordinate system. It does **not** estimate a calibrated physical
camera angle.

## Two independent coordinates

The contract deliberately separates:

1. **Observed sequence phase** — where a frame lies in a declared uniformly
   sampled cyclic viewer sequence.
2. **Semantic orientation gauge** — one deterministic N/E/S/W convention used
   consistently across the sequence.

A source may have a semantic gauge even when phase is unavailable.

## Phase provenance

Phase is emitted only when the source manifest explicitly declares:

```json
{
  "sequence_sampling": {
    "kind": "uniform_cyclic_viewer_phase",
    "period_frames": 256,
    "nominal_cycle_deg": 360.0,
    "physical_angle_calibrated": false
  }
}
```

For a 256-frame source, the nominal viewer-phase step is 1.40625 degrees.

These degrees are **viewer-sequence phase**, not laboratory camera angle. If
uniform cyclic sampling is not declared, phase is unavailable rather than
inferred from frame count.

Phase zero uses the #73 resolved likely-crown lobe when available. If crown
identity is unresolved but a best face-on geometry lobe exists, it may be used
as a review-status reference with that provenance serialized.

## Stable 90-degree gauge

#73 intentionally preserves Asscher orientation modulo 90 degrees. #80 resolves
the per-frame equivalent branches by minimizing circular orientation
discontinuity across the ordered sequence, including the end/start edge for a
complete cycle.

The reference frame fixes one deterministic branch, but the result remains
explicitly equivalent under a global 0/90/180/270-degree quarter turn. N/E/S/W
therefore means a stable semantic convention, not physical compass direction.

The existing #73 canonical transform is not rewritten. #80 composes an
additional quarter-turn transform and serializes:

- `canonical_to_sequence_gauge_xy`
- `sequence_gauge_to_canonical_xy`
- `camera_to_sequence_gauge_xy`
- `sequence_gauge_to_camera_xy`

This lets downstream code consume the stable gauge without parsing semantic
names or changing the meaning of #73 outputs.

## Failure and review states

- Missing/untrusted sampling metadata: phase `unavailable`.
- Rejected but geometrically available pose: gauge `review`.
- Failed pose/no canonical transform: phase may remain available from source
  provenance while the semantic gauge transform is `unavailable`.
- No physical rotation direction is claimed unless independent provenance is
  added later.

## Downstream rule

#75/#76 should use the sequence-gauge transform for stable semantic identities
such as `P3_N`. They should not independently choose N/E/S/W per frame.
