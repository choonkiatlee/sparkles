"""Frozen-policy external D360 geometry/brightness falsification (Karl holdout pair).

No expert observations, predicted quality rankings or source-specific tuning
enter this module. Both sequence manifests come from the verified #64 archive.
The already-frozen #96 v2 estimator may fit ONE stone-level scaffold per unseen
stone. Subsequent image-plane brightness samples use that scaffold without
per-frame refitting, and abstain if pose/gauge/scaffold support is unavailable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import asscher_geometry_stability as stability
from . import asscher_geometry_validation as validation
from . import asscher_pose_sequence as pose
from . import asscher_semantic_optical_handoff as handoff
from . import asscher_semantic_optical_sensitivity as sensitivity
from . import asscher_semantic_optical_real_replay as plots
from . import asscher_wireframe as wireframe
from . import external_media
from . import pipeline

SCHEMA="diamond360-asscher-external-d360-handoff/1"
SAMPLES=("asscher-eval-crispest","asscher-eval-glittery")
SOURCE_INDICES=(250,252,255,0,2,5,8,11,13,16,19)
POLICY={
    "external_media":"exact_pinned_pricescope_64_archived_original_d360_frames",
    "sample_ids":list(SAMPLES),
    "pixel_sampling_indices":list(SOURCE_INDICES),
    "geometry_method":validation.OUTER_METHOD,
    "geometry_fit":"once_per_stone_with_existing_frozen_method",
    "within_stone_per_frame_refit":False,
    "selection":"predeclared_source_indices_no_quality_cherry_pick",
    "faceup":"not_assumed_even_for_wrapped_frame_core",
    "missing_geometry":"unavailable_no_fake_semantic_traces",
    "source_expert_labels":"never_loaded_or_used_in_generator",
    "expert_validation_status":"prior_descriptor_exposure_pr70_not_strictly_unseen",
    "image_support":"nonexclusive_appearance_not_polished_facet",
    "photometry":"existing_canonical_source_brightness_uncalibrated",
    "facet_identification":"not_established",
    "no_quality_scoring":True,
}


def _sample_from_manifest(manifest, sample_id):
    if manifest.get("schema_version")!="sparkles-external-benchmark/1":
        raise ValueError("unexpected external archive schema")
    rows=[s for s in manifest.get("samples",[]) if s.get("sample_id")==sample_id]
    if len(rows)!=1:
        raise ValueError("missing or ambiguous preselected external sample")
    source=rows[0]
    media=source.get("media") or {}
    seq=media.get("sequence") or {}
    if (media.get("status")!="complete_frame_sequence_archived"
        or seq.get("frame_count")!=256
        or not seq.get("manifest_sha256")
        or seq.get("timing_seconds") is not None
        or seq.get("calibrated_angles_degrees") is not None):
        raise ValueError("no verified uncalibrated 256-frame D360 source sequence")
    return {"manifest_path":seq["manifest_path"],
            "manifest_sha256":seq["manifest_sha256"],
            "frame_index_field":seq["frame_index_field"],
            "frame_count":seq["frame_count"]}


def _status(sample_id, reason, source_provenance):
    return {
        "schema_version":SCHEMA,
        "sample_id":sample_id,
        "status":"unavailable",
        "reason":reason,
        "policy":POLICY,
        "archived_media_provenance":source_provenance,
        "scaffold":None,
        "traces":[],
        "successful_image_support_rows":0,
        "facet_correspondence":"unavailable",
        "physical_angle_comparison":None,
        "quality_score":None,
    }


def _face_role(pose_result):
    face=pose_result.get("face_selection") or {}
    if face.get("status")!="resolved":
        return "unresolved_not_verified_crown"
    return "likely_crown_from_73_not_physical_facet_proof"


def run_external(sample_id, manifest, archive_root, output):
    if sample_id not in SAMPLES:
        raise ValueError("sample is not among precommitted holdout candidates")
    validation.assert_frozen_method(validation.OUTER_METHOD)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    sequence=_sample_from_manifest(manifest,sample_id)
    source_dir=output/"source"
    metadata={
        "sample_id":sample_id,"archive_manifest":sequence["manifest_path"],
        "archive_manifest_sha256":sequence["manifest_sha256"],
        "source_class":"archived_real_stone_vendor_360",
    }
    source=external_media.adapt_archived_sequence(
        archive_root,sequence,source_dir,provenance=metadata)
    manifest_file=source_dir/"source-manifest.json"
    if not manifest_file.is_file():
        # external_media.build_source writes source-manifest.json
        raise ValueError("missing prepared external source manifest")
    processed=output/"processed"
    pose_root=output/"pose"
    pipeline.run(source_dir,processed,manifest_file,gain=1.0,accept_review=True)
    pose.analyse_processed_sequence(processed,pose_root,persist_canonical=True)
    pose_data=json.loads((pose_root/"asscher-pose.json").read_text())
    face=_face_role(pose_data)
    primary, selected, _, _=stability._primary_fit(
        pose_root,pose_data,method=validation.OUTER_METHOD)
    src_provenance={
        **metadata,
        "frame_count":256,
        "source_order":"verified_manifest_indices_not_reordered_for_quality",
        "face_role_from_73":face,
        "selected_geometry_source_indices":[v["source_index"] for v in selected],
        "frozen_method":validation.OUTER_METHOD,
        "geometry_status":primary.get("status"),
    }
    if primary.get("scaffold") is None:
        result=_status(sample_id,"frozen_primary_geometry_unavailable:"
                       +str(primary.get("reason")),src_provenance)
        (output/"external-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        return result

    scaffold=primary["scaffold"]
    primary_sha=__import__("hashlib").sha256(
        json.dumps(primary,sort_keys=True,allow_nan=False).encode()).hexdigest()
    src_provenance["primary_scaffold_record_canonical_sha256"]=primary_sha
    by_source={int(frame["source_index"]):frame for frame in pose_data["frames"]}
    selected_pos={v.get("position") for v in selected}
    rows=[]; contrast=[]; refused=[]
    for source_index in SOURCE_INDICES:
        rec=by_source.get(source_index)
        if rec is None:
            refused.append({"source_index":source_index,"reason":"source_index_missing"})
            continue
        coord=rec.get("sequence_coordinate") or {}
        if (coord.get("gauge_status") not in ("available","review")
            or not rec.get("canonical",{}).get("path")):
            refused.append({"source_index":source_index,"reason":"canonical_source_gauge_unavailable"})
            continue
        if wireframe._gauge_id(pose_data)!=primary.get("semantic_gauge_id"):
            raise ValueError("fixed gauge changed between primary and replay")
        bright,mask,valid=stability._load_gauged_arrays(pose_root,rec)
        u, evidence=wireframe.extract_sector_evidence(bright,mask,valid)
        transfer=stability.transfer_fixed_ruler_frame(
            evidence,u,primary,frame_metadata=stability._metadata(rec),
            crown_peak_position=(pose_data.get("face_selection") or {}).get("likely_crown_peak_position"),
            sequence_size=len(pose_data["frames"]),
            in_primary_fit=rec.get("position") in selected_pos,
        )
        trace=handoff.sample_fixed_frame(scaffold,transfer,bright,mask,valid)
        trace.update({
            "face_role_from_73":face,
            "archived_external_source_index":source_index,
            "source_index":source_index,
            "rotation_phase_calibrated":False,
            "initial_frozen_geometry_from_source":primary_sha,
            "fixed_semantic_scaffold_not_independent_physical_facet_identity":True,
        })
        rows.append(trace)
        contrast.append(sensitivity.sample_frame_sensitivity(
            scaffold,transfer,bright,mask,valid,trace))
    if not rows:
        result=_status(sample_id,"no_source_frames_with_usable_fixed_gauge",src_provenance)
        result["refused_source_frames"]=refused
        (output/"external-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        return result
    frozen_ids=[r["semantic_id"] for r in rows[0]["entities"]]
    if any([r["semantic_id"] for r in frame["entities"]]!=frozen_ids for frame in rows):
        raise ValueError("held-out frame changed fixed semantic IDs")
    non_null=sum(item["raw_mean_brightness"] is not None
                 for frame in rows for item in frame["entities"])
    result={
        "schema_version":SCHEMA,
        "sample_id":sample_id,
        "status":"image_plane_fixed_scaffold_replay_review",
        "policy":POLICY,
        "archived_media_provenance":src_provenance,
        "source_indices_requested":list(SOURCE_INDICES),
        "source_indices_measured":[frame["source_index"] for frame in rows],
        "refused_source_frames":refused,
        "frozen_scaffold_status":primary.get("status"),
        "one_stone_level_fit_only":True,
        "refit_per_frame":False,
        "semantic_id_count":len(frozen_ids),
        "successful_image_support_rows":non_null,
        "face_status":face,
        "facet_correspondence":"not_established",
        "physical_angle_comparison":None,
        "quality_score":None,
        "traces":rows,
    }
    sens=sensitivity.summarize(sample_id,contrast,
              {"primary_wireframe_sha256":primary_sha},face)
    sensitivity.save(sens,output)
    result["sensitivity_path"]="exposure-support-sensitivity.json"
    plotted={
        "certificate":sample_id,
        "sampled_source_indices":[x["source_index"] for x in rows],
        "frames":rows,
        "archived_crown_face_selection":face,
    }
    plots.render_traces(plotted,output/"external-image-plane-traces.png")
    (output/"external-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--archive-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    manifest=json.loads(args.manifest.read_text())
    for sid in SAMPLES:
        result=run_external(sid,manifest,args.archive_root,args.out/sid)
        print(json.dumps({"sample":sid,"status":result["status"],
                          "reason":result.get("reason"),
                          "source_frames":len(result.get("traces",[])),
                          "non_null_image_support_rows":result["successful_image_support_rows"]}))
if __name__=="__main__":
    main()
