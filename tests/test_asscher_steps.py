import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import asscher_steps as s


def synthetic_sector_frames(boundaries=(.50, .75, .87), frames=9, samples=160):
    u = np.linspace(0, 1, samples)
    sector_frames = []
    for frame in range(frames):
        sectors = []
        for sector in range(8):
            offsets = np.array([-.006, .004, -.003]) * np.cos(sector * np.pi / 2)
            cuts = np.array(boundaries) + offsets
            levels = np.array([.75, 1.15, .72, 1.05])
            if frame % 2:
                levels = levels[[1, 0, 3, 2]]
            profile = np.zeros(samples)
            edges = np.r_[0, np.searchsorted(u, cuts), samples]
            for j in range(4):
                profile[edges[j]:edges[j+1]] = levels[j] + .03 * np.sin((frame + 1) * (j + 1))
            profile += .01 * np.sin(np.arange(samples) * .41 + sector)
            smooth = np.convolve(profile, np.ones(3) / 3, mode="same")
            evidence = np.abs(np.gradient(smooth))
            sectors.append(evidence)
        sector_frames.append(sectors)
    return u, np.asarray(sector_frames)


def octagon_mask(size=128):
    y, x = np.indices((size, size))
    c = (size - 1) / 2
    dx, dy = np.abs(x - c), np.abs(y - c)
    return (np.maximum(dx, dy) <= size * .38) & ((dx + dy) <= size * .62)


