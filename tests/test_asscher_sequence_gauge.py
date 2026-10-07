import unittest

import numpy as np

from diamond360 import asscher_sequence_gauge as gauge


def _record(position, orientation_deg, *, status="ok", size=181):
    return {
        "position": position,
        "source_index": position,
        "rank": position + 1,
        "face_role": "outside_face_on_lobes",
        "assessment": {"status": status},
        "canonical": {
            "registered_outline": {
                "orientation_deg_mod_90": orientation_deg,
            },
            "camera_to_canonical_xy": np.eye(3).tolist(),
            "normalization": {"canvas_size_px": size},
        },
    }


def _sampling_manifest(size):
    return {
        "sequence_complete": True,
        "source_frame_count": size,
        "sequence_sampling": {
            "kind": "uniform_cyclic_viewer_phase",
            "period_frames": size,
            "nominal_cycle_deg": 360.0,
            "physical_angle_calibrated": False,
            "direction_physical_meaning": "unknown",
        },
    }


def _resolved_face(position):
    return {
        "status": "resolved",
        "likely_crown_peak_position": position,
        "likely_crown_peak_source_index": position,
        "lobes": [
            {
                "peak_position": position,
                "peak_source_index": position,
            }
        ],
    }


class AsscherSequenceGaugeTests(unittest.TestCase):
    def test_uniform_256_phase_wrap_is_continuous_across_255_to_zero(self):
        size = 256
        records = [_record(i, 12.0) for i in range(size)]
        phase, coordinates = gauge.build_phase(
            records,
            _sampling_manifest(size),
            _resolved_face(255),
        )

        self.assertEqual(phase["status"], "available")
        self.assertAlmostEqual(phase["nominal_step_deg"], 1.40625)
        self.assertAlmostEqual(coordinates[255]["rotation_phase_deg"], 0.0)
        self.assertAlmostEqual(
            coordinates[0]["rotation_phase_deg"],
            1.40625,
        )
        self.assertAlmostEqual(
            coordinates[1]["rotation_phase_deg"],
            2.8125,
        )

    def test_phase_direction_can_be_conventional_and_reversed(self):
        records = [_record(i, 5.0) for i in range(8)]
        manifest = _sampling_manifest(8)
        face = _resolved_face(0)

        forward, forward_frames = gauge.build_phase(
            records,
            manifest,
            face,
            direction_sign=1,
        )
        reverse, reverse_frames = gauge.build_phase(
            records,
            manifest,
            face,
            direction_sign=-1,
        )

        self.assertEqual(forward["physical_rotation_direction_known"], False)
        self.assertEqual(reverse["physical_rotation_direction_known"], False)
        self.assertEqual(forward_frames[1]["rotation_phase_deg"], 45.0)
        self.assertEqual(reverse_frames[1]["rotation_phase_deg"], -45.0)

    def test_missing_sampling_contract_refuses_to_invent_phase(self):
        records = [_record(i, 10.0) for i in range(4)]
        phase, coordinates = gauge.build_phase(
            records,
            {"sequence_complete": True, "source_frame_count": 4},
            _resolved_face(0),
        )

        self.assertEqual(phase["status"], "unavailable")
        self.assertEqual(
            phase["reason"],
            "sequence_sampling_contract_missing",
        )
        self.assertTrue(all(not row for row in coordinates))

    def test_mod_90_wrap_does_not_swap_semantic_quarter_turn(self):
        records = [
            _record(0, 88.0),
            _record(1, 89.0),
            _record(2, 1.0),
            _record(3, 2.0),
        ]
        model, coordinates = gauge.build_orientation_gauge(
            records,
            {
                "status": "available",
                "reference_position": 0,
            },
            _sampling_manifest(4),
        )

        self.assertEqual(model["status"], "available")
        self.assertEqual(
            [row["gauge_quarter_turn"] for row in coordinates],
            [0, 0, 1, 1],
        )
        selected = [
            row["selected_orientation_branch_deg"]
            for row in coordinates
        ]
        self.assertEqual(selected, [88.0, 89.0, 91.0, 92.0])
        self.assertLessEqual(model["maximum_neighbor_branch_jump_deg"], 2.0)
        self.assertLessEqual(model["closure_jump_deg"], 4.0)

    def test_global_90_equivalent_gauge_is_explicit_and_deterministic(self):
        records = [
            _record(0, 88.0),
            _record(1, 89.0),
            _record(2, 1.0),
            _record(3, 2.0),
        ]
        manifest = _sampling_manifest(4)
        phase = {"status": "available", "reference_position": 0}

        base, base_frames = gauge.build_orientation_gauge(
            records,
            phase,
            manifest,
            reference_quarter_turn=0,
        )
        rotated, rotated_frames = gauge.build_orientation_gauge(
            records,
            phase,
            manifest,
            reference_quarter_turn=1,
        )

        self.assertEqual(
            base["equivalent_global_quarter_turns"],
            [0, 1, 2, 3],
        )
        self.assertFalse(base["physically_unique"])
        for first, second in zip(base_frames, rotated_frames):
            self.assertEqual(
                second["gauge_quarter_turn"],
                (first["gauge_quarter_turn"] + 1) % 4,
            )
            relative = (
                second["selected_orientation_branch_deg"]
                - first["selected_orientation_branch_deg"]
            ) % 360.0
            self.assertAlmostEqual(relative, 90.0)

    def test_low_suitability_pose_is_marked_review_not_silently_trusted(self):
        records = [
            _record(0, 5.0),
            _record(1, 6.0, status="rejected"),
            _record(2, 7.0),
            _record(3, 8.0),
        ]
        _, coordinates = gauge.build_orientation_gauge(
            records,
            {"status": "available", "reference_position": 0},
            _sampling_manifest(4),
        )

        self.assertEqual(coordinates[1]["gauge_status"], "review")
        self.assertEqual(
            coordinates[1]["gauge_branch_provenance"],
            "sequence_continuity_from_low_suitability_pose",
        )

    def test_sequence_contract_keeps_phase_when_pose_is_unavailable(self):
        records = [
            _record(0, 5.0),
            {
                "position": 1,
                "source_index": 1,
                "rank": 2,
                "face_role": "outside_face_on_lobes",
                "assessment": {"status": "failed"},
                "canonical": None,
            },
            _record(2, 7.0),
            _record(3, 8.0),
        ]
        result = gauge.build_sequence_coordinates(
            records,
            _sampling_manifest(4),
            _resolved_face(0),
        )

        failed = result["frames"][1]
        self.assertEqual(failed["phase_status"], "available")
        self.assertEqual(failed["rotation_phase_deg"], 90.0)
        self.assertEqual(failed["gauge_status"], "unavailable")
        self.assertIsNone(failed["camera_to_sequence_gauge_xy"])

    def test_composed_transform_rotates_about_canonical_centre(self):
        records = [
            _record(0, 89.0),
            _record(1, 1.0),
        ]
        model, coordinates = gauge.build_orientation_gauge(
            records,
            {"status": "available", "reference_position": 0},
            _sampling_manifest(2),
        )

        self.assertEqual(model["status"], "available")
        self.assertEqual(coordinates[1]["gauge_quarter_turn"], 1)
        matrix = np.asarray(
            coordinates[1]["camera_to_sequence_gauge_xy"],
            dtype=float,
        )
        centre = np.array([90.0, 90.0, 1.0])
        np.testing.assert_allclose(matrix @ centre, centre, atol=1e-10)
        linear = matrix[:2, :2]
        np.testing.assert_allclose(
            linear.T @ linear,
            np.eye(2),
            atol=1e-10,
        )


if __name__ == "__main__":
    unittest.main()
