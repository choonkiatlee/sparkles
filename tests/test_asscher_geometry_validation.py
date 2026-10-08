from copy import deepcopy
import inspect
import unittest

from diamond360 import asscher_geometry_validation as validation
from diamond360 import asscher_topology as topology
from diamond360 import asscher_wireframe as wireframe


def benchmark_manifest():
    return {
        "schema_version": "sparkles-benchmark-sources/2",
        "core_indices": [248, 249, 250, 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5, 6, 7, 8],
        "sequence_complete": True,
        "bundles": [
            {
                "certificate": "IGI-LG756580087",
                "sha256": "d3a0ed93af5e2a089d2bf108a01fceafe21edf191f3bb79f6fc627718ec23016",
                "bytes": 8963440,
                "frame_count": 256,
                "source_manifest": "docs/360/benchmark/per-stone/IGI-LG756580087/source-manifest.json",
                "filename": "IGI-LG756580087-benchmark-full-sequence.zip",
                "download_url": "https://github.com/choonkiatlee/sparkles/releases/download/benchmark-sources-v1/IGI-LG756580087-benchmark-full-sequence.zip",
            },
            {
                "certificate": "IGI-LG756520111",
                "sha256": "b45647292c207d46fab8871b66ff62c3aa4a7652c910c5cd975fce10f3c5fc90",
                "bytes": 5504096,
                "frame_count": 256,
                "source_manifest": "docs/360/benchmark/per-stone/IGI-LG756520111/source-manifest.json",
                "filename": "IGI-LG756520111-benchmark-full-sequence.zip",
                "download_url": "https://github.com/choonkiatlee/sparkles/releases/download/benchmark-sources-v1/IGI-LG756520111-benchmark-full-sequence.zip",
            },
            {
                "certificate": "IGI-LG818659722",
                "sha256": "dbee1b288573d425c8f487a4e8b5965bf69d460e5c259ca63017abb202738939",
                "bytes": 8121970,
                "frame_count": 256,
                "source_manifest": "docs/360/benchmark/per-stone/IGI-LG818659722/source-manifest.json",
                "filename": "IGI-LG818659722-benchmark-full-sequence.zip",
                "download_url": "https://github.com/choonkiatlee/sparkles/releases/download/benchmark-sources-v1/IGI-LG818659722-benchmark-full-sequence.zip",
            },
            {
                "certificate": "IGI-LG836619414",
                "sha256": "8de35bbc0193a18c183c037b3b8f3a61ace503a23d8ee4e0953d45399f9bf596",
                "bytes": 8519867,
                "frame_count": 256,
                "source_manifest": "docs/360/benchmark/per-stone/IGI-LG836619414/source-manifest.json",
                "filename": "IGI-LG836619414-benchmark-full-sequence.zip",
                "download_url": "https://github.com/choonkiatlee/sparkles/releases/download/benchmark-sources-v1/IGI-LG836619414-benchmark-full-sequence.zip",
            },
        ],
        "storage": "github-release-assets",
        "release_tag": "benchmark-sources-v1",
        "release_url": "https://github.com/choonkiatlee/sparkles/releases/tag/benchmark-sources-v1",
    }


def wireframe_result(scaffold):
    return {
        "schema_version": wireframe.SCHEMA,
        "status": "ok",
        "scaffold": scaffold,
    }


