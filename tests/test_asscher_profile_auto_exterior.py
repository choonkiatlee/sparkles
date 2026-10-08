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
            ys = [p["xy_px"][1] for p in points]
            self.assertEqual(ys, sorted(set(ys)))
            self.assertTrue(all(
                0 <= p["xy_px"][0] < 410 and 0 <= p["xy_px"][1] < 319
                for p in points
            ))
            self.assertEqual(row["named_facet_angles"], "unavailable")
            self.assertTrue(
                all(run["status"] == "exploratory_contiguous_image_slope_only"
                    for run in row["supported_runs"])
            )


if __name__ == "__main__":
    unittest.main()
