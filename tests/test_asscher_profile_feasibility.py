"""PR A: profile-feasibility diagnostics, never external angle matching."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_profile_feasibility as feasibility

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


class ProfileFeasibilityTests(unittest.TestCase):
    def _synthetic(self, folder):
        image = Image.new("RGB", (320, 260), (220, 220, 220))
        draw = ImageDraw.Draw(image)
        draw.polygon(
            [(136, 35), (184, 35), (271, 158), (253, 175),
             (160, 245), (67, 175), (49, 158)],
            fill=(175, 180, 177),
        )
        for y, span in ((45, 32), (75, 54), (105, 82), (160, 112), (177, 88)):
            draw.line((160 - span, y, 160 + span, y), fill=(45, 48, 49), width=2)
        draw.line((49, 158, 160, 245), fill=(35, 40, 45), width=2)
        draw.line((271, 158, 160, 245), fill=(35, 40, 45), width=2)
        path = folder / "profile.png"
        image.save(path)
        return path

    def test_frozen_policy_and_all_semantic_slots_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = self._synthetic(folder)
            result, _, _ = feasibility.analyse_image(path)
            self.assertEqual(result["schema_version"], feasibility.SCHEMA)
            self.assertEqual(
                result["policy_sha256"],
                feasibility.canonical_sha256(feasibility.POLICY),
            )
            self.assertEqual(result["status"], "review")
            self.assertGreater(len(result["image_evidence"]["line_candidates"]), 0)
            self.assertEqual(set(result["semantic_measurements"]), {"left", "right"})
            for side in result["semantic_measurements"].values():
                self.assertEqual(set(side), set(feasibility.SLOTS))
                for row in side.values():
                    self.assertEqual(row["status"], "unavailable")
                    self.assertIsNone(row["apparent_angle_deg"])
                    self.assertIsNone(row["uncertainty_deg"])
                    self.assertEqual(row["image_support"], [])
            self.assertEqual(
                result["landmark_assessment"]["table"]["status"],
                "not_assessed",
            )
            self.assertEqual(
                result["projection_suitability"]["status"], "not_assessed"
            )

    def test_line_candidates_are_generic_deterministic_and_clipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._synthetic(Path(temporary))
            a, _, _ = feasibility.analyse_image(path)
            b, _, _ = feasibility.analyse_image(path)
            self.assertEqual(a, b)
            lines = a["image_evidence"]["line_candidates"]
            self.assertLessEqual(len(lines), feasibility.POLICY["max_candidate_lines"])
            w, h = a["source"]["width_px"], a["source"]["height_px"]
            for line in lines:
                self.assertIsNone(line["facet_identity"])
                self.assertEqual(line["status"], "candidate_only")
                self.assertGreater(line["vote_strength"], 0)
                for x, y in line["endpoints_xy_px"]:
                    self.assertGreaterEqual(x, 0)
                    self.assertLess(x, w)
                    self.assertGreaterEqual(y, 0)
                    self.assertLess(y, h)

    def test_blank_image_fails_closed_without_inventing_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "blank.png"
            Image.fromarray(
                np.full((100, 120, 3), 190, dtype=np.uint8)
            ).save(path)
            result, _, _ = feasibility.analyse_image(path)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["image_evidence"]["line_candidates"], [])
            self.assertIsNone(
                result["image_evidence"]["activity_bbox_xyxy_px"]
            )

    def test_hash_guard_rejects_modified_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._synthetic(Path(temporary))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                feasibility.analyse_image(
                    path, expected_sha256=feasibility.ORIGINAL_PROFILE_SHA256
                )

    def test_output_is_self_contained_and_target_blind(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image = self._synthetic(folder)
            # Only the synthetic image exists here: no expert-target JSON file.
            out = folder / "output"
            result = feasibility.write_diagnostics(image, out)
            self.assertEqual(
                sorted(p.name for p in out.iterdir()),
                [
                    "gradient-evidence.png",
                    "profile-feasibility.json",
                    "unassigned-line-candidates.png",
                ],
            )
            self.assertEqual(
                json.loads((out / "profile-feasibility.json").read_text()),
                result,
            )

    def test_archived_profile_original_is_pinned_without_angle_targets(self):
        self.assertTrue(FIXTURE.is_file())
        self.assertEqual(
            feasibility._hash_file(FIXTURE),
            feasibility.ORIGINAL_PROFILE_SHA256,
        )
        result, _, _ = feasibility.analyse_image(
            FIXTURE, expected_sha256=feasibility.ORIGINAL_PROFILE_SHA256
        )
        self.assertEqual(
            (result["source"]["width_px"], result["source"]["height_px"]),
            feasibility.ORIGINAL_PROFILE_SIZE,
        )
        self.assertTrue(result["source"]["archived_original_match"])
        # This test deliberately does not impose any minimum line count,
        # angle agreement or labeled landmark requirement on the real photo.
        self.assertIn(result["status"], {"review", "unavailable"})
        self.assertTrue(all(
            row["status"] == "unavailable"
            for side in result["semantic_measurements"].values()
            for row in side.values()
        ))


if __name__ == "__main__":
    unittest.main()
