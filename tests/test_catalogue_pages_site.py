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
                "catalogue/rotation.mjs",
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
            self.assertTrue(all(row["has_motion"] for row in by_id.values()))
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

    def test_generated_icons_only_affect_overview_not_original_comparison(self):
        app = (ROOT / "catalogue/app.mjs").read_text(encoding="utf-8")
        comparator = (ROOT / "catalogue/compare.mjs").read_text(encoding="utf-8")
        self.assertIn("overview_thumbnail_url || row.thumbnail_url", app)
        self.assertIn("const original = httpUrl(row.thumbnail_url)", app)
        self.assertNotIn("overview_thumbnail_url", comparator)

    def test_c3a_shared_360_player_preserves_original_stills_and_default_prefetch(self):
        view = (ROOT / "catalogue/comparison-view.mjs").read_text(encoding="utf-8")
        rot = (ROOT / "catalogue/rotation.mjs").read_text(encoding="utf-8")
        html = (ROOT / "catalogue/index.html").read_text(encoding="utf-8")
        self.assertIn('["rotation","360 rotation"]', view)
        self.assertIn('fillColumn(column,data)', view)
        self.assertIn('renderMotion(column,data)', view)
        self.assertIn('DEFAULT_PREFETCH_MODE', view)
        self.assertIn('Prefetch every frame (more data)', view)
        self.assertIn('export const PREFETCH_ALL_DEFAULT = false', rot)
        self.assertIn('concurrency=PREFETCH_CONCURRENCY', rot)
        self.assertIn('Shared', view)
        self.assertIn('relative frame position', html)
        self.assertNotIn("angle-calibrated playback", html)

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
