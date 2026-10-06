import csv
import json
import tempfile
import unittest
from pathlib import Path

from diamond360 import descriptor_profile as dp


CORE = [248,249,250,251,252,253,254,255,0,1,2,3,4,5,6,7,8]


def _write(root, family, payload):
    path = root / "docs" / "360" / family / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _status(cert):
    return ("review", "foreground_or_nonuniformity_on_border;outline_near_image_edge") if cert == "B" else ("ok", "")


def build_fixture(root: Path):
    certs = ["A", "B"]
    activation_rows = []
    mobility_rows = []
    occupancy_rows = []
    switching_rows = []
    persistence_rows = []
    opposing_rows = []
    for ci, cert in enumerate(certs, start=1):
        status, reasons = _status(cert)
        activation_rows.append({
            "certificate": cert, "window": "core", "representation": "whole_stone",
            "region": "whole_stone", "support_mode": "fixed", "trace_type": "raw",
            "status": status, "reasons": reasons, "total_excursion": ci * 0.01,
            "mad_scale": ci * 0.001, "persistent_support_fraction": None,
        })
        for ri, region in enumerate(("centre", "inner", "middle"), start=1):
            activation_rows.append({
                "certificate": cert, "window": "core", "representation": "coarse",
                "region": region, "support_mode": "fixed", "trace_type": "relative",
                "status": status, "reasons": reasons,
                "total_excursion": ci * 0.1 + ri * 0.01,
                "mad_scale": ci * 0.01, "persistent_support_fraction": 1.0,
            })
            mobility_rows.append({
                "certificate": cert, "window": "core",
                "trace_id": f"coarse/{region}/fixed/relative",
                "representation": "coarse", "region": region,
                "support_mode": "fixed", "trace_type": "relative", "primary": True,
                "upstream_disposition": "KEEP", "status": status, "reasons": reasons,
                "observed_adjacent_pairs": 16,
                "median_mobility": ci * 0.02 + ri * 0.001,
                "q90_mobility": ci * 0.03, "activation_total_excursion": ci * 0.1,
                "switching_rate": None, "persistent_support_fraction": 1.0,
            })
            occupancy_rows.append({
                "certificate": cert, "window": "core", "threshold": 0.65,
                "representation": "coarse", "region": region, "support_mode": "fixed",
                "status": status, "reasons": reasons, "finite_frames": 17,
                "mean": ci * 0.05 + ri * 0.002, "median": 0.0,
                "q10": 0.0, "q50": 0.0, "q90": 0.1, "persistent_support_fraction": 1.0,
            })
        for ri, region in enumerate(("inner", "middle"), start=1):
            switching_rows.append({
                "certificate": cert, "window": "core", "representation": "coarse",
                "region": region, "support_mode": "fixed", "threshold": 0.65,
                "status": status, "reasons": reasons,
                "regional_switch_rate": ci * 0.04 + ri * 0.003,
                "pixel_rate_q50": 0.0, "pixel_rate_q90": 0.2,
                "pixel_fraction_nonzero": 0.5, "observed_adjacent_pairs": 16,
                "eligible_pixel_pairs": 100, "persistent_support_fraction": 1.0,
            })
        persistence_rows.append({
            "threshold": 0.65, "representation": "coarse", "region": "inner",
            "support_mode": "fixed", "status": status, "reasons": reasons,
            "requested_source_steps": 17, "state": "dark", "q90_window_fraction": ci * 0.1,
            "certificate": cert, "window": "core",
        })
        for pi, pair in enumerate(("side_E_W", "side_N_S", "corner_NE_SW", "corner_NW_SE"), start=1):
            opposing_rows.append({
                "certificate": cert, "window": "core", "surface_id": "coarse_whole",
                "representation": "coarse", "radial_band": None, "support_mode": "fixed",
                "pair_id": pair, "status": status, "reasons": reasons, "paired_frames": 17,
                "correlation": (-1 if ci == 1 else 1) * (0.1 * pi),
                "median_absolute_difference": 0.0, "median_signed_difference": 0.0,
                "sign_agreement": 0.5, "directional_pairs": 16, "flat_pairs": 0,
                "worse_persistent_support_fraction": 0.8,
            })

    _write(root, "activation", {
        "schema_version": "diamond360-activation-benchmark/1",
        "core_indices": CORE, "wide_indices": [], "stones": certs, "rows": activation_rows,
    })
    _write(root, "mobility", {
        "schema_version": "sparkles-contrast-mobility-benchmark/1",
        "issue": 30, "core_indices": CORE, "wide_indices": [], "stones": certs,
        "rows": mobility_rows,
    })
    _write(root, "occupancy", {
        "schema_version": "sparkles-relative-dark-occupancy-benchmark/1",
        "stones": certs, "core_indices": CORE, "wide_indices": [],
        "thresholds": [0.6, 0.65, 0.7], "baseline_threshold": 0.65,
        "rows": occupancy_rows,
    })
    _write(root, "switching", {
        "schema_version": "sparkles-bright-dark-switching-benchmark/1",
        "issue": 28, "core_indices": CORE, "wide_indices": [], "stones": certs,
        "thresholds": [0.6, 0.65, 0.7], "baseline_threshold": 0.65,
        "rows": switching_rows,
    })
    _write(root, "persistence", {
        "schema_version": "sparkles-bright-dark-persistence-benchmark/1",
        "issue": 29, "core_indices": CORE, "wide_indices": [],
        "thresholds": [0.6, 0.65, 0.7], "baseline_threshold": 0.65,
        "baseline_rows": persistence_rows,
    })
    # Reverse order deliberately: adapter must map values through the declared stone order.
    _write(root, "coordination", {
        "schema_version": "diamond360-concentric-coordination-summary/1",
        "core_indices": CORE, "wide_indices": [], "stones": ["B", "A"],
        "primary_pairs": {
            "centre__inner": {"core_pearson_r": [0.81, 0.11]},
            "inner__middle": {"core_pearson_r": [-0.82, -0.12]},
        },
    })
    _write(root, "opposing-symmetry", {
        "schema_version": "diamond360-opposing-region-symmetry-benchmark/1",
        "core_indices": CORE, "wide_indices": [], "stones": certs, "rows": opposing_rows,
    })
    morphology_stones = []
    for ci, cert in enumerate(certs, start=1):
        status, reasons = _status(cert)
        morphology_stones.append({
            "certificate": cert,
            "windows": {"core": {"supports": {"fixed": {"1.00": {
                "validity": {"status": status, "reasons": [r for r in reasons.split(";") if r]},
                "persistent_support_fraction": 0.9,
                "summary": {
                    "status": "ok", "observed_frames": 17, "active_frames": 16,
                    "active_frame_fraction": 16 / 17,
                    "median_largest_component_fraction": ci * 0.15,
                },
            }}}}},
        })
    _write(root, "morphology", {
        "schema_version": "diamond360-flash-morphology-benchmark/1",
        "core_indices": CORE, "wide_indices": [], "thresholds": [0.9, 1.0, 1.1],
        "baseline_threshold": 1.0, "connectivity": 8, "stones": morphology_stones,
    })


