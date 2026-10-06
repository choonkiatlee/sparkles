import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from diamond360 import tier_readability_calibration as trc


def _candidate(indices, values, q25_factor=0.5):
    rows = []
    for i, (source_index, value) in enumerate(zip(indices, values)):
        rows.append({
            "position": i,
            "source_index": source_index,
            "separation": value,
            "median_separation": value,
            "q25_separation": value * q25_factor,
        })
    return {"frame_trace": rows}


def _result(offset=0.0):
    indices = [0, 1, 2, 3, 4, 5]
    ci = [0.05 + offset, 0.12 + offset, 0.25 + offset,
          0.10 + offset, 0.40 + offset, 0.18 + offset]
    im = [0.08 + offset, 0.15 + offset, 0.20 + offset,
          0.35 + offset, 0.12 + offset, 0.22 + offset]

    def pair(values):
        simple = _candidate(indices, values)
        localized = _candidate(indices, [v * 0.9 for v in values])
        semantic_rows = []
        for pos, (source_index, value) in enumerate(zip(indices, values)):
            semantic_rows.append({
                "position": pos,
                "source_index": source_index,
                "median_separation": value,
                "q25_separation": value * (0.2 if pos == 3 else 0.6),
            })
        return {
            "simple": simple,
            "localized": localized,
            "boundary_local": {
                "multi_scale": {
                    "semantic": {"frame_trace": semantic_rows}
                }
            },
        }

    joint_rows = []
    for pos, source_index in enumerate(indices):
        joint = min(ci[pos], im[pos]) * 0.7
        joint_rows.append({
            "position": pos,
            "source_index": source_index,
            "median_joint_separation": joint,
            "q25_joint_separation": joint * 0.5,
            "joint_median_penalty": 0.25 if pos == 4 else 0.01 * pos,
            "ordering_fractions": {
                "monotonic_light_to_dark_outward": 0.5,
                "monotonic_dark_to_light_outward": 0.0,
                "inner_local_minimum": 0.25,
                "inner_local_maximum": 0.25,
                "tied": 0.0,
            },
        })
    return {
        "requested_indices": indices,
        "pairs": {
            "centre__inner": pair(ci),
            "inner__middle": pair(im),
        },
        "tier_readability_profile": {"frame_trace": joint_rows},
    }


def _write_fixture(root, certificates=("A", "B", "C", "D")):
    benchmark = root / "benchmark"
    source = root / "source"
    for n, certificate in enumerate(certificates):
        destination = benchmark / "per-stone" / certificate / "wide"
        destination.mkdir(parents=True)
        (destination / "tier-contrast.json").write_text(
            json.dumps(_result(offset=n * 0.01))
        )

        stone = source / certificate
        frames = stone / "frames"
        frames.mkdir(parents=True)
        manifest_rows = []
        for source_index in range(6):
            path = frames / f"{certificate}-{source_index}.jpg"
            Image.new(
                "RGB", (80, 80), (20 + 20 * n, 30 + 10 * source_index, 60)
            ).save(path)
            manifest_rows.append({
                "source_index": source_index,
                "path": f"frames/{certificate}-{source_index}.jpg",
                "sha256": f"{n + 1:02x}{source_index:02x}",
            })
        (stone / "source-manifest.json").write_text(json.dumps({
            "certificate": certificate,
            "frames": manifest_rows,
        }))
    return benchmark, source


