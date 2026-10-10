# Expert learning references

This is the **agent-authored curation contract**, not a second diamond catalogue or a second comparison system.

An external ChatGPT/coding-agent session reads a source (PriceScope thread, article or similar), distils useful examples and expert commentary, and opens a PR adding a small JSON record. **No LLM is run in GitHub Actions.** Later enrichment (#196/#197) may use explicit Loupe360/V360 links or an IGI report to obtain original stills and 360s, without scraping arbitrary supplier HTML.

## Add a reference from an external session

1. Read [the schema](../reference.schema.json) and one of the [seed records](ps285166-r07.json). Work from the actual source and cite it; do not guess an IGI certificate, expert judgement, physical angle, or media availability.
2. Create **one** file at data/references/<stable-id>.json (all lowercase alphanumeric/hyphens; e.g. ps285166-r07); the filename must equal its id.
3. Supply a short label, one **consolidated commentary** explaining what the experts noticed (with post numbers and disagreements where useful), and at least one source link. Optional identity, specifications, topic slugs and direct media URLs are helpful, but a reference without local media is valid.
4. Put **viewer/image/direct-video URLs** in media_sources with status linked_unverified. Put PriceScope pages, retailer listings and real-world YouTube videos in source_links. A linked viewer is *not* recovered validated motion.
5. Use identity.status = unverified when no report is established, or reported when a full report number and lab appear in the source. Numeric/UUID Loupe IDs must **not** be treated as lab reports. Only use linked with linked_diamond_id when the report/lab match an existing locally published certified manifest.
6. **Review the [learning guide](../learning-guide.json)** as part of the *same* reference-ingestion PR: add this stone to relevant existing teaching categories, or author a new category if the experts explain a genuinely new visual phenomenon. The guide can remain unchanged if the source contains no defensible teaching observation.
7. Regenerate the deterministic compact index, include any guide update in the PR, and run tests:

       python -m diamond_catalogue.references --write
       python -m diamond_catalogue.references --check
       python -m unittest tests.test_learning_references tests.test_catalogue_pages_site -v
       node --test tests/learning-guide.test.mjs

An external agent needs only repository write/PR capability and this small contract. No media publishing privileges or LLM API key are necessary.

## Maintain the Learning Corner guide during reference ingestion

**The teaching categories are editorial data, not hardcoded JavaScript.** Read [`data/learning-guide.json`](../learning-guide.json) before every new reference PR. Each entry in `lessons[]` is one human-friendly visual concept; the same diamond can illustrate multiple concepts. The site's guide and comparison actions automatically render new categories and examples.

When an external agent curates a new stone:

1. Finish `data/references/<id>.json` with the original source links, a single consolidated commentary, and honest media/identity status. Regenerate `data/reference-index.json` with the usual CLI.
2. **Inspect every existing lesson** in `data/learning-guide.json`. If the stone illustrates that specific phenomenon, append `{"id":"<id>","label":"Short example role","comment":"One concise, reviewer-attributed observation (forum post #...)"}` to its `examples[]`. References don't have to appear in a lesson just because they have a topic tag; include only supported teaching cases.
3. If none fits and there is a well-supported new phenomenon, append a new lesson with a unique slug `id`, readable `category`/`title`/`summary`/`prompt`, source URL, and **one or more** examples. All display copy is in JSON. Order in `lessons[]` controls the page order; numbering is automatic.
4. Optionally set `featured_pair: ["<reference-id-1>", "<reference-id-2>"]` using **two distinct IDs already in that lesson's examples**. This powers **Compare this pair** via the existing five-stone shared basket and 360 player. A lesson with one example is fully supported; it simply has no featured-pair button until another suitable example arrives. **Adding a third or fourth example never silently changes the featured pair.**
5. Optionally link a genuinely existing expert annotated visual via `annotated_source: {"label":"Annotated image + expert explanation","url":"https://..." }`. The UI links to the attributed original. Do not pretend our generic SVG schematic was drawn by a named expert, rehost copyrighted forum attachments, or invent optical evidence.
6. Run `python -m diamond_catalogue.references --check`, `node --test tests/learning-guide.test.mjs` and `python -m unittest tests.test_catalogue_pages_site -v`. The Pages build rejects nonexistent reference IDs, duplicate examples/category IDs, invalid links and invalid featured pairs; JS tests check deep-link comparison and new-category compatibility.

Example of **adding a new category** (one reference is enough to begin):

```json
{
  "id": "environment-reflections",
  "category": "Lighting & reflections",
  "title": "Could the surroundings be causing that dark patch?",
  "summary": "Changes in the environment can look like leakage in some videos.",
  "prompt": "Check whether the patch moves with lighting or persists across a tilt.",
  "source_url": "https://www.pricescope.com/community/threads/asscher-evaluation-seeking-help.285166/",
  "examples": [
    {
      "id": "ps285166-r01",
      "label": "Environment-reflection caution",
      "comment": "0-0-0 points out that reflections may mimic apparent windowing (#54)."
    }
  ]
}
```

A future agent should add this object inside the existing `lessons` array, not replace the whole file. **No frontend code, new schema, extra viewer, or automatic LLM pipeline is required.** When the reference is later enriched with stored media, the same guide cards pick up its published thumbnail automatically.

## Three-thread learning reference inventory (R01–R23)

The curated Learning Corner now includes **23 educational diamonds**. As before, each diamond is a separate, named reference; any later media enrichment should add to its existing JSON, never replace curated commentary. This inventory is **not** a blind holdout for the optical-research metrics.

- **R01–R11**: PriceScope *Asscher evaluation — seeking help* (`ps285166-r01` through `r11`).
- **R12–R15**: PriceScope *Are these Asschers well cut?* (`ps282648-r12` through `r15`). R12 preserves Karl_K's original promising vendor-360 read and his later ASET-informed reassessment. R14 and R15 are distinct same-spec stones sharing an external comparison album.
- **R16–R23**: PriceScope *Asscher cut evaluation* (`ps281114-r16` through `r23`). Source of truth for existing benchmark identities is [the #64 research source catalog](../../docs/360/external-benchmark/pricescope/source-catalog.json); identifiers and interpretations are restated only as teaching commentary, never re-labelled as untouched validation samples.

**Do not download archived footage a second time.** The #64 [PriceScope research recovery bundle](https://github.com/choonkiatlee/sparkles/releases/download/pricescope-research-2026-10-06-v1/pricescope-media-recovery-2026-10-06-v3.zip) already holds the full original 256-frame D360 sequences for R17/R18 and the original Kashi MP4s for R20/R22. These source pointers live in their `source_links`, while their original vendor URLs live in `media_sources` as `linked_unverified`. **None of the newly curated R12–R23 records declares published `evidence` or playable reference media.** A later enrichment agent should verify/reuse the archive's hashes and storage locators rather than inventing a duplicate release or assuming the research ZIP is a reference playback endpoint.

Other important caveats: R12's Loupe URL is not certificate verification; R21's Whiteflash 2.05ct **D VS1** conflicts with forum **E VS1 / D VS2** descriptions; R23's retailer categorizes its square step cut as **Emerald**, though the forum discusses it with Asschers; R19's original clone is not equated with the later clone #2. Preserve chronology, source attribution and uncertainty.

The [learning-guide.json](../learning-guide.json) is curated with these references: existing four topics have additional examples, and new lessons cover evidence-dependent reassessment, localized P3 leakage, same-spec comparisons, and optical aesthetics versus wearer preferences. **Future agents should keep updating the same guide** using the steps above when new references are curated. 

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
