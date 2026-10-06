import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from diamond360 import geometric_crispness_benchmark as b


def build_synthetic(root: Path, frame_count=8):
    processed = root / "processed"
    for folder in (
        "photometry", "diamond", "camera"
    ):
        (
            processed / folder
        ).mkdir(
            parents=True,
            exist_ok=True,
        )

    size = 160
    y, x = np.indices(
        (size, size), dtype=float
    )
    cy = cx = (size - 1) / 2
    radius = 64.0
    rr = np.hypot(
        x-cx, y-cy
    )
    mask = rr <= radius
    uu = rr / radius
    records = []

    for pos in range(frame_count):
        scale = (
            1.0
            + .02*np.sin(pos)
        )
        brightness = scale * np.where(
            uu < .50,
            1.00,
            np.where(
                uu < .73,
                .62,
                np.where(
                    uu < .87,
                    1.18,
                    .76,
                ),
            ),
        )

        for angle in (
            np.pi/4,
            3*np.pi/4,
            5*np.pi/4,
            7*np.pi/4,
        ):
            ca, sa = (
                np.cos(angle),
                np.sin(angle),
            )
            dx, dy = x-cx, y-cy
            t = dx*ca + dy*sa
            perp = (
                dx*(-sa) + dy*ca
            )
            gate = (
                (t > .18*radius)
                & (t < .82*radius)
            )
            brightness += (
                .18
                * np.exp(
                    -.5
                    * (perp/1.8)**2
                )
                * gate
            )

        brightness += (
            .004
            * np.sin(
                x*.17 + pos
            )
        )
        valid = mask.copy()
        np.savez_compressed(
            processed
            / "photometry"
            / f"{pos:04d}.npz",
            encoded_brightness=
                brightness.astype(
                    np.float32
                ),
            valid_mask=valid,
        )

        rgb = np.repeat(
            np.clip(
                brightness[..., None]
                / 1.35
                * 255,
                0,
                255,
            ).astype(np.uint8),
            3,
            axis=2,
        )
        rgb[~mask] = 245
        Image.fromarray(rgb).save(
            processed
            / "diamond"
            / f"{pos:04d}.png"
        )
        Image.fromarray(rgb).save(
            processed
            / "camera"
            / f"{pos:04d}.png"
        )
        Image.fromarray(
            mask.astype(np.uint8)
            * 255
        ).save(
            processed
            / "diamond"
            / f"{pos:04d}-mask.png"
        )

        records.append(
            {
                "position": pos,
                "source_index": pos,
                "sha256":
                    f"{pos+1:064x}",
                "photometry_path":
                    (
                        "photometry/"
                        f"{pos:04d}.npz"
                    ),
                "camera_original_path":
                    (
                        "camera/"
                        f"{pos:04d}.png"
                    ),
                "segmentation": {
                    "status": "ok",
                    "reasons": [],
                },
                "registration": {
                    "mask_path":
                        (
                            "diamond/"
                            f"{pos:04d}"
                            "-mask.png"
                        ),
                    "rgb_path":
                        (
                            "diamond/"
                            f"{pos:04d}.png"
                        ),
                },
            }
        )

    (
        processed / "sequence.json"
    ).write_text(
        json.dumps(
            {
                "source_frame_count":
                    frame_count,
                "frames": records,
            }
        )
    )
    return processed


class GeometricCrispnessBenchmarkTests(
    unittest.TestCase
):
    def test_measure_stone_runs_both_experiments(self):
        with tempfile.TemporaryDirectory() as td:
            processed = (
                build_synthetic(
                    Path(td)
                )
            )
            result = b.measure_stone(
                processed,
                list(range(8)),
                wrap=False,
            )
            self.assertEqual(
                result[
                    "schema_version"
                ],
                b.SCHEMA,
            )
            self.assertEqual(
                set(
                    result[
                        "baseline"
                    ]["tier_summary"]
                ),
                {
                    "centre_inner",
                    "inner_middle",
                    "middle_outer",
                },
            )
            self.assertEqual(
                set(
                    result[
                        "baseline"
                    ]["arm_summary"][
                        "arms"
                    ]
                ),
                {
                    "SE",
                    "SW",
                    "NW",
                    "NE",
                },
            )
            self.assertEqual(
                set(
                    result[
                        "pipeline_sensitivity"
                    ]
                ),
                set(
                    b.old_crispness
                    .PERTURBATIONS
                ),
            )
            self.assertEqual(
                result["contract"][
                    "combined_score"
                ],
                "none",
            )
            self.assertEqual(
                len(
                    result["baseline"][
                        "transforms"
                    ]
                ),
                8,
            )
            self.assertTrue(
                all(
                    row[
                        "source_effective_diameter_px"
                    ] > 0
                    for row in result[
                        "baseline"
                    ]["transforms"]
                )
            )

    def test_output_is_json_safe_and_renders_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            processed = (
                build_synthetic(root)
            )
            result = b.measure_stone(
                processed,
                list(range(8)),
                wrap=False,
            )
            clean = (
                b.write_stone_outputs(
                    result,
                    root / "out",
                    human_source_indices=[0],
                )
            )
            payload = json.loads(
                (
                    root
                    / "out"
                    / "geometric-crispness.json"
                ).read_text()
            )
            self.assertNotIn(
                "_render", payload
            )
            self.assertTrue(
                payload[
                    "evidence_files"
                ]
            )
            self.assertEqual(
                set(
                    payload[
                        "human_evidence_files"
                    ]
                ),
                {"0"},
            )
            self.assertTrue(
                (
                    root
                    / "out"
                    / "evidence"
                    / "human_static_0.jpg"
                ).exists()
            )
            encoded = (
                root
                / "out"
                / "geometric-crispness.json"
            ).read_text()
            self.assertNotIn(
                "NaN", encoded
            )
            self.assertNotIn(
                "Infinity", encoded
            )
            self.assertNotIn(
                "_render", clean
            )


if __name__ == "__main__":
    unittest.main()
