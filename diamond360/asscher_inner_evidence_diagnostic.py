"""#124: audit canonical registration and multimodal inner-edge evidence.

This is an evidence inspector, not a fitting algorithm. It reuses the frozen
#96/#115 source pipeline and discovers no new semantic physical facets. In
particular, "canonical" currently means a 2-D similarity transform, not
projective face-on rectification.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_frame_ablation as ablation
from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_outer_octagon as octagon
from . import asscher_steps as steps
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-inner-evidence-diagnostic/1"
C3_WINDOW = tuple(steps.BOUNDARY_WINDOWS[0])
MODE_HALF_WINDOW = 0.022


def _finite_number(value):
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def _candidate_records(template):
    """Expose all #19 persistent-edge candidates; never reclassify physically."""
    return [{
        "radial_u": float(c["u"]),
        "prominence": float(c["prominence"]),
        "sector_support_fraction": float(c["sector_support"]),
        "per_sector_peak_u": [
            None if p is None else float(p["u"])
            for p in c["sector_peaks"]
        ],
    } for c in template.get("candidates", [])]


def _selected_c3(template):
    for control in template.get("controls", []):
        if C3_WINDOW[0] <= control["global_u"] <= C3_WINDOW[1]:
            return float(control["global_u"])
    return None


def _template_report(data, u):
    fit = steps.discover_template(data, u)
    control = fit.get("partial_controls", {}).get("centre_inner")
    if fit.get("controls"):
        control = fit["controls"][0]
    return {
        "status": fit["status"],
        "reason": fit.get("reason"),
        "c3_selected_u": (
            None if control is None else float(control["global_u"])
        ),
        "c3_sector_support": (
            None if control is None else float(control["sector_support"])
        ),
        "persistent_edge_candidates": _candidate_records(fit),
    }


def _local_energy(profile, u, target):
    profile = np.asarray(profile, float)
    indices = np.flatnonzero(
        np.isfinite(profile) & (np.abs(u - target) <= MODE_HALF_WINDOW)
    )
    if len(indices) == 0:
        return {"peak_u": None, "peak_evidence": None}
    index = int(indices[np.argmax(profile[indices])])
    return {
        "peak_u": float(u[index]),
        "peak_evidence": float(profile[index]),
    }


def _frame_evidence(data, u, source_indices, mode_a, mode_b):
    """Summarize evidence at both observed modes before imposing semantics."""
    output = []
    for idx, frame in zip(source_indices, data):
        sectors = []
        for sector, profile in enumerate(frame):
            a = _local_energy(profile, u, mode_a)
            b = _local_energy(profile, u, mode_b)
            if a["peak_evidence"] is None or b["peak_evidence"] is None:
                preference = None
            elif a["peak_evidence"] > b["peak_evidence"]:
                preference = "full_mode"
            elif a["peak_evidence"] < b["peak_evidence"]:
                preference = "omit_mode"
            else:
                preference = "tie"
            sectors.append({
                "sector_index_step_order": sector,
                "full_mode": a,
                "omit_mode": b,
                "stronger_local_peak": preference,
            })
        output.append({
            "source_index": int(idx),
            "sectors": sectors,
            "full_mode_stronger_sector_count": sum(
                row["stronger_local_peak"] == "full_mode" for row in sectors
            ),
            "omit_mode_stronger_sector_count": sum(
                row["stronger_local_peak"] == "omit_mode" for row in sectors
            ),
        })
    return output


def _similarity_diagnostics(record):
    canonical = record.get("canonical") or {}
    transform = canonical.get("normalization") or {}
    matrix = np.asarray(canonical.get("registered_to_canonical_xy"), dtype=float)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("missing registered-to-canonical similarity transform")
    linear = matrix[:2, :2]
    singular = np.linalg.svd(linear, compute_uv=False)
    # Scale anisotropy should be ~0 for a declared similarity transform.
    anisotropy = float(max(singular) / min(singular) - 1.0)
    outline = canonical.get("registered_outline") or {}
    return {
        "registered_to_canonical_xy": matrix.tolist(),
        "normalization_rectification": transform.get("rectification", "none"),
        "normalization_rotation_deg": transform.get("rotation_deg"),
        "registered_orientation_mod90_deg": outline.get(
            "orientation_deg_mod_90"
        ),
        "registered_aspect_ratio": outline.get("aspect_ratio"),
        "registered_outline_residual": outline.get(
            "normalized_q90_boundary_residual"
        ),
        "singular_values": singular.tolist(),
        "linear_anisotropy_fraction": anisotropy,
        "note": "Similarity-only alignment; no perspective or tilt correction.",
    }


