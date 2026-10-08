"""#123: sparse-neighbor optical contrast dynamics, never physical facet tracks.

Consumes only immutable #146 native RGB line diagnostics and #162 junction
artifacts. Physical/optical provenance is gated by #172/#176. Candidate
correspondences describe optical appearance changes, NOT facet identity.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_validation as validation
from . import asscher_optical_physical_provenance as provenance

SCHEMA = "diamond360-asscher-optical-neighbor-dynamics/1"
POLICY = {
    "schema_version": SCHEMA,
    "sequence_length": 256,
    "maximum_observed_frame_gap": 3,
    "radial_fraction_pair_gate": 0.045,
    "gauge_midpoint_pair_gate": 0.16,
    "pairing": "one_to_one_nearest_image_plane_appearance_not_facet_identity",
    "measurements": [
        "signed_silhouette_normalized_radial_fraction_change",
        "gauge_xy_midpoint_shift",
        "gradient_strength_change",
        "coverage_change",
        "not_redetected_and_newly_detected_candidate_counts",
    ],
    "source": "frozen_146_RGB_lines_and_162_junctions_no_new_downloads",
    "exact_neighbor_only_when_gap_one": True,
    "missing_intervening_frames": "explicitly_recorded_not_interpolated",
    "crown_face_provenance": "inherited_no_unresolved_role_promotion",
    "candidate_semantics": "optical_or_structural_unresolved_not_confirmed_virtual_facet",
    "physical_facets": "all_interior_unavailable",
    "no_estimator_change": True,
    "no_source_stress": True,
}


def _finite(value, label):
    if type(value) not in (float, int) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _segments(frame):
    """Read *observed* contiguous RGB segments, not synthetic radial peaks."""
    result = []
    sides = frame.get("sides") or []
    if len(sides) not in (0, 8):
        raise ValueError("source must enumerate all eight side families or none")
    for side_number, side in enumerate(sides):
        if side.get("side") != side_number:
            raise ValueError("source orientation family has changed")
        for rank, item in enumerate(side.get("detected_candidates", [])):
            if item.get("rendered_segment_policy") != (
                    "only_contiguous_observed_RGB_gradient_pixels"):
                raise ValueError("unsupported RGB line extrapolation")
            a = item.get("sample_start")
            b = item.get("sample_end")
            if (not isinstance(a, list) or not isinstance(b, list) or
                    len(a) != 2 or len(b) != 2):
                raise ValueError("missing observed camera-gauge segment")
            midpoint = [
                (_finite(a[i], "source endpoint")
                 + _finite(b[i], "source endpoint")) * 0.5
                for i in range(2)
            ]
            fraction = _finite(item.get("fraction"), "radial fraction")
            if not 0.0 < fraction < 1.0:
                raise ValueError("invalid silhouette-normalized radial fraction")
            result.append({
                "candidate_id": f"src{frame['source_index']:04d}:side{side_number}:line{rank}",
                "source_index": frame["source_index"],
                "side_orientation_family": side_number,
                "fraction": fraction,
                "gauge_midpoint_xy": midpoint,
                "gradient_strength": _finite(item.get("strength"), "gradient strength"),
                "gradient_coverage": _finite(item.get("coverage"), "gradient coverage"),
                "longest_contiguous_fraction": _finite(
                    item.get("longest_contiguous_fraction"), "continuous line support"
                ),
                "physical_facet_semantic_id": None,
                "provenance_class": "image_plane_optical_contrast_candidate",
            })
    return result


def _pair_candidates(before, after, gap):
    """Locally pair *appearance observations* without claiming true identity.

    Closest one-to-one match within frozen spatial thresholds. No transitive
    tracking: a future match is not evidence that a line is a physical facet.
    """
    available = []
    for i, a in enumerate(before):
        for j, b in enumerate(after):
            if a["side_orientation_family"] != b["side_orientation_family"]:
                continue
            radial = abs(a["fraction"] - b["fraction"])
            euclidean = float(np.linalg.norm(
                np.asarray(a["gauge_midpoint_xy"])
                - np.asarray(b["gauge_midpoint_xy"])
            ))
            if (radial <= POLICY["radial_fraction_pair_gate"]
                    and euclidean <= POLICY["gauge_midpoint_pair_gate"]):
                cost = (0.75 * radial / POLICY["radial_fraction_pair_gate"]
                        + 0.25 * euclidean / POLICY["gauge_midpoint_pair_gate"])
                available.append((cost, i, j, radial, euclidean))
    matched_i, matched_j, matches = set(), set(), []
    for cost, i, j, radial, euclidean in sorted(
            available, key=lambda p: (p[0], p[1], p[2])):
        if i in matched_i or j in matched_j:
            continue
        matched_i.add(i)
        matched_j.add(j)
        a, b = before[i], after[j]
        matches.append({
            "from_candidate_id": a["candidate_id"],
            "to_candidate_id": b["candidate_id"],
            "side_orientation_family": a["side_orientation_family"],
            "from_fraction": a["fraction"],
            "to_fraction": b["fraction"],
            "signed_radial_fraction_delta": b["fraction"] - a["fraction"],
            "signed_radial_fraction_change_per_source_frame": (
                (b["fraction"] - a["fraction"]) / gap
            ),
            "midpoint_gauge_xy_delta": [
                b["gauge_midpoint_xy"][dim] - a["gauge_midpoint_xy"][dim]
                for dim in range(2)
            ],
            "midpoint_shift_gauge_units": euclidean,
            "gradient_strength_delta": (
                b["gradient_strength"] - a["gradient_strength"]
            ),
            "coverage_delta": (
                b["gradient_coverage"] - a["gradient_coverage"]
            ),
            "matching_cost": float(cost),
            "physical_facet_correspondence": "not_established",
            "possible_virtual_or_reflected_facet": True,
        })
    return {
        "candidate_pairs": matches,
        "not_redetected_candidates": [
            a["candidate_id"] for i, a in enumerate(before)
            if i not in matched_i
        ],
        "newly_detected_candidates": [
            b["candidate_id"] for j, b in enumerate(after)
            if j not in matched_j
        ],
        "number_tentative_pairs": len(matches),
        "number_not_redetected": len(before) - len(matched_i),
        "number_newly_detected": len(after) - len(matched_j),
        "note": ("Non-redetection is threshold-censored optical evidence, "
                 "NOT proof that a facet or reflection physically vanished."),
    }


def selected_neighbor_pairs(frames, *, cycle_length=256, max_gap=3):
    """Adjacent *selected* frames, with observable skip gaps documented."""
    cycle_length = int(cycle_length)
    if cycle_length < 2 or max_gap < 1:
        raise ValueError("invalid sequence window")
    by_pos = {}
    for row in frames:
        index, pos = row.get("source_index"), row.get("position")
        if type(index) is not int or type(pos) is not int:
            raise ValueError("frozen view indices and positions required")
        if not 0 <= pos < cycle_length or pos in by_pos:
            raise ValueError("invalid or duplicate source rotation position")
        by_pos[pos] = row
    if len(by_pos) < 2:
        return [], []
    ordered = [by_pos[p] for p in sorted(by_pos)]
    included, skipped = [], []
    for i, a in enumerate(ordered):
        b = ordered[(i + 1) % len(ordered)]
        gap = (b["position"] - a["position"]) % cycle_length
        if not gap:
            raise ValueError("duplicate or invalid cyclic frame order")
        event = {
            "from_source_index": a["source_index"],
            "to_source_index": b["source_index"],
            "from_position": a["position"],
            "to_position": b["position"],
            "frame_gap": gap,
            "is_exact_consecutive_frame": gap == 1,
            "number_unsampled_intervening_frames": gap - 1,
        }
        if gap <= max_gap:
            included.append(event)
        else:
            skipped.append({**event, "reason": "unsampled_gap_exceeds_declared_limit"})
    return included, skipped


def analyse_stone(lines, junctions):
    """Use the frozen provenance adapter as mandatory physical-safety gate."""
    evidence = provenance.adapt_stone(lines, junctions)
    if evidence["can_use_as_physical_facet_geometry"]:
        raise ValueError("optical archive must never promote physical geometry")
    for name in provenance.INTERIOR_BOUNDARIES:
        row = evidence["physical_geometry"]["interior_boundaries"][name]
        if row["status"] != "unavailable" or row["vertices_topology_order"] is not None:
            raise ValueError("unverified physical facet geometry in input")
    records = lines["frames"]
    if {r["source_index"] for r in records} != set(evidence["selected_source_indices"]):
        raise ValueError("frozen selected source identities changed")
    by_source = {r["source_index"]: r for r in records}
    windows, gaps = selected_neighbor_pairs(
        records, cycle_length=POLICY["sequence_length"],
        max_gap=POLICY["maximum_observed_frame_gap"]
    )
    output = []
    for event in windows:
        a, b = (by_source[event[key]] for key in
                ("from_source_index", "to_source_index"))
        measured = _pair_candidates(
            _segments(a), _segments(b), event["frame_gap"]
        )
        output.append({
            **event,
            **measured,
            "crown_face_status": evidence["face_identity"]["status"],
            "semantic_interpretation": "optical_appearance_only",
            "physical_facet_identity_verified": False,
        })
    return {
        "schema_version": SCHEMA,
        "certificate": lines["certificate"],
        "source_indices": evidence["selected_source_indices"],
        "crown_face_status": evidence["face_identity"]["status"],
        "pair_window_policy": POLICY,
        "observed_neighbor_windows": output,
        "unobserved_frame_gaps": gaps,
        "complete_sequence_claim": False,
        "total_exact_consecutive_windows": sum(
            e["is_exact_consecutive_frame"] for e in output
        ),
        "total_tentative_optical_pairs": sum(
            e["number_tentative_pairs"] for e in output
        ),
        "total_not_redetected": sum(
            e["number_not_redetected"] for e in output
        ),
        "total_newly_detected": sum(
            e["number_newly_detected"] for e in output
        ),
        "physical_geometry": {
            "outer": "frozen_96_observed_silhouette_only",
            "C1_C2": "unavailable",
            "C2_C3": "unavailable",
            "C3_TABLE": "unavailable",
        },
        "no_physical_or_virtual_facet_auto_labels": True,
        "no_estimator_or_quality_score_change": True,
    }


def _original_rgb_crop(path):
    """First untouched camera-RGB pane from #146's three-panel visual QC."""
    image = Image.open(path).convert("RGB")
    # #146 draws three equal-width camera crops with four-pixel inter-pane gaps.
    width = (image.width - 8) // 3
    if width < 20:
        raise ValueError("RGB diagnostic is missing original source pane")
    return image.crop((0, 0, width, image.height))


