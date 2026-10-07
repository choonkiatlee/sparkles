import unittest

import numpy as np

from diamond360 import asscher_topology as topology
from diamond360 import asscher_wireframe as wireframe


def synthetic_evidence(
    *,
    frames=9,
    samples=160,
    boundaries=(0.50, 0.75, 0.87),
    sector_offsets=None,
):
    u = np.linspace(0.0, 1.0, samples)
    data = np.zeros((frames, 8, samples), dtype=float)
    sector_offsets = sector_offsets or {}
    for frame in range(frames):
        for sector in range(8):
            for boundary_index, centre in enumerate(boundaries):
                offset = float(
                    sector_offsets.get((boundary_index, sector), 0.0)
                )
                amplitude = (1.0, 0.88, 0.78)[boundary_index]
                data[frame, sector] += amplitude * np.exp(
                    -0.5 * ((u - (centre + offset)) / 0.009) ** 2
                )
            data[frame, sector] += 0.004 * (
                1.0
                + np.sin(
                    np.arange(samples) * 0.37
                    + frame * 0.41
                    + sector * 0.23
                )
            )
    return u, data


def metadata(count):
    return [
        {
            "source_index": 100 + i,
            "position": i,
            "rotation_phase_deg": float(i) * 1.40625,
        }
        for i in range(count)
    ]


