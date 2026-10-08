# #123 — Physical geometry versus optical/virtual appearance provenance

## Why

Four-stone source-RGB experiments #140, #146 and #162 conclusively falsified
the assumption that a strong, straight, repeatable or connected *image* edge is
automatically a polished facet junction. At least some lines follow **virtual
facets/reflections**, including examples inspected by the user. An octagon
generated from those edges can look geometrically regular yet cut through
visible facets.

The research data should be valuable to #92's optical/perceptual project,
**without silently feeding its unverified edge positions into the physical
geometry estimator**. This PR creates that explicit machine-readable contract
as a read-only conversion of archived source diagnostic outputs. It does not
claim that an automated method can yet tell which individual line is a
reflection versus a physical junction.

## Three distinct evidence categories

| Kind | Meaning | Permitted geometry claim |
| --- | --- | --- |
| `physical_silhouette` | Observed, frozen #96 girdle/stone-background outer contour | **Outer outline only**; not inner polished facet boundaries |
| `optical_image_plane_observation` | Original camera-RGB contrast segment or local two-orientation junction candidate from #146/#162 | Optical/structural **unresolved**, no facet identity, no 3D angle |
| `unavailable_physical_correspondence` | C1_C2, C2_C3 and C3_TABLE, for which independent polished-junction correspondence has not been established | No physical vertices, explicit `unavailable` |

The `require_physical_support` gate fails closed on any RGB segment,
cross-view repeated line or local junction masquerading as physically
validated geometry. Only the externally observed `GIRDLE_OUTLINE`
can pass, as a stone/background silhouette. The preexisting fitted
interior wireframe is still useful as **nonexclusive semantic image-plane
support**, but it must not be reinterpreted as verified physical geometry.

## Source and cross-view provenance

Inputs are the **immutable original camera-RGB diagnostic artifacts**,
not a new scan with user-specific thresholds:

- #146 [native RGB lines, four stones](https://github.com/choonkiatlee/sparkles/actions/runs/37813575116)
- #162 [observed junction graph, four stones](https://github.com/choonkiatlee/sparkles/actions/runs/37815198934)
- #96 reference [frozen four-stone outer validation](https://github.com/choonkiatlee/sparkles/actions/runs/37755387174)

Every observation retains its source frame, side index or junction/corner
slot, native RGB diagnostic path and normalized gauge coordinates.
Cross-view proximity counts compare **all** line candidate offsets
across frame pairs, avoiding greedy nearest-neighbor facet IDs. Repeated
contrast can be a repeated *virtual* feature; the counts can never
upgrade their physical status.

A view is `likely_crown` only when #73 explicitly resolves it. Other
stones retain `uncertain`. Automated `confirmed_virtual_facet_labels`
is an empty list: the user's visual finding that some lines are virtual
does not justify claiming precisely which unlabeled candidate is
refracted or reflected.

## Reproducibility and acceptance

A focused workflow downloads the pinned #146/#162 artifacts and frozen
source manifest. It checks all four certificate/selected-source identities
and stores per-stone `facet-provenance.json` plus `summary.json`.
Negative tests try to promote a repeated virtual-looking line and a
local junction into a physical facet and must fail. Missing observations
remain absent, not a synthetically completed boundary.

- [ ] Focused tests and frozen-manifest replay pass.
- [ ] All four stones retain optical observations, uncertain crown metadata
      and zero validated inner physical boundaries.
- [ ] Optical edge/junction features remain accessible for #92/#123 but
      *cannot* be used as physical facet geometry via the provenance API.
- [ ] No change to #96 estimator, existing #92 optical handoff,
      facet-angle inference, quality scoring or source stress.

**Research disposition:** A data-contract improvement, *not* a successful
facet detector. Any future promotion of C3/table geometry requires new
independent physical evidence; mere positional repeatability and
straight-line junction appearance are insufficient.
