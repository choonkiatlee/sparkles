import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import activation_benchmark as ab
from diamond360 import asscher_steps as steps
from diamond360 import regions
from diamond360 import tier_contrast_benchmark as tb


def _cell(values, validity=None):
    return {
        "relative_values": values,
        "relative_validity": validity or {"status": "ok", "reasons": []},
        "persistent_support_fraction": 1.0,
    }


def activation_fixture():
    indices = [254, 255, 0, 1]
    cells = {
        "centre": [0.0, 0.1, 0.2, 0.3],
        "inner": [0.1, 0.1, 0.3, 0.0],
        "middle": [0.4, 0.2, 0.1, 0.1],
    }
    return {
        "schema_version": ab.SCHEMA,
        "requested_indices": indices,
        "accepted_indices": indices,
        "excluded": [],
        "wrap_explicit": True,
        "representations": {
            "coarse": {
                "regions": {
                    name: {"fixed": _cell(values)}
                    for name, values in cells.items()
                }
            }
        },
        "frame_rgb_paths": [],
    }


def boundary_local_fixture(root, edge_spike=False):
    processed = root / "processed"
    step_output = root / "steps"
    (processed / "photometry").mkdir(parents=True)
    (processed / "registered").mkdir()
    (processed / "regions").mkdir()
    (step_output / "regions").mkdir(parents=True)

    size = 192
    y, x = np.indices((size, size))
    c = (size - 1) / 2
    dx, dy = np.abs(x - c), np.abs(y - c)
    mask = (np.maximum(dx, dy) <= 78) & ((dx + dy) <= 124)
    u, _ = steps.normalised_radius_map(mask)
    controls = [
        {"sector_u": np.full(8, value)}
        for value in (.50, .75, .87)
    ]
    semantic_masks = steps.build_masks(mask, controls)
    coarse = regions.build(mask)

    records = []
    step_frames = []
    for pos, scale in enumerate((1.0, 1.7, 2.6)):
        brightness = np.where(
            u < .50, 1.0,
            np.where(u < .75, .5, np.where(u < .87, .8, .6)),
        ) * scale
        brightness[~mask] = np.nan
        if edge_spike:
            brightness[mask & (np.abs(u - .50) < .004)] = 20.0 * scale
        valid = mask.copy()
        np.savez_compressed(
            processed / "photometry" / f"{pos:04d}.npz",
            encoded_brightness=brightness,
            valid_mask=valid,
        )
        Image.fromarray((mask.astype(np.uint8) * 255)).save(
            processed / "registered" / f"{pos:04d}-mask.png"
        )
        rgb = np.zeros((size, size, 3), np.uint8)
        Image.fromarray(rgb).save(processed / "registered" / f"{pos:04d}.png")
        np.savez_compressed(
            processed / "regions" / f"{pos:04d}.npz",
            **coarse,
        )
        np.savez_compressed(
            step_output / "regions" / f"{pos:04d}.npz",
            **semantic_masks,
        )
        records.append({
            "position": pos,
            "source_index": pos,
            "sha256": f"{pos + 1:064x}",
            "photometry_path": f"photometry/{pos:04d}.npz",
            "regions_path": f"regions/{pos:04d}.npz",
            "registration": {
                "mask_path": f"registered/{pos:04d}-mask.png",
                "rgb_path": f"registered/{pos:04d}.png",
            },
        })
        step_frames.append({
            "source_index": pos,
            "position": pos,
            "status": "ok",
            "region_path": f"regions/{pos:04d}.npz",
            "boundary_support": [],
        })

    (processed / "sequence.json").write_text(json.dumps({
        "source_frame_count": 3,
        "frames": records,
    }))
    (step_output / "steps.json").write_text(json.dumps({
        "template_status": "ok",
        "template_reason": None,
        "boundaries": {
            name: {"sector_u": [float(v) for v in control["sector_u"]]}
            for name, control in zip(steps.BOUNDARIES, controls)
        },
        "frames": step_frames,
    }))
    activation_result = {
        "requested_indices": [0, 1, 2],
        "wrap_explicit": False,
        "upstream_validity": {"status": "ok", "reasons": []},
    }
    return processed, step_output, activation_result