class AsscherGeometryValidationTests(unittest.TestCase):
    def test_frozen_method_and_benchmark_snapshot_are_identifiable(self):
        self.assertTrue(validation.assert_frozen_method())
        frozen = validation.frozen_method_record()
        self.assertEqual(
            frozen["wireframe_revision"],
            "6334cc9d0c7e2c9a26854bfaeec7a8ebbb6fc668",
        )
        self.assertEqual(
            frozen["wireframe_specification_sha256"],
            validation.FROZEN_WIREFRAME_SPEC_SHA256,
        )
        snapshot = validation.benchmark_snapshot(benchmark_manifest())
        self.assertTrue(snapshot["manifest_matches_frozen_snapshot"])
        self.assertEqual(len(snapshot["bundles"]), 4)
        self.assertTrue(
            all(len(row["sha256"]) == 64 for row in snapshot["bundles"])
        )

    def test_benchmark_manifest_drift_fails_closed(self):
        changed = benchmark_manifest()
        changed["core_indices"] = changed["core_indices"][:-1]
        with self.assertRaises(RuntimeError):
            validation.assert_frozen_benchmark_manifest(changed)

    def test_boundary_displacement_reports_raw_and_local_tier_fraction(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g")
        candidate = deepcopy(reference)
        for vertex_id in next(
            row["vertex_ids"]
            for row in candidate["boundaries"]
            if row["boundary_id"] == "C2_C3"
        ):
            x, y = candidate["vertices"][vertex_id]
            candidate["vertices"][vertex_id] = [x * 1.02, y * 1.02]
        result = validation.compare_scaffolds(reference, candidate)
        metric = result["boundary_displacement"]["C2_C3"]
        self.assertEqual(result["status"], "ok")
        self.assertTrue(metric["comparable"])
        self.assertGreater(metric["mean_displacement_u"], 0)
        self.assertGreater(metric["mean_displacement_tier_fraction"], 0)
        self.assertTrue(
            all("displacement_u" in row for row in metric["per_vertex"])
        )

    def test_gauge_change_is_explicit_unavailable_not_silent_swap(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g-A")
        candidate = topology.canonical_synthetic_scaffold(gauge_id="g-B")
        result = validation.compare_scaffolds(reference, candidate)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reasons"], ["semantic_identity_or_gauge_changed"]
        )
        self.assertFalse(result["identity"]["gauge_consistent"])

    def test_semantic_reassignment_is_detected(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g")
        candidate = deepcopy(reference)
        support = candidate["semantic_supports"][0]
        original = support["semantic_ids"][0]
        support["semantic_ids"] = [
            "C1_S" if original != "C1_S" else "C1_N"
        ]
        identity = validation.semantic_identity_consistency(
            reference, candidate
        )
        self.assertFalse(identity["consistent"])
        self.assertEqual(len(identity["support_semantic_reassignments"]), 1)

    def test_provenance_regression_propagates_review(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g")
        candidate = deepcopy(reference)
        reference["entity_observations"]["C3_N"]["provenance"] = "observed"
        candidate["entity_observations"]["C3_N"][
            "provenance"
        ] = "model_inferred"
        result = validation.compare_scaffolds(reference, candidate)
        self.assertEqual(result["status"], "review")
        self.assertIn(
            "observation_provenance_regressed", result["reasons"]
        )
        row = result["observation_changes"]["C3_N"]
        self.assertTrue(row["provenance_regressed"])

    def test_invalid_topology_fails_closed(self):
        reference = topology.canonical_synthetic_scaffold(gauge_id="g")
        candidate = deepcopy(reference)
        for vertex_id in next(
            row["vertex_ids"]
            for row in candidate["boundaries"]
            if row["boundary_id"] == "C2_C3"
        ):
            x, y = candidate["vertices"][vertex_id]
            candidate["vertices"][vertex_id] = [x * 2.0, y * 2.0]
        result = validation.compare_scaffolds(reference, candidate)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reasons"], ["topology_validation_failed"])
        self.assertTrue(result["topology_failures"])

    def test_validation_record_does_not_mutate_or_refit_inputs(self):
        reference = wireframe_result(
            topology.canonical_synthetic_scaffold(gauge_id="g")
        )
        candidate = deepcopy(reference)
        reference_before = deepcopy(reference)
        candidate_before = deepcopy(candidate)
        record = validation.build_validation_record(
            reference,
            candidate,
            benchmark_manifest(),
            case_id="synthetic-identical",
            comparison_kind="estimator_stability",
            run_metadata={"subset": "all"},
        )
        self.assertEqual(reference, reference_before)
        self.assertEqual(candidate, candidate_before)
        self.assertEqual(record["schema_version"], validation.SCHEMA)
        self.assertEqual(record["status"], "ok")
        self.assertIn("boundary_displacement", record["measurements"])

    def test_public_record_api_has_no_target_or_image_fitting_input(self):
        parameters = set(
            inspect.signature(
                validation.build_validation_record
            ).parameters
        )
        self.assertFalse(
            {"target", "target_values", "image", "image_path", "fitter"}
            & parameters
        )
        anti_leakage = validation.contract_document()["anti_leakage"]
        self.assertFalse(
            anti_leakage["image_fitting_available_in_this_module"]
        )
        self.assertFalse(
            anti_leakage["external_target_loading_available_in_this_module"]
        )


if __name__ == "__main__":
    unittest.main()
