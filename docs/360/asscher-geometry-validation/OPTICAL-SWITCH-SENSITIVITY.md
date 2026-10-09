# #123: controlled confound sensitivity of adjacent RGB bright/dark switching

## Why

Optical motion and appearance research (#178, #182, #186, #187) is now
merged and verified on four SHA-256-pinned original 360 rotations. The
dense switching atlas (#186) measures actual **registered image-plane**
dark/bright changes across 74 consecutive source frame pairs. It cannot
distinguish lighting, alignment, virtual facets, surface structures or
the movement of the diamond itself. The #187 motion atlas specifically
found large shared drift and many ambiguous or search-limit-clipped
local tile shifts, especially on LG836619414.

Before associating apparent optical switching with expert judgements,
ask a more elementary negative-control question:

> **How much do the same already-observed switching measurements change
> under a small *known artificial* change to image registration or
> illumination, with no different diamond or new facet geometry?**

## Predeclared frozen sensitivity protocol

Replay the *unchanged* #73/#80 pose pipeline and the exact #186
shortest-circular source-frame window on each of the four original
camera-RGB SHA-256-pinned 256-frame sequences. The frozen #96 outer
anchor indices, 74 original consecutive pairs, and all 4x4 gauge bins
are identical. Verify each unperturbed pair's original observed
normalized difference and dark/bright occupancy-switch fractions
numerically against immutable workflow 37856375493 (tolerance 1e-10).

For each observed original pair, change **only image B** under a fixed,
target-blind scenario set, without refitting any geometry:

- **Global exposure control:** multiply B by 1.20. The frame-median
  normalization should leave relative brightness switching unchanged;
  negative control for any supposed additional optical dynamics.
- **Registration confounds:** translate B by +1/-1 gauge pixel
  horizontally and vertically. Translate its own valid RGB footprint
  and silhouette mask consistently; outside pixels remain invalid
  (no wraparound). No new physical geometry estimation occurs.
- **Spatial illumination confounds:** multiply B by a smooth linear
  factor from 0.94 to 1.06 along horizontal or vertical gauge
  image axes. This is a *known synthetic spatial lighting change*
  (12 percentage points across frame), not a physically calibrated
  light field.

Re-run **exactly the pre-existing #186 region_appearance()** function
for each perturbation. Report, independently for all seven scenarios:

- Delta from unperturbed pair in gain-normalized median absolute
  change, total *relative dark* switch fraction, and total
  *relative bright* switch fraction.
- Changed valid overlap count, available/unavailable status and
  missingness.
- Per-stone median and p90 of absolute perturbation sensitivity;
  per-pair JSON and a compact chart of dark-switch response.

Do **not** choose a perturbation to improve a stone's ranking, tune
facet boundaries, replace the original measurement, or create a
virtual-vs-physical classifier. This is a **measurement confound audit**.
Even a low perturbation sensitivity does not establish the physical
origin of a contrast feature.

## Tests and acceptance

- [ ] Synthetic unchanged RGB: median normalized difference zero.
- [ ] Multiplicative exposure: no artificial normalized optical change.
- [ ] An illumination gradient on an unchanged scene creates an
      apparent dark/bright response despite zero physical change.
- [ ] A single known 1px misregistration on unchanged textured imagery
      creates an apparent optical difference, without pixel wrapping.
- [ ] Missing/invalid common image support remains unavailable.
- [ ] Four frozen source hashes, exact #96 anchors and all 74 pair
      baselines reproduced against the immutable original #186 atlas.
- [ ] Report per-stone sensitivity rather than a pooled quality score.
- [ ] Keep original #96 estimator, #92 semantic handoff, all physical
      C1/C2/C3 table correspondence, and source-stress policy unchanged.

**Research interpretation:** this does not establish optical quality or
identify true/virtual facets. The benchmark informs whether apparent
scintillation-like image changes are robust against small plausible
non-physical changes, and where an honest `review` or `unavailable`
would be appropriate. No #90 source stress.
