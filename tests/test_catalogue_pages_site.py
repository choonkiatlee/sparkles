"""Network-free checks for static catalogue and Pages staging."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.build_catalogue_pages import ROOT, build

class PagesCatalogueTests(unittest.TestCase):
    def test_build_preserves_existing_archive_and_real_published_manifests(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            build(out)
            for path in (
                "index.html", ".nojekyll", "catalogue/index.html",
                "catalogue/core.mjs", "catalogue/app.mjs", "catalogue/styles.css",
                "catalogue/compare.mjs", "catalogue/comparison-view.mjs",
                "catalogue/rotation.mjs", "catalogue/rotation-canvas.mjs",
                "catalogue/rotation-player.mjs",
                "data/catalog.json", "data/diamonds/igi-lg756520111.json",
                "data/diamonds/igi-lg816611062.json",
            ):
                self.assertTrue((out / path).is_file(), path)
            home = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="catalogue/"', home)
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

    def test_frontend_uses_static_index_and_no_github_rest_discovery(self):
        app = (ROOT / "catalogue/app.mjs").read_text(encoding="utf-8")
        self.assertIn('fetch("../data/catalog.json"', app)
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
