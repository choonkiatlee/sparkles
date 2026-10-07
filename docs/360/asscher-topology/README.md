# Canonical semantic Asscher topology

Issue: #74 · Parent: #72 · North-star architecture: #79

This directory defines the **geometry-only semantic contract** consumed by the
later constrained wireframe fitter.

The central design rule is that Sparkles must not collapse three different
representations into one:

\`\`\`text
stable physical-facet topology
        ↓
2-D image-plane semantic scaffold + confidence/provenance
        ↓
[future issue boundary]
        ↓
empirical optical / appearance regions
        ↓
optical event tracks
\`\`\`

\`P3_N\`, \`P2_E\`, \`C2_SW\`, etc. are stable semantic identities in the
physical topology. They do **not** mean that particular image pixels are the
direct geometric projection of that polished facet.

That distinction is especially important for pavilion structure visible
through the table. Internal reflection and projection can make the visible
appearance more complicated than a flat map of polished facets.

## Two contracts, not one pixel segmentation

### Physical semantic topology

\`diamond360.asscher_topology.canonical_physical_topology()\` defines:

- C1/C2/C3 crown facet families;
- P1/P2/P3 pavilion facet families;
- table, girdle, culet-region and windmill/junction structures;
- explicit structural adjacency;
- explicit opposite and quarter-turn counterpart relations;
- the 90-degree canonical orientation gauge inherited from #73.

This layer contains semantic identity and topology only. It does not own pixels
and is not a 3-D reconstruction.

The v1 family ordering convention is:

- crown: \`C1 -> C2 -> C3 -> TABLE\` from girdle inward;
- pavilion: \`P1 -> P2 -> P3 -> CULET_REGION\` from girdle inward.

Each step family has eight orientation members:
\`N, NE, E, SE, S, SW, W, NW\`.

These labels are a canonical gauge, not an absolute mark on the physical stone.

### Image-plane semantic scaffold

\`canonical_synthetic_scaffold()\` demonstrates the separate image-plane
representation.

A scaffold contains:

- normalized 2-D vertices;
- named boundaries;
- **non-exclusive** semantic spatial supports;
- per-entity observation state;
- confidence;
- provenance;
- a sequence-stable \`gauge_id\`.

The scaffold is an association layer, not an exclusive segmentation.

The following are explicitly legal:

- two semantic supports overlap;
- one support refers to more than one physical semantic entity;
- a physical semantic entity has no directly observed support in a frame;
- a support is only partially observable;
- coordinates differ between nominally corresponding facets;
- one semantic entity is observed while its counterpart is inferred or unavailable.

The following interpretation is explicitly forbidden:

\`\`\`text
every image pixel -> exactly one polished physical facet
\`\`\`

Likewise, \`semantic_supports\` must not be read as ray-traced polished-facet
projections.

## Future optical / virtual-facet layer

#74 does **not** define empirical virtual facets.

The contract deliberately leaves a many-to-many extension point so later work
can represent something conceptually like:

\`\`\`text
optical_region_17:
  spatial_support: ...
  physical_associations:
    - semantic_id: P3_N
      confidence: ...
    - semantic_id: P2_NE
      confidence: ...
\`\`\`

Nothing in #74 requires an optical region to have a single physical parent.
Future optical regions may overlap, subdivide or cross apparent physical
regions, or retain uncertain attribution.

## Orientation gauge and sequence stability

#73 establishes canonical pose only modulo 90 degrees. #74 preserves that
ambiguity.

\`N/E/S/W\` are therefore an arbitrary but stable canonical gauge. A sequence
may select any quarter-turn-equivalent gauge, but once selected it must not
change frame-by-frame.

The physical topology encodes counterpart relationships directly, so later
code should use helpers rather than parsing semantic-ID strings:

\`\`\`python
rotate_semantic_id(topology, "P3_N", 1)   # P3_E
opposite_semantic_id(topology, "P2_E")    # P2_W
\`\`\`

\`validate_sequence_gauge()\` checks that the same \`gauge_id\` is retained
across scaffold instances.

## Observation provenance is separate from identity

A physical entity exists in the topology regardless of whether it is visible
in a particular image.

Per-instance observations distinguish provenance:

- \`observed\`
- \`model_inferred\`
- \`symmetry_inferred\`
- \`unavailable\`

and separately observation state:

- \`complete\`
- \`partial\`
- \`unavailable\`

Changing provenance never changes semantic identity. This permits one weak or
missing P3 counterpart without hallucinating equal certainty around the stone.

## Geometric invariants

The v1 image-plane validator requires:

- valid semantic references;
- finite connected geometry;
- simple/non-self-crossing declared closed boundaries;
- ordered nested crown scaffold boundaries;
- a stable sequence gauge;
- explicit confidence/provenance/observation state;
- no exclusive pixel-partition claim;
- no direct polished-facet projection claim.

Fourfold equality of coordinates is **not** an invariant.

The synthetic asymmetric fixture deliberately perturbs the inner crown/table
scaffold and can independently mark P3/C2 entities partially observed or
unavailable.

Pavilion semantic supports in the synthetic fixture are deliberately
overlapping image-plane hints. They demonstrate the representation contract
only and are not an ideal Asscher, a projection model, a training target or a
quality reference.

## Machine-readable contract

\`contract-v1.json\` records the version IDs, enums, ordering convention,
invariants and the explicit future-extension boundary. Runtime construction and
validation live in \`diamond360/asscher_topology.py\`.

Tests in \`tests/test_asscher_topology.py\` cover:

- symmetric and asymmetric topology;
- partial and unavailable observations;
- provenance-independent semantic identity;
- programmatic counterpart lookup;
- sequence gauge stability;
- overlapping and multi-entity semantic support;
- crossing, reordered and disconnected geometry failures;
- source-free synthetic rendering.

## Non-goals

#74 does not implement:

- facet detection from pixels;
- empirical optical / virtual-facet segmentation;
- optical event tracking;
- brilliance, fire or scintillation metrics;
- quality scoring;
- physical angle recovery;
- full 3-D reconstruction.

Those layers remain downstream of the geometry contract.
