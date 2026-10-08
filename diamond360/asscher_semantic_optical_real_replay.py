"""#92 short real-data replay with frozen #89 scaffold and per-frame transfer.

Reconstruct ONLY canonical frame measurements from two SHA-256-pinned
benchmark source sequences, then apply the already archived fixed stone-level
ruler and per-frame #89 transfer records. Never call a geometry fitter or
recompute source-dependent semantic IDs/targets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asscher_geometry_validation as validation
from . import asscher_geometry_stability as stability
from . import asscher_semantic_optical_handoff as handoff
from . import asscher_wireframe as wireframe
from . import pipeline
from .asscher_pose_sequence import analyse_processed_sequence

SCHEMA = "diamond360-asscher-real-fixed-ruler-smoke/1"
# Pin selections independently of measured brightness, before replay.
SELECTED = {
    "IGI-LG756520111": (0, 13, 16, 19, 255),  # #73 resolved crown lobe
    "IGI-LG756580087": (13, 16, 19),          # unresolved crown role negative control
}
FROZEN_SOURCE_RUN = 37830584391
HIGHLIGHTS = ("C1_N", "C2_N", "C3_N", "P1_N", "TABLE")
SWATCHES = ((29, 110, 189), (15, 157, 121), (213, 101, 30),
            (153, 78, 187), (195, 46, 94))


def frozen_inputs(certificate, archived):
    """Validate archived #89 evidence, without running its geometry fitter."""
    root = Path(archived) / "per-stone" / certificate
    primary = json.loads((root / "primary-wireframe.json").read_text())
    transfer = json.loads((root / "transfer.json").read_text())
    scaffold = primary.get("scaffold")
    if (primary.get("status") not in ("ok", "review") or scaffold is None):
        raise ValueError(f"{certificate}: no source-supported frozen scaffold")
    if (transfer.get("schema_version") != stability.TRANSFER_SCHEMA
            or transfer.get("policy") != stability.TRANSFER_POLICY
            or transfer.get("primary_semantic_gauge_id") !=
            primary.get("semantic_gauge_id")):
        raise ValueError(f"{certificate}: frozen #89 contract mismatch")
    requested = set(SELECTED[certificate])
    rows = {frame["source_index"]:frame for frame in transfer["frames"]
            if frame["source_index"] in requested}
    if set(rows) != requested:
        raise ValueError(f"{certificate}: selected source frame absent in frozen #89")
    if any(row["transfer_scope"] not in ("crown_view_window", "cyclic_wrap_control")
           or row.get("refit_performed") is not False
           or row.get("semantic_gauge_id") != primary["semantic_gauge_id"]
           for row in rows.values()):
        raise ValueError(f"{certificate}: invalid fixed-ruler transfer")
    return primary, scaffold, rows


def replay_stone(certificate, source_root, manifest, archived, working):
    if certificate not in SELECTED:
        raise ValueError("replay only permitted for predeclared stone IDs")
    primary, scaffold, frozen_frames = frozen_inputs(certificate, archived)
    source = Path(source_root) / certificate
    path = Path(manifest["source_manifest"])
    if not path.is_absolute():
        path = Path.cwd() / path
    if not source.is_dir() or not path.is_file():
        raise ValueError("verified original source and source manifest required")
    dest = Path(working) / certificate
    processed, posed = dest/"processed", dest/"pose"
    pipeline.run(source, processed, path, gain=1.0, accept_review=True)
    # Recreate only #73/#80 canonical arrays; no #75/#96/89 geometry refit.
    analyse_processed_sequence(processed, posed, persist_canonical=True)
    sequence = json.loads((posed / "asscher-pose.json").read_text())
    if wireframe._gauge_id(sequence) != primary["semantic_gauge_id"]:
        raise ValueError(f"{certificate}: regenerated sequence gauge drift")
    frames_by_id = {record["source_index"]:record for record in sequence["frames"]}
    if any(idx not in frames_by_id for idx in SELECTED[certificate]):
        raise ValueError("source image indices not available in original pose")
    readback = []
    for idx in SELECTED[certificate]:
        fixed = frozen_frames[idx]
        record = frames_by_id[idx]
        if (fixed.get("position") != record.get("position") or
            fixed.get("face_role") != record.get("face_role") or
            fixed.get("gauge_quarter_turn") !=
                (record.get("sequence_coordinate") or {}).get("gauge_quarter_turn")):
            raise ValueError(f"{certificate}: frozen frame pose or role drift")
        brightness, mask, valid = stability._load_gauged_arrays(posed, record)
        readback.append((fixed, brightness, mask, valid, None))
    sampled = handoff.sample_sequence(scaffold, readback)
    sampled["certificate"] = certificate
    sampled["frozen_transfer_run"] = FROZEN_SOURCE_RUN
    sampled["source_artifact_policy"] = "SHA256_checked_release_bundle"
    sampled["selected_source_indices"] = list(SELECTED[certificate])
    sampled["face_roles"] = [frozen_frames[x]["face_role"] for x in SELECTED[certificate]]
    sampled["frame_transfer_scopes"] = [
        frozen_frames[x]["transfer_scope"] for x in SELECTED[certificate]
    ]
    sampled["primary_geometry_frozen"] = True
    sampled["primary_scaffold_gauge_id"] = primary["semantic_gauge_id"]
    sampled["pose_reconstructed_not_geometry_refit"] = True
    sampled["physical_facet_correspondence"] = "not_established"
    sampled["brightness_is_canonical_measurement_not_vendor_raw_RGB"] = True
    return sampled


