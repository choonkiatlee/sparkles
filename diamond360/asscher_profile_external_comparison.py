"""#91 PR C: independently compare immutable profile evidence with photo estimates.

This is ONLY a post-freeze audit. It never runs profile extraction, never maps
an image-plane silhouette slope to P1/P2/P3/C1, and never claims physical facet
angles. Expert reference data is read only AFTER the independently frozen
image-output bytes and provenance have been authenticated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import asscher_profile_feasibility as source
from . import asscher_profile_pavilion_refinement as fitted

SCHEMA = "diamond360-asscher-profile-post-freeze-comparison/1"

# Frozen source image and exact *pre-comparison* JSON output from PR #118,
# GitHub Actions run 37798814740, artifact 11559723054.
# This digest is over original UTF-8 JSON bytes, not a reserialization.
FROZEN_PROFILE_SHA256 = "63bebfce1c6946c375ee79bcf81fbe56404ebeb3cc71ae860787befa6265132c"
FROZEN_RUN = "https://github.com/choonkiatlee/sparkles/actions/runs/37798814740"
FROZEN_ARTIFACT = "asscher-profile-physical-evidence/pavilion-refinement.json"

POLICY = {
    "method": "independent_post_freeze_comparison_only",
    "frozen_output": FROZEN_PROFILE_SHA256,
    "strict_source_sha256": source.ORIGINAL_PROFILE_SHA256,
    "source_orientation": "pointed_upper_pavilion_broad_lower_crown",
    "comparison_basis": "expert_photo_estimate_is_not_physical_ground_truth",
    "facet_correspondence": "unavailable_without_independent_physical_junction_review",
    "image_breaks_not_facets": True,
    "do_not_match_image_slopes_to_nearest_expert_angles": True,
    "do_not_refit": True,
    "no_physical_plane_angles_from_2d_silhouette": True,
}


def _digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def validate_frozen_profile_bytes(data: bytes):
    """Does NOT and must not accept any expert targets as input."""
    if _digest(data) != FROZEN_PROFILE_SHA256:
        raise ValueError("frozen #118 profile artifact byte SHA mismatch")
    obj = json.loads(data)
    if obj.get("schema_version") != fitted.SCHEMA:
        raise ValueError("frozen profile schema mismatch")
    if obj.get("source_sha256") != source.ORIGINAL_PROFILE_SHA256:
        raise ValueError("source image SHA mismatch")
    if obj.get("source_orientation") != POLICY["source_orientation"]:
        raise ValueError("profile source orientation mismatch")
    if obj.get("policy_sha256") != source.canonical_sha256(fitted.POLICY):
        raise ValueError("source extraction policy differs from frozen PR #118")
    if obj.get("comparison_targets_loaded") is not False:
        raise ValueError("target contamination in frozen extraction")
    if obj.get("physical_facet_angles") != "all_unavailable":
        raise ValueError("frozen profile unexpectedly asserts physical facet angles")
    if obj.get("status") != "review":
        raise ValueError("unexpected frozen profile status")
    geom = {}
    for side in ("left", "right"):
        evidence = obj["independent_pavilion"][side]
        points = obj["observed_supported_points"][side]
        if evidence["status"] != "review":
            raise ValueError("unreviewed/unsupported frozen pavilion fit")
        if not all(p["xy_px"][1] < obj["widest_width_band_candidate"]["y_first_px"]
                   for p in points):
            raise ValueError("crown image rows mislabelled as upper pavilion")
        if not all(m["status"] == "observed_source_changepoint_candidate_not_facet_junction"
                   for m in evidence["breakpoints"]):
            raise ValueError("unverified physical identity promoted")
        geom[side] = {
            "source_supported_row_count": len(points),
            "model_selected_projected_stretches": evidence["selected_segment_count"],
            "image_plane_slope_dx_per_dy": evidence["slope_dx_per_dy"],
            "breakpoints": [{
                "xy_px": mark["xy_px"],
                "stability": mark["stability"],
                "penalty_variants_support": mark["penalty_variants_support"],
                "penalty_variant_total": mark["penalty_variant_total"],
                "meaning": "projected_silhouette_kink_not_physical_facet_junction",
            } for mark in evidence["breakpoints"]],
            "physical_facet_correspondence": "not_established",
            "image_plane_angle_to_physical_facet_angle": "not_identifiable",
        }
    return geom


def compare(frozen_bytes: bytes, external_reference: dict):
    # Critical order: independently authenticate/parse the target-blind
    # frozen evidence before opening even the *in-memory* target record.
    geometry = validate_frozen_profile_bytes(frozen_bytes)

    target = external_reference.get("independent_photo_estimate", {})
    if (external_reference.get("case_id") != "pricescope-diagem-sergey-2008-asscher"
        or target.get("evidence_class") != "photo_estimate"
        or target.get("source_post") != 156
        or target.get("stated_uncertainty_deg") != 1):
        raise ValueError("wrong independent photo-estimate provenance")
    sides = {}
    for side in ("left", "right"):
        tvals = target.get(side + "_side_deg", {})
        if set(tvals) != {"P1", "P2", "P3", "C1"}:
            raise ValueError("expected four independent photo-estimate slots per side")
        slots = {}
        for family in ("P1", "P2", "P3", "C1"):
            value = tvals[family]
            if type(value) not in (int, float) or not 0 <= value <= 90:
                raise ValueError("invalid independent photo estimate")
            slots[family] = {
                "target_photo_estimate_deg": value,
                "reference_uncertainty_deg": target["stated_uncertainty_deg"],
                "reference_evidence_class": "photo_estimate_not_physical_ground_truth",
                "sparkles_image_derived_facet_angle_deg": None,
                "residual_deg": None,
                "status": "not_comparable_unverified_physical_facet_correspondence",
                "why": (
                    "Frozen source output observes projected external silhouette, "
                    "not a source-verified P1/P2/P3/C1 polished-facet line. "
                    "No target proximity or line-order assignment is allowed."
                ),
            }
        sides[side] = slots
    return {
        "schema_version": SCHEMA,
        "status": "inconclusive_physical_facet_correspondence",
        "frozen_source_profile_sha256": FROZEN_PROFILE_SHA256,
        "frozen_source_image_sha256": source.ORIGINAL_PROFILE_SHA256,
        "frozen_profile_source": FROZEN_RUN + " (artifact " + FROZEN_ARTIFACT + ")",
        "comparison_policy_sha256": source.canonical_sha256(POLICY),
        "policy": POLICY,
        "frozen_image_only_evidence": geometry,
        "independent_reference": {
            "expert": target.get("estimator"),
            "source_post": target["source_post"],
            "evidence_class": "photo_estimate",
            "stated_uncertainty_deg": target["stated_uncertainty_deg"],
            "manual_cutting_measurements_inferred_from_photo": False,
        },
        "semantic_facet_comparison": sides,
        "numeric_deltas_available": 0,
        "requested_slots": 8,
        "physical_facet_angles_claimed": 0,
        "independent_angle_reference_opened_only_after_frozen_verification": True,
        "interpretation": (
            "Neither silhouette slope order nor the 3-tier Asscher topology "
            "identifies polished P1/P2/P3 facets. DiaGem profile evidence has "
            "usable projected outer-geometry kinks (left stronger than right), "
            "but cannot be scored for agreement with independent facet-angle "
            "photo estimates without independently identified facet junctions "
            "and supported camera projection. Explicit scientific abstention."
        ),
        "negative_view_status": "unverified_rejected_original_source_not_included",
        "downstream_geometry_handoff": (
            "Crown-view fixed outer semantic scaffold may be sampled as "
            "non-exclusive image-plane support; inner C3/table physical identity "
            "must remain uncertain pending independent evidence."
        ),
    }


def write_comparison(frozen_path: Path, reference_path: Path, output_path: Path):
    # Deliberately load/authenticate the target-blind output *first*.
    frozen = Path(frozen_path).read_bytes()
    validate_frozen_profile_bytes(frozen)
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    record = compare(frozen, reference)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-profile-json", type=Path, required=True)
    parser.add_argument("--reference-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_comparison(args.frozen_profile_json, args.reference_json, args.output)
    print(json.dumps({
        "status": result["status"],
        "reference_slots": result["requested_slots"],
        "numeric_deltas_available": result["numeric_deltas_available"],
        "frozen_profile_sha256": FROZEN_PROFILE_SHA256,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
