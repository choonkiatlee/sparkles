import json
import tempfile
import unittest
from pathlib import Path

from diamond360 import calibration as cal
from diamond360 import descriptor_profile as dp


def _comparison():
    measurements = {
        field_id: {
            key: value
            for key, value in spec.items()
            if key not in {"role", "family"}
        }
        for field_id, spec in dp.FIELD_SPECS.items()
        if spec["role"] == "descriptor"
    }
    context = {
        field_id: {
            key: value
            for key, value in spec.items()
            if key not in {"role", "family"}
        }
        for field_id, spec in dp.FIELD_SPECS.items()
        if spec["role"] == "context"
    }
    stones = []
    for ci, certificate in enumerate(("A", "B")):
        cells = {}
        for fi, field_id in enumerate(dp.PRODUCTION_FIELD_IDS, start=1):
            cells[field_id] = {
                "value": float(fi + ci),
                "status": "review" if certificate == "B" else "ok",
                "reasons": ["fixture_review"] if certificate == "B" else [],
                "source_refs": [],
            }
        stones.append({"certificate": certificate, "measurements": cells, "context": {}})
    return {
        "schema_version": dp.COMPARISON_SCHEMA,
        "profile_schema": dp.PROFILE_SCHEMA,
        "window_contract": {
            "id": "core17",
            "source_indices": list(dp.CORE_INDICES),
            "wrap_explicit": True,
            "source_step_semantics": "ordinal samples; not seconds or calibrated degrees",
        },
        "field_catalog": {"measurements": measurements, "context": context},
        "redundancy_groups": dp.REDUNDANCY_GROUPS,
        "stones": stones,
    }


def _human(field_id=None, explanation="explained"):
    links = []
    if field_id is not None:
        links = [{
            "field_id": field_id,
            "assessment": "supports",
            "rationale": "fixture relationship",
        }]
    return {
        "schema_version": cal.OBSERVATION_SCHEMA,
        "concept_catalog": {"movement": "fixture concept"},
        "stone_reviews": [
            {"certificate": "A", "outcome": "Shortlist", "evaluation_path": "eval/A.md"},
            {"certificate": "B", "outcome": "Reserve", "evaluation_path": "eval/B.md"},
        ],
        "observations": [
            {
                "id": "A-movement",
                "certificate": "A",
                "concept": "movement",
                "hypothesis_family": "activity_motion",
                "role": "strength",
                "profile_explanation": explanation,
                "summary": "fixture observation",
                "source_frames": [248, 10],
                "descriptor_links": links,
            }
        ],
    }


def _root(tmp):
    root = Path(tmp)
    (root / "eval").mkdir(parents=True)
    (root / "eval" / "A.md").write_text("A")
    (root / "eval" / "B.md").write_text("B")
    return root


class CalibrationContractTests(unittest.TestCase):
    def test_join_preserves_profile_validity_and_direction_free_ranks(self):
        field_id = dp.PRODUCTION_FIELD_IDS[0]
        with tempfile.TemporaryDirectory() as td:
            payload = cal.build_calibration_payload(
                _comparison(), _human(field_id), repository_root=_root(td)
            )
        observation = payload["observations"][0]
        link = observation["descriptor_links"][0]
        self.assertEqual(link["measurement"]["value"], 1.0)
        self.assertEqual(link["measurement"]["status"], "ok")
        self.assertEqual(link["measurement"]["rank_descending"], 2)
        self.assertEqual(link["measurement"]["sample_size"], 2)
        self.assertEqual(
            payload["field_orders"][field_id]["direction"],
            "descriptive_only",
        )
        self.assertNotIn("score", json.dumps(payload).lower())
        self.assertEqual(observation["source_frames_outside_profile_window"], [10])

    def test_context_or_unknown_field_cannot_be_used_as_calibration_measurement(self):
        field_id = dp.CONTEXT_FIELD_IDS[0]
        with tempfile.TemporaryDirectory() as td:
            root = _root(td)
            with self.assertRaisesRegex(ValueError, "retained #45 measurement"):
                cal.build_calibration_payload(
                    _comparison(), _human(field_id), repository_root=root
                )

    def test_unexplained_observation_cannot_hide_descriptor_links(self):
        field_id = dp.PRODUCTION_FIELD_IDS[0]
        human = _human(field_id, explanation="unexplained")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "unexplained"):
                cal.build_calibration_payload(
                    _comparison(), human, repository_root=_root(td)
                )

    def test_redundancy_metadata_is_preserved_not_aggregated(self):
        field_id = "dark_state.occupancy.inner_mean"
        with tempfile.TemporaryDirectory() as td:
            payload = cal.build_calibration_payload(
                _comparison(), _human(field_id), repository_root=_root(td)
            )
        link = payload["observations"][0]["descriptor_links"][0]
        self.assertEqual(link["metadata"]["redundancy_group"], "relative_dark_state")
        self.assertIn("relative_dark_state", payload["redundancy_groups"])
        self.assertNotIn("composite", json.dumps(payload).lower())

    def test_unexplained_concepts_are_counted_explicitly(self):
        human = _human(None, explanation="unexplained")
        with tempfile.TemporaryDirectory() as td:
            payload = cal.build_calibration_payload(
                _comparison(), human, repository_root=_root(td)
            )
        self.assertEqual(
            payload["unexplained_concepts"],
            [{
                "concept": "movement",
                "observation_ids": ["A-movement"],
                "certificates": ["A"],
                "occurrences": 1,
            }],
        )


class CommittedCalibrationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    CALIBRATION = ROOT / "docs" / "360" / "calibration"

    def test_committed_inputs_build_a_four_stone_calibration(self):
        comparison = json.loads(
            (self.ROOT / "docs" / "360" / "profile" / "comparison.json").read_text()
        )
        observations = json.loads(
            (self.CALIBRATION / "human-observations.json").read_text()
        )
        payload = cal.build_calibration_payload(
            comparison, observations, repository_root=self.ROOT
        )
        self.assertEqual(payload["schema_version"], cal.CALIBRATION_SCHEMA)
        self.assertEqual(payload["sample"]["certificate_count"], 4)
        self.assertEqual(len(payload["observations"]), 17)
        self.assertEqual(
            payload["machine_evidence"]["status"],
            "pending_issue_21_compact_packet",
        )

    def test_recurring_unexplained_inner_panel_observation_is_not_forced_into_a_metric(self):
        benchmark = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        concepts = {
            item["concept"]: item
            for item in benchmark["unexplained_concepts"]
        }
        inner = concepts["quiet_or_pale_inner_region"]
        self.assertEqual(inner["occurrences"], 3)
        self.assertEqual(
            set(inner["certificates"]),
            {
                "IGI-LG756520111",
                "IGI-LG756580087",
                "IGI-LG836619414",
            },
        )
        observations = {
            item["id"]: item for item in benchmark["observations"]
        }
        for obs_id in inner["observation_ids"]:
            self.assertEqual(observations[obs_id]["descriptor_links"], [])

    def test_committed_benchmark_matches_current_inputs_semantically(self):
        comparison = json.loads(
            (self.ROOT / "docs" / "360" / "profile" / "comparison.json").read_text()
        )
        observations = json.loads(
            (self.CALIBRATION / "human-observations.json").read_text()
        )
        expected = cal.build_calibration_payload(
            comparison, observations, repository_root=self.ROOT
        )
        committed = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        self.assertEqual(committed, expected)

    def test_core_counterexamples_are_present(self):
        benchmark = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        by_id = {item["id"]: item for item in benchmark["observations"]}

        grouped = by_id["LG818659722-grouped-dark-stack"]
        fields = {link["field_id"]: link for link in grouped["descriptor_links"]}
        self.assertGreater(
            fields["directional.side_N_S_pearson"]["measurement"]["value"],
            0.9,
        )
        self.assertEqual(grouped["review_outcome"], "Reserve")

        independent = by_id["LG756580087-independent-layers"]
        self.assertLess(
            independent["descriptor_links"][0]["measurement"]["value"],
            -0.5,
        )
        self.assertEqual(independent["review_outcome"], "Shortlist")

        crisp = by_id["LG836619414-static-crispness"]
        self.assertEqual(crisp["profile_explanation"], "unexplained")


if __name__ == "__main__":
    unittest.main()
