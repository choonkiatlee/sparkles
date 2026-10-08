"""Issue #91 PR B1: classify profile evidence before attempting facet geometry.

This module explicitly refuses to equate reflected/virtual-facet contrast with
a polished facet junction. The only task here is provenance-preserving review
input; NO facet angle estimator, automatic semantic assignment or expert-target
access is present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_profile_feasibility as feasibility

SCHEMA = "diamond360-asscher-profile-physical-evidence/1"
REVIEW_POLICY = {
    "allowed_input": "one source image only; no expert comparison target",
    "source_coordinates": "original_image_xy_origin_top_left",
    "candidate_policy": "generic edges are unclassified appearance evidence",
    "physical_boundary_policy": (
        "only separately traced and corroborated source-image contour or "
        "surface-junction evidence may be proposed as physical; even manual "
        "annotation remains an image-derived hypothesis, not physical truth"
    ),
    "semantic_policy": (
        "no P1/P2/P3/C1 assignment from contrast, line order or nearest "
        "expected angle; physical projection must be assessed separately"
    ),
    "measurement_policy": (
        "all eight angle slots unavailable until independent geometric "
        "correspondence and table reference have been reviewed"
    ),
    "target_values_policy": "never imported or read in extraction or annotation QC",
}
CANDIDATE_CLASS = "unclassified_image_edge"
PHYSICAL_CANDIDATE_CLASSES = (
    "external_silhouette_candidate",
    "visible_surface_junction_candidate",
    "table_edge_candidate",
    "girdle_edge_candidate",
    "culet_candidate",
)
NON_PHYSICAL_CLASSES = (
    "optical_contrast_only",
    "ambiguous_or_occluded",
    "unclassified_image_edge",
)
CLASSIFICATIONS = PHYSICAL_CANDIDATE_CLASSES + NON_PHYSICAL_CLASSES
LANDMARKS = ("table_left", "table_right", "girdle_left", "girdle_right", "culet")
FACETS = feasibility.SLOTS
SIDES = feasibility.SIDES


def make_review_template(image_path, expected_sha256=None):
    """Use generic edges to *locate review tasks*, never to assign facets."""
    diagnostic, _, _ = feasibility.analyse_image(image_path, expected_sha256)
    candidates = []
    for source_line in diagnostic["image_evidence"]["line_candidates"]:
        candidates.append({
            "candidate_id": source_line["candidate_id"],
            "evidence_class": CANDIDATE_CLASS,
            "review_status": "unreviewed",
            "physical_correspondence": "not_established",
            "physical_measurement_eligible": False,
            "semantic_facet_id": None,
            "source_pixel_segment_xy": source_line["supported_segment_xy_px"],
            "support_edgel_count": source_line["support_edgel_count"],
            "origin": "automated_appearance_gradient",
            "notes": (
                "Hough-supported intensity boundary; may be real, reflected, "
                "refracted, virtual or background, so cannot certify anatomy"
            ),
        })
    return {
        "schema_version": SCHEMA,
        "source": diagnostic["source"],
        "feasibility_policy_sha256": diagnostic["policy_sha256"],
        "review_policy": REVIEW_POLICY,
        "review_policy_sha256": feasibility.canonical_sha256(REVIEW_POLICY),
        "status": "requires_physical_correspondence_review",
        "image_only_evidence": candidates,
        "physical_landmark_annotations": {
            key: {
                "status": "unavailable",
                "xy_px": None,
                "evidence_class": None,
                "provenance": "not_annotated",
            }
            for key in LANDMARKS
        },
        "physical_boundary_annotations": [],
        "semantic_measurements": diagnostic["semantic_measurements"],
        "projection": {
            "status": "not_assessed",
            "side_facet_visibility": "unknown",
            "assumed_angle_model": None,
        },
        "comparison": {
            "status": "forbidden_until_measurement_frozen",
            "external_targets_loaded": False,
        },
        "interpretation": (
            "Image-only generic line evidence. All facet-family angles are "
            "unavailable: no physical-polished facet identification claimed."
        ),
    }


def _point_is_in_image(point, width, height):
    return (
        isinstance(point, (list, tuple))
        and len(point) == 2
        and all(isinstance(v, (float, int)) and not isinstance(v, bool) for v in point)
        and 0 <= point[0] < width
        and 0 <= point[1] < height
    )


def validate_human_annotations(payload):
    """Fail closed on unsupported assertions, without producing angles.

    Any independently authored physical-boundary claim remains explicitly
    HUMAN_CORRELATED; it is never promoted to an automatic observation or
    used as an angle without future physical/model review. Generic Hough
    candidate IDs are not permitted as the only provenance of a physical edge.
    """
    if payload.get("schema_version") != SCHEMA:
        raise ValueError("unsupported profile physical-evidence schema")
    image = payload.get("source", {})
    w, h = image.get("width_px"), image.get("height_px")
    if not isinstance(w, int) or not isinstance(h, int) or min(w, h) < 64:
        raise ValueError("invalid source dimensions")
    if payload.get("comparison", {}).get("external_targets_loaded") is not False:
        raise ValueError("expert-target data is forbidden in this stage")
    for candidate in payload.get("image_only_evidence", []):
        if (
            candidate.get("evidence_class") != CANDIDATE_CLASS
            or candidate.get("physical_measurement_eligible") is not False
            or candidate.get("semantic_facet_id") is not None
        ):
            raise ValueError("generic appearance edges cannot become physical facets")
    for name in LANDMARKS:
        land = payload.get("physical_landmark_annotations", {}).get(name)
        if land is None:
            raise ValueError("missing required landmark slot")
        if land.get("status") == "unavailable":
            if land.get("xy_px") is not None:
                raise ValueError("unavailable landmark cannot have a coordinate")
            continue
        if land.get("status") != "human_correlated":
            raise ValueError("landmark must be unavailable or human_correlated")
        if (
            land.get("provenance") != "separate_image_only_manual_trace"
            or land.get("evidence_class") not in PHYSICAL_CANDIDATE_CLASSES
            or not _point_is_in_image(land.get("xy_px"), w, h)
        ):
            raise ValueError("manually correlated landmark requires trace provenance")
    for row in payload.get("physical_boundary_annotations", []):
        if row.get("evidence_class") not in CLASSIFICATIONS:
            raise ValueError("invalid boundary evidence class")
        if row.get("semantic_facet_id") is not None:
            raise ValueError("facet labels need independent geometric adjudication")
        segment = row.get("segment_xy_px")
        if (
            not isinstance(segment, list)
            or len(segment) != 2
            or not all(_point_is_in_image(point, w, h) for point in segment)
        ):
            raise ValueError("invalid boundary segment coordinates")
        if row.get("evidence_class") in PHYSICAL_CANDIDATE_CLASSES:
            if (
                row.get("review_status") != "human_correlated"
                or row.get("provenance") != "separate_image_only_manual_trace"
                or not isinstance(row.get("review_notes"), str)
                or len(row["review_notes"].strip()) < 15
            ):
                raise ValueError(
                    "a proposed physical boundary requires independently traced "
                    "pixels and an explicit corroboration note"
                )
        else:
            if row.get("physical_measurement_eligible") is not False:
                raise ValueError("optical/ambiguous lines cannot support physical angles")
    for side in SIDES:
        group = payload.get("semantic_measurements", {}).get(side)
        if set(group or {}) != set(FACETS):
            raise ValueError("must preserve all left/right facet slots")
        for observation in group.values():
            if (
                observation.get("status") != "unavailable"
                or observation.get("apparent_angle_deg") is not None
                or observation.get("uncertainty_deg") is not None
            ):
                raise ValueError("PR B1 cannot manufacture P1/P2/P3/C1 angles")
    return True


def write_review_template(image_path, output, expected_sha256=None):
    payload = make_review_template(image_path, expected_sha256)
    validate_human_annotations(payload)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-original", action="store_true")
    args = parser.parse_args()
    payload = write_review_template(
        args.image, args.output,
        feasibility.ORIGINAL_PROFILE_SHA256 if args.require_original else None,
    )
    print(json.dumps({
        "schema_version": payload["schema_version"],
        "source_sha256": payload["source"]["sha256"],
        "unclassified_image_edges": len(payload["image_only_evidence"]),
        "physical_boundary_annotations": len(payload["physical_boundary_annotations"]),
        "status": payload["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