class DescriptorProfileTests(unittest.TestCase):
    def test_builds_only_explicit_production_and_context_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            out = root / "out"
            dp.build_profiles(root, out)
            profile = json.loads((out / "per-stone" / "A.json").read_text())
            self.assertEqual(profile["schema_version"], dp.PROFILE_SCHEMA)
            self.assertEqual(set(profile["measurements"]), set(dp.PRODUCTION_FIELD_IDS))
            self.assertEqual(set(profile["context"]), set(dp.CONTEXT_FIELD_IDS))
            catalog = json.dumps(profile["field_catalog"])
            self.assertNotIn('"outer"', catalog)
            self.assertNotIn('"semantic"', catalog)
            self.assertNotIn('"dynamic"', catalog)
            self.assertNotIn('"pair_local"', catalog)

    def test_extra_revised_or_rejected_rows_do_not_change_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            before = root / "before"
            dp.build_profiles(root, before)
            source = root / "docs" / "360" / "activation" / "summary.json"
            payload = json.loads(source.read_text())
            payload["rows"].extend([
                {
                    "certificate": "A", "window": "core", "representation": "coarse",
                    "region": "outer", "support_mode": "fixed", "trace_type": "relative",
                    "status": "ok", "reasons": "", "total_excursion": 999.0,
                },
                {
                    "certificate": "A", "window": "core", "representation": "semantic",
                    "region": "inner_step", "support_mode": "dynamic", "trace_type": "relative",
                    "status": "ok", "reasons": "", "total_excursion": 888.0,
                },
            ])
            source.write_text(json.dumps(payload))
            after = root / "after"
            dp.build_profiles(root, after)
            for rel in ("per-stone/A.json", "per-stone/B.json", "comparison.json", "comparison.csv"):
                self.assertEqual((before / rel).read_bytes(), (after / rel).read_bytes())

    def test_wrong_upstream_schema_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            source = root / "docs" / "360" / "activation" / "summary.json"
            payload = json.loads(source.read_text())
            payload["schema_version"] = "diamond360-activation-benchmark/2"
            source.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "activation.*schema"):
                dp.build_profiles(root, root / "out")

    def test_duplicate_selected_row_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            source = root / "docs" / "360" / "occupancy" / "summary.json"
            payload = json.loads(source.read_text())
            target = next(
                row for row in payload["rows"]
                if row["certificate"] == "A" and row["region"] == "inner"
            )
            payload["rows"].append(dict(target))
            source.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "exactly one"):
                dp.build_profiles(root, root / "out")

    def test_coordination_maps_declared_stone_order_and_inherits_component_validity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            dp.build_profiles(root, root / "out")
            a = json.loads((root / "out" / "per-stone" / "A.json").read_text())
            b = json.loads((root / "out" / "per-stone" / "B.json").read_text())
            key = "nested_step.centre_inner_pearson"
            self.assertEqual(a["measurements"][key]["value"], 0.11)
            self.assertEqual(b["measurements"][key]["value"], 0.81)
            self.assertEqual(a["measurements"][key]["status"], "ok")
            self.assertEqual(b["measurements"][key]["status"], "review")
            self.assertIn("foreground_or_nonuniformity_on_border", b["measurements"][key]["reasons"])

    def test_comparison_preserves_validity_and_is_json_safe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_fixture(root)
            out = root / "out"
            dp.build_profiles(root, out)
            encoded = (out / "comparison.json").read_text()
            self.assertNotIn("NaN", encoded)
            self.assertNotIn("Infinity", encoded)
            with (out / "comparison.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            field = "dark_state.occupancy.inner_mean"
            self.assertIn(field, rows[0])
            self.assertIn(field + "__status", rows[0])
            self.assertIn(field + "__reasons", rows[0])
            b = next(row for row in rows if row["certificate"] == "B")
            self.assertEqual(b[field + "__status"], "review")
            self.assertIn("outline_near_image_edge", b[field + "__reasons"])


class CommittedDescriptorProfileTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    PROFILE = ROOT / "docs" / "360" / "profile"
    CERTS = [
        "IGI-LG756520111",
        "IGI-LG756580087",
        "IGI-LG818659722",
        "IGI-LG836619414",
    ]

    def test_committed_profiles_are_complete_and_reproducible(self):
        self.assertEqual(
            sorted(path.stem for path in (self.PROFILE / "per-stone").glob("*.json")),
            self.CERTS,
        )
        with tempfile.TemporaryDirectory() as td:
            fresh = Path(td) / "profile"
            dp.build_profiles(self.ROOT, fresh)
            for cert in self.CERTS:
                rel = Path("per-stone") / f"{cert}.json"
                self.assertEqual((fresh / rel).read_bytes(), (self.PROFILE / rel).read_bytes())
            for name in ("comparison.json", "comparison.csv"):
                self.assertEqual((fresh / name).read_bytes(), (self.PROFILE / name).read_bytes())

    def test_committed_contract_exposes_only_declared_fields(self):
        comparison = json.loads((self.PROFILE / "comparison.json").read_text())
        self.assertEqual(comparison["profile_schema"], dp.PROFILE_SCHEMA)
        self.assertEqual(set(comparison["field_catalog"]["measurements"]), set(dp.PRODUCTION_FIELD_IDS))
        self.assertEqual(set(comparison["field_catalog"]["context"]), set(dp.CONTEXT_FIELD_IDS))
        self.assertEqual(comparison["window_contract"]["source_indices"], CORE)
        encoded = json.dumps(comparison["field_catalog"])
        for excluded in ('"outer"', '"semantic"', '"dynamic"', '"pair_local"'):
            self.assertNotIn(excluded, encoded)


if __name__ == "__main__":
    unittest.main()