def draw_traces(report, destination):
    """Review-only plot; ranges are descriptive, not normalized comparisons."""
    rows=report["stones"]
    width, section = 1260, 380
    image=Image.new("RGB", (width,section*len(rows)),(249,250,253))
    draw=ImageDraw.Draw(image)
    for i, record in enumerate(rows):
        y0=i*section
        title=record["certificate"]+"    (geometry NOT refitted)"
        draw.text((34,y0+18),title,fill=(21,31,44))
        draw.text((34,y0+38),
            "Frozen #89 source indices: "+", ".join(map(str,record["selected_source_indices"]))+
            "  |  "+(", ".join(sorted(set(record["face_roles"])))) ,
            fill=(80,88,99))
        left,right,top,bottom=82,1218,y0+83,y0+290
        for level in (0,.25,.5,.75,1):
            py=bottom-int((bottom-top)*level)
            draw.line((left,py,right,py),fill=(224,226,230),width=1)
            draw.text((42,py-7),f"{level:.2f}",fill=(82,89,100))
        indices=record["selected_source_indices"]
        for j,index in enumerate(indices):
            x=left+int((right-left)*j/max(1,len(indices)-1))
            draw.text((x-10,bottom+12),str(index),fill=(65,70,79))
        for entity,color in zip(HIGHLIGHTS,SWATCHES):
            samples=[]
            for j,frame in enumerate(record["frames"]):
                row=next((x for x in frame["entities"] if x["semantic_id"]==entity),None)
                if row is None or row["raw_mean_brightness"] is None:
                    samples.append(None)
                else:
                    x=left+int((right-left)*j/max(1,len(indices)-1))
                    val=max(0,min(1,float(row["raw_mean_brightness"])))
                    samples.append((x,bottom-int((bottom-top)*val)))
            for p,q in zip(samples,samples[1:]):
                if p is not None and q is not None:
                    draw.line((*p,*q),fill=color,width=3)
            for xy in samples:
                if xy is not None:
                    x,y=xy
                    draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
        for j,(entity,color) in enumerate(zip(HIGHLIGHTS,SWATCHES)):
            x=left+j*225
            draw.line((x,y0+345,x+35,y0+345),fill=color,width=4)
            draw.text((x+41,y0+338),entity,fill=(35,44,56))
        draw.text((750,y0+37),"Image-plane appearance only; C3/table physical identity unverified",
                  fill=(114,70,65))
    output=Path(destination)
    output.parent.mkdir(parents=True,exist_ok=True)
    image.save(output)
    return output


def run(source_root, manifest_path, frozen_root, output):
    manifest=json.loads(Path(manifest_path).read_text())
    validation.assert_frozen_method(validation.OUTER_METHOD)
    validation.assert_frozen_benchmark_manifest(manifest)
    lookup={row["certificate"]:row for row in manifest["bundles"]}
    if any(x not in lookup for x in SELECTED):
        raise ValueError("predeclared certificates missing from frozen bundle manifest")
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="sparkles-real-smoke-") as temp:
        result=[replay_stone(stone,source_root,lookup[stone],frozen_root,temp)
                for stone in SELECTED]
    report={
        "schema_version":SCHEMA,
        "status":"real_source_fixed_ruler_appearance_smoke",
        "frozen_geometry_source_run":FROZEN_SOURCE_RUN,
        "method":validation.OUTER_METHOD,
        "replay_scope":"two_pinned_stones_selected_8_frames_no_geom_refit",
        "stones":result,
        "counts":{"stones":len(result),"frames":sum(len(x["frames"]) for x in result)},
        "physical_facet_angles_inferred":False,
        "inner_C3_table_physical_identity":"unverified",
        "normalized_brightness_available":False,
        "final_92_disposition":"pending",
        "not_a_quality_score":True,
    }
    (out/"real-fixed-ruler-smoke.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    draw_traces(report,out/"real-fixed-ruler-traces.png")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--frozen-stability-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run(args.source_root,args.manifest,args.frozen_stability_root,args.output)
    print(json.dumps({"status":result["status"],"counts":result["counts"],
                      "no_refit":True,"physical_angles_available":False},sort_keys=True))


if __name__=="__main__":
    main()