def _per_frame_outer_geometry(masks, selected, full_outer):
    reference = np.asarray(full_outer["vertices_topology_order"], float)
    rows = []
    for record, mask in zip(selected, masks):
        points, fit = octagon._normalized_fitted_vertices(mask)
        distances = np.linalg.norm(points - reference, axis=1)
        rows.append({
            "source_index": record.get("source_index"),
            "octagon_vertices_gauge_xy": points.tolist(),
            "median_octagon_rms_u": float(np.sqrt(np.mean(distances ** 2))),
            "median_octagon_max_vertex_u": float(max(distances)),
            "canonical_octagon_aspect_ratio": float(fit["aspect_ratio"]),
            "canonical_octagon_residual": float(
                fit["normalized_q90_boundary_residual"]
            ),
            "normalization": _similarity_diagnostics(record),
        })
    return rows


def inspect_pose(pose_output, *, reference_dir=None):
    pose_output = Path(pose_output)
    validation.assert_frozen_method(validation.OUTER_METHOD)
    factor_summary, factor_cases, selected = ablation.analyse_pose(pose_output)
    if reference_dir is not None:
        ablation._confirm_frozen_reference(factor_summary, reference_dir)
    data, u, masks, brightness, meta = stability._load_evidence(
        pose_output, selected
    )
    source_indices = [int(record["source_index"]) for record in selected]
    if source_indices != factor_summary["full_selected_source_indices"]:
        raise RuntimeError("frozen full selection changed")
    ref = _template_report(data, u)
    without_indices = [i for i, src in enumerate(source_indices)
                       if src != ablation.OMIT_SOURCE_INDEX]
    if len(without_indices) != len(source_indices) - 1:
        raise RuntimeError("frozen frame-16 selection no longer unique")
    leave = _template_report(data[without_indices], u)
    if ref["c3_selected_u"] is None or leave["c3_selected_u"] is None:
        raise RuntimeError("C3 template is missing for diagnostic")
    per_frame = _frame_evidence(
        data, u, source_indices,
        ref["c3_selected_u"], leave["c3_selected_u"],
    )
    one_out = {}
    for i in range(len(source_indices)):
        subset = np.delete(data, i, axis=0)
        one_out[str(source_indices[i])] = _template_report(subset, u)
    outer_geometry = _per_frame_outer_geometry(
        masks, selected, factor_cases["full_outer_full_inner"]["outer_evidence"]
    )
    report = {
        "schema_version": SCHEMA,
        "certificate": ablation.CERTIFICATE,
        "frozen_method": validation.frozen_method_record(
            validation.OUTER_METHOD
        ),
        "frozen_115_reference_checked": reference_dir is not None,
        "selected_source_indices": source_indices,
        "normalization_contract": (
            "2-D similarity rotation, translation and isotropic rescaling; "
            "no square-on projective rectification or camera-tilt recovery"
        ),
        "c3_modes": {
            "full_global_u": ref["c3_selected_u"],
            "without_16_global_u": leave["c3_selected_u"],
            "delta_without_minus_full_u": (
                leave["c3_selected_u"] - ref["c3_selected_u"]
            ),
            "mode_evidence_probe_half_width_u": MODE_HALF_WINDOW,
        },
        "full_template": ref,
        "without_16_template": leave,
        "leave_one_out_templates": one_out,
        "per_frame_8_sector_evidence": per_frame,
        "per_frame_normalization_and_octagon": outer_geometry,
        "factor_ablation": factor_summary["cases"],
        "interpretation_limits": (
            "Different source-normalized edge modes do not identify physical "
            "facets. Low silhouette residual does not prove correct "
            "face-on geometry; registration, projection, and moving optical "
            "contrast remain confounded without independent calibration."
        ),
    }
    return report, (data, u, selected, masks, brightness, factor_cases)


def _heat_colour(value):
    t = int(round(255 * float(np.clip(value, 0, 1))))
    return (t, t, t)


