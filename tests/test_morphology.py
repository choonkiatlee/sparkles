import unittest

import numpy as np

from diamond360 import morphology as m


class MorphologyTests(unittest.TestCase):
    def test_same_active_area_distinguishes_connected_from_fragmented(self):
        support = np.ones((7, 7), bool)
        broad = np.zeros((7, 7), bool)
        broad[2:5, 2:5] = True
        fragmented = np.zeros((7, 7), bool)
        fragmented[1, 1:4] = True
        fragmented[3, 1:4] = True
        fragmented[5, 1:4] = True

        coherent = m.frame_morphology(broad, support)
        split = m.frame_morphology(fragmented, support)

        self.assertEqual(coherent["active_pixels"], split["active_pixels"])
        self.assertEqual(coherent["component_count"], 1)
        self.assertEqual(split["component_count"], 3)
        self.assertEqual(coherent["largest_component_fraction"], 1.0)
        self.assertAlmostEqual(split["largest_component_fraction"], 1 / 3)
        self.assertEqual(coherent["effective_component_count"], 1.0)
        self.assertAlmostEqual(split["effective_component_count"], 3.0)

    def test_eight_connected_is_explicit_default(self):
        diagonal = np.eye(3, dtype=bool)
        support = np.ones((3, 3), bool)
        self.assertEqual(m.frame_morphology(diagonal, support, 8)["component_count"], 1)
        self.assertEqual(m.frame_morphology(diagonal, support, 4)["component_count"], 3)

    def test_support_boundary_contact_is_auditable(self):
        support = np.ones((5, 5), bool)
        active = np.zeros((5, 5), bool)
        active[0, 1:4] = True
        active[2, 2] = True
        result = m.frame_morphology(active, support)
        self.assertEqual(result["components_touching_support_boundary"], 1)
        self.assertEqual(result["boundary_active_pixels"], 3)
        self.assertAlmostEqual(result["boundary_active_fraction"], 0.75)

    def test_zero_active_pixels_is_unavailable_not_coherent(self):
        result = m.frame_morphology(np.zeros((3, 3), bool), np.ones((3, 3), bool))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "no_active_pixels")
        self.assertEqual(result["component_count"], 0)
        self.assertIsNone(result["largest_component_fraction"])

    def test_relative_bright_threshold_is_strict(self):
        state = m.relative_bright_state(np.array([12.49, 12.50, 12.51]), 10.0, 2.0, 1.25)
        self.assertEqual(state.tolist(), [False, False, True])
        self.assertIsNone(m.relative_bright_state(np.array([13.0]), None, 2.0, 1.25))
        self.assertIsNone(m.relative_bright_state(np.array([13.0]), 10.0, None, 1.25))
        with self.assertRaises(ValueError):
            m.relative_bright_state(np.array([13.0]), 10.0, 2.0, 0.0)

    def test_fixed_and_dynamic_support_are_distinct(self):
        brightness = np.array([
            [[10.0, 14.0], [10.0, 10.0]],
            [[10.0, 14.0], [10.0, 14.0]],
        ])
        valid = np.ones_like(brightness, dtype=bool)
        stone = np.ones_like(brightness, dtype=bool)
        stone[1, 1, 1] = False
        fixed = m.morphology_trace(
            brightness, valid, stone, [10.0, 10.0], [True, True], "fixed", 1.25
        )
        dynamic = m.morphology_trace(
            brightness, valid, stone, [10.0, 10.0], [True, True], "dynamic", 1.25
        )
        self.assertEqual(fixed["persistent_support_pixels"], 3)
        self.assertEqual(dynamic["frames"][0]["support_pixels"], 4)
        self.assertEqual(dynamic["frames"][1]["support_pixels"], 3)

    def test_threshold_perturbation_changes_marginal_connectivity(self):
        brightness = np.array([[
            [9.0, 9.0, 14.0, 9.0, 9.0],
            [14.0, 14.0, 11.7, 14.0, 14.0],
            [11.0, 11.0, 10.0, 11.0, 11.0],
        ]])
        valid = np.ones_like(brightness, dtype=bool)
        stone = np.ones_like(brightness, dtype=bool)
        sweep = m.threshold_sweep(
            brightness, valid, stone, [10.0], [True], "fixed"
        )
        self.assertEqual(sweep["0.75"]["frames"][0]["component_count"], 1)
        self.assertEqual(sweep["1.25"]["frames"][0]["component_count"], 2)
        sensitivity = m.select_threshold_sensitivity(sweep, [7])
        self.assertEqual(sensitivity["source_index"], 7)
        self.assertGreater(sensitivity["largest_component_fraction_range"], 0)

    def test_evidence_finds_matched_area_morphology_difference(self):
        frames = [
            {
                "status": "ok", "active_fraction": 0.20,
                "largest_component_fraction": 1.0,
                "largest_component_support_fraction": 0.20,
                "effective_component_count": 1.0,
            },
            {
                "status": "ok", "active_fraction": 0.205,
                "largest_component_fraction": 0.40,
                "largest_component_support_fraction": 0.082,
                "effective_component_count": 2.5,
            },
            {
                "status": "ok", "active_fraction": 0.50,
                "largest_component_fraction": 0.50,
                "largest_component_support_fraction": 0.25,
                "effective_component_count": 2.0,
            },
        ]
        evidence = m.select_frame_evidence(frames, [1, 2, 3])
        pair = evidence["matched_active_area_pair"]
        self.assertTrue(pair["within_tolerance"])
        self.assertEqual(pair["left"]["source_index"], 1)
        self.assertEqual(pair["right"]["source_index"], 2)

    def test_support_disagreement_selects_extreme_and_control(self):
        fixed = [
            {"largest_component_fraction": 0.8},
            {"largest_component_fraction": 0.5},
            {"largest_component_fraction": 0.3},
        ]
        dynamic = [
            {"largest_component_fraction": 0.79},
            {"largest_component_fraction": 0.9},
            {"largest_component_fraction": 0.3},
        ]
        evidence = m.select_support_disagreement(fixed, dynamic, [10, 11, 12])
        self.assertEqual(evidence["strongest"]["source_index"], 11)
        self.assertEqual(evidence["control"]["source_index"], 12)


if __name__ == "__main__":
    unittest.main()