def render_window(line_root, certificate, event, output):
    """Original RGB crops plus *nonphysical* optical-candidate motion chart."""
    line_root, output = Path(line_root), Path(output)
    root = line_root / "per-stone" / certificate
    originals = []
    for index in (event["from_source_index"], event["to_source_index"]):
        path = root / f"source-{index:04d}-native-RGB.jpg"
        if not path.is_file():
            raise FileNotFoundError(f"missing original-camera RGB QC: {path}")
        image = _original_rgb_crop(path)
        image.thumbnail((420, 510), Image.Resampling.LANCZOS)
        originals.append(image)
    chart_width, chart_height = 430, 470
    chart = Image.new("RGB", (chart_width, chart_height), "#fcfcfc")
    draw = ImageDraw.Draw(chart)
    draw.text((12, 10), "Image-plane optical candidates ONLY", fill=(30, 30, 30))
    draw.text((12, 31), "No verified facets / no facet tracking", fill=(100, 60, 60))
    draw.text((12, 51),
              f"matched {event['number_tentative_pairs']} | "
              f"not redetected {event['number_not_redetected']} | "
              f"newly detected {event['number_newly_detected']}",
              fill=(30, 30, 30))
    ytop, rowheight = 90, 39
    xlo, xhi = 65, 404
    ulo, uhi = .32, .81
    def xp(frac):
        return xlo + (float(frac) - ulo) / (uhi - ulo) * (xhi - xlo)
    for side in range(8):
        y = ytop + side*rowheight
        draw.line((xlo, y, xhi, y), fill=(220, 220, 220), width=1)
        draw.text((9,y-7),f"S{side}",fill=(70,70,70))
    for m in event["candidate_pairs"]:
        side = m["side_orientation_family"]
        y = ytop + side * rowheight
        x1, x2 = xp(m["from_fraction"]), xp(m["to_fraction"])
        draw.line((x1, y-8, x2, y+8), fill=(90, 105, 110), width=2)
        draw.ellipse((x1-4,y-12,x1+4,y-4), fill=(20,100,220))
        draw.ellipse((x2-4,y+4,x2+4,y+12), fill=(230,115,30))
    draw.text((12, 417), "Blue: earlier  /  Orange: later", fill=(60,60,60))
    draw.text((12, 438), "Distances normalized to outer silhouette", fill=(60,60,60))

    pad, header = 7, 63
    height = max(im.height for im in originals+[chart])+header
    width = sum(im.width for im in originals)+chart.width+3*pad
    result = Image.new("RGB", (width,height), (18,18,18))
    d = ImageDraw.Draw(result)
    d.text((10,8),
           f"{certificate} | source {event['from_source_index']} "
           f"to {event['to_source_index']} | gap {event['frame_gap']} frames",
           fill=(255,255,255))
    d.text((10,29),
           "ORIGINAL RGB camera crops from frozen #146 | "
           "optical, not physical facet evidence",
           fill=(225,225,225))
    x = pad
    for img in originals+[chart]:
        result.paste(img,(x,header))
        x += img.width+pad
    output.parent.mkdir(parents=True,exist_ok=True)
    result.save(output,quality=89)
    return output.name