def write_evidence_qc(data, u, source_indices, full_mode, omit_mode, output):
    """Source-by-source C3-profile heatmap with fixed global-radial markers."""
    n = len(source_indices)
    width, cell_h, header, footer = 720, 66, 48, 24
    image = Image.new("RGB", (width, header + (n + 2) * cell_h + footer),
                      "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 10),
              "C3 radial edge evidence — appearance only, NOT physical facets",
              fill="black")
    # Horizontal range includes both observed modes and the declared C3 window.
    left, right = 150, width - 18
    lo, hi = .38, .63
    def xpos(x):
        return int(round(left + (float(x) - lo) / (hi - lo) * (right-left)))

    with np.errstate(invalid="ignore"):
        full_median = np.nanmedian(np.nanmedian(data, axis=0), axis=0)
        without = np.delete(
            data, source_indices.index(ablation.OMIT_SOURCE_INDEX), axis=0
        )
        leave_median = np.nanmedian(np.nanmedian(without, axis=0), axis=0)
    curves = [(str(k), np.nanmedian(frame, axis=0))
              for k,frame in zip(source_indices, data)]
    curves += [("all frames median", full_median),
               ("omit 16 median", leave_median)]
    for row, (name, profile) in enumerate(curves):
        y0 = header + row * cell_h
        draw.text((10, y0 + 21), name, fill="black")
        finite = np.asarray(profile, float)
        mask = (u >= lo) & (u <= hi) & np.isfinite(finite)
        values = finite[mask]
        maximum = max(float(np.max(values)) if len(values) else 0, 1e-9)
        for idx in np.flatnonzero(mask):
            x = xpos(u[idx])
            value = max(0.0, float(finite[idx]) / maximum)
            draw.line([(x, y0 + 9), (x, y0 + 52)],
                      fill=_heat_colour(1 - value), width=3)
        draw.line([(xpos(full_mode), y0+4),
                   (xpos(full_mode), y0+57)], fill=(190,40,30), width=2)
        draw.line([(xpos(omit_mode), y0+4),
                   (xpos(omit_mode), y0+57)], fill=(40,90,200), width=2)
    draw.text((12, image.height - 18),
              "Red = all-frame mode. Blue = omit-16 mode. Each row independently scaled.",
              fill="black")
    image.save(output)
    return Path(output).name


def write_registration_qc(processed, pose_output, selected, masks, full_result,
                          outer_rows, output):
    """Same fixed semantic ruler mapped back onto each original camera frame."""
    panels = []
    by_source = {r["source_index"]: r for r in outer_rows}
    for record, mask in zip(selected, masks):
        img = wireframe._draw_scaffold_on_source(
            processed, record, mask, full_result["scaffold"]
        )
        if img is None:
            raise RuntimeError("native RGB camera mapping missing; no blurred fallback")
        info = by_source[record["source_index"]]
        footer = ("source " + str(record["source_index"])
                  + " / octagon RMS " + format(info["median_octagon_rms_u"], ".4f"))
        tile = ablation._labelled_panel(
            img, f"Source frame {record['source_index']}",
            footer, width=320
        )
        panels.append(tile)
    cols = 3
    rows = (len(panels) + cols - 1)//cols
    out = Image.new("RGB", (cols*320, rows*374), "white")
    for i, tile in enumerate(panels):
        out.paste(tile, ((i%cols)*320,(i//cols)*374))
    out.save(output, quality=92)
    return Path(output).name


def run(source_root, source_manifest, output, *, reference_dir=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sparkles-inner-evidence-") as tmp:
        processed, pose = Path(tmp)/"processed", Path(tmp)/"pose"
        pipeline.run(
            Path(source_root), processed, Path(source_manifest),
            gain=1.0, accept_review=True,
        )
        analyse_processed_sequence(processed, pose, persist_canonical=True)
        report, arrays = inspect_pose(pose, reference_dir=reference_dir)
        data, u, selected, masks, _, factor_cases = arrays
        report["evidence_qc"] = write_evidence_qc(
            data, u, report["selected_source_indices"],
            report["c3_modes"]["full_global_u"],
            report["c3_modes"]["without_16_global_u"],
            output/"c3-evidence.png"
        )
        report["registration_qc"] = write_registration_qc(
            processed, pose, selected, masks,
            factor_cases["full_outer_full_inner"],
            report["per_frame_normalization_and_octagon"],
            output/"frame-registration-qc.jpg"
        )
        (output/"inner-evidence-diagnostic.json").write_text(
            json.dumps(report, indent=2, allow_nan=False)+"\n"
        )
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Frozen #96 C3 candidate and source-normalization diagnostics"
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()
    report = run(args.source_root, args.source_manifest, args.output,
                 reference_dir=args.reference_dir)
    print("method", report["frozen_method"]["wireframe_revision"])
    print("canonical normalization:", report["normalization_contract"])
    print("modes", report["c3_modes"])
    for row in report["per_frame_normalization_and_octagon"]:
        print("frame", row["source_index"], "outer RMS",
              row["median_octagon_rms_u"],
              "registration orientation",
              row["normalization"]["registered_orientation_mod90_deg"])
    for row in report["per_frame_8_sector_evidence"]:
        print("frame", row["source_index"],
              "full vs omit peaks", row["full_mode_stronger_sector_count"],
              row["omit_mode_stronger_sector_count"])


if __name__ == "__main__":
    main()
