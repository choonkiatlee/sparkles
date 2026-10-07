from copy import deepcopy
import unittest

import numpy as np

from diamond360 import asscher_geometry_stability as stability
from diamond360 import asscher_topology as topology
from diamond360 import asscher_wireframe as wireframe


def synthetic_evidence(
    *,
    frames=7,
    samples=160,
    boundaries=(0.50, 0.75, 0.87),
):
    u = np.linspace(0.0, 1.0, samples)
    data = np.zeros((frames, 8, samples), dtype=float)
    for frame in range(frames):
        for sector in range(8):
            for boundary_index, centre in enumerate(boundaries):
                amplitude = (1.0, 0.88, 0.78)[boundary_index]
                data[frame, sector] += amplitude * np.exp(
                    -0.5 * ((u - centre) / 0.009) ** 2
                )
            # Persistent inner structure gives the pavilion loci evidence.
            for centre, amplitude in (
                (0.16, 0.55),
                (0.27, 0.50),
                (0.39, 0.45),
            ):
                data[frame, sector] += amplitude * np.exp(
                    -0.5 * ((u - centre) / 0.010) ** 2
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
            "source_index": i,
            "position": i,
            "rotation_phase_deg": float(i) * 1.40625,
            "rotation_phase_0_360_deg": float(i) * 1.40625,
            "gauge_quarter_turn": 0,
            "gauge_status": "available",
            "face_role": "likely_crown_lobe",
            "pose_status": "ok",
            "pose_score": 0.9,
        }
        for i in range(count)
    ]


def primary_result():
    u, data = synthetic_evidence()
    result = wireframe.fit_from_sector_evidence(
        data,
        u,
        gauge_id="fixed-gauge",
        frame_metadata=metadata(len(data)),
    )
    assert result["scaffold"] is not None
    return u, data, result


class AsscherGeometryStabilityTests(unittest.TestCase):
    def test_transfer_uses_fixed_targets_and_semantic_ids(self):
        u, data, primary = primary_result()
        before = deepcopy(primary)
        row = stability.transfer_fixed_ruler_frame(
            data[0],
            u,
            primary,
            frame_metadata=metadata(1)[0],
            crown_peak_position=0,
            sequence_size=256,
        )
        self.assertFalse(row["refit_performed"])
        self.assertEqual(
            row["semantic_identity_source"],
            "primary_fixed_scaffold",
        )
        self.assertEqual(
            set(row["entities"]),
            set(primary["scaffold"]["entity_observations"]),
        )
        self.assertEqual(primary, before)
        self.assertEqual(
            row["boundary_support"]["C3_TABLE"][
                "target_sector_u_step_order"
            ],
            primary["boundary_evidence"]["C3_TABLE"][
                "sector_u_step_order"
            ],
        )

    def test_moving_tonal_edge_changes_evidence_not_ruler(self):
        u, data, primary = primary_result()
        base = stability.transfer_fixed_ruler_frame(
            data[0],
            u,
            primary,
            frame_metadata=metadata(1)[0],
            crown_peak_position=0,
            sequence_size=256,
        )
        changed = data[0].copy()
        distractor = 3.0 * np.exp(
            -0.5 * ((u - 0.58) / 0.006) ** 2
        )
        changed += distractor[None, :]
        moved = stability.transfer_fixed_ruler_frame(
            changed,
            u,
            primary,
            frame_metadata=metadata(1)[0],
            crown_peak_position=0,
            sequence_size=256,
        )
        self.assertEqual(
            base["boundary_support"]["C3_TABLE"][
                "target_sector_u_step_order"
            ],
            moved["boundary_support"]["C3_TABLE"][
                "target_sector_u_step_order"
            ],
        )
        self.assertEqual(
            set(base["entities"]), set(moved["entities"])
        )

    def test_low_support_degrades_without_identity_reassignment(self):
        u, _, primary = primary_result()
        weak = np.zeros((8, len(u)), dtype=float)
        row = stability.transfer_fixed_ruler_frame(
            weak,
            u,
            primary,
            frame_metadata=metadata(1)[0],
            crown_peak_position=0,
            sequence_size=256,
        )
        self.assertIn(row["status"], {"review", "unavailable"})
        self.assertEqual(
            set(row["entities"]),
            set(primary["scaffold"]["entity_observations"]),
        )
        crown = [
            item
            for semantic_id, item in row["entities"].items()
            if semantic_id.startswith(("C1_", "C2_", "C3_"))
        ]
        self.assertTrue(
            any(item["status"] != "ok" for item in crown)
        )

    def test_wrap_summary_requires_both_cyclic_boundary_frames(self):
        rows = [
            {
                "position": 255,
                "gauge_status": "available",
                "refit_performed": False,
            },
            {
                "position": 0,
                "gauge_status": "available",
                "refit_performed": False,
            },
        ]
        summary = stability._wrap_summary(rows, 256)
        self.assertTrue(summary["cyclic_255_to_0_wrap_exercised"])
        self.assertEqual(summary["missing_gauge_count"], 0)
        self.assertEqual(summary["refit_count"], 0)

    def test_validation_summary_preserves_normalized_displacement(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g")
        candidate = deepcopy(reference)
        for vertex_id in next(
            row["vertex_ids"]
            for row in candidate["boundaries"]
            if row["boundary_id"] == "C2_C3"
        ):
            x, y = candidate["vertices"][vertex_id]
            candidate["vertices"][vertex_id] = [x * 1.01, y * 1.01]
        comparison = {
            "status": "ok",
            "reasons": [],
            "measurements": {
                "boundary_displacement": (
                    __import__(
                        "diamond360.asscher_geometry_validation",
                        fromlist=["boundary_displacement"],
                    ).boundary_displacement(reference, candidate)
                ),
                "entity_displacement": {},
                "semantic_identity": {"consistent": True},
                "observation_changes": {},
            },
        }
        summary = stability.summarize_validation_record(comparison)
        self.assertGreater(
            summary["max_boundary_displacement_tier_fraction"], 0
        )
        self.assertTrue(summary["semantic_identity_consistent"])


if __name__ == "__main__":
    unittest.main()
