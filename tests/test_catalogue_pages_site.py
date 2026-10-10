"""Network-free checks for static catalogue and Pages staging."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.build_catalogue_pages import ROOT, build, validate_learning_guide

class PagesCatalogueTests(unittest.TestCase):
    def test_build_preserves_existing_archive_and_real_published_manifests(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            build(out)
            for path in (
                "index.html", ".nojekyll", "catalogue/index.html",
                "learning/index.html", "learning/app.mjs", "learning/styles.css",
                "learning/guide.mjs", "learning/where-to-look.svg",
                "catalogue/reference.mjs",
                "catalogue/core.mjs", "catalogue/app.mjs", "catalogue/styles.css",
                "catalogue/compare.mjs", "catalogue/comparison-view.mjs",
                "catalogue/rotation.mjs", "catalogue/rotation-canvas.mjs",
                "catalogue/rotation-player.mjs",
                "data/catalog.json", "data/reference-index.json", "data/learning-guide.json",
                "data/references/ps285166-r07.json", "data/diamonds/igi-lg756520111.json",
                "data/diamonds/igi-lg816611062.json",
            ):
                self.assertTrue((out / path).is_file(), path)
            home = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="catalogue/"', home)
            self.assertIn('href="learning/"', home)
            self.assertIn('href="#diamonds"', home)
            index = json.loads((out / "data/catalog.json").read_text(encoding="utf-8"))
            by_id = {r["id"]: r for r in index["diamonds"]}
            self.assertEqual(by_id["igi-lg756520111"]["retrieval_status"], "partial")
            self.assertEqual(by_id["igi-lg816611062"]["retrieval_status"], "complete")
            # Other legitimate catalogue stones may have only still evidence.
            self.assertTrue(by_id["igi-lg756520111"]["has_motion"])
            self.assertTrue(by_id["igi-lg816611062"]["has_motion"])
            self.assertFalse((out / ".github").exists())
            self.assertFalse((out / "diamond_retrieval").exists())

    def test_reference_index_is_statically_published_with_curated_references(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            build(out)
            index = json.loads((out / "data/reference-index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["schema"], "sparkles-reference-index/1")
            self.assertGreaterEqual(len(index["references"]), 11)
            self.assertTrue(all(isinstance(row["has_motion"], bool) for row in index["references"]))
            self.assertTrue(all((out / row["manifest_path"]).is_file() for row in index["references"]))
            r07 = json.loads((out / "data/references/ps285166-r07.json").read_text(encoding="utf-8"))
            self.assertIn("under-table steps", r07["commentary"])

    def test_learning_corner_is_separate_but_reuses_basket_and_player(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            build(out)
            html = (out / "learning/index.html").read_text(encoding="utf-8")
            app = (out / "learning/app.mjs").read_text(encoding="utf-8")
            shared = (out / "catalogue/comparison-view.mjs").read_text(encoding="utf-8")
            self.assertIn('href="../catalogue/styles.css"', html)
            self.assertIn('id="references"', html)
            self.assertIn('id="guide-cards"', html)
            self.assertIn('src="./where-to-look.svg"', html)
            self.assertIn('id="comparison-grid"', html)
            self.assertIn("createComparisonView", app)
            self.assertIn("selectionFromSearch", app)
            self.assertIn("selectionSearch", app)
            self.assertIn("toggleSelection", app)
            self.assertIn("createRotationPlayer", shared)
            self.assertIn("projectReferenceComparison", shared)
            self.assertIn('id="learning-link"', (out / "catalogue/index.html").read_text(encoding="utf-8"))

    def test_learning_guide_can_grow_and_rejects_orphan_reference_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            build(out)
            path = out / "data/learning-guide.json"
            guide = json.loads(path.read_text(encoding="utf-8"))
            refs = json.loads((out / "data/reference-index.json").read_text(encoding="utf-8"))
            ids = {row["id"] for row in refs["references"]}
            self.assertEqual(guide["schema"], "sparkles-learning-guide/1")
            self.assertGreaterEqual(len(guide["lessons"]), 4)
            new_category = {
                "id": "new-teaching-observation", "category": "Example theme",
                "title": "What should we check?", "summary": "A source-grounded lesson.",
                "prompt": "Examine motion at several angles.",
                "source_url": "https://www.pricescope.com/community/threads/example.12345/",
                "examples": [{
                    "id": refs["references"][0]["id"],
                    "label": "A single supported example",
                    "comment": "Reviewer reports a specific visible observation."
                }]
            }
            guide["lessons"].append(new_category)
            path.write_text(json.dumps(guide), encoding="utf-8")
            validate_learning_guide(out, ids)  # One-example new categories work.
            new_category["featured_pair"] = [new_category["examples"][0]["id"]] * 2
            path.write_text(json.dumps(guide), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "featured pair"):
                validate_learning_guide(out, ids)
            del new_category["featured_pair"]
            new_category["examples"][0]["id"] = "not-published"
            path.write_text(json.dumps(guide), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing example"):
                validate_learning_guide(out, ids)

    def test_frontend_uses_static_index_and_no_github_rest_discovery(self):
        app = (ROOT / "catalogue/app.mjs").read_text(encoding="utf-8")
        self.assertIn('fetch("../data/catalog.json"', app)
        self.assertIn('fetch("../data/reference-index.json"', app)
        self.assertNotIn("api.github.com", app)
        self.assertNotIn("releases/latest", app)
        comparison = (ROOT / "catalogue/compare.mjs").read_text(encoding="utf-8")
        self.assertIn("../data/diamonds/", comparison)
        self.assertNotIn("api.github.com", comparison)
        self.assertIn("createManifestLoader", comparison)

    def test_c3b_ordinal_viewer_buffers_originals_with_full_prefetch_enabled(self):
        html=(ROOT / "catalogue/index.html").read_text(encoding="utf-8")
        comparison=(ROOT / "catalogue/comparison-view.mjs").read_text(encoding="utf-8")
        player=(ROOT / "catalogue/rotation-player.mjs").read_text(encoding="utf-8")
        model=(ROOT / "catalogue/rotation.mjs").read_text(encoding="utf-8")
        self.assertIn("shared controls", html)
        self.assertIn("createRotationPlayer", comparison)
        self.assertIn('"rotation","Original rotation"', comparison)
        self.assertIn("stepPosition", player)
        self.assertIn("setTimeout", player)
        self.assertIn('mode: "all"', model)
        self.assertIn("createBufferedFrameCoordinator", model)
        self.assertIn("maxDecoded: 24", model)
        self.assertIn("Preload all frames", player)
        self.assertIn("pointerdown", player)
        self.assertIn("requestAnimationFrame", player)
        self.assertNotIn("motion-frame-caption", player)
        self.assertNotIn("motion-prefetch-progress", player)
        self.assertIn("coordinator.seek", player)
        self.assertIn("createPreviewCache", player)
        self.assertIn("createCanvasSurface", player)
        self.assertIn("subscribeFrames", model)
        self.assertIn('"all"', model)
        self.assertIn("asset?.storage?.url", model)
        self.assertNotIn("api.github.com", model)
        self.assertNotIn("overview_thumbnail_url", player)

    def test_generated_icons_only_affect_overview_not_original_comparison(self):
        app = (ROOT / "catalogue/app.mjs").read_text(encoding="utf-8")
        comparator = (ROOT / "catalogue/compare.mjs").read_text(encoding="utf-8")
        self.assertIn("overview_thumbnail_url || row.thumbnail_url", app)
        self.assertIn("const original = httpUrl(row.thumbnail_url)", app)
        self.assertNotIn("overview_thumbnail_url", comparator)

    def test_compact_table_has_real_selection_and_future_score_placeholders(self):
        html = (ROOT / "catalogue/index.html").read_text(encoding="utf-8")
        app = (ROOT / "catalogue/app.mjs").read_text(encoding="utf-8")
        for value in ('class="overview-table"', 'id="cards"', 'value="colour"',
                      'value="clarity"', 'Diamond score', 'id="compare-button"'):
            self.assertIn(value, html)
        self.assertNotIn('class="cards"', html)
        self.assertIn('function makeRow(row)', app)
        self.assertIn('input.type = "checkbox"', app)
        self.assertIn('Not scored', app)
        self.assertIn('thumbnail_url', app)
        self.assertIn('comparisonView.update', app)

    def test_ingestion_invokes_pages_after_publishing(self):
        ingest = (ROOT / ".github/workflows/diamond-catalogue-ingest.yml").read_text(encoding="utf-8")
        pages = (ROOT / ".github/workflows/catalogue-pages.yml").read_text(encoding="utf-8")
        self.assertIn("needs: publish", ingest)
        self.assertIn("uses: ./.github/workflows/catalogue-pages.yml", ingest)
        self.assertIn("workflow_call:", pages)
        self.assertIn("ref: master", pages)
        self.assertIn("actions/deploy-pages@v4", pages)
