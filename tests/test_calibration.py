import copy
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
            "id": dp.WINDOW_ID,
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


def _evidence():
    summary = {
        "schema_version": cal.EVIDENCE_SUMMARY_SCHEMA,
        "profile_schema": dp.PROFILE_SCHEMA,
        "packet_schema": cal.EVIDENCE_PACKET_SCHEMA,
        "window_contract": dp.WINDOW_ID,
        "stones": [],
    }
    packets = {}
    for certificate in ("A", "B"):
        item = {
            "rank": 1,
            "location": {"kind": "pair", "source_indices": [248, 249]},
            "coverage_families": [
                "activity_motion",
                "relative_dark_state",
                "dark_persistence",
                "nested_step",
                "directional",
                "flash_morphology",
            ],
            "selected_for": "activity_motion",
            "render_source_indices": [248, 249],
            "claims": [
                {
                    "descriptor_family": dp.FIELD_SPECS[field_id]["family"],
                    "event_type": "fixture",
                    "profile_field_ids": [field_id],
                }
                for field_id in dp.PRODUCTION_FIELD_IDS
            ],
        }
        packets[certificate] = {
            "schema_version": cal.EVIDENCE_PACKET_SCHEMA,
            "profile_schema": dp.PROFILE_SCHEMA,
            "certificate": certificate,
            "window_contract": dp.WINDOW_ID,
            "selected_count": 1,
            "covered_families": list(item["coverage_families"]),
            "items": [item],
        }
        summary["stones"].append({
            "certificate": certificate,
            "selected_count": 1,
            "packet": f"per-stone/{certificate}/evidence.json",
            "contact_sheet": f"per-stone/{certificate}/contact-sheet.jpg",
        })
    return summary, packets


def _root(tmp):
    root = Path(tmp)
    (root / "eval").mkdir(parents=True)
    (root / "eval" / "A.md").write_text("A")
    (root / "eval" / "B.md").write_text("B")
    return root


def _build(root, human, comparison=None, evidence=None):
    comparison = comparison or _comparison()
    summary, packets = evidence or _evidence()
    return cal.build_calibration_payload(
        comparison,
        human,
        evidence_summary=summary,
        evidence_packets=packets,
        repository_root=root,
    )


class CalibrationContractTests(unittest.TestCase):
    def test_join_preserves_profile_validity_ranks_and_exact_evidence(self):
        field_id = dp.PRODUCTION_FIELD_IDS[0]
        with tempfile.TemporaryDirectory() as td:
            payload = _build(_root(td), _human(field_id))
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
        self.assertEqual(link["machine_evidence"]["resolution"], "exact_field")
        item = link["machine_evidence"]["items"][0]
        self.assertEqual(item["human_frame_overlap"], [248])
        self.assertEqual(item["packet_item_rank"], 1)
        self.assertEqual(observation["source_frames_outside_profile_window"], [10])
        self.assertNotIn("score", json.dumps(payload).lower())

    def test_compact_packet_family_fallback_is_explicit_not_reselection(self):
        field_id = "activity.activation.middle_relative_total_excursion"
        summary, packets = _evidence()
        packets = copy.deepcopy(packets)
        packets["A"]["items"][0]["claims"] = [
            claim
            for claim in packets["A"]["items"][0]["claims"]
            if field_id not in claim["profile_field_ids"]
        ]
        with tempfile.TemporaryDirectory() as td:
            payload = _build(
                _root(td),
                _human(field_id),
                evidence=(summary, packets),
            )
        evidence = payload["observations"][0]["descriptor_links"][0]["machine_evidence"]
        self.assertEqual(evidence["resolution"], "family_representative")
        self.assertEqual(evidence["coverage_family"], "activity_motion")
        self.assertEqual(evidence["items"][0]["selected_for"], "activity_motion")

    def test_context_or_unknown_field_cannot_be_used_as_calibration_measurement(self):
        field_id = dp.CONTEXT_FIELD_IDS[0]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "retained #45 measurement"):
                _build(_root(td), _human(field_id))

    def test_unexplained_observation_cannot_hide_descriptor_links(self):
        field_id = dp.PRODUCTION_FIELD_IDS[0]
        human = _human(field_id, explanation="unexplained")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "unexplained"):
                _build(_root(td), human)

    def test_redundancy_metadata_is_preserved_not_aggregated(self):
        field_id = "dark_state.occupancy.inner_mean"
        with tempfile.TemporaryDirectory() as td:
            payload = _build(_root(td), _human(field_id))
        link = payload["observations"][0]["descriptor_links"][0]
        self.assertEqual(link["metadata"]["redundancy_group"], "relative_dark_state")
        self.assertIn("relative_dark_state", payload["redundancy_groups"])
        self.assertNotIn("composite", json.dumps(payload).lower())

    def test_unexplained_concepts_are_counted_explicitly(self):
        human = _human(None, explanation="unexplained")
        with tempfile.TemporaryDirectory() as td:
            payload = _build(_root(td), human)
        self.assertEqual(
            payload["unexplained_concepts"],
            [{
                "concept": "movement",
                "observation_ids": ["A-movement"],
                "certificates": ["A"],
                "occurrences": 1,
            }],
        )

    def test_missing_or_nonproduction_evidence_fails_loudly(self):
        summary, packets = _evidence()
        packets = copy.deepcopy(packets)
        packets["A"]["items"][0]["claims"][0]["profile_field_ids"] = ["not-production"]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "non-production"):
                _build(
                    _root(td),
                    _human(dp.PRODUCTION_FIELD_IDS[0]),
                    evidence=(summary, packets),
                )


class CommittedCalibrationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    CALIBRATION = ROOT / "docs" / "360" / "calibration"
    EVIDENCE = ROOT / "docs" / "360" / "evidence-packet"

    @classmethod
    def _inputs(cls):
        comparison = json.loads(
            (cls.ROOT / "docs" / "360" / "profile" / "comparison.json").read_text()
        )
        observations = json.loads(
            (cls.CALIBRATION / "human-observations.json").read_text()
        )
        summary = json.loads((cls.EVIDENCE / "summary.json").read_text())
        packets = {
            certificate: json.loads(
                (
                    cls.EVIDENCE
                    / "per-stone"
                    / certificate
                    / "evidence.json"
                ).read_text()
            )
            for certificate in [
                "IGI-LG756520111",
                "IGI-LG756580087",
                "IGI-LG818659722",
                "IGI-LG836619414",
            ]
        }
        return comparison, observations, summary, packets

    def test_committed_inputs_build_a_four_stone_integrated_calibration(self):
        comparison, observations, summary, packets = self._inputs()
        payload = cal.build_calibration_payload(
            comparison,
            observations,
            evidence_summary=summary,
            evidence_packets=packets,
            repository_root=self.ROOT,
        )
        self.assertEqual(payload["schema_version"], cal.CALIBRATION_SCHEMA)
        self.assertEqual(payload["sample"]["certificate_count"], 4)
        self.assertEqual(len(payload["observations"]), 17)
        self.assertEqual(payload["machine_evidence"]["status"], "integrated_issue_21")
        self.assertEqual(
            payload["machine_evidence"]["selected_counts"],
            {
                "IGI-LG756520111": 4,
                "IGI-LG756580087": 4,
                "IGI-LG818659722": 5,
                "IGI-LG836619414": 4,
            },
        )
        audit = payload["machine_evidence"]["audit"]
        self.assertEqual(audit["missing_links"], 0)
        self.assertEqual(
            audit["exact_field_links"] + audit["family_representative_links"],
            audit["linked_descriptor_count"],
        )

    def test_every_link_resolves_to_compact_machine_evidence(self):
        benchmark = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        for observation in benchmark["observations"]:
            self.assertTrue(
                (self.ROOT / observation["evidence_packet"]["packet_path"]).exists()
            )
            self.assertTrue(
                (self.ROOT / observation["evidence_packet"]["contact_sheet_path"]).exists()
            )
            for link in observation["descriptor_links"]:
                machine = link["machine_evidence"]
                self.assertIn(
                    machine["resolution"],
                    {"exact_field", "family_representative"},
                )
                self.assertTrue(machine["items"])
                for item in machine["items"]:
                    self.assertTrue(item["render_source_indices"])

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
        comparison, observations, summary, packets = self._inputs()
        expected = cal.build_calibration_payload(
            comparison,
            observations,
            evidence_summary=summary,
            evidence_packets=packets,
            repository_root=self.ROOT,
        )
        committed = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        self.assertEqual(committed, expected)

    def test_core_counterexamples_and_evidence_are_present(self):
        benchmark = json.loads((self.CALIBRATION / "benchmark.json").read_text())
        by_id = {item["id"]: item for item in benchmark["observations"]}

        grouped = by_id["LG818659722-grouped-dark-stack"]
        fields = {link["field_id"]: link for link in grouped["descriptor_links"]}
        self.assertGreater(
            fields["directional.side_N_S_pearson"]["measurement"]["value"],
            0.9,
        )
        self.assertEqual(
            fields["directional.side_N_S_pearson"]["machine_evidence"]["resolution"],
            "exact_field",
        )
        self.assertEqual(grouped["review_outcome"], "Reserve")

        independent = by_id["LG756580087-independent-layers"]
        self.assertLess(
            independent["descriptor_links"][0]["measurement"]["value"],
            -0.5,
        )
        self.assertEqual(
            independent["descriptor_links"][0]["machine_evidence"]["resolution"],
            "exact_field",
        )
        self.assertEqual(independent["review_outcome"], "Shortlist")

        crisp = by_id["LG836619414-static-crispness"]
        self.assertEqual(crisp["profile_explanation"], "unexplained")
        self.assertEqual(crisp["descriptor_links"], [])


if __name__ == "__main__":
    unittest.main()