class AsscherWireframeTests(unittest.TestCase):
    def test_emits_valid_fixed_topology_scaffold(self):
        u, data = synthetic_evidence()
        result = wireframe.fit_from_sector_evidence(
            data,
            u,
            gauge_id="stone-A-gauge",
            frame_metadata=metadata(len(data)),
        )
        self.assertIn(result["status"], {"ok", "review"})
        self.assertEqual(
            result["semantic_gauge_id"],
            "stone-A-gauge",
        )
        self.assertTrue(
            topology.validate_scaffold(result["scaffold"])
        )
        self.assertFalse(
            result["scaffold"]["representation_policy"][
                "exclusive_pixel_partition_required"
            ]
        )
        self.assertFalse(
            result["scaffold"]["representation_policy"][
                "direct_projection_claim"
            ]
        )

    def test_crown_boundaries_are_ordered_and_semantically_named(self):
        u, data = synthetic_evidence()
        result = wireframe.fit_from_sector_evidence(
            data, u, gauge_id="g"
        )
        evidence = result["boundary_evidence"]
        self.assertAlmostEqual(
            evidence["C3_TABLE"]["global_u"], 0.50, delta=0.03
        )
        self.assertAlmostEqual(
            evidence["C2_C3"]["global_u"], 0.75, delta=0.03
        )
        self.assertAlmostEqual(
            evidence["C1_C2"]["global_u"], 0.87, delta=0.03
        )
        self.assertLess(
            evidence["C3_TABLE"]["global_u"],
            evidence["C2_C3"]["global_u"],
        )
        self.assertLess(
            evidence["C2_C3"]["global_u"],
            evidence["C1_C2"]["global_u"],
        )

    def test_pavilion_supports_remain_nonexclusive_projection_caveats(self):
        u, data = synthetic_evidence()
        result = wireframe.fit_from_sector_evidence(
            data, u, gauge_id="g"
        )
        supports = [
            row
            for row in result["scaffold"]["semantic_supports"]
            if any(
                semantic_id.startswith(("P1_", "P2_", "P3_"))
                for semantic_id in row["semantic_ids"]
            )
        ]
        self.assertTrue(supports)
        self.assertTrue(
            all(row["direct_projection_claim"] is False for row in supports)
        )
        self.assertTrue(
            result["scaffold"]["representation_policy"][
                "supports_may_overlap"
            ]
        )

    def test_persistent_asymmetry_is_not_regularised_away(self):
        offsets = {
            (0, 6): 0.028,  # raw sector N
            (0, 2): -0.016,  # raw sector S
            (1, 0): 0.018,  # E
            (1, 4): -0.010,  # W
        }
        u, data = synthetic_evidence(sector_offsets=offsets)
        result = wireframe.fit_from_sector_evidence(
            data, u, gauge_id="asymmetric"
        )
        table = result["boundary_evidence"]["C3_TABLE"][
            "sector_u_topology_order"
        ]
        middle = result["boundary_evidence"]["C2_C3"][
            "sector_u_topology_order"
        ]
        self.assertGreater(table[0] - table[4], 0.025)
        self.assertGreater(middle[2] - middle[6], 0.015)

    def test_moving_tonal_edge_does_not_move_canonical_scaffold(self):
        u, baseline = synthetic_evidence(frames=11)
        base = wireframe.fit_from_sector_evidence(
            baseline, u, gauge_id="g"
        )
        perturbed = baseline.copy()
        moving = np.linspace(0.43, 0.59, len(perturbed))
        for frame, centre in enumerate(moving):
            distractor = 2.8 * np.exp(
                -0.5 * ((u - centre) / 0.006) ** 2
            )
            perturbed[frame] += distractor[None, :]
        changed = wireframe.fit_from_sector_evidence(
            perturbed, u, gauge_id="g"
        )
        self.assertIn(changed["status"], {"ok", "review"})
        before = base["boundary_evidence"]["C3_TABLE"]["global_u"]
        after = changed["boundary_evidence"]["C3_TABLE"]["global_u"]
        self.assertAlmostEqual(before, after, delta=0.025)
        self.assertAlmostEqual(after, 0.50, delta=0.035)

    def test_per_frame_evidence_is_relative_to_one_fixed_scaffold(self):
        u, data = synthetic_evidence(frames=6)
        meta = metadata(len(data))
        result = wireframe.fit_from_sector_evidence(
            data,
            u,
            gauge_id="fixed",
            frame_metadata=meta,
        )
        rows = result["frame_evidence"]
        self.assertEqual(len(rows), 6)
        self.assertTrue(
            all("C3_TABLE" in row["boundaries"] for row in rows)
        )
        self.assertNotIn("scaffold", rows[0])
        observed = result["scaffold"]["entity_observations"]["C3_N"]
        self.assertTrue(observed["supporting_source_indices"])
        self.assertTrue(
            set(observed["supporting_source_indices"])
            <= {row["source_index"] for row in meta}
        )

    def test_missing_boundary_returns_explicit_unavailable(self):
        u, data = synthetic_evidence(boundaries=(0.50, 0.75, 0.79))
        data[:, :, u >= 0.82] = 0.0
        result = wireframe.fit_from_sector_evidence(
            data, u, gauge_id="g"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["scaffold"])
        self.assertIn("outer", result["reason"])

    def test_too_few_views_returns_unavailable(self):
        u, data = synthetic_evidence(frames=2)
        result = wireframe.fit_from_sector_evidence(
            data, u, gauge_id="g"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reason"],
            "fewer_than_three_compatible_geometry_views",
        )

    def test_geometry_selection_requires_stable_gauge_and_crown_lobe(self):
        payload = {
            "face_selection": {"status": "resolved"},
            "frames": [
                {
                    "rank": rank,
                    "position": rank - 1,
                    "source_index": rank - 1,
                    "face_role": role,
                    "assessment": {"status": "ok"},
                    "canonical": {"path": f"canonical/{rank:04d}.npz"},
                    "sequence_coordinate": {
                        "gauge_status": "available",
                        "gauge_quarter_turn": 0,
                    },
                }
                for rank, role in enumerate(
                    [
                        "likely_crown_lobe",
                        "likely_opposite_lobe",
                        "likely_crown_lobe",
                        "outside_face_on_lobes",
                        "likely_crown_lobe",
                    ],
                    start=1,
                )
            ],
        }
        selected = wireframe._select_geometry_records(payload)
        self.assertEqual(
            [row["source_index"] for row in selected],
            [0, 2, 4],
        )

    def test_gauge_id_is_sequence_level_not_per_frame(self):
        payload = {
            "sequence_gauge": {
                "orientation_gauge": {
                    "status": "available",
                    "reference_source_index": 253,
                    "selected_reference_quarter_turn": 2,
                }
            }
        }
        self.assertEqual(
            wireframe._gauge_id(payload),
            "asscher-sequence-gauge-v1:253:2",
        )


if __name__ == "__main__":
    unittest.main()