class AsscherStepTests(unittest.TestCase):
    def test_discovers_three_ordered_persistent_boundaries(self):
        u, frames = synthetic_sector_frames()
        result = s.discover_template(frames, u)
        self.assertIn(result["status"], {"ok", "review"})
        found = [c["global_u"] for c in result["controls"]]
        for got, expected in zip(found, (.50, .75, .87)):
            self.assertAlmostEqual(got, expected, delta=.035)
        for sector in range(8):
            vals = [c["sector_u"][sector] for c in result["controls"]]
            self.assertTrue(np.all(np.diff(vals) > .07))
        alignment = s.boundary_alignment(frames, u, result["controls"])
        self.assertTrue(all(row["edge_ratio"] > 1 for row in alignment))

    def test_stronger_inner_reflection_does_not_steal_semantic_boundary(self):
        u, frames = synthetic_sector_frames()
        distractor = np.exp(-0.5 * ((u - .245) / .012) ** 2) * .12
        frames = frames + distractor[None, None, :]
        result = s.discover_template(frames, u)
        self.assertIn(result["status"], {"ok", "review"})
        found = [c["global_u"] for c in result["controls"]]
        self.assertAlmostEqual(found[0], .50, delta=.04)
        self.assertGreater(found[0], .42)
        self.assertAlmostEqual(found[1], .75, delta=.04)
        self.assertAlmostEqual(found[2], .87, delta=.04)

    def test_semantic_window_edge_downgrades_template_without_moving_prior(self):
        u, frames = synthetic_sector_frames(boundaries=(.60, .75, .87))
        result = s.discover_template(frames, u)
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["reason"], "semantic_window_edge")
        first = result["controls"][0]
        self.assertEqual(first["semantic_window"], (.42, .60))
        self.assertAlmostEqual(first["window_margin"],
                               min(first["global_u"] - .42, .60 - first["global_u"]))
        self.assertLessEqual(first["window_margin_samples"], 1)
        self.assertTrue(first["near_window_edge"])
        encoded = s._json_control(first)
        self.assertEqual(encoded["window_margin"], first["window_margin"])
        self.assertTrue(encoded["near_window_edge"])

    def test_masks_partition_silhouette_and_allow_side_corner_shape(self):
        mask = octagon_mask()
        controls = []
        for base in (.50, .75, .87):
            vals = np.array([base-.015, base+.012, base-.015, base+.012,
                             base-.015, base+.012, base-.015, base+.012])
            controls.append(dict(sector_u=vals))
        regions = s.build_masks(mask, controls)
        self.assertEqual(set(regions), set(s.BANDS))
        total = sum(r.astype(np.uint8) for r in regions.values())
        self.assertTrue(np.all(total[mask] == 1))
        self.assertTrue(np.all(total[~mask] == 0))
        self.assertGreater(regions["outer_step"].sum(), 0)

    def test_boundary_strip_masks_are_disjoint_and_respect_guard(self):
        mask = octagon_mask()
        controls = np.full(8, .60)
        strips = s.boundary_strip_masks(mask, controls, width=.05, guard=.02)
        self.assertFalse(np.any(strips["inside"] & strips["outside"]))
        self.assertGreater(strips["inside"].sum(), 0)
        self.assertGreater(strips["outside"].sum(), 0)

        u, _ = s.normalised_radius_map(mask)
        self.assertLess(float(np.max(u[strips["inside"]])), .60 - .02 + .01)
        self.assertGreater(float(np.min(u[strips["outside"]])), .60 + .02 - .01)

    def test_boundary_strip_masks_can_be_clipped_to_one_sector(self):
        mask = octagon_mask()
        controls = np.full(8, .60)
        _, theta = s.normalised_radius_map(mask)
        east = mask & ((theta < np.pi / 8) | (theta >= 15 * np.pi / 8))
        strips = s.boundary_strip_masks(
            mask, controls, width=.04, guard=.01, sector_mask=east
        )
        self.assertTrue(np.all(~strips["inside"] | east))
        self.assertTrue(np.all(~strips["outside"] | east))

    def test_boundary_strip_masks_reject_invalid_geometry(self):
        mask = octagon_mask()
        with self.assertRaises(ValueError):
            s.boundary_strip_masks(mask, np.full(8, .60), width=0)
        with self.assertRaises(ValueError):
            s.boundary_strip_masks(mask, np.full(7, .60), width=.04)
    def test_relative_boundary_strip_masks_follow_adjacent_tier_spans(self):
        mask = octagon_mask()
        inner = np.full(8, .40)
        boundary = np.full(8, .60)
        outer = np.full(8, .90)
        strips = s.relative_boundary_strip_masks(
            mask, inner, boundary, outer, fraction=.5, guard=.01
        )
        self.assertFalse(np.any(strips["inside"] & strips["outside"]))
        self.assertGreater(strips["inside"].sum(), 0)
        self.assertGreater(strips["outside"].sum(), 0)
        self.assertAlmostEqual(
            float(np.median(strips["inside_width_u"][mask])), .10, places=6
        )
        self.assertAlmostEqual(
            float(np.median(strips["outside_width_u"][mask])), .15, places=6
        )

    def test_relative_boundary_strip_masks_reject_unordered_controls(self):
        mask = octagon_mask()
        with self.assertRaises(ValueError):
            s.relative_boundary_strip_masks(
                mask,
                np.full(8, .70),
                np.full(8, .60),
                np.full(8, .90),
                fraction=.4,
            )

    def test_missing_outer_edge_preserves_supported_inner_boundaries(self):
        u = np.linspace(0, 1, 160)
        profile = (
            np.exp(-0.5 * ((u - .50) / .012) ** 2)
            + .8 * np.exp(-0.5 * ((u - .75) / .012) ** 2)
        )
        profile[u >= .82] = 0.0
        frames = np.stack([
            np.stack([profile * (1 + .01 * frame + .005 * sector)
                      for sector in range(8)])
            for frame in range(6)
        ])
        result = s.discover_template(frames, u)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "no_supported_middle_outer_edge")
        self.assertEqual(
            set(result["partial_controls"]),
            {"centre_inner", "inner_middle"},
        )
        self.assertAlmostEqual(
            result["partial_controls"]["centre_inner"]["global_u"],
            .50, delta=.03,
        )
        self.assertAlmostEqual(
            result["partial_controls"]["inner_middle"]["global_u"],
            .75, delta=.03,
        )
    def test_flat_evidence_surfaces_failure(self):
        u = np.linspace(0, 1, 160)
        result = s.discover_template(np.zeros((5, 8, len(u))), u)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNotNone(result["reason"])

    def test_end_to_end_writes_masks_and_qc(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = root / "processed"
            output = root / "steps"
            (processed / "diamond").mkdir(parents=True)
            (processed / "photometry").mkdir()
            mask = octagon_mask(128)
            y, x = np.indices(mask.shape)
            c = 63.5
            rr = np.maximum(np.abs(x-c), np.abs(y-c)) / (128*.38)
            records = []
            for pos in range(7):
                brightness = np.where(rr < .50, .65,
                                      np.where(rr < .75, 1.0,
                                               np.where(rr < .87, .58, .92)))
                if pos % 2:
                    brightness = 1.2 - .45 * brightness
                brightness = np.clip(brightness + .015*np.sin(x*.23+pos), 0, 1)
                rgb = np.repeat((brightness[...,None]*255).astype(np.uint8), 3, axis=2)
                rgb[~mask] = 245
                Image.fromarray(rgb).save(processed / "diamond" / f"{pos:04d}.png")
                Image.fromarray(mask.astype(np.uint8)*255).save(processed / "diamond" / f"{pos:04d}-mask.png")
                valid = mask.copy()
                np.savez_compressed(processed / "photometry" / f"{pos:04d}.npz",
                                    encoded_brightness=brightness.astype(np.float32),
                                    valid_mask=valid)
                records.append({
                    "position": pos,
                    "source_index": pos,
                    "sha256": f"{pos:064x}",
                    "photometry_path": f"photometry/{pos:04d}.npz",
                    "registration": {
                        "mask_path": f"diamond/{pos:04d}-mask.png",
                        "rgb_path": f"diamond/{pos:04d}.png",
                    },
                })
            (processed / "sequence.json").write_text(json.dumps({
                "source_frame_count": 7,
                "frames": records,
            }))
            result = s.run(processed, output, list(range(7)))
            self.assertIn(result["template_status"], {"ok", "review"})
            self.assertEqual(set(result["boundaries"]), set(s.BOUNDARIES))
            self.assertTrue((output / "steps.json").exists())
            self.assertTrue((output / "edge-profile.png").exists())
            self.assertTrue((output / "overlays.jpg").exists())
            self.assertEqual(len(list((output / "regions").glob("*.npz"))), 7)
            with np.load(output / "regions" / "0000.npz") as regions:
                total = sum(regions[name].astype(np.uint8) for name in s.BANDS)
                self.assertTrue(np.all(total[mask] == 1))


if __name__ == "__main__":
    unittest.main()
