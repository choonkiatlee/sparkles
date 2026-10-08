"""Auto-traced outer shape may not be mistaken for verified physical facets."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from diamond360 import asscher_profile_auto_exterior as auto
from diamond360 import asscher_profile_feasibility as feasibility

ORIGINAL = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


def synthetic(with_internal_bands=False, blank=False):
    image = Image.new("RGB", (410, 319), (208, 207, 209))
    if blank:
        return np.asarray(image, dtype=np.uint8)
    d = ImageDraw.Draw(image)
    d.polygon([
        (205, 60), (241, 85), (306, 146), (367, 212),
        (340, 229), (296, 251), (230, 285), (183, 285),
        (117, 251), (72, 229), (42, 212), (104, 146),
        (168, 85),
    ], fill=(248, 244, 249), outline=(65, 69, 75), width=2)
    if with_internal_bands:
        # Entirely inside the external polygon. The side/background edge
        # is pixel-for-pixel unchanged; stripes are virtual-like distractions.
        for y in range(110, 200, 9):
            d.line((165, y, 245, y), fill=(32, 37, 41), width=3)
        d.line((174, 140, 227, 182), fill=(20, 25, 31), width=2)
    return np.asarray(image, dtype=np.uint8)


class AutoExteriorTests(unittest.TestCase):
    def test_internal_optical_lines_do_not_move_external_path(self):
        a = auto.analyse_array(synthetic(False))
        b = auto.analyse_array(synthetic(True))
        self.assertEqual(a["policy_sha256"], b["policy_sha256"])
        for key in a["paths"]:
            ax = [p["xy_px"] for p in a["paths"][key]["points"]]
            bx = [p["xy_px"] for p in b["paths"][key]["points"]]
            self.assertEqual(ax, bx, key)
            self.assertTrue(all(
                r["physical_facet_correspondence"] == "not_established"
                for r in [a["paths"][key], b["paths"][key]]
            ))
            for path in (a["paths"][key], b["paths"][key]):
                for run in path["supported_runs"]:
                    for segment in run["fitted"]["segments"]:
                        self.assertIsNone(segment["semantic_facet_id"])

    def test_weaker_exterior_beats_brighter_internal_virtual_band(self):
        """A faint real silhouette must win over a brilliant internal face."""
        image = Image.new("RGB", (410, 319), (207, 207, 209))
        d = ImageDraw.Draw(image)
        shape = [(205, 60), (242, 84), (311, 143), (368, 212),
                 (337, 229), (281, 271), (204, 287),
                 (129, 271), (75, 229), (42, 212),
                 (99, 143), (168, 84)]
        # Deliberately weak exterior/flat fill; bright central virtual face
        # is much higher contrast but does not touch the outside boundary.
        d.polygon(shape, fill=(201, 202, 202))
        baseline = auto.analyse_array(np.asarray(image, dtype=np.uint8))
        d.polygon([(183, 80), (225, 80), (255, 183), (153, 183)],
                  fill=(250, 250, 251), outline=(18, 18, 18))
        with_virtual_face = auto.analyse_array(np.asarray(image, dtype=np.uint8))
        for name in baseline["paths"]:
            before = [p["xy_px"] for p in baseline["paths"][name]["points"]]
            after = [p["xy_px"] for p in with_virtual_face["paths"][name]["points"]]
            paired = [(a, b) for a, b in zip(before, after) if a is not None and b is not None]
            self.assertGreater(len(paired), 40, name)
            self.assertLessEqual(
                max(abs(a[0] - b[0]) for a, b in paired), 5,
                "faint exterior must not jump inward to brilliant virtual face"
            )
            self.assertTrue(all(
                p["support"] != "edge_supported_candidate"
                or p["xy_px"] is not None
                for p in with_virtual_face["paths"][name]["points"]
            ))

    def test_actual_photo_chooses_outer_crown_not_bright_internal_table(self):
        record, = (auto.write_qc(
            ORIGINAL, Path(tempfile.mkdtemp()),
            feasibility.ORIGINAL_PROFILE_SHA256
        ),)
        left = {p["xy_px"][1]: p for p in record["paths"]["left_crown"]["points"]
                if p["xy_px"] is not None}
        right = {p["xy_px"][1]: p for p in record["paths"]["right_crown"]["points"]
                 if p["xy_px"] is not None}
        # Image-only silhouette sanity ranges, not Sergey angle targets:
        # the brightest central face would put x much closer to the center.
        self.assertLess(left[100]["xy_px"][0], 150)
        self.assertGreater(right[100]["xy_px"][0], 260)
        self.assertLess(left[160]["xy_px"][0], 110)
        self.assertGreater(right[160]["xy_px"][0], 300)

    def test_blank_source_does_not_become_a_supported_diamond(self):
        result = auto.analyse_array(synthetic(blank=True))
        self.assertEqual(result["status"], "partial_or_unavailable")
        for row in result["paths"].values():
            self.assertEqual(row["status"], "unavailable")
            self.assertEqual(row["supported_fraction"], 0)
            self.assertEqual(row["supported_runs"], [])
            self.assertTrue(all(
                point["support"] == "weak_or_ambiguous"
                for point in row["points"]
            ))

    def test_original_source_fits_only_candidate_outline_and_records_weak_regions(self):
        self.assertTrue(ORIGINAL.is_file())
        with tempfile.TemporaryDirectory() as temp:
            record = auto.write_qc(
                ORIGINAL, Path(temp), feasibility.ORIGINAL_PROFILE_SHA256
            )
            self.assertTrue(record["original_verified"])
            self.assertEqual(record["source_sha256"], feasibility.ORIGINAL_PROFILE_SHA256)
            self.assertGreater(record["paths"]["left_crown"]["supported_fraction"], 0.5)
            self.assertGreater(record["paths"]["right_crown"]["supported_fraction"], 0.5)
            self.assertTrue(any(
                point["support"] == "weak_or_ambiguous"
                for row in record["paths"].values()
                for point in row["points"]
            ))
            self.assertEqual(json.loads(
                (Path(temp) / "auto-exterior.json").read_text()
            ), record)
            self.assertTrue((Path(temp) / "auto-exterior-overlay.png").is_file())
            for side in record["semantic_measurements"].values():
                self.assertTrue(all(
                    value["status"] == "unavailable"
                    and value["physical_angle_deg"] is None
                    for value in side.values()
                ))
            self.assertFalse(record["comparison_targets_loaded"])

    def test_source_mismatch_and_wrong_shape_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            synthetic_file = Path(temp) / "synthetic.png"
            Image.fromarray(synthetic()).save(synthetic_file)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                auto.write_qc(synthetic_file, temp, feasibility.ORIGINAL_PROFILE_SHA256)
        with self.assertRaisesRegex(ValueError, "source too small"):
            auto.analyse_array(np.full((80, 80, 3), 212, dtype=np.uint8))

    def test_contour_proposals_are_bounded_and_monotonic_not_physical_angles(self):
        result = auto.analyse_array(synthetic())
        self.assertEqual(result["schema_version"], auto.SCHEMA)
        self.assertEqual(len(result["paths"]), 4)
        for name, row in result["paths"].items():
            points = row["points"]
            ys = [p["xy_px"][1] for p in points if p["xy_px"] is not None]
            self.assertEqual(ys, sorted(set(ys)))
            self.assertTrue(all(
                0 <= p["xy_px"][0] < 410 and 0 <= p["xy_px"][1] < 319
                for p in points if p["xy_px"] is not None
            ))
            self.assertTrue(all(
                p["support"] == "weak_or_ambiguous"
                for p in points if p["xy_px"] is None
            ))
            self.assertEqual(row["named_facet_angles"], "unavailable")
            self.assertTrue(
                all(run["status"] == "exploratory_contiguous_image_slope_only"
                    for run in row["supported_runs"])
            )


if __name__ == "__main__":
    unittest.main()
