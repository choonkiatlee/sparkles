"""#91 exterior-only step-change detector: no internal virtual facets or target angles."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from diamond360 import asscher_profile_outline_changepoints as cp
from diamond360 import asscher_profile_feasibility as feasibility

PROFILE = (
    Path(__file__).resolve().parents[1]
    / "docs/360/geometry-ground-truth/diagem-2008-asscher/profile-photo.JPG"
)


def stroke(slopes, n_each=20, left=True, noise=0.15):
    """Piecewise contour with real change points, not a facet-angle target."""
    y = 65.0
    x = 65.0 if left else 350.0
    points = []
    for slope in slopes:
        for i in range(n_each):
            points.append([
                round(x + noise * math.sin(0.7 * len(points)), 4),
                round(y, 4),
            ])
            x += slope * 3
            y += 3
    return points


def record(points, key="left_pavilion"):
    r = cp.template()
    r["strokes"][key] = {
        "status": "reviewed_image_only",
        "provenance": "human_traced_image_only",
        "points_xy_px": points,
        "review_notes": "Synthetic annotated external contour, with no optical feature data.",
    }
    return r


class ContourChangepointTests(unittest.TestCase):
    def test_predeclared_one_two_three_segment_synthetic_contours(self):
        cases = [
            ([0.32], 1),
            ([0.12, 1.25], 2),
            ([0.12, 1.2, 0.15], 3),
        ]
        for slopes, expected in cases:
            with self.subTest(slopes=slopes):
                r = cp.analyse_trace_record(record(stroke(slopes)))
                row = r["contours"]["left_pavilion"]
                self.assertEqual(row["status"], "review")
                self.assertEqual(row["selected_segment_count"], expected)
                self.assertEqual(len(row["changepoints"]), expected - 1)
                self.assertTrue(all(s["semantic_facet_id"] is None for s in row["segments"]))
                self.assertTrue(all(
                    f["physical_angle_deg"] is None
                    for family in r["semantic_measurements"].values()
                    for f in family.values()
                ))

    def test_left_right_asymmetry_and_less_than_three_visible_tiers(self):
        r = cp.template()
        r["strokes"]["left_pavilion"] = record(stroke([0.1,1.2]))["strokes"]["left_pavilion"]
        r["strokes"]["right_pavilion"] = record(
            stroke([-0.35], left=False), key="right_pavilion"
        )["strokes"]["right_pavilion"]
        res = cp.analyse_trace_record(r)
        self.assertEqual(res["contours"]["left_pavilion"]["selected_segment_count"], 2)
        self.assertEqual(res["contours"]["right_pavilion"]["selected_segment_count"], 1)
        self.assertEqual(res["contours"]["left_crown"]["status"], "unavailable")
        self.assertFalse(res["comparison_targets_loaded"])

    def test_strong_virtual_stripes_cannot_alter_trace_only_fit(self):
        r = record(stroke([0.1, 1.2, .1]))
        res = cp.analyse_trace_record(r)
        # The trace-input API accepts no image intensity or Hough evidence;
        # a different internal optical scene does not enter the fit.
        self.assertEqual(res, cp.analyse_trace_record(deepcopy(r)))
        self.assertEqual(cp.fit_stroke(r["strokes"]["left_pavilion"]["points_xy_px"]),
                         res["contours"]["left_pavilion"])

    def test_smooth_contour_avoids_inventing_three_segments(self):
        a = stroke([0.45], n_each=50, noise=0.1)
        row = cp.fit_stroke(a)
        self.assertEqual(row["selected_segment_count"], 1)

    def test_missing_trace_stays_unavailable_and_no_angle_fabrication(self):
        result = cp.analyse_trace_record(cp.template())
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(all(r["status"]=="unavailable" for r in result["contours"].values()))
        self.assertTrue(all(
            v["status"] == "unavailable" for group in result["semantic_measurements"].values()
            for v in group.values()
        ))

    def test_rejects_external_targets_missing_source_and_bad_side(self):
        good = record(stroke([0.1, 1.2]))
        variants = [
            ("target_values_loaded", lambda r: r.update(target_values_loaded=True), "comparison"),
            ("source_sha256", lambda r: r.update(source_sha256="other"), "source"),
            ("wrong_side", lambda r: r["strokes"]["left_pavilion"]["points_xy_px"][0].__setitem__(0, 390), "left contour"),
            ("wrong_y", lambda r: r["strokes"]["left_pavilion"]["points_xy_px"][1].__setitem__(1, 60), "increasing"),
        ]
        for name, change, reason in variants:
            with self.subTest(name=name):
                altered = deepcopy(good)
                change(altered)
                with self.assertRaisesRegex(ValueError, reason):
                    cp.analyse_trace_record(altered)

    def test_original_photo_generates_empty_valid_template_and_overlay(self):
        self.assertTrue(PROFILE.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            result = cp.write_result(PROFILE, output)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(
                json.loads((output / "exterior-changepoints.json").read_text()),
                result,
            )
            self.assertTrue((output / "exterior-changepoints-overlay.png").is_file())
            self.assertEqual(json.loads((output / "exterior-trace-template.json").read_text()),
                             cp.template())


if __name__ == "__main__":
    unittest.main()
