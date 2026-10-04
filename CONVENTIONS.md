# Sparkles conventions

- Open the repository root as an Obsidian vault; start at `Sparkles home.md`.
- `resources/<LAB>-<REPORT>/Sparkles <KEY> research.md` is the single evolving dossier for a certificate.
- Original evidence and curated ZIPs live in that certificate's `artifacts/` folder. Preserve original bytes, source URLs, SHA-256, frame indices and explicit reading order.
- `evaluations/` holds dated HTML reports and Markdown companions. Substantive reassessments create a new timestamped report; preserve earlier evaluations.
- Notes use flat YAML: type, status, tags, aliases and certificate/date fields. Navigation uses repository-root-qualified wikilinks; relative Markdown asset links are also supported. Explicit edges, when useful, are rows of a `## Links` table with Target, Type and Note.
- Preserve the compact source-bundle budget from the research skill. Missing ASET, unknown recording setup and deferred official IGI verification remain explicit evidence limits.
- Research facts, optical interpretation and user preferences remain distinguishable. Never treat ordinary grey/black photography as proof of leakage.
- Existing ZIPs were migrated byte-for-byte. Any legacy `spaces/personal/sparkles/` path written inside an archived README or manifest maps to the same path here with that prefix removed; source hashes remain unchanged.
- Use focused PRs; merge only on request. Verify links, YAML, manifests and remote content before reporting successful saving.
