"""Human frame-level calibration for issue #57 tier readability.

PR C deliberately separates three concerns:

1. select a deterministic, label-blind set of informative source frames;
2. collect genuinely human labels with explicit provenance;
3. compare research formulations with leave-one-diamond-out validation.

No aesthetic threshold or production score is fit here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PACKET_SCHEMA = "diamond360-tier-readability-label-packet/1"
LABEL_SCHEMA = "diamond360-tier-readability-human-labels/1"
CALIBRATION_SCHEMA = "diamond360-tier-readability-calibration/1"

SEPARATION_LEVELS = {"collapsed": 0.0, "partial": 1.0, "clear": 2.0}
THREE_LAYER_LEVELS = {"ambiguous": 0.0, "obvious": 1.0}

FORMULATIONS = (
    "coarse_whole_weakest",
    "broad_sector_median_weakest",
    "boundary_median_weakest",
    "boundary_q25_weakest",
    "joint_median",
    "joint_q25",
    "ordering_monotonic_fraction",
    "ordering_alternating_fraction",
    "ordering_concentration",
)

_SELECTION_REASONS = (
    "lowest_boundary_q25",
    "highest_boundary_median",
    "largest_coverage_gap",
    "largest_joint_penalty",
    "typical_joint",
)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"missing required input: {path}") from exc


def _finite(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _weakest(left, right):
    left, right = _finite(left), _finite(right)
    if left is None or right is None:
        return None
    return float(min(left, right))


def _row_at(candidate, position):
    rows = candidate.get("frame_trace") or []
    if position >= len(rows):
        return {}
    return rows[position] or {}


def extract_frame_features(result):
    """Extract aligned PR-B frame descriptors without changing measurements."""
    pair_ids = ("centre__inner", "inner__middle")
    pairs = result.get("pairs") or {}
    if any(pair_id not in pairs for pair_id in pair_ids):
        raise ValueError("tier contrast result is missing nested pair outputs")
    indices = list(result.get("requested_indices") or [])
    if not indices:
        raise ValueError("tier contrast result has no requested_indices")

    features = []
    joint = result.get("tier_readability_profile") or {}
    if not joint.get("frame_trace"):
        raise ValueError("tier readability profile is unavailable")

    for position, source_index in enumerate(indices):
        simple = {}
        broad = {}
        semantic = {}
        for pair_id in pair_ids:
            pair = pairs[pair_id]
            simple[pair_id] = _row_at(pair.get("simple") or {}, position)
            broad[pair_id] = _row_at(pair.get("localized") or {}, position)
            semantic[pair_id] = _row_at(
                (((pair.get("boundary_local") or {}).get("multi_scale") or {})
                 .get("semantic") or {}),
                position,
            )
        joint_row = _row_at(joint, position)
        ordering = joint_row.get("ordering_fractions") or {}
        monotonic = sum(
            value or 0.0
            for key, value in ordering.items()
            if key.startswith("monotonic_")
        )
        alternating = sum(
            value or 0.0
            for key, value in ordering.items()
            if key in {"inner_local_minimum", "inner_local_maximum"}
        )
        finite_ordering = [
            float(value) for value in ordering.values()
            if _finite(value) is not None
        ]
        row = {
            "position": position,
            "source_index": int(source_index),
            "coarse_whole_weakest": _weakest(
                simple["centre__inner"].get("separation"),
                simple["inner__middle"].get("separation"),
            ),
            "broad_sector_median_weakest": _weakest(
                broad["centre__inner"].get("median_separation"),
                broad["inner__middle"].get("median_separation"),
            ),
            "boundary_median_weakest": _weakest(
                semantic["centre__inner"].get("median_separation"),
                semantic["inner__middle"].get("median_separation"),
            ),
            "boundary_q25_weakest": _weakest(
                semantic["centre__inner"].get("q25_separation"),
                semantic["inner__middle"].get("q25_separation"),
            ),
            "joint_median": _finite(joint_row.get("median_joint_separation")),
            "joint_q25": _finite(joint_row.get("q25_joint_separation")),
            "joint_median_penalty": _finite(joint_row.get("joint_median_penalty")),
            "ordering_monotonic_fraction": (
                float(monotonic) if finite_ordering else None
            ),
            "ordering_alternating_fraction": (
                float(alternating) if finite_ordering else None
            ),
            "ordering_concentration": (
                float(max(finite_ordering)) if finite_ordering else None
            ),
        }
        if (
            row["boundary_median_weakest"] is not None
            and row["boundary_q25_weakest"] is not None
        ):
            row["coverage_gap"] = float(
                row["boundary_median_weakest"] - row["boundary_q25_weakest"]
            )
        else:
            row["coverage_gap"] = None
        features.append(row)
    return features


def load_benchmark_features(benchmark_root):
    root = Path(benchmark_root)
    per_stone = root / "per-stone"
    if not per_stone.exists():
        raise ValueError(f"benchmark root has no per-stone output: {root}")
    result = {}
    for stone_dir in sorted(path for path in per_stone.iterdir() if path.is_dir()):
        path = stone_dir / "wide" / "tier-contrast.json"
        if not path.exists():
            continue
        payload = _load_json(path)
        result[stone_dir.name] = extract_frame_features(payload)
    if len(result) < 2:
        raise ValueError("calibration requires at least two stones")
    return result


def _rank_candidates(rows, key, reverse):
    finite = [row for row in rows if _finite(row.get(key)) is not None]
    return sorted(
        finite,
        key=lambda row: (
            -float(row[key]) if reverse else float(row[key]),
            int(row["source_index"]),
        ),
    )


def _nearest_typical(rows, key, excluded):
    finite = [
        row for row in rows
        if _finite(row.get(key)) is not None
        and row["source_index"] not in excluded
    ]
    if not finite:
        return None
    target = float(np.median([row[key] for row in finite]))
    return min(
        finite,
        key=lambda row: (
            abs(float(row[key]) - target),
            int(row["source_index"]),
        ),
    )


def select_informative_frames(features_by_stone, per_stone=5):
    """Select fixed descriptor-informed frames before any human labels exist."""
    if per_stone != len(_SELECTION_REASONS):
        raise ValueError(
            f"current packet contract requires {len(_SELECTION_REASONS)} frames per stone"
        )
    selected = []
    for certificate, rows in sorted(features_by_stone.items()):
        if not rows:
            raise ValueError(f"{certificate}: no frame features")
        used = set()
        specs = (
            ("lowest_boundary_q25", "boundary_q25_weakest", False),
            ("highest_boundary_median", "boundary_median_weakest", True),
            ("largest_coverage_gap", "coverage_gap", True),
            ("largest_joint_penalty", "joint_median_penalty", True),
        )
        for reason, key, reverse in specs:
            candidates = _rank_candidates(rows, key, reverse)
            choice = next(
                (row for row in candidates if row["source_index"] not in used),
                None,
            )
            if choice is None:
                raise ValueError(f"{certificate}: cannot select unique frame for {reason}")
            used.add(choice["source_index"])
            selected.append({
                "certificate": certificate,
                "source_index": choice["source_index"],
                "selection_reason": reason,
            })
        typical = _nearest_typical(rows, "joint_median", used)
        if typical is None:
            raise ValueError(f"{certificate}: cannot select typical joint frame")
        selected.append({
            "certificate": certificate,
            "source_index": typical["source_index"],
            "selection_reason": "typical_joint",
        })

    # Blind the labelling order: stable hash rather than certificate grouping.
    selected.sort(
        key=lambda row: hashlib.sha256(
            f"{row['certificate']}:{row['source_index']}".encode()
        ).hexdigest()
    )
    for number, row in enumerate(selected, start=1):
        row["item_id"] = f"T{number:02d}"
    return selected


def _source_frame(source_root, certificate, source_index):
    root = Path(source_root) / certificate
    manifest = _load_json(root / "source-manifest.json")
    if manifest.get("certificate") != certificate:
        raise ValueError(f"{certificate}: source manifest certificate mismatch")
    matches = [
        row for row in manifest.get("frames", [])
        if row.get("source_index") == source_index
    ]
    if len(matches) != 1:
        raise ValueError(f"{certificate}: source frame {source_index} not unique")
    row = matches[0]
    path = root / row["path"]
    if not path.exists():
        raise ValueError(f"{certificate}: missing source frame {path}")
    return path, row


def _render_contact_sheet(items, source_root, destination):
    thumb = 230
    label_h = 28
    columns = 5
    rows = math.ceil(len(items) / columns)
    canvas = Image.new("RGB", (columns * thumb, rows * (thumb + label_h)), "white")
    draw = ImageDraw.Draw(canvas)
    for index, item in enumerate(items):
        path, _ = _source_frame(
            source_root, item["certificate"], item["source_index"]
        )
        with Image.open(path) as source:
            image = source.convert("RGB")
        image.thumbnail((thumb - 8, thumb - 8))
        x = (index % columns) * thumb
        y = (index // columns) * (thumb + label_h)
        px = x + (thumb - image.width) // 2
        py = y + (thumb - image.height) // 2
        canvas.paste(image, (px, py))
        draw.text((x + 8, y + thumb + 4), item["item_id"], fill="black")
    canvas.save(destination, quality=92)


def build_label_packet(benchmark_root, source_root, output, per_stone=5):
    features = load_benchmark_features(benchmark_root)
    selected = select_informative_frames(features, per_stone=per_stone)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    manifest_items = []
    blind_frames = output / "frames"
    blind_frames.mkdir(exist_ok=True)
    feature_lookup = {
        (certificate, row["source_index"]): row
        for certificate, rows in features.items()
        for row in rows
    }
    audit = []
    for item in selected:
        path, source = _source_frame(
            source_root, item["certificate"], item["source_index"]
        )
        blind_path = blind_frames / f"{item['item_id']}.jpg"
        with Image.open(path) as source_image:
            source_image.convert("RGB").save(blind_path, quality=95)
        manifest_items.append({
            **item,
            "source_sha256": source.get("sha256"),
            "source_path": source.get("path"),
            "blind_frame_path": str(blind_path.relative_to(output)),
        })
        audit.append({
            **item,
            "features": {
                key: feature_lookup[(item["certificate"], item["source_index"])].get(key)
                for key in FORMULATIONS + ("joint_median_penalty", "coverage_gap")
            },
        })

    manifest = {
        "schema_version": PACKET_SCHEMA,
        "selection_contract": {
            "per_stone": per_stone,
            "reasons": list(_SELECTION_REASONS),
            "selection_uses_human_labels": False,
            "label_sheet_exposes_descriptor_values": False,
            "ordering": "stable sha256(certificate:source_index) blind order",
        },
        "items": manifest_items,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )
    (output / "selection-audit.json").write_text(
        json.dumps(
            {"schema_version": PACKET_SCHEMA, "items": audit},
            indent=2,
            allow_nan=False,
        ) + "\n"
    )
    template = {
        "schema_version": LABEL_SCHEMA,
        "provenance": {
            "kind": "human_entered",
            "ai_assistance": False,
            "status": "pending",
            "reviewer_session": None,
        },
        "label_contract": {
            "separation": list(SEPARATION_LEVELS),
            "three_layers": list(THREE_LAYER_LEVELS),
            "instruction": (
                "Judge the source image only. separation: collapsed/partial/clear; "
                "three_layers: ambiguous/obvious. Do not consult descriptor values."
            ),
        },
        "labels": [
            {
                "item_id": item["item_id"],
                "separation": None,
                "three_layers": None,
                "note": "",
            }
            for item in selected
        ],
    }
    (output / "labels-template.json").write_text(
        json.dumps(template, indent=2, allow_nan=False) + "\n"
    )
    _render_contact_sheet(selected, source_root, output / "contact-sheet.jpg")
    return manifest


def validate_human_labels(labels, manifest):
    if labels.get("schema_version") != LABEL_SCHEMA:
        raise ValueError(f"expected label schema {LABEL_SCHEMA}")
    if manifest.get("schema_version") != PACKET_SCHEMA:
        raise ValueError(f"expected packet schema {PACKET_SCHEMA}")
    provenance = labels.get("provenance") or {}
    if provenance.get("kind") != "human_entered":
        raise ValueError("labels must have human_entered provenance")
    if provenance.get("ai_assistance") is not False:
        raise ValueError("AI-assisted labels cannot satisfy PR C human calibration")
    if provenance.get("status") != "complete":
        raise ValueError("human labels are not marked complete")
    session = provenance.get("reviewer_session")
    if not isinstance(session, str) or not session.strip():
        raise ValueError("complete human labels require reviewer_session")

    expected = {item["item_id"] for item in manifest.get("items") or []}
    rows = labels.get("labels")
    if not isinstance(rows, list):
        raise ValueError("labels must be a list")
    observed = [row.get("item_id") for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("labels must cover every packet item exactly once")
    for row in rows:
        if row.get("separation") not in SEPARATION_LEVELS:
            raise ValueError(f"{row.get('item_id')}: invalid separation label")
        if row.get("three_layers") not in THREE_LAYER_LEVELS:
            raise ValueError(f"{row.get('item_id')}: invalid three_layers label")
    return rows


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0
        for i in order[start:end]:
            ranks[i] = rank
        start = end
    return ranks


def _pearson(left, right):
    if len(left) < 2:
        return None
    x = np.asarray(left, float)
    y = np.asarray(right, float)
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(left, right):
    if len(left) < 2:
        return None
    return _pearson(_average_ranks(left), _average_ranks(right))


def _pairwise_concordance(rows, score_key, label_key, binary=False):
    comparable = 0
    credit = 0.0
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            sa, sb = _finite(a.get(score_key)), _finite(b.get(score_key))
            la, lb = _finite(a.get(label_key)), _finite(b.get(label_key))
            if sa is None or sb is None or la is None or lb is None or la == lb:
                continue
            if binary and {la, lb} != {0.0, 1.0}:
                continue
            comparable += 1
            score_delta = sa - sb
            label_delta = la - lb
            if score_delta == 0:
                credit += 0.5
            elif score_delta * label_delta > 0:
                credit += 1.0
    return {
        "comparable_pairs": comparable,
        "concordance": float(credit / comparable) if comparable else None,
    }


def _learn_direction(training, formulation, label_key):
    aligned = [
        row for row in training
        if _finite(row.get(formulation)) is not None
        and _finite(row.get(label_key)) is not None
    ]
    rho = _spearman(
        [row[formulation] for row in aligned],
        [row[label_key] for row in aligned],
    )
    direction = -1.0 if rho is not None and rho < 0 else 1.0
    return direction, rho, len(aligned)


def leave_one_diamond_out(rows, formulation, label_key, binary=False):
    certificates = sorted({row["certificate"] for row in rows})
    folds = []
    total_pairs = 0
    weighted = 0.0
    for held_out in certificates:
        training = [row for row in rows if row["certificate"] != held_out]
        testing = [dict(row) for row in rows if row["certificate"] == held_out]
        direction, training_rho, training_n = _learn_direction(
            training, formulation, label_key
        )
        for row in testing:
            value = _finite(row.get(formulation))
            row["_directed_score"] = (
                float(direction * value) if value is not None else None
            )
        concordance = _pairwise_concordance(
            testing, "_directed_score", label_key, binary=binary
        )
        test_aligned = [
            row for row in testing
            if _finite(row.get("_directed_score")) is not None
            and _finite(row.get(label_key)) is not None
        ]
        test_rho = _spearman(
            [row["_directed_score"] for row in test_aligned],
            [row[label_key] for row in test_aligned],
        )
        pairs = concordance["comparable_pairs"]
        if pairs and concordance["concordance"] is not None:
            total_pairs += pairs
            weighted += pairs * concordance["concordance"]
        folds.append({
            "held_out_certificate": held_out,
            "training_certificates": sorted(
                {row["certificate"] for row in training}
            ),
            "training_rows": training_n,
            "direction": direction,
            "training_spearman": training_rho,
            "held_out_rows": len(test_aligned),
            "held_out_spearman": test_rho,
            **concordance,
        })
    return {
        "formulation": formulation,
        "label": label_key,
        "split": "leave_one_diamond_out",
        "aggregate_comparable_pairs": total_pairs,
        "aggregate_concordance": (
            float(weighted / total_pairs) if total_pairs else None
        ),
        "folds": folds,
    }


def _joined_rows(benchmark_root, labels, manifest):
    features = load_benchmark_features(benchmark_root)
    labels_by_id = {row["item_id"]: row for row in labels}
    rows = []
    for item in manifest["items"]:
        matches = [
            row for row in features[item["certificate"]]
            if row["source_index"] == item["source_index"]
        ]
        if len(matches) != 1:
            raise ValueError(f"{item['item_id']}: frame features not unique")
        human = labels_by_id[item["item_id"]]
        rows.append({
            "item_id": item["item_id"],
            "certificate": item["certificate"],
            "source_index": item["source_index"],
            "separation_label": human["separation"],
            "separation_ordinal": SEPARATION_LEVELS[human["separation"]],
            "three_layers_label": human["three_layers"],
            "three_layers_binary": THREE_LAYER_LEVELS[human["three_layers"]],
            "note": human.get("note", ""),
            **{key: matches[0].get(key) for key in FORMULATIONS},
        })
    return rows


def build_calibration(benchmark_root, manifest_path, labels_path, output):
    manifest = _load_json(manifest_path)
    label_payload = _load_json(labels_path)
    labels = validate_human_labels(label_payload, manifest)
    rows = _joined_rows(benchmark_root, labels, manifest)

    results = {}
    for formulation in FORMULATIONS:
        results[formulation] = {
            "separation": leave_one_diamond_out(
                rows, formulation, "separation_ordinal", binary=False
            ),
            "three_layers": leave_one_diamond_out(
                rows, formulation, "three_layers_binary", binary=True
            ),
        }
    payload = {
        "schema_version": CALIBRATION_SCHEMA,
        "label_schema": LABEL_SCHEMA,
        "packet_schema": PACKET_SCHEMA,
        "human_provenance": label_payload["provenance"],
        "sample": {
            "frame_count": len(rows),
            "certificate_count": len({row["certificate"] for row in rows}),
            "frames_per_certificate": dict(sorted(
                (certificate, sum(row["certificate"] == certificate for row in rows))
                for certificate in {row["certificate"] for row in rows}
            )),
        },
        "method": {
            "split": "leave_one_diamond_out",
            "direction_learning": (
                "descriptor direction chosen only from the three training diamonds "
                "using Spearman sign; no thresholds or magnitudes are fit"
            ),
            "primary_discrimination": (
                "held-out within-diamond pairwise concordance; ties score 0.5"
            ),
            "pseudo_replication_guard": (
                "all frames from a held-out diamond remain together in the test fold"
            ),
        },
        "rows": rows,
        "results": results,
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "calibration.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    flat = []
    for formulation, targets in results.items():
        for target, result in targets.items():
            flat.append({
                "formulation": formulation,
                "target": target,
                "aggregate_comparable_pairs": result["aggregate_comparable_pairs"],
                "aggregate_concordance": result["aggregate_concordance"],
            })
    with (output / "calibration.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    packet = sub.add_parser("packet")
    packet.add_argument("--benchmark-root", type=Path, required=True)
    packet.add_argument("--source-root", type=Path, required=True)
    packet.add_argument("--output", type=Path, required=True)

    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("--benchmark-root", type=Path, required=True)
    calibrate.add_argument("--manifest", type=Path, required=True)
    calibrate.add_argument("--labels", type=Path, required=True)
    calibrate.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "packet":
        build_label_packet(args.benchmark_root, args.source_root, args.output)
    else:
        build_calibration(
            args.benchmark_root, args.manifest, args.labels, args.output
        )


if __name__ == "__main__":
    main()