class TierReadabilityCalibrationTests(unittest.TestCase):
    def test_extracts_all_pr_b_formulations(self):
        rows = trc.extract_frame_features(_result())
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            set(trc.FORMULATIONS).difference(rows[0]),
            set(),
        )
        self.assertAlmostEqual(
            rows[0]["boundary_q25_weakest"],
            min(0.05, 0.08) * 0.6,
        )
        self.assertAlmostEqual(
            rows[3]["coverage_gap"],
            rows[3]["boundary_median_weakest"]
            - rows[3]["boundary_q25_weakest"],
        )

    def test_selection_is_unique_balanced_and_label_blind(self):
        features = {
            certificate: trc.extract_frame_features(_result(offset=n * .01))
            for n, certificate in enumerate(("A", "B", "C", "D"))
        }
        first = trc.select_informative_frames(features)
        second = trc.select_informative_frames(features)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 20)
        self.assertEqual(len({row["item_id"] for row in first}), 20)
        for certificate in features:
            rows = [row for row in first if row["certificate"] == certificate]
            self.assertEqual(len(rows), 5)
            self.assertEqual(
                {row["selection_reason"] for row in rows},
                set(trc._SELECTION_REASONS),
            )

    def test_packet_hides_descriptor_values_from_label_template(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            benchmark, source = _write_fixture(root)
            out = root / "packet"
            manifest = trc.build_label_packet(benchmark, source, out)
            template = json.loads((out / "labels-template.json").read_text())
            self.assertEqual(manifest["schema_version"], trc.PACKET_SCHEMA)
            self.assertEqual(len(manifest["items"]), 20)
            self.assertTrue((out / "contact-sheet.jpg").exists())
            text = json.dumps(template)
            self.assertNotIn("certificate", text)
            self.assertNotIn("boundary_q25", text)
            self.assertEqual(
                {row["item_id"] for row in template["labels"]},
                {row["item_id"] for row in manifest["items"]},
            )

    def test_ai_assisted_or_pending_labels_are_rejected(self):
        manifest = {
            "schema_version": trc.PACKET_SCHEMA,
            "items": [{"item_id": "T01"}],
        }
        labels = {
            "schema_version": trc.LABEL_SCHEMA,
            "provenance": {
                "kind": "human_entered",
                "ai_assistance": True,
                "status": "complete",
                "reviewer_session": "fixture",
            },
            "labels": [{
                "item_id": "T01",
                "separation": "clear",
                "three_layers": "obvious",
            }],
        }
        with self.assertRaisesRegex(ValueError, "AI-assisted"):
            trc.validate_human_labels(labels, manifest)
        labels["provenance"]["ai_assistance"] = False
        labels["provenance"]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "not marked complete"):
            trc.validate_human_labels(labels, manifest)

    def test_leave_one_diamond_out_never_trains_on_held_out_stone(self):
        rows = []
        for ci, certificate in enumerate(("A", "B", "C", "D")):
            for level in range(3):
                rows.append({
                    "certificate": certificate,
                    "predictor": float(level) + ci * .01,
                    "label": float(level),
                })
        result = trc.leave_one_diamond_out(
            rows, "predictor", "label", binary=False
        )
        self.assertAlmostEqual(result["aggregate_concordance"], 1.0)
        for fold in result["folds"]:
            self.assertNotIn(
                fold["held_out_certificate"],
                fold["training_certificates"],
            )
            self.assertEqual(len(fold["training_certificates"]), 3)

    def test_build_calibration_requires_complete_human_labels_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            benchmark, source = _write_fixture(root)
            packet = root / "packet"
            manifest = trc.build_label_packet(benchmark, source, packet)
            template = json.loads((packet / "labels-template.json").read_text())
            template["provenance"] = {
                "kind": "human_entered",
                "ai_assistance": False,
                "status": "complete",
                "reviewer_session": "fixture-human",
            }
            for i, row in enumerate(template["labels"]):
                row["separation"] = ("collapsed", "partial", "clear")[i % 3]
                row["three_layers"] = ("ambiguous", "obvious")[i % 2]
            labels = root / "labels.json"
            labels.write_text(json.dumps(template))
            out = root / "calibration"
            result = trc.build_calibration(
                benchmark,
                packet / "manifest.json",
                labels,
                out,
            )
            self.assertEqual(result["schema_version"], trc.CALIBRATION_SCHEMA)
            self.assertEqual(result["sample"]["certificate_count"], 4)
            self.assertEqual(result["sample"]["frame_count"], 20)
            self.assertTrue((out / "calibration.json").exists())
            self.assertTrue((out / "calibration.csv").exists())
            for formulation in trc.FORMULATIONS:
                self.assertEqual(
                    result["results"][formulation]["separation"]["split"],
                    "leave_one_diamond_out",
                )


if __name__ == "__main__":
    unittest.main()