def run_archive(line_root, junction_root, output):
    """Reproduce only already-hash-verified four-stone research evidence."""
    line_root, junction_root, output = map(Path, (line_root,junction_root,output))
    a = json.loads((line_root/"summary.json").read_text())
    b = json.loads((junction_root/"summary.json").read_text())
    expected = validation.BENCHMARK_MANIFEST_CANONICAL_SHA256
    if (a.get("benchmark_manifest_canonical_sha256") != expected or
            b.get("pinned_source_manifest_sha256") != expected or
            a.get("method_change") is not False or
            b.get("estimator_modified") is not False or
            b.get("physical_facet_identity_verified") is not False):
        raise ValueError("not immutable frozen observational RGB sources")
    certs_a = [x["certificate"] for x in a["stones"]]
    certs_b = [x["certificate"] for x in b["stones"]]
    if certs_a != certs_b or len(certs_a) != 4 or len(set(certs_a)) != 4:
        raise ValueError("not the four-stone benchmark")
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for certificate in certs_a:
        line = json.loads((line_root/"per-stone"/certificate/"line-evidence.json").read_text())
        junction = json.loads((junction_root/"per-stone"/certificate/"junction-evidence.json").read_text())
        result = analyse_stone(line,junction)
        dest = output/"per-stone"/certificate
        dest.mkdir(parents=True,exist_ok=True)
        for event in result["observed_neighbor_windows"]:
            event["original_RGB_QC_path"] = render_window(
                line_root,certificate,event,
                dest / (f"pair-{event['from_source_index']:04d}-"
                        f"{event['to_source_index']:04d}.jpg")
            )
        (dest/"neighbor-dynamics.json").write_text(
            json.dumps(result,indent=2,allow_nan=False)+"\n")
        summaries.append({
            "certificate":certificate,
            "crown_face_status":result["crown_face_status"],
            "source_indices":result["source_indices"],
            "neighbor_windows":len(result["observed_neighbor_windows"]),
            "exact_consecutive_pairs":result["total_exact_consecutive_windows"],
            "candidate_pairs":result["total_tentative_optical_pairs"],
            "not_redetected":result["total_not_redetected"],
            "newly_detected":result["total_newly_detected"],
            "qc_images":[
                f"per-stone/{certificate}/{e['original_RGB_QC_path']}"
                for e in result["observed_neighbor_windows"]
            ],
            "all_interior_physical_facets_unavailable":True,
        })
    report={
        "schema_version":SCHEMA,
        "policy":POLICY,
        "frozen_source_manifest_sha256":expected,
        "stones":summaries,
        "physical_facet_identity_from_optical_motion":False,
        "no_automatic_virtual_facet_classification":True,
        "no_estimator_change":True,
        "scope":"sparse selected source neighbors; unsampled frames explicitly censored",
    }
    (output/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line-root",type=Path,required=True)
    p.add_argument("--junction-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=run_archive(a.line_root,a.junction_root,a.output)
    for s in result["stones"]:
        print(s["certificate"], "crown",s["crown_face_status"],
              "windows",s["neighbor_windows"], "exact",s["exact_consecutive_pairs"],
              "tentative optical matches",s["candidate_pairs"],
              "not redetected",s["not_redetected"],
              "newly",s["newly_detected"])


if __name__=="__main__":
    main()
