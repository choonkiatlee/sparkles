# DiaGem / Sergey 2008 Asscher geometry fixture

This fixture preserves a small external geometry test case from the PriceScope thread
[Why cut asschers with small corners and windmills?](https://www.pricescope.com/community/threads/why-cut-asschers-with-small-corners-and-windmills.78433/).

## Why this case is useful

Yoram F. (DiaGem) cut the real stone discussed in the thread and reported manual measurements and known cutting asymmetries. Sergey Sivovolenko then estimated several crown/pavilion angles independently from a profile photograph. The discussion also records which photographic conditions Sergey considered suitable or unsuitable for angle recovery.

This makes the case useful for testing **geometry extraction**, not cut quality. It is intentionally small and should not be used to tune a universal Asscher model.

Structured facts live in [ground-truth.json](ground-truth.json). Every value is tagged by evidence class so that direct/manual facts, image-derived estimates, scanner readings, and contextual design values are not conflated.

## Evidence classes

- `manual_reported`: DiaGem/Yoram reports a physical/manual measurement or a fact about how he cut the stone.
- `photo_estimate`: Sergey estimates geometry from the supplied photograph.
- `scanner_reported`: OGI/Sarin/FacetWare output quoted in the discussion; not treated as ground truth.
- `design_context`: intended/model values from the design discussion; not treated as the finished stone.
- `source_media_unresolved`: the source says an image was attached, but the exact original bytes have not yet been recovered.

## Particularly valuable checks

1. Sergey estimated, from the better profile photograph, right-side P1/P2/P3/C1 angles of 50/42/31/43.5 degrees and left-side values of 49.5/41/30/46 degrees, with ±1 degree stated uncertainty (post 156).
2. DiaGem says the real P1 and P2 physical lengths are practically identical, while P3 is about 60% of their length (post 171). He explicitly says the photograph makes P1 look longer. This is a useful test that an image-plane wireframe must not be mislabeled as physical facet length.
3. DiaGem reports a small real asymmetry: two opposed P3 facets were adjusted to close the culet, and the C3/table junctions are slightly unbalanced (post 115). A geometry fitter therefore should use symmetry as a prior, not a hard equality constraint.
4. Sergey describes suitable profile imagery as sharp, subdued/no-flash front light, white background and horizontal table; he additionally asks for minimum projection so pavilion side facets are not visible (posts 136–137). In post 163 he rejects a tilted/short-focus image once pavilion side facets become visible.

## Source media status

The full PriceScope attachment objects are now archived for post 151 (`profile-photo.JPG`, 410 × 319), post 157 (`manual-measurements.JPG`, 421 × 277) and post 158 (`manual-measurements-last-line.JPG`, 414 × 281). They were downloaded through the authenticated full attachment endpoints without re-encoding. Exact URLs, original filenames, content types, bytes, dimensions, SHA-256 and retrieval provenance are recorded in `ground-truth.json`, alongside the earlier inline-preview metadata.

Post 158 is a distinct corrected complete table with the previously omitted pavilion row. No numeric values were inferred/transcribed from the images. See [media-recovery.md](media-recovery.md) for recovery history.

## Intended first experiment

The first Sparkles geometry experiment should recover a **2D semantic wireframe** from appropriate face-on/profile imagery and keep that separate from any inferred 3D physical model. A useful output should identify named facet families (P1/P2/P3, C1/C2/C3 where visible), emit confidence per boundary/facet, and preserve observed-vs-inferred status.

Do not tune the extractor to reproduce the stored numbers. Use this fixture as an external check after the extraction method is specified.
