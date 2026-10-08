"""Adversarial silhouette-first tests for #91 physical/virtual separation."""
from pathlib import Path
import json
import tempfile
import unittest

from PIL import Image, ImageDraw

from diamond360 import asscher_profile_outer_contour as outer
from diamond360 import asscher_profile_feasibility as feasibility

ORIGINAL = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


class OuterContourTests(unittest.TestCase):
    def synthetic(self, directory, virtual=False, occluded=False, tilted=False):
        width, height = 320, 260
        image = Image.new("RGB", (width, height), (210, 211, 211))
        draw = ImageDraw.Draw(image)
        # Fixed exterior contour, including a thin darker outline.
        shape = [(152, 35), (168, 35), (226, 100), (280, 166),
                 (235, 184), (160, 238), (85, 184), (40, 166),
                 (94, 100)]
        if tilted:
            shape = [(x + int((y - 120)*0.28), y) for x, y in shape]
        draw.polygon(shape, fill=(170, 174, 178), outline=(75, 77, 79), width=3)
        if virtual:
            # Appearance changes only. Do not touch the object exterior.
            draw.rectangle((105, 90, 214, 155), fill=(247, 246, 245))
            for y in (96, 111, 123, 141, 156, 172, 193):
                draw.line((104, y, 213, y), fill=(37, 40, 39), width=2)
            draw.line((118, 112, 200, 176), fill=(30, 30, 30), width=2)
        if occluded:
            # Deliberately erase a piece of the exterior so the support
            # should not be advertised as anatomically confirmed.
            draw.rectangle((260, 140, 294, 177), fill=(210, 211, 211))
        path = directory / ("variant%d%d%d.png" % (virtual, occluded, tilted))
        image.save(path)
        return path

    def test_internal_virtual_stripes_do_not_move_contour_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain, _ = outer.analyse_image(self.synthetic(root, virtual=False))
            striped, _ = outer.analyse_image(self.synthetic(root, virtual=True))
            self.assertEqual(plain["status"], "review")
            self.assertEqual(striped["status"], "review")
            pa = {r["y_px"]: r for r in plain["outer_rows"]
                  if r["status"] == "supported_candidate"}
            pb = {r["y_px"]: r for r in striped["outer_rows"]
                  if r["status"] == "supported_candidate"}
            common = set(pa) & set(pb)
            self.assertGreater(len(common), 70)
            self.assertLessEqual(
                max(
                    abs(pa[y]["left_x_px"] - pb[y]["left_x_px"])
                    for y in common
                ), 2,
            )
            self.assertLessEqual(
                max(
                    abs(pa[y]["right_x_px"] - pb[y]["right_x_px"])
                    for y in common
                ), 2,
            )
            for record in (plain, striped):
                self.assertEqual(
                    record["physical_landmark_status"]["girdle"]["status"],
                    "unavailable"
                )
                self.assertFalse(record["projection_suitability"]["table_reference_calibrated"])
                for side in record["semantic_measurements"].values():
                    self.assertTrue(all(
                        facet["status"] == "unavailable"
                        and facet["physical_angle_deg"] is None
                        for facet in side.values()
                    ))

    def test_blank_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            file = folder / "empty.png"
            Image.new("RGB", (320, 260), (210, 210, 210)).save(file)
            record, _ = outer.analyse_image(file)
            self.assertEqual(record["status"], "unavailable")
            self.assertEqual(record["qc"]["supported_row_count"], 0)
            self.assertTrue(all(
                v["status"] == "unavailable"
                for v in record["anatomical_candidates"].values()
            ))

    def test_tilt_or_occlusion_never_confirms_physical_angles(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for tilted, occluded in ((False, True), (True, False)):
                payload, _ = outer.analyse_image(self.synthetic(
                    folder, tilted=tilted, occluded=occluded
                ))
                self.assertIn(payload["status"], ("review", "unavailable"))
                self.assertEqual(payload["projection_suitability"]["status"], "not_assessed")
                self.assertTrue(all(
                    facet["physical_angle_deg"] is None
                    for side in payload["semantic_measurements"].values()
                    for facet in side.values()
                ))

    def test_hash_and_json_overlay_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            file = self.synthetic(folder)
            a = outer.write_qc(file, folder / "first")
            b = outer.write_qc(file, folder / "second")
            self.assertEqual(a, b)
            self.assertEqual(
                json.loads((folder / "first" / "outer-contour.json").read_text()),
                a,
            )
            self.assertTrue((folder / "first" / "outer-contour-candidates.png").is_file())
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                outer.analyse_image(file, feasibility.ORIGINAL_PROFILE_SHA256)

    def test_original_photo_is_pinned_and_does_not_use_semantic_edges(self):
        self.assertTrue(ORIGINAL.is_file())
        payload, _ = outer.analyse_image(
            ORIGINAL, feasibility.ORIGINAL_PROFILE_SHA256
        )
        self.assertEqual(payload["schema_version"], outer.SCHEMA)
        self.assertEqual(
            payload["policy_sha256"],
            feasibility.canonical_sha256(outer.POLICY)
        )
        self.assertTrue(payload["source"]["original_verified"])
        self.assertIn(payload["status"], ("review", "unavailable"))
        self.assertFalse(any(
            "facet" in row for row in payload["outer_rows"]
        ))
        self.assertTrue(all(
            v["status"] == "unavailable"
            for v in payload["physical_landmark_status"].values()
        ))


if __name__ == "__main__":
    unittest.main()
