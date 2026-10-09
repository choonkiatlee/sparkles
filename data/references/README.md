# Expert learning references

This is the **agent-authored curation contract**, not a second diamond catalogue or a second comparison system.

An external ChatGPT/coding-agent session reads a source (PriceScope thread, article or similar), distils useful examples and expert commentary, and opens a PR adding a small JSON record. **No LLM is run in GitHub Actions.** Later enrichment (#196/#197) may use explicit Loupe360/V360 links or an IGI report to obtain original stills and 360s, without scraping arbitrary supplier HTML.

## Add a reference from an external session

1. Read [the schema](reference.schema.json) and one of the [seed records](ps285166-r07.json). Work from the actual source and cite it; do not guess an IGI certificate, expert judgement, physical angle, or media availability.
2. Create **one** file at data/references/<stable-id>.json (all lowercase alphanumeric/hyphens; e.g. ps285166-r07); the filename must equal its id.
3. Supply a short label, one **consolidated commentary** explaining what the experts noticed (with post numbers and disagreements where useful), and at least one source link. Optional identity, specifications, topic slugs and direct media URLs are helpful, but a reference without local media is valid.
4. Put **viewer/image/direct-video URLs** in media_sources with status linked_unverified. Put PriceScope pages, retailer listings and real-world YouTube videos in source_links. A linked viewer is *not* recovered validated motion.
5. Use identity.status = unverified when no report is established, or reported when a full report number and lab appear in the source. Numeric/UUID Loupe IDs must **not** be treated as lab reports. Only use linked with linked_diamond_id when the report/lab match an existing locally published certified manifest.
6. Regenerate the deterministic compact index, add the JSON and index to the PR, and run tests:

       python -m diamond_catalogue.references --write
       python -m diamond_catalogue.references --check
       python -m unittest tests.test_learning_references tests.test_catalogue_pages_site -v

An external agent needs only repository write/PR capability and this small contract. No media publishing privileges or LLM API key are necessary.

## Minimal example (illustrative)

    {
      "schema": "sparkles-reference/1",
      "id": "my-thread-stone-01",
      "label": "2.12ct Asscher - under-table behaviour on tilt",
      "identity": {"status": "unverified", "lab": null, "report_number": null},
      "linked_diamond_id": null,
      "diamond_metadata": {"shape": "Asscher", "carat": "2.12"},
      "commentary": "Reviewer A notices leakage on tilt; Reviewer B sees potential. Source posts #28/#32.",
      "source_links": [
        {"kind": "discussion", "url": "https://www.pricescope.com/community/threads/asscher-evaluation-seeking-help.285166/"}
      ],
      "media_sources": [
        {"kind": "viewer", "provider": "v360.diamonds",
         "url": "https://v360.diamonds/c/72c0cf42-7370-4210-92b0-c1bc7d27ef4b?a=625406458&m=i",
         "status": "linked_unverified"}
      ],
      "topics": ["under-table-leakage", "tilt"],
      "evidence": []
    }

## Contract and storage invariants

- Each record has a stable ref ID; it never changes when metadata or a certificate is discovered. The global existing basket will use selection key ref-<id>, leaving certified IDs untouched. The later shared-basket PR #198 owns the frontend integration.
- The record's commentary and original source links are **curated input**. Retrieval may attach new evidence/provenance but must never silently rewrite them. A disagreement can simply be described in the same commentary.
- Unverified/merely reported identities stay distinct from a certified catalogue identity. The validator checks that a linked identity points to an **existing matching certified diamond**. Duplicate reports across reference manifests fail validation rather than being silently merged.
- The index data/reference-index.json is generated and sorted, not edited by hand. It supplies safe manifest paths, compact browse fields, stable selection IDs and evidence availability hints.
- Original bytes and verified rotations, when recovered in later PRs, belong in GitHub Release assets, referenced by the existing evidence[] shape. Never put binary media into Git history.
- The PriceScope #194 eleven-stone seed is **educational/development material**, not fresh independent validation. Its published commentary is a human-curated paraphrase rather than a verified verbatim forum quotation. Scientific granular #82 observations/holdouts remain separate.
- A reference may legitimately have no report, no price, no local still and no 360. Never imply that a remote Loupe360/V360 URL has been successfully downloaded, and don't infer cut quality scores from the discussion.

See #194 for the original source inventory, #195 for this PR, #196/#197 for enrichment, #198 for the single global comparison basket and #199 for Learning Corner UI.
