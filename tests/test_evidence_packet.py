import json
import tempfile
import unittest
from pathlib import Path

from diamond360 import descriptor_profile as dp
from diamond360 import evidence_packet as ep


INDICES = [255, 0, 1]


def _validity(status="ok", reasons=None):
    return {"status": status, "reasons": list(reasons or [])}


def _frame(source_index=0, position=1, value=0.5):
    return {"position": position, "source_index": source_index, "value": value}


def _move(left=255, right=0, right_position=1, delta=0.2):
    return {
        "position": right_position,
        "source_index": right,
        "value": 0.5,
        "delta": delta,
    }


def _pair(left=255, right=0, left_position=0, right_position=1, **extra):
    return {
        "left_position": left_position,
        "right_position": right_position,
        "left_source_index": left,
        "right_source_index": right,
        **extra,
    }


def build_results():
    activation_regions = {}
    for region in ("centre", "inner", "middle"):
        activation_regions[region] = {
            "fixed": {
                "relative_validity": _validity(),
                "relative_evidence": {
                    "q90": _frame(),
                    "largest_positive_move": _move(),
                },
            }
        }
    activation = {
        "schema_version": dp.SOURCE_SPECS["activation"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "whole_stone": {
            "validity": _validity(),
            "evidence": {"q90": _frame()},
        },
        "representations": {
            "coarse": {"regions": activation_regions}
        },
    }

    occupancy_regions = {}
    for region in ("centre", "inner", "middle"):
        occupancy_regions[region] = {
            "fixed": {
                "thresholds": {
                    "0.65": {
                        "validity": _validity(),
                        "evidence": {"q90": _frame()},
                        "evidence_panel": f"evidence/coarse-{region}-fixed.png",
                    }
                }
            }
        }
    occupancy = {
        "schema_version": dp.SOURCE_SPECS["occupancy"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "baseline_threshold": 0.65,
        "representations": {"coarse": {"regions": occupancy_regions}},
    }

    switching_regions = {}
    for region in ("inner", "middle"):
        switching_regions[region] = {
            "fixed": {
                "thresholds": {
                    "0.65": {
                        "validity": _validity(),
                        "evidence": {
                            "highest": _pair(
                                switch_fraction=0.4,
                                eligible_pixels=10,
                                switched_pixels=4,
                            )
                        },
                        "evidence_panel": f"evidence/coarse-{region}-fixed.png",
                    }
                }
            }
        }
    switching = {
        "schema_version": dp.SOURCE_SPECS["switching"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "baseline_threshold": 0.65,
        "representations": {"coarse": {"regions": switching_regions}},
    }

    mobility_traces = {}
    for region in ("centre", "inner", "middle"):
        trace_id = f"coarse/{region}/fixed/relative"
        mobility_traces[trace_id] = {
            "validity": _validity(),
            "evidence": {
                "largest": _pair(
                    left=0,
                    right=1,
                    left_position=1,
                    right_position=2,
                    mobility=0.3,
                    signed_delta=-0.3,
                )
            },
            "evidence_panel": f"evidence/{trace_id.replace('/', '-')}.png",
        }
    mobility = {
        "schema_version": dp.SOURCE_SPECS["mobility"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "traces": mobility_traces,
    }

    persistence = {
        "schema_version": dp.SOURCE_SPECS["persistence"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "baseline_threshold": 0.65,
        "representations": {
            "coarse": {
                "regions": {
                    "inner": {
                        "fixed": {
                            "thresholds": {
                                "0.65": {
                                    "validity": _validity(),
                                    "evidence": {
                                        "dark": {
                                            "start_position": 0,
                                            "middle_position": 0,
                                            "end_position": 1,
                                            "start_source_index": 255,
                                            "middle_source_index": 255,
                                            "end_source_index": 0,
                                            "observed_run_length_frames": 2,
                                        }
                                    },
                                    "evidence_panel": "evidence/coarse-inner-fixed.png",
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    coordination_pairs = {}
    for pair_id in ("centre__inner", "inner__middle"):
        coordination_pairs[pair_id] = {
            "level_validity": _validity(),
            "change_validity": _validity(),
            "evidence": {
                "strongest_coordinated": _pair(
                    delta_a=0.2,
                    delta_b=0.15,
                    relationship="same",
                    joint_move_strength=0.15,
                )
            },
        }
    coordination = {
        "schema_version": dp.SOURCE_SPECS["coordination"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "representations": {
            "coarse": {
                "fixed": {"pairs": coordination_pairs}
            }
        },
    }

    opposing_pairs = {}
    for pair_id in ("side_E_W", "side_N_S", "corner_NE_SW", "corner_NW_SE"):
        opposing_pairs[pair_id] = {
            "validity": _validity(),
            "evidence": {
                "strongest_coordinated": _pair(
                    left_delta=0.2,
                    right_delta=0.1,
                    direction="same",
                    coordination_strength=0.1,
                    divergence_strength=0.1,
                    movement_strength=0.2,
                )
            },
            "evidence_panel": f"evidence/coarse_whole-fixed-{pair_id}.png",
        }
    opposing = {
        "schema_version": dp.SOURCE_SPECS["opposing"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "surfaces": {
            "coarse_whole": {
                "support_modes": {
                    "fixed": {"pairs": opposing_pairs}
                }
            }
        },
    }

    morphology = {
        "schema_version": dp.SOURCE_SPECS["morphology"]["descriptor_schema"],
        "requested_indices": INDICES,
        "accepted_indices": INDICES,
        "excluded": [],
        "wrap_explicit": True,
        "baseline_threshold": 1.0,
        "connectivity": 8,
        "supports": {
            "fixed": {
                "thresholds": {
                    "1.00": {"validity": _validity()}
                },
                "baseline_evidence": {
                    "broadest": {
                        "position": 1,
                        "source_index": 0,
                        "largest_component_fraction": 0.8,
                        "effective_component_count": 1.4,
                    },
                    "most_fragmented": {
                        "position": 2,
                        "source_index": 1,
                        "largest_component_fraction": 0.2,
                        "effective_component_count": 6.0,
                    },
                    "matched_active_area_pair": {
                        "largest_component_fraction_difference": 0.6,
                        "left": {"position": 1, "source_index": 0},
                        "right": {"position": 2, "source_index": 1},
                    },
                },
            }
        },
    }

    return {
        "activation": activation,
        "occupancy": occupancy,
        "switching": switching,
        "persistence": persistence,
        "mobility": mobility,
        "coordination": coordination,
        "opposing": opposing,
        "morphology": morphology,
    }


def build_profile():
    return {
        "schema_version": dp.PROFILE_SCHEMA,
        "measurements": {
            field_id: {"value": 0.0, "status": "ok", "reasons": []}
            for field_id in dp.PRODUCTION_FIELD_IDS
        },
    }


class EvidenceLocationTests(unittest.TestCase):
    def test_location_contract_is_explicit(self):
        self.assertEqual(
            ep.EvidenceLocation("pair", (255, 0)).to_dict(),
            {"kind": "pair", "source_indices": [255, 0]},
        )
        with self.assertRaises(ValueError):
            ep.EvidenceLocation("frame", (1, 2))
        with self.assertRaises(ValueError):
            ep.EvidenceLocation("pair", (1,))

    def test_circular_distance_handles_wrap(self):
        frame = ep.EvidenceLocation("frame", (255,))
        wrapped = ep.EvidenceLocation("frame", (0,))
        far = ep.EvidenceLocation("frame", (20,))
        self.assertEqual(ep.location_distance(frame, wrapped), 1)
        self.assertEqual(ep.location_distance(frame, far), 21)


class AdapterTests(unittest.TestCase):
    def test_all_retained_profile_fields_receive_native_evidence(self):
        candidates = ep.collect_candidates(build_results())
        observed = {
            field_id
            for candidate in candidates
            for field_id in candidate.profile_field_ids
        }
        self.assertEqual(observed, set(dp.PRODUCTION_FIELD_IDS))
        self.assertNotIn(
            "flash_morphology.active_frame_fraction",
            observed,
        )

    def test_wrap_pair_and_run_provenance_are_preserved(self):
        candidates = ep.collect_candidates(build_results())
        activation_move = next(
            item for item in candidates
            if item.descriptor_family == "activation"
            and item.event_type == "largest_positive_move"
        )
        self.assertEqual(
            activation_move.location,
            ep.EvidenceLocation("pair", (255, 0)),
        )
        persistence = next(
            item for item in candidates
            if item.descriptor_family == "persistence"
        )
        self.assertEqual(
            persistence.location,
            ep.EvidenceLocation("run", (255, 0)),
        )

    def test_revise_or_reject_cannot_enter_through_adapter_mapping(self):
        candidates = ep.collect_candidates(build_results())
        for candidate in candidates:
            for field_id in candidate.profile_field_ids:
                self.assertIn(field_id, dp.PRODUCTION_FIELD_IDS)
                spec = dp.FIELD_SPECS[field_id]
                self.assertNotEqual(spec.get("region"), "outer")
                self.assertNotEqual(spec.get("representation"), "semantic")
                self.assertNotEqual(spec.get("support_policy"), "dynamic")
                self.assertNotEqual(spec.get("support_policy"), "pair_local")


class ProfileIntegrationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_real_45_profile_accepts_every_retained_evidence_mapping(self):
        profile = json.loads(
            (
                self.ROOT
                / "docs"
                / "360"
                / "profile"
                / "per-stone"
                / "IGI-LG818659722.json"
            ).read_text()
        )
        candidates = ep.apply_profile_contract(
            ep.collect_candidates(build_results()),
            profile,
        )
        observed = {
            field_id
            for candidate in candidates
            for field_id in candidate.profile_field_ids
        }
        self.assertEqual(observed, set(dp.PRODUCTION_FIELD_IDS))
        self.assertTrue(
            all(
                candidate.provenance.get("profile_schema") == dp.PROFILE_SCHEMA
                for candidate in candidates
            )
        )


class ConsolidationTests(unittest.TestCase):
    def test_exact_duplicate_merge_preserves_all_supporting_claims(self):
        candidates = ep.collect_candidates(build_results())
        items = ep.merge_exact_duplicates(candidates)
        frame_zero = next(
            item for item in items
            if item.location == ep.EvidenceLocation("frame", (0,))
        )
        families = {claim.descriptor_family for claim in frame_zero.claims}
        self.assertTrue(
            {"activation", "occupancy", "morphology"}.issubset(families)
        )
        self.assertLess(len(items), len(candidates))

    def test_near_grouping_is_non_destructive_and_does_not_chain(self):
        make = lambda index, name: ep.EvidenceItem(
            ep.EvidenceLocation("frame", (index,)),
            (
                ep.EvidenceCandidate(
                    descriptor_family="test",
                    native_id=name,
                    event_type="event",
                    location=ep.EvidenceLocation("frame", (index,)),
                    profile_field_ids=(),
                    rationale="test",
                ),
            ),
        )
        groups = ep.group_near_duplicates(
            [make(0, "zero"), make(1, "one"), make(2, "two")],
            max_distance=1,
        )
        self.assertEqual([len(group.items) for group in groups], [2, 1])
        self.assertEqual(
            sum(len(group.items) for group in groups),
            3,
        )

    def test_profile_validity_is_monotone_and_unknown_fields_are_filtered(self):
        profile = build_profile()
        field_id = dp.PRODUCTION_FIELD_IDS[0]
        profile["measurements"][field_id] = {
            "value": 1.0,
            "status": "review",
            "reasons": ["profile_review"],
        }
        candidate = ep.EvidenceCandidate(
            descriptor_family="activation",
            native_id="test",
            event_type="q90",
            location=ep.EvidenceLocation("frame", (0,)),
            profile_field_ids=(field_id, "not-a-retained-field"),
            rationale="test",
            validity_status="ok",
        )
        result = ep.apply_profile_contract([candidate], profile)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].profile_field_ids, (field_id,))
        self.assertEqual(result[0].validity_status, "review")
        self.assertIn("profile_review", result[0].validity_reasons)

        unavailable = ep.EvidenceCandidate(
            descriptor_family="activation",
            native_id="test2",
            event_type="q10",
            location=ep.EvidenceLocation("frame", (1,)),
            profile_field_ids=(field_id,),
            rationale="test",
            validity_status="unavailable",
            validity_reasons=("native_unavailable",),
        )
        result = ep.apply_profile_contract([unavailable], profile)
        self.assertEqual(result[0].validity_status, "unavailable")
        self.assertIn("native_unavailable", result[0].validity_reasons)

    def test_inventory_is_json_safe_and_records_counts(self):
        profile = build_profile()
        payload = ep.build_inventory(build_results(), profile=profile)
        self.assertEqual(payload["schema_version"], ep.SCHEMA)
        self.assertEqual(payload["profile_schema"], dp.PROFILE_SCHEMA)
        self.assertGreater(payload["candidate_count"], 20)
        self.assertLess(
            payload["exact_item_count"],
            payload["candidate_count"],
        )
        self.assertLessEqual(
            payload["near_group_count"],
            payload["exact_item_count"],
        )
        encoded = json.dumps(payload, allow_nan=False)
        self.assertNotIn("NaN", encoded)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            ep.write_inventory(payload, path)
            self.assertEqual(
                json.loads(path.read_text())["candidate_count"],
                payload["candidate_count"],
            )


class CompactSelectionTests(unittest.TestCase):
    def test_compact_selection_covers_all_available_roles(self):
        profile = build_profile()
        candidates = ep.apply_profile_contract(
            ep.collect_candidates(build_results()),
            profile,
        )
        items = ep.merge_exact_duplicates(candidates)
        groups = ep.group_near_duplicates(items)
        selected = ep.select_compact_evidence(
            items,
            profile,
            groups,
            min_items=4,
            max_items=6,
        )
        covered = {
            role
            for item in selected
            for role in item.coverage_families
        }
        self.assertEqual(covered, set(ep.COVERAGE_ORDER))
        self.assertGreaterEqual(len(selected), 1)
        self.assertLessEqual(len(selected), 6)
        self.assertEqual(
            len({item.item.location.key for item in selected}),
            len(selected),
        )
        self.assertTrue(
            any(len(item.coverage_families) > 1 for item in selected)
        )

    def test_morphology_prefers_one_matched_area_contrast_event(self):
        profile = build_profile()
        candidates = ep.apply_profile_contract(
            ep.adapt_morphology(build_results()["morphology"]),
            profile,
        )
        items = ep.merge_exact_duplicates(candidates)
        selected = ep.select_compact_evidence(
            items,
            profile,
            min_items=1,
            max_items=1,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(
            selected[0].item.location,
            ep.EvidenceLocation("pair", (0, 1)),
        )
        self.assertTrue(
            any(
                claim.event_type == "matched_active_area_pair"
                for claim in selected[0].item.claims
            )
        )

    def test_correlation_event_choice_follows_profile_sign(self):
        field_id = "nested_step.centre_inner_pearson"
        profile = build_profile()
        profile["measurements"][field_id]["value"] = -0.75

        coordinated = ep.EvidenceCandidate(
            descriptor_family="coordination",
            native_id="coarse/fixed/centre__inner",
            event_type="strongest_coordinated",
            location=ep.EvidenceLocation("pair", (0, 1)),
            profile_field_ids=(field_id,),
            rationale="test coordinated",
        )
        divergent = ep.EvidenceCandidate(
            descriptor_family="coordination",
            native_id="coarse/fixed/centre__inner",
            event_type="strongest_divergent",
            location=ep.EvidenceLocation("pair", (1, 2)),
            profile_field_ids=(field_id,),
            rationale="test divergent",
        )
        selected = ep.select_compact_evidence(
            ep.merge_exact_duplicates([coordinated, divergent]),
            profile,
            min_items=1,
            max_items=1,
        )
        self.assertEqual(
            selected[0].item.location,
            ep.EvidenceLocation("pair", (1, 2)),
        )

        profile["measurements"][field_id]["value"] = 0.75
        selected = ep.select_compact_evidence(
            ep.merge_exact_duplicates([coordinated, divergent]),
            profile,
            min_items=1,
            max_items=1,
        )
        self.assertEqual(
            selected[0].item.location,
            ep.EvidenceLocation("pair", (0, 1)),
        )

    def test_packet_and_contact_sheet_use_original_source_frames(self):
        import hashlib
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frames = root / "frames"
            frames.mkdir()
            manifest_frames = []
            for index, shade in ((255, 70), (0, 140), (1, 210)):
                path = frames / f"frame-{index:03d}.jpg"
                Image.new("RGB", (120, 100), (shade, shade, shade)).save(
                    path,
                    quality=95,
                )
                raw = path.read_bytes()
                manifest_frames.append({
                    "source_index": index,
                    "path": f"frames/{path.name}",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                    "source_url": f"https://example.invalid/batch/{index}",
                })
            manifest = {
                "schema_version": "diamond360-source/1",
                "certificate": "TEST",
                "source_pipeline": "synthetic",
                "source_frame_count": 256,
                "frames": manifest_frames,
            }
            packet = ep.build_packet(
                build_results(),
                build_profile(),
                manifest,
                source_manifest_ref="synthetic/source-manifest.json",
            )
            out = root / "out"
            ep.write_packet(packet, out, source_root=root)
            self.assertTrue((out / "evidence.json").is_file())
            self.assertTrue((out / "contact-sheet.jpg").is_file())
            self.assertGreater(
                (out / "contact-sheet.jpg").stat().st_size,
                1000,
            )
            encoded = json.loads((out / "evidence.json").read_text())
            self.assertEqual(encoded["schema_version"], ep.PACKET_SCHEMA)
            self.assertEqual(encoded["certificate"], "TEST")
            self.assertGreaterEqual(encoded["selected_count"], 1)
            self.assertLessEqual(encoded["selected_count"], 6)
            self.assertEqual(
                set(encoded["covered_families"]),
                set(ep.COVERAGE_ORDER),
            )
            for item in encoded["items"]:
                self.assertTrue(item["original_frames"])
                for frame in item["original_frames"]:
                    self.assertIn(frame["source_index"], {255, 0, 1})
                    self.assertIn("sha256", frame)


if __name__ == "__main__":
    unittest.main()
