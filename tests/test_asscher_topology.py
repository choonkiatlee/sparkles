import json
import unittest
from copy import deepcopy
from pathlib import Path

from diamond360 import asscher_topology as topology


class AsscherTopologyTests(unittest.TestCase):
    def setUp(self):
        self.physical = topology.canonical_physical_topology()

    def test_canonical_physical_topology_validates(self):
        self.assertTrue(topology.validate_topology(self.physical))
        mapping = self.physical["image_mapping_policy"]
        self.assertFalse(mapping["exclusive_pixel_partition_required"])
        self.assertFalse(mapping["direct_projection_claim"])
        self.assertEqual(
            mapping["future_optical_association_cardinality"],
            "many_to_many",
        )

    def test_counterparts_are_explicit_without_name_parsing(self):
        self.assertEqual(
            topology.rotate_semantic_id(self.physical, "P3_N", 1),
            "P3_E",
        )
        self.assertEqual(
            topology.rotate_semantic_id(self.physical, "C2_SW", 1),
            "C2_NW",
        )
        self.assertEqual(
            topology.opposite_semantic_id(self.physical, "P2_E"),
            "P2_W",
        )
        self.assertEqual(
            topology.rotate_semantic_id(
                self.physical, "WINDMILL_NE", 1
            ),
            "WINDMILL_SE",
        )

    def test_semantic_identity_is_independent_of_observation_provenance(self):
        scaffold = topology.canonical_synthetic_scaffold()
        identity_before = deepcopy(
            topology.get_entity(self.physical, "P3_N")
        )
        scaffold["entity_observations"]["P3_N"].update(
            {
                "provenance": "symmetry_inferred",
                "observation_state": "partial",
                "confidence": 0.44,
                "validity": "review",
            }
        )
        self.assertTrue(
            topology.validate_scaffold(scaffold, self.physical)
        )
        self.assertEqual(
            topology.get_entity(self.physical, "P3_N"),
            identity_before,
        )

    def test_asymmetric_and_partially_observed_scaffold_is_valid(self):
        scaffold = topology.canonical_synthetic_scaffold(
            asymmetric=True,
            unavailable_semantic_ids=("P3_E", "C2_SW"),
        )
        self.assertTrue(
            topology.validate_scaffold(scaffold, self.physical)
        )
        self.assertEqual(
            scaffold["entity_observations"]["P3_E"]["provenance"],
            "unavailable",
        )
        self.assertEqual(
            scaffold["entity_observations"]["P3_N"][
                "observation_state"
            ],
            "partial",
        )

    def test_nonexclusive_overlapping_many_entity_support_is_valid(self):
        scaffold = topology.canonical_synthetic_scaffold()
        donor = deepcopy(scaffold["semantic_supports"][0])
        donor["support_id"] = "OVERLAP_MULTI_ASSOC"
        donor["semantic_ids"] = ["P3_N", "P2_NE"]
        donor["confidence"] = 0.61
        donor["provenance"] = "observed"
        donor["observation_state"] = "partial"
        scaffold["semantic_supports"].append(donor)
        scaffold["entity_observations"]["P3_N"]["support_ids"].append(
            donor["support_id"]
        )
        scaffold["entity_observations"]["P2_NE"]["support_ids"].append(
            donor["support_id"]
        )
        self.assertTrue(
            topology.validate_scaffold(scaffold, self.physical)
        )
        self.assertTrue(
            scaffold["representation_policy"]["supports_may_overlap"]
        )

    def test_observation_cannot_claim_unrelated_semantic_support(self):
        scaffold = topology.canonical_synthetic_scaffold()
        scaffold["entity_observations"]["P3_N"]["support_ids"] = [
            "SUPPORT_C1_N"
        ]
        with self.assertRaises(topology.ScaffoldValidationError):
            topology.validate_scaffold(scaffold, self.physical)

    def test_sequence_gauge_must_not_drift_frame_by_frame(self):
        first = topology.canonical_synthetic_scaffold(
            gauge_id="stone-A-gauge"
        )
        second = topology.canonical_synthetic_scaffold(
            gauge_id="stone-A-gauge"
        )
        self.assertTrue(
            topology.validate_sequence_gauge([first, second])
        )
        second["semantic_gauge"]["gauge_id"] = "different-gauge"
        with self.assertRaises(topology.ScaffoldValidationError):
            topology.validate_sequence_gauge([first, second])

    def test_crossing_boundary_fails(self):
        scaffold = topology.canonical_synthetic_scaffold()
        boundary = next(
            row for row in scaffold["boundaries"]
            if row["boundary_id"] == "C1_C2"
        )
        ids = boundary["vertex_ids"]
        boundary["vertex_ids"] = [
            ids[0], ids[2], ids[1], ids[3],
            ids[4], ids[5], ids[6], ids[7],
        ]
        with self.assertRaises(topology.ScaffoldValidationError):
            topology.validate_scaffold(scaffold, self.physical)

    def test_reordered_nested_boundaries_fail(self):
        scaffold = topology.canonical_synthetic_scaffold()
        boundary = next(
            row for row in scaffold["boundaries"]
            if row["boundary_id"] == "C1_C2"
        )
        for vertex_id in boundary["vertex_ids"]:
            scaffold["vertices"][vertex_id] = [
                value * 1.5
                for value in scaffold["vertices"][vertex_id]
            ]
        with self.assertRaises(topology.ScaffoldValidationError):
            topology.validate_scaffold(scaffold, self.physical)

    def test_disconnected_geometry_fails(self):
        scaffold = topology.canonical_synthetic_scaffold()
        scaffold["semantic_supports"][0]["vertex_ids"][0] = "MISSING"
        with self.assertRaises(topology.ScaffoldValidationError):
            topology.validate_scaffold(scaffold, self.physical)

    def test_invalid_topology_reference_fails(self):
        physical = deepcopy(self.physical)
        row = topology.get_entity(physical, "P3_N")
        row["structural_neighbors"].append("NOT_A_REAL_ENTITY")
        with self.assertRaises(topology.TopologyValidationError):
            topology.validate_topology(physical)

    def test_contract_keeps_future_optical_layer_open(self):
        contract = topology.contract_document()
        self.assertIn(
            "image-plane semantic supports are non-exclusive",
            contract["invariants"],
        )
        self.assertIn(
            "future optical regions may associate many-to-many with physical entities",
            contract["invariants"],
        )
        self.assertIn(
            "empirical optical or virtual-facet segmentation",
            contract["future_extension_boundary"][
                "explicitly_not_implemented_here"
            ],
        )

    def test_committed_contract_matches_runtime_contract(self):
        path = (
            Path(__file__).parents[1]
            / "docs"
            / "360"
            / "asscher-topology"
            / "contract-v1.json"
        )
        self.assertEqual(
            json.loads(path.read_text()),
            topology.contract_document(),
        )

    def test_synthetic_scaffold_renders_without_source_image(self):
        scaffold = topology.canonical_synthetic_scaffold(
            asymmetric=True
        )
        image = topology.render_scaffold(
            scaffold,
            self.physical,
            size=256,
        )
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
