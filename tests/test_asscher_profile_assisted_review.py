"""Assisted source-image annotation must never become manufactured physical geometry."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_profile_assisted_review as review
from diamond360 import asscher_profile_feasibility as feasibility


IMAGE = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


class AssistedProfileReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = review.make_worksheet(IMAGE)

    def test_exact_source_and_all_proposals_are_unverified(self):
        data = deepcopy(self.template)
        self.assertEqual(data["source"]["sha256"], feasibility.ORIGINAL_PROFILE_SHA256)
        self.assertEqual(data["status"], "awaiting_image_only_review")
        self.assertEqual(
            [r["region_id"] for r in data["region_proposals"]],
            list("ABCDEFG"),
        )
        self.assertTrue(review.validate_worksheet(data))
        self.assertTrue(all(
            r["proposed_by"] == "assistant_visual_image_only"
            and r["reviewer_verdict"] == "unreviewed"
            and not r["independently_verified_physical_junction"]
            and r["semantic_facet_id"] is None
            for r in data["region_proposals"]
        ))
        self.assertEqual(data["physical_facet_angles_measured"], 0)
        self.assertTrue(all(
            facet["status"] == "unavailable" and facet["physical_angle_deg"] is None
            for group in data["semantic_measurements"].values()
            for facet in group.values()
        ))

    def test_selected_review_traces_are_tentative_not_physical_truth(self):
        decisions = {
            "schema_version": "diamond360-asscher-profile-human-review/1",
            "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
            "decisions": [
                {
                    "region_id": "B",
                    "verdict": "likely_external_contour",
                    "note": "Visible external edge is reasonably distinguishable from white background.",
                    "trace_xy_px": [[68, 170], [96, 146], [118, 123]],
                },
                {
                    "region_id": "G",
                    "verdict": "optical_appearance_only",
                    "note": "Internal appearance bands are not independently correlated to polished planes.",
                    "trace_xy_px": [],
                },
            ],
        }
        result = review.apply_review(self.template, decisions)
        self.assertTrue(review.validate_worksheet(result))
        self.assertEqual(result["status"], "image_only_review_recorded_no_physical_facet_certification")
        self.assertEqual(result["physical_facet_junctions_verified"], 0)
        self.assertEqual(result["physical_facet_angles_measured"], 0)
        self.assertEqual(result["semantic_measurements"]["left"]["P1"]["status"], "unavailable")
        self.assertEqual(result["region_proposals"][1]["review_status"], "reviewer_assessed")
        self.assertEqual(result["region_proposals"][1]["reviewer_trace_xy_px"][1], [96, 146])

    def test_rejects_reference_targets_and_semantic_promotion(self):
        for mutation, match in (
            (lambda x: x.update(comparison_targets_loaded=True), "target leakage"),
            (lambda x: x.update(physical_facet_angles_measured=1), "cannot certify"),
            (lambda x: x["semantic_measurements"]["right"]["P1"].update(physical_angle_deg=50), "cannot produce"),
            (lambda x: x["region_proposals"][0].update(semantic_facet_id="P1"), "cannot promote"),
            (lambda x: x["region_proposals"][0].update(independently_verified_physical_junction=True), "cannot promote"),
        ):
            data = deepcopy(self.template)
            mutation(data)
            with self.assertRaisesRegex(ValueError, match):
                review.validate_worksheet(data)

    def test_image_only_review_rejects_optical_trace_claim(self):
        record = {
            "schema_version": "diamond360-asscher-profile-human-review/1",
            "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
            "decisions": [{
                "region_id": "G",
                "verdict": "likely_external_contour",
                "note": "incorrect attempt to relabel a virtual feature as exterior",
                "trace_xy_px": [[135, 145], [270, 145]],
            }],
        }
        with self.assertRaisesRegex(ValueError, "internal optical band"):
            review.apply_review(self.template, record)

    def test_rejects_trace_outside_review_roi_and_source(self):
        cases = (
            ([[3, 3], [20, 10]], "outside stated review ROI"),
            ([[60, 195], [490, 195]], "outside source-image coordinates"),
            ([[55, 165]], "trace must be empty"),
        )
        for trace, message in cases:
            data = {
                "schema_version": "diamond360-asscher-profile-human-review/1",
                "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
                "decisions": [{
                    "region_id": "D",
                    "verdict": "possible_girdle_edge",
                    "note": "This is just a test, not a confirmed physical interpretation.",
                    "trace_xy_px": trace,
                }],
            }
            with self.subTest(trace=trace):
                with self.assertRaisesRegex(ValueError, message):
                    review.apply_review(self.template, data)

    def test_does_not_allow_unrecorded_decisions_or_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "wrong image"):
            review.apply_review(self.template, {
                "schema_version": "diamond360-asscher-profile-human-review/1",
                "source_sha256": "bad", "decisions": [],
            })
        with self.assertRaisesRegex(ValueError, "unknown or duplicate"):
            review.apply_review(self.template, {
                "schema_version": "diamond360-asscher-profile-human-review/1",
                "source_sha256": feasibility.ORIGINAL_PROFILE_SHA256,
                "decisions": [{"region_id": "H", "verdict": "ambiguous", "note": "bad"}],
            })

    def test_export_produces_usable_image_and_self_contained_touch_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = review.write_worksheet(IMAGE, folder)
            self.assertEqual(
                sorted(p.name for p in folder.iterdir()),
                ["assisted-review-regions.png", "assisted-review.html", "assisted-worksheet.json"],
            )
            self.assertEqual(json.loads((folder / "assisted-worksheet.json").read_text()), data)
            page = (folder / "assisted-review.html").read_text()
            self.assertIn('data:image/png;base64,', page)
            self.assertIn('function draw()', page)
            self.assertIn("Export human review JSON", page)
            self.assertNotIn("__DOC__", page)
            self.assertNotIn("__IMAGE__", page)
            self.assertNotIn("independent_photo_estimate", page)
            with self.assertRaisesRegex(ValueError, "exact archived original"):
                review.make_worksheet(folder / "assisted-review-regions.png")


if __name__ == "__main__":
    unittest.main()
