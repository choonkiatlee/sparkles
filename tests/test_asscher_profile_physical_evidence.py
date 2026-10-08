"""Image-only physical vs optical evidence separation for #91 PR B1."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_profile_physical_evidence as physical
from diamond360 import asscher_profile_feasibility as feasibility

ORIGINAL = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


class PhysicalEvidenceTests(unittest.TestCase):
    @staticmethod
    def make_image(root, add_virtual_bands):
        """Two otherwise identical objects, one with many distracting lines."""
        image = Image.new("RGB", (320, 256), (220, 221, 222))
        d = ImageDraw.Draw(image)
        silhouette = [(130, 40), (190, 40), (270, 150), (160, 240), (50, 150)]
        d.polygon(silhouette, fill=(170, 172, 171))
        d.line(silhouette + [silhouette[0]], fill=(36, 36, 36), width=3)
        if add_virtual_bands:
            # These lines resemble optical/virtual facet edges but were
            # introduced without changing the object's external silhouette.
            for y in (62, 78, 95, 114, 130, 157, 176, 195):
                d.line((82, y, 242, y), fill=(50, 50, 50), width=3)
            for offset in (0, 20, 40):
                d.line((90 + offset, 110, 220 + offset, 182), fill=(55, 55, 55), width=2)
        path = root / ("virtual.png" if add_virtual_bands else "physical.png")
        image.save(path)
        return path

    def test_virtual_optical_bands_do_not_create_physical_facet_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                physical.make_review_template(self.make_image(root, add_virtual_bands=b))
                for b in (False, True)
            ]
            # Optical/virtual lines can change the generic edge detections.
            # Neither condition is ever allowed to claim polishing geometry.
            for record in records:
                self.assertTrue(physical.validate_human_annotations(record))
                self.assertEqual(record["physical_boundary_annotations"], [])
                self.assertEqual(
                    set(record["physical_landmark_annotations"]),
                    set(physical.LANDMARKS),
                )
                for side in record["semantic_measurements"].values():
                    for row in side.values():
                        self.assertEqual(row["status"], "unavailable")
                        self.assertIsNone(row["apparent_angle_deg"])
                self.assertTrue(all(
                    row["physical_measurement_eligible"] is False
                    for row in record["image_only_evidence"]
                ))
            self.assertNotEqual(
                records[0]["source"]["sha256"], records[1]["source"]["sha256"]
            )

    def test_no_direct_promotion_of_hough_or_optical_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = physical.make_review_template(self.make_image(root, True))
            self.assertTrue(record["image_only_evidence"])
            for change in (
                {"semantic_facet_id": "P1"},
                {"physical_measurement_eligible": True},
                {"evidence_class": "visible_surface_junction_candidate"},
            ):
                invalid = deepcopy(record)
                invalid["image_only_evidence"][0].update(change)
                with self.assertRaisesRegex(ValueError, "generic appearance edges"):
                    physical.validate_human_annotations(invalid)

    def test_manually_correlated_contour_keeps_provenance_and_no_semantic_angles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = physical.make_review_template(self.make_image(root, False))
            record["physical_landmark_annotations"]["girdle_left"] = {
                "status": "human_correlated",
                "xy_px": [50, 150],
                "evidence_class": "girdle_edge_candidate",
                "provenance": "separate_image_only_manual_trace",
            }
            record["physical_boundary_annotations"].append({
                "evidence_class": "external_silhouette_candidate",
                "semantic_facet_id": None,
                "review_status": "human_correlated",
                "physical_measurement_eligible": False,
                "segment_xy_px": [[50, 150], [130, 40]],
                "provenance": "separate_image_only_manual_trace",
                "review_notes": "Directly follows the visible external contour of the synthetic object.",
            })
            self.assertTrue(physical.validate_human_annotations(record))
            self.assertEqual(record["semantic_measurements"]["left"]["P1"]["status"], "unavailable")
            invalid = deepcopy(record)
            invalid["physical_boundary_annotations"][0]["semantic_facet_id"] = "P1"
            with self.assertRaisesRegex(ValueError, "independent geometric adjudication"):
                physical.validate_human_annotations(invalid)

    def test_unverified_physical_or_optical_claims_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_image(Path(tmp), True)
            original = physical.make_review_template(path)
            physical_edge = {
                "evidence_class": "external_silhouette_candidate",
                "semantic_facet_id": None,
                "review_status": "unreviewed",
                "physical_measurement_eligible": False,
                "segment_xy_px": [[50, 150], [130, 40]],
                "provenance": "automated_appearance_gradient",
                "review_notes": "",
            }
            optical_edge = {
                "evidence_class": "optical_contrast_only",
                "semantic_facet_id": None,
                "review_status": "human_correlated",
                "physical_measurement_eligible": True,
                "segment_xy_px": [[80, 90], [242, 90]],
                "provenance": "separate_image_only_manual_trace",
            }
            for edge, expected in [
                (physical_edge, "independently traced"),
                (optical_edge, "optical/ambiguous"),
            ]:
                bad = deepcopy(original)
                bad["physical_boundary_annotations"].append(edge)
                with self.assertRaisesRegex(ValueError, expected):
                    physical.validate_human_annotations(bad)

    def test_target_data_and_preemptive_angles_are_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = physical.make_review_template(self.make_image(Path(tmp), True))
            bad = deepcopy(record)
            bad["comparison"]["external_targets_loaded"] = True
            with self.assertRaisesRegex(ValueError, "expert-target"):
                physical.validate_human_annotations(bad)
            bad = deepcopy(record)
            bad["semantic_measurements"]["right"]["P2"]["apparent_angle_deg"] = 42.0
            with self.assertRaisesRegex(ValueError, "cannot manufacture"):
                physical.validate_human_annotations(bad)

    def test_archived_original_is_pinned_and_templates_are_deterministic(self):
        self.assertTrue(ORIGINAL.is_file())
        first = physical.make_review_template(
            ORIGINAL, expected_sha256=feasibility.ORIGINAL_PROFILE_SHA256
        )
        second = physical.make_review_template(
            ORIGINAL, expected_sha256=feasibility.ORIGINAL_PROFILE_SHA256
        )
        self.assertEqual(first, second)
        self.assertTrue(first["source"]["archived_original_match"])
        self.assertEqual(
            first["review_policy_sha256"],
            feasibility.canonical_sha256(physical.REVIEW_POLICY),
        )
        self.assertTrue(physical.validate_human_annotations(first))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "review.json"
            written = physical.write_review_template(
                ORIGINAL, p, feasibility.ORIGINAL_PROFILE_SHA256
            )
            self.assertEqual(written, first)
            self.assertTrue(p.is_file())


if __name__ == "__main__":
    unittest.main()
