# Diamond retrieval framework

`diamond_retrieval` is the framework milestone from issue #98. It defines the public, in-memory single-URL retrieval contract and dependency-injection seams. It **does not yet claim production support for Diyona, Quality Diamonds, IGI PDF extraction, Loupe360, Diajewel, Workshop/Core360 or D360**; those adapters are added by #99 and #100.

## Public interface

```python
from diamond_retrieval import retrieve_diamond

result = retrieve_diamond(url)
```

The default composition currently has no real listing providers, so unsupported real URLs raise `UnsupportedInputError`. Tests and downstream adapters can supply a `RetrievalConfig`:

```python
result = retrieve_diamond(url, config=my_config)
```

One call accepts one listing URL and returns one `DiamondResult`. Evidence bytes live in the result; the framework creates no output directory or persistent cache.

## Extension contract

The retriever is constructor-injected with listing providers, evidence resolvers, retrieval policy, evidence downloaders, evidence processors, an identity validator and a result assembler. Components expose `supports(...)`; registration must match exactly one component when a component is required. Multiple matches raise `AmbiguousRegistrationError` rather than silently choosing the first.

Evidence kinds are extensible string identifiers. `DiamondResult.evidence` is a heterogeneous collection of `Evidence` objects, with convenience filters for certificate, still, rotation and video kinds. Adding another evidence kind does not require editing the retriever or standard assembler.

An `EvidenceReference.retrieval_key` is the stable per-invocation deduplication identity supplied by the adapter. Provenance is separate: a repeated reference reached through another source chain can be recorded as a duplicate attempt without downloading the underlying bytes again.

Resolution is bounded by `max_resolution_depth` and by a visited retrieval-key set. Policy selection runs before resolution/download and again for every newly resolved reference. Excluded references are recorded as `not_requested` and never reach a downloader.

## Validation and failure semantics

Generic non-empty byte validation runs in the retriever after every download and cannot be disabled by policy. Format-specific validation remains the processor's responsibility. Identity validation always runs after processing and before result assembly. Any returned `conflict` comparison raises `IdentityConflictError`, so conflicting evidence is never packaged into a combined result.

Asset-level problems are represented by `EvidenceAttempt` statuses such as `unsupported`, `missing`, `download_failed`, `processing_failed`, `invalid_payload`, `resolution_failed` and `resolution_limit`. Recoverable asset failures therefore produce a partial result when identity remains established; configuration ambiguity and identity conflicts remain exceptions.

The standard policy requests certificate, still, rotation and video references. It considers a result complete only when certificate evidence has a parsed, matching report identity, at least one motion evidence object (rotation or video) succeeded, and no selected discovered asset failed or was unsupported. Optional absence of undiscovered stills does not itself make a result partial.

## Boundaries for later PRs

Issue #99 supplies real retailer metadata/certificate/still adapters, HTTP composition and concrete identity normalization. Issue #100 supplies reusable supplier-motion downloaders/processors. Those PRs should register implementations against these contracts rather than add retailer/viewer branches to `DiamondRetriever`.
