import unittest

from diamond360.external_benchmark import (
    _mode,
    build_dispositions,
)


def measured(sample_id, *, tier=None, occupancy=None, persistence=None, switching=None):
    profile = {}
    if occupancy is not None:
        profile["dark_state.occupancy.inner_mean"] = {
            "value": occupancy, "status": "ok"
        }
    if persistence is not None:
        profile["dark_state.persistence.inner_dark_q90_window_fraction"] = {
            "value": persistence, "status": "ok"
        }
    if switching is not None:
        profile["temporal_reconfiguration.switching.inner_rate"] = {
            "value": switching, "status": "ok"
        }
    return {
        "sample_id": sample_id,
        "status": "measured",
        "retained_profile": profile,
        "tier_readability_research": {
            "median_summary": {"q50": tier}
        } if tier is not None else None,
    }


class ExternalBenchmarkTests(unittest.TestCase):
    def test_mode_never_invents_motion_for_stills(self):
        self.assertEqual(
            _mode(
                {
                    "evidence_type": "still",
                    "media": {
                        "assets": [{"media_type": "jpg"}],
                        "sequence": None,
                    },
                }
            ),
            "static",
        )
        self.assertEqual(
            _mode(
                {
                    "evidence_type": "vendor_360",
                    "media": {
                        "assets": [],
                        "sequence": {"frame_count": 256},
                    },
                }
            ),
            "dynamic_faceup",
        )

    def test_predeclared_p3_directions_can_falsify(self):
        results = [
            measured(
                "p3-video-cut-for-weight",
                tier=0.10,
                occupancy=0.40,
                persistence=0.35,
            ),
            measured(
                "p3-video-corrected",
                tier=0.20,
                occupancy=0.30,
                persistence=0.25,
            ),
            measured(
                "p3-video-higher-performance",
                tier=0.30,
                occupancy=0.20,
                persistence=0.15,
            ),
        ]
        dispositions = build_dispositions(results)
        p3 = [
            row for row in dispositions
            if row.get("sample_ids")
            == [
                "p3-video-cut-for-weight",
                "p3-video-corrected",
                "p3-video-higher-performance",
            ]
        ]
        self.assertEqual(
            [row["kind"] for row in p3[:3]],
            ["supports_external_case"] * 3,
        )

    def test_kashi_contradiction_is_preserved(self):
        results = [
            measured(
                "asscher-eval-messy-arrows",
                persistence=0.20,
                switching=0.40,
            ),
            measured(
                "asscher-eval-nice-dance",
                persistence=0.30,
                switching=0.30,
            ),
        ]
        dispositions = build_dispositions(results)
        kashi = [
            row for row in dispositions
            if row.get("sample_ids")
            == ["asscher-eval-messy-arrows", "asscher-eval-nice-dance"]
        ]
        self.assertEqual(
            [row["kind"] for row in kashi[:2]],
            ["contradicts_external_case", "contradicts_external_case"],
        )


if __name__ == "__main__":
    unittest.main()
