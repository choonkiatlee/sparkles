# #92 — replay real original 360 brightness against frozen #89 semantic ruler

This is a small **real-source** follow-up to [#166](https://github.com/choonkiatlee/sparkles/pull/166), not another geometry fitter or subjective Asscher ranking.

## Independently fixed inputs

1. Download exactly the archived [#89 run 37830584391](https://github.com/choonkiatlee/sparkles/actions/runs/37830584391), artifact \`asscher-geometry-stability-outer-v2\`. The original **stone-level primary-wireframe.json**, **transfer.json** and their byte SHA-256 are consumed without re-estimation.
2. Download two SHA-256-pinned, real 256-view source bundles from \`docs/360/benchmark/source-bundles.json\`: **LG756520111** (face role likely crown) and **LG756580087** (face role unresolved; negative control against claiming crown identity). Every source archive's size and SHA-256 is verified before extraction.
3. Re-run only the previously frozen **image-preparation and #73/#80 sequence-gauge registration** to recover per-frame measurement brightness and valid pixel masks. No \`_fit_records\`, \`fit_from_sector_evidence\`, \`_primary_fit\` or per-frame \`transfer_fixed_ruler_frame\` is invoked. The archived #89 per-frame support and geometry remain authoritative. Verify each source frame's gauge quarter-turn agrees.
4. Use **predeclared** original source indices \`[250,252,255,0,2,5,8,11,13,16,19]\`, crossing the 255→0 cyclic wrap. One per-source \`semantic_id\` table uses the exact #80 gauge mapping from merged #166.
5. Emit plain average **already-canonical measurement brightness**, not physical facet light return. Normalized value remains \`null\` (source-independent photometric normalization not yet supplied). Unsupported source/semantic combinations remain \`null\`; no invented zeros or interpolated support. All polygon attribution is non-exclusive.

## Results, provenance and caution

Each of the two PNGs shows 6 example semantic supports (N orientation): C1, C2, C3, P1, P2, P3, for eleven actual crown-window observations. A JSON per stone includes all **55** stable semantic IDs, support status and confidence for every frame, pixel count and brightness, source phase, archived face role, archived geometry JSON SHA-256 and unrevised scaffold flag.

We must assess the resulting traces **without** assigning polished facet ownership to optical image regions. In particular:

- LG756580087 has \`face_role=unresolved\` in the frozen #89 result. The fixed N-labelled support is not independently verified as a physical crown facet in that recording.
- Inner C3/table physical facet identity is still unresolved by #124; observational pixel brightness does not fix that.
- "Phase" is an approximate 256-step vendor viewer phase; physical camera rotation calibration and actual diamond photometry are not established.
- These traces do not report scintillation, fire, virtual facets, contrast quality, P3 leakage, hall of mirrors or any composite score.
- A real-source replay showing brightness changes with stable semantic IDs is a **handoff/API smoke success**, not sufficient alone for #92's final KEEP/REVISE/REJECT decision.
- The fourth retained test stone (LG818659722) has no verified primary scaffold in frozen #89; do **not** fabricate an apparently valid brightness trace.

## Repeatability

The dedicated workflow \`asscher-real-fixed-ruler-optical-replay.yml\` downloads the original artifacts and the two pinned source archives; checks SHA and source-index/gauge consistency; replays no other stones; uploads only two JSON reports and two PNG traces (not thousands of new canonical frame arrays).

The original #89 source window, frozen geometry, #91 post-freeze negative angle result and #124/123 internal boundary uncertainties remain unchanged. This is the next auditable input for the eventual #92 disposition and #79 optical research.


## #92 small generalization gate: exposure/reference and fixed-support sensitivity

This replay also **predeclares a small sensitivity check** for the two
already-selected original diamonds and 11 source frames. The baseline output
\`real-fixed-ruler-brightness.json\` is unchanged; the separate output
\`exposure-support-sensitivity.json\` and two-panel PNG are diagnostics.

1. **A descriptive within-frame exposure/reference proxy**, not vendor
   photometric calibration: compute p10, median and p90 over *all valid
   canonical stone pixels*, using the existing fixed #80 gauge/mask. For
   each semantic support mean \`I\`, record \`(I - p10) / (p90 - p10)\`.
   If the denominator is flat or the region is unsupported, return
   \`null\`. Values outside [0,1] are retained; no clipping or output tuning.
   Per-stone p10/p50/p90 variation is reported to reveal global brightness
   shifts. Changes after referencing **cannot** be uniquely attributed
   to exposure: global optical behaviour, illumination, clipping and
   vendor processing can also alter the stone-pixel distribution.
2. **A geometrically fixed, alternative sampling zone**: erode the *same*
   original frozen #89 semantic support polygon **2 image pixels inward**,
   before intersecting with the original valid stone mask. Compare this
   interior mean to the full-support mean, record surviving pixel count
   and frame-by-frame absolute differences. No new boundary is searched,
   rotated, fitted, or matched to a visual reflection. If erosion empties
   a region, the eroded brightness is \`null\`.
3. Across the 11 frames, record raw and within-frame-reference amplitude,
   mean/max absolute erosion effect, and **descriptive** Spearman rank
   agreement where at least four nonconstant paired observations exist.
   These diagnostics are not pass/fail thresholds or stone-quality scores.
4. Plot four predeclared supports (\`C1_N\`, \`C3_N\`, \`P1_N\`, \`P2_N\`)
   both raw and frame-relative, with faint dotted 2px-inset trajectories.
   Keep actual missing observations as gaps rather than connecting them.

A controlled synthetic test verifies **affine gain and offset invariance**
of the frame-relative index when no pixel clipping occurs. This is an
algebraic sanity check, **not proof of real-vendor comparability**.
Source scaling, normalization/exposure and uncertainty of physical polished
C3/table correspondence remain open issues. The orientation-unresolved
LG756580087 must not be treated as a verified crown.

This work deliberately reuses the **same existing real-data replay** and
does not introduce another full-rotation benchmark, synthetic renderer,
facet fitting method, or source-specific ROI correction.

### Scientific decision enabled

If core-vs-full support means disagree markedly, it indicates **polygon
boundary sensitivity** rather than a verified physical facet difference.
If the within-frame contrast index behaves differently from the raw trace,
global/reference brightness variation contributes to the original trace.
Neither observation alone proves which optical ray/facet caused a change.
The #92 handoff should therefore still be assessed **REVISE** for exclusive
physical-facet claims while nonexclusive time-varying image support may
remain useful for downstream optical research.