class TierContrastBenchmarkTests(unittest.TestCase):
    def test_strip_trace_follows_fixed_normalised_geometry_without_pixel_intersection(self):
        brightness = np.stack([
            np.full((5, 5), 1.0),
            np.full((5, 5), 2.0),
            np.full((5, 5), 3.0),
        ])
        valid = np.ones_like(brightness, dtype=bool)
        masks = np.zeros_like(brightness, dtype=bool)
        masks[0, 1, 1] = True
        masks[1, 2, 2] = True
        masks[2, 3, 3] = True
        values, support = tb._strip_trace(
            brightness, valid, masks, np.array([True, True, True])
        )
        self.assertEqual(values, [1.0, 2.0, 3.0])
        self.assertEqual(support["min_support_pixels"], 1)
        self.assertEqual(
            support["support_mode"],
            "per_frame_valid_with_fixed_normalised_geometry",
        )
    def test_boundary_local_semantic_strips_recover_known_tier_jump(self):
        with tempfile.TemporaryDirectory() as td:
            processed, step_output, activation_result = boundary_local_fixture(Path(td))
            result = tb._boundary_local_inputs(
                processed, step_output, activation_result, widths=(.04,), guard=.01
            )
            pair = result["pairs"]["centre__inner"]["widths"]["0.040"]
            semantic = pair["semantic"]
            coarse = pair["coarse"]
            self.assertEqual(semantic["validity"]["status"], "ok")
            self.assertAlmostEqual(
                semantic["median_summary"]["q50"], math.log(2.0), delta=.03
            )
            self.assertLess(coarse["median_summary"]["q50"], .03)
            signed = semantic["frame_trace"][0]["sector_signed_log_contrasts"]
            self.assertTrue(all(value > 0 for value in signed.values() if value is not None))

    def test_guarded_strips_ignore_narrow_boundary_spike(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "base"
            spike = root / "spike"
            p1, s1, a1 = boundary_local_fixture(base, edge_spike=False)
            p2, s2, a2 = boundary_local_fixture(spike, edge_spike=True)
            first = tb._boundary_local_inputs(
                p1, s1, a1, widths=(.04,), guard=.01
            )["pairs"]["centre__inner"]["widths"]["0.040"]["semantic"]
            second = tb._boundary_local_inputs(
                p2, s2, a2, widths=(.04,), guard=.01
            )["pairs"]["centre__inner"]["widths"]["0.040"]["semantic"]
            self.assertAlmostEqual(
                first["median_summary"]["q50"],
                second["median_summary"]["q50"],
                places=10,
            )
    def test_consumes_only_retained_coarse_fixed_pairs(self):
        result = tb.measure_from_activation(activation_fixture())
        self.assertEqual(
            set(result["pairs"]),
            {"centre__inner", "inner__middle"},
        )
        pair = result["pairs"]["centre__inner"]
        self.assertEqual(pair["representation"], "coarse")
        self.assertEqual(pair["support_mode"], "fixed")
        self.assertTrue(pair["primary"])

    def test_simple_candidate_works_without_pixel_spread(self):
        result = tb.measure_from_activation(activation_fixture())
        pair = result["pairs"]["centre__inner"]
        self.assertEqual(pair["simple"]["validity"]["status"], "ok")
        self.assertEqual(
            pair["standardized"]["validity"]["status"],
            "unavailable",
        )
        self.assertIn(
            "standardized_spread_unavailable",
            pair["standardized"]["validity"]["reasons"],
        )

    def test_standardized_challenger_is_optional_and_aligned(self):
        spreads = {
            "centre": [0.1, 0.1, 0.1, 0.1],
            "inner": [0.2, 0.2, 0.2, 0.2],
            "middle": [0.3, 0.3, 0.3, 0.3],
        }
        result = tb.measure_from_activation(
            activation_fixture(),
            spreads,
        )
        pair = result["pairs"]["inner__middle"]
        self.assertEqual(
            pair["standardized"]["validity"]["status"],
            "ok",
        )
        self.assertEqual(
            len(pair["standardized"]["frame_trace"]),
            4,
        )
        self.assertIsNotNone(
            pair["evidence"]["strongest_formulation_disagreement"]
        )

    def test_localized_sector_challenger_is_optional_and_aligned(self):
        localized = {
            band: {
                "side_E": values,
                "side_W": list(reversed(values)),
            }
            for band, values in {
                "centre": [1.0, 1.1, 1.2, 1.3],
                "inner": [1.3, 1.2, 1.1, 1.0],
                "middle": [0.9, 1.0, 1.1, 1.2],
            }.items()
        }
        support = {
            band: {"side_E": 12, "side_W": 11}
            for band in localized
        }
        result = tb.measure_from_activation(
            activation_fixture(),
            localized_band_values=localized,
            localized_support_pixels=support,
        )
        pair = result["pairs"]["centre__inner"]["localized"]
        self.assertEqual(pair["validity"]["status"], "ok")
        self.assertEqual(pair["sectors"], ["side_E", "side_W"])
        self.assertEqual(pair["support_pixels"]["left"]["side_E"], 12)
        self.assertIsNotNone(pair["median_summary"]["q50"])
        self.assertIsNotNone(pair["evidence"]["strongest"])

    def test_localized_sector_challenger_is_unavailable_without_raw_pixels(self):
        result = tb.measure_from_activation(activation_fixture())
        self.assertEqual(
            result["pairs"]["centre__inner"]["localized"]["status"],
            "unavailable",
        )

    def test_upstream_review_propagates_without_upgrade(self):
        fixture = activation_fixture()
        fixture["representations"]["coarse"]["regions"]["inner"]["fixed"][
            "relative_validity"
        ] = {
            "status": "review",
            "reasons": ["segmentation_review"],
        }
        result = tb.measure_from_activation(fixture)
        for pair_id in ("centre__inner", "inner__middle"):
            self.assertEqual(
                result["pairs"][pair_id]["simple"]["validity"]["status"],
                "review",
            )
            self.assertIn(
                "segmentation_review",
                result["pairs"][pair_id]["simple"]["validity"]["reasons"],
            )

    def test_writer_is_json_safe(self):
        result = tb.measure_from_activation(activation_fixture())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            tb.write_stone_outputs(result, out)
            payload = json.loads(
                (out / "tier-contrast.json").read_text()
            )
            self.assertEqual(payload["schema_version"], tb.SCHEMA)
            self.assertTrue((out / "tier-contrast.csv").exists())


    def test_committed_region_trace_reconstruction_matches_log_ratio(self):
        trace = {
            "schema_version": tb.REGION_TRACE_SCHEMA,
            "requested_indices": [0, 1, 2],
            "accepted_indices": [0, 1, 2],
            "excluded": [],
            "wrap_explicit": False,
            "regions": {
                "centre": {"median_brightness": [4.0, 8.0, 16.0]},
                "inner": {"median_brightness": [2.0, 4.0, 8.0]},
                "middle": {"median_brightness": [1.0, 8.0, 4.0]},
            },
        }
        result = tb.measure_primary_from_region_trace(trace)
        centre_inner = result["pairs"]["centre__inner"]["simple"]
        self.assertTrue(
            all(abs(value - 0.6931471805599453) < 1e-12
                for value in centre_inner["separation_values"])
        )
        self.assertEqual(
            result["reconstruction_source_schema"],
            tb.REGION_TRACE_SCHEMA,
        )

    def test_rejects_wrong_activation_schema(self):
        fixture = activation_fixture()
        fixture["schema_version"] = "other/1"
        with self.assertRaises(ValueError):
            tb.measure_from_activation(fixture)


class CommittedTierContrastArtifactTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_primary_summary_reconstructs_from_committed_region_traces(self):
        summary_path = self.ROOT / "docs" / "360" / "tier-contrast" / "summary.json"
        summary = json.loads(summary_path.read_text())
        self.assertEqual(
            summary["schema_version"],
            "diamond360-tier-contrast-primary-benchmark/1",
        )
        self.assertEqual(summary["provisional_disposition"], "REVISE")
        self.assertEqual(len(summary["rows"]), 16)

        for row in summary["rows"]:
            trace_path = self.ROOT / row["source_trace"]
            trace = json.loads(trace_path.read_text())
            rebuilt = tb.measure_primary_from_region_trace(trace)
            simple = rebuilt["pairs"][row["pair"]]["simple"]
            self.assertAlmostEqual(simple["summary"]["q10"], row["q10"])
            self.assertAlmostEqual(simple["summary"]["q50"], row["q50"])
            self.assertAlmostEqual(simple["summary"]["q90"], row["q90"])
            evidence = rebuilt["pairs"][row["pair"]]["evidence"]
            self.assertIn(row["status"], {"ok", "review", "unavailable"})
            self.assertIsInstance(row["reasons"], list)
            self.assertEqual(
                evidence["weakest"]["source_index"],
                row["weakest"]["source_index"],
            )
            self.assertEqual(
                evidence["strongest"]["source_index"],
                row["strongest"]["source_index"],
            )

    def test_summary_preserves_window_sensitivity_warning(self):
        summary = json.loads(
            (self.ROOT / "docs" / "360" / "tier-contrast" / "summary.json").read_text()
        )
        sensitivity = summary["core_wide_sensitivity"]
        self.assertEqual(
            sensitivity["centre__inner"]["q10"]["core_wide_rank_spearman"],
            0.0,
        )
        self.assertEqual(
            sensitivity["inner__middle"]["q50"]["core_wide_rank_spearman"],
            0.0,
        )
        self.assertEqual(
            sensitivity["centre__inner"]["q90"]["core_wide_rank_spearman"],
            0.8,
        )
        self.assertEqual(
            sensitivity["inner__middle"]["q90"]["core_wide_rank_spearman"],
            0.8,
        )


if __name__ == "__main__":
    unittest.main()
