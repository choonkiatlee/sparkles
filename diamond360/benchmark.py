"""Batch/aggregate continuous Asscher 360 measurements across stones."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

REGIONS=("centre","inner","middle","outer")
TRACE_SCHEMA="diamond360-region-traces/1"; MANIFEST_SCHEMA="diamond360-benchmark/1"; SUMMARY_SCHEMA="diamond360-benchmark-summary/1"
CSV_FIELDS=["certificate","source_pipeline","window","region","requested_frames","accepted_frames","excluded_frames","common_support_fraction","activation_amplitude_p90_p10","mean_relative_dark_pixel_fraction","region_dark_occupancy","transition_count","observed_adjacent_pairs","transition_rate","longest_dark_run_frames","longest_bright_run_frames","longest_dark_run_fraction","longest_bright_run_fraction","pixel_fraction_with_transitions","pixel_transitions_median","pixel_transitions_p90","pixel_longest_dark_run_p90_frames","pixel_longest_bright_run_p90_frames"]


def cyclic_window(center,size,frame_count):
    if any(type(x) is not int for x in (center,size,frame_count)): raise ValueError("Window arguments must be integers")
    if frame_count<=0 or size<=0 or size%2==0 or size>frame_count: raise ValueError("Window size must be positive, odd, and no larger than the sequence")
    if not 0<=center<frame_count: raise ValueError("Face-up centre is outside the source sequence")
    half=size//2
    return [(center+i)%frame_count for i in range(-half,half+1)]


def _continuous(indices):
    if not isinstance(indices,list) or len(indices)<2 or len(indices)!=len(set(indices)): return False
    maximum=max(indices)
    return all(b==a+1 or (a==maximum and b==0) for a,b in zip(indices,indices[1:]))


def validate_manifest(m):
    if m.get("schema_version")!=MANIFEST_SCHEMA: raise ValueError(f"Expected {MANIFEST_SCHEMA}")
    for key in ("core_window","wide_window"):
        if type(m.get(key)) is not int or m[key]<=0 or m[key]%2==0: raise ValueError(f"{key} must be a positive odd integer")
    if m["core_window"]>m["wide_window"]: raise ValueError("core_window cannot exceed wide_window")
    if not isinstance(m.get("stones"),list) or not m["stones"]: raise ValueError("Benchmark manifest needs at least one stone")
    seen=set()
    for s in m["stones"]:
        cert=s.get("certificate")
        if not isinstance(cert,str) or not cert: raise ValueError("Every stone needs a certificate")
        if cert in seen: raise ValueError(f"Duplicate certificate: {cert}")
        seen.add(cert)
        if not s.get("source_pipeline"): raise ValueError(f"{cert}: source_pipeline is required")
        total,available=s.get("source_frame_count"),s.get("available_frame_count")
        if type(total) is not int or total<=0 or type(available) is not int or not 0<=available<=total: raise ValueError(f"{cert}: invalid source/available frame counts")
        if s.get("source_status") not in {"complete","partial"}: raise ValueError(f"{cert}: source_status must be complete or partial")
        if s["source_status"]=="complete" and available!=total: raise ValueError(f"{cert}: complete source must contain every frame")
        if type(s.get("faceup_center")) is not int or not 0<=s["faceup_center"]<total: raise ValueError(f"{cert}: invalid faceup_center")
        if "trace_files" in s and (not isinstance(s["trace_files"],dict) or set(s["trace_files"])!={"core","wide"}): raise ValueError(f"{cert}: trace_files must contain core and wide")
    return m


def _rate(a,b): return a/b if b else None


def summarise_trace(trace,certificate,source_pipeline,window):
    if trace.get("schema_version")!=TRACE_SCHEMA: raise ValueError(f"{certificate}/{window}: expected {TRACE_SCHEMA}")
    indices=trace.get("requested_indices")
    if not _continuous(indices): raise ValueError(f"{certificate}/{window}: sparse samples cannot supply temporal run statistics")
    accepted=trace.get("accepted_indices",[]); excluded=trace.get("excluded",[]); rows=[]
    for name in REGIONS:
        r=trace.get("regions",{}).get(name)
        if not r: raise ValueError(f"{certificate}/{window}: missing {name} region")
        states,pixels=r.get("states"),r.get("pixel_states")
        if not isinstance(states,dict) or not isinstance(pixels,dict): raise ValueError(f"{certificate}/{window}/{name}: temporal statistics missing")
        observed=states.get("observed_frames") or 0; pairs=states.get("observed_adjacent_pairs") or 0
        dark=states.get("longest_dark_run_frames") or 0; bright=states.get("longest_bright_run_frames") or 0; transitions=states.get("transitions") or 0
        rows.append(dict(certificate=certificate,source_pipeline=source_pipeline,window=window,region=name,
            requested_frames=len(indices),accepted_frames=len(accepted),excluded_frames=len(excluded),
            common_support_fraction=r.get("common_support_fraction"),activation_amplitude_p90_p10=r.get("activation_amplitude_p90_p10"),
            mean_relative_dark_pixel_fraction=r.get("mean_relative_dark_pixel_fraction"),region_dark_occupancy=states.get("dark_occupancy"),
            transition_count=transitions,observed_adjacent_pairs=pairs,transition_rate=_rate(transitions,pairs),
            longest_dark_run_frames=dark,longest_bright_run_frames=bright,longest_dark_run_fraction=_rate(dark,observed),longest_bright_run_fraction=_rate(bright,observed),
            pixel_fraction_with_transitions=pixels.get("fraction_with_transitions"),pixel_transitions_median=pixels.get("transitions_median"),pixel_transitions_p90=pixels.get("transitions_p90"),
            pixel_longest_dark_run_p90_frames=pixels.get("longest_dark_run_p90_frames"),pixel_longest_bright_run_p90_frames=pixels.get("longest_bright_run_p90_frames")))
    return rows


def source_contract(source,expected_frame_count):
    source=Path(source)
    path=source/'source-manifest.json'
    if not path.is_file():
        raise ValueError(f'Complete source requires {path} using diamond360-source/1')
    metadata=json.loads(path.read_text())
    if metadata.get('schema_version')!='diamond360-source/1':
        raise ValueError(f'{path}: expected diamond360-source/1')
    if metadata.get('source_frame_count')!=expected_frame_count:
        raise ValueError(f'{path}: source_frame_count does not match benchmark manifest')
    if metadata.get('sequence_complete') is not True:
        raise ValueError(f'{path}: complete benchmark source must declare sequence_complete=true')
    return path


def _stone_status(s,status,reason=None):
    result={k:s[k] for k in ("certificate","source_pipeline","source_status","source_frame_count","available_frame_count")}; result["status"]=status
    if reason: result["reason"]=reason
    return result


def collect_existing(manifest_path):
    path=Path(manifest_path).resolve(); m=validate_manifest(json.loads(path.read_text())); rows=[]; stones=[]
    for s in m["stones"]:
        if s.get("trace_files"):
            for window in ("core","wide"):
                p=(path.parent/s["trace_files"][window]).resolve()
                if not p.exists(): raise ValueError(f"{s['certificate']}: missing trace file {p}")
                rows+=summarise_trace(json.loads(p.read_text()),s["certificate"],s["source_pipeline"],window)
            stones.append(_stone_status(s,"measured"))
        elif s["source_status"]=="partial": stones.append(_stone_status(s,"partial_source","continuous benchmark withheld until complete ordered frames are available"))
        else: stones.append(_stone_status(s,"source_available","complete source is known but processed trace files are not committed"))
    return dict(schema_version=SUMMARY_SCHEMA,benchmark_manifest=str(path),core_window=m["core_window"],wide_window=m["wide_window"],stones=stones,rows=rows)


def _canvas(title):
    im=Image.new("RGB",(1200,720),"white"); d=ImageDraw.Draw(im); d.text((20,15),title,fill="black"); return im,d


def _metrics_plot(rows,path):
    im,d=_canvas("Cross-stone coarse metrics (core window)"); core=[r for r in rows if r["window"]=="core"]
    metrics=["activation_amplitude_p90_p10","mean_relative_dark_pixel_fraction","pixel_fraction_with_transitions","common_support_fraction"]
    if not core: d.text((20,55),"No measured core rows yet.",fill="black"); im.save(path); return
    width=max(35,min(90,900//len(core)))
    for j,metric in enumerate(metrics):
        vals=[r.get(metric) for r in core]; nums=[v for v in vals if isinstance(v,(int,float)) and math.isfinite(v)]; lo,hi=(min(nums),max(nums)) if nums else (0,1); span=hi-lo or 1; y=90+j*135
        d.text((20,y),metric,fill="black")
        for i,v in enumerate(vals):
            if not isinstance(v,(int,float)): continue
            shade=int(245-180*(v-lo)/span); x=280+i*width; d.rectangle((x,y,x+width-2,y+55),fill=(shade,shade,shade),outline="black"); d.text((x+3,y+18),f"{v:.2f}",fill="black")
    im.save(path)


def _sensitivity_plot(rows,path):
    im,d=_canvas("Core vs wide-window sensitivity"); lookup={(r["certificate"],r["region"],r["window"]):r for r in rows}; pairs=sorted({(r["certificate"],r["region"]) for r in rows}); y=65
    if not pairs: d.text((20,55),"No measured pairs yet.",fill="black")
    for cert,region in pairs:
        a,b=lookup.get((cert,region,"core")),lookup.get((cert,region,"wide"))
        if not a or not b: continue
        d.text((20,y),f"{cert} {region}",fill="black"); x=300
        for metric in ("activation_amplitude_p90_p10","mean_relative_dark_pixel_fraction","common_support_fraction"):
            d.text((x,y),f"{metric.split('_')[0]} {a[metric]:.3f} -> {b[metric]:.3f}",fill="black"); x+=270
        y+=28
    im.save(path)


def _ranks(v):
    order=sorted(range(len(v)),key=lambda i:v[i]); ranks=[0.]*len(v); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and v[order[j]]==v[order[i]]: j+=1
        for k in order[i:j]: ranks[k]=(i+j-1)/2
        i=j
    return ranks


def _redundancy_plot(rows,path):
    im,d=_canvas("Exploratory Spearman metric redundancy (core rows)"); core=[r for r in rows if r["window"]=="core"]; metrics=["activation_amplitude_p90_p10","mean_relative_dark_pixel_fraction","pixel_fraction_with_transitions","common_support_fraction"]
    if len(core)<3: d.text((20,55),"Need at least three measured rows; correlations are diagnostic only.",fill="black"); im.save(path); return
    for i,a in enumerate(metrics):
        d.text((20,130+i*130),a,fill="black")
        for j,b in enumerate(metrics):
            pairs=[(r.get(a),r.get(b)) for r in core]; pairs=[p for p in pairs if all(isinstance(x,(int,float)) for x in p)]; rho=None
            if len(pairs)>=3:
                x=np.asarray(_ranks([p[0] for p in pairs])); y=np.asarray(_ranks([p[1] for p in pairs])); rho=None if np.std(x)==0 or np.std(y)==0 else float(np.corrcoef(x,y)[0,1])
            d.text((380+j*150,130+i*130),"n/a" if rho is None else f"{rho:+.2f}",fill="black")
    im.save(path)


def write_outputs(result,output):
    out=Path(output); out.mkdir(parents=True,exist_ok=True); (out/"summary.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    with (out/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=CSV_FIELDS); w.writeheader(); [w.writerow({k:r.get(k) for k in CSV_FIELDS}) for r in result["rows"]]
    _metrics_plot(result["rows"],out/"metrics.png"); _sensitivity_plot(result["rows"],out/"sensitivity.png"); _redundancy_plot(result["rows"],out/"redundancy.png")


def run(manifest_path,output,source_root=None):
    path=Path(manifest_path).resolve(); m=validate_manifest(json.loads(path.read_text())); out=Path(output).resolve()
    if source_root is None:
        result=collect_existing(path); write_outputs(result,out); return result
    from .pipeline import run as preprocess
    from .region_traces import run as trace_run
    root=Path(source_root).resolve(); rows=[]; stones=[]
    for s in m["stones"]:
        if s["source_status"]!="complete": stones.append(_stone_status(s,"partial_source","continuous benchmark withheld for incomplete ordered source")); continue
        source=root/s["certificate"]
        if not source.is_dir(): stones.append(_stone_status(s,"source_missing",f"expected recovered frames at {source}")); continue
        order_manifest=source_contract(source,s["source_frame_count"])
        target=out/"per-stone"/s["certificate"]; processed=target/"processed"; wide=cyclic_window(s["faceup_center"],m["wide_window"],s["source_frame_count"])
        preprocess(source,processed,order_manifest=order_manifest,gain=1.0,diagnostic_indices=wide)
        for window,size in (("core",m["core_window"]),("wide",m["wide_window"])):
            indices=cyclic_window(s["faceup_center"],size,s["source_frame_count"]); trace=trace_run(processed,target/window,indices,wrap=any(b<a for a,b in zip(indices,indices[1:])))
            rows+=summarise_trace(trace,s["certificate"],s["source_pipeline"],window)
        stones.append(_stone_status(s,"measured"))
    result=dict(schema_version=SUMMARY_SCHEMA,benchmark_manifest=str(path),core_window=m["core_window"],wide_window=m["wide_window"],stones=stones,rows=rows); write_outputs(result,out); return result


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("manifest",type=Path); p.add_argument("--output",type=Path,required=True); p.add_argument("--source-root",type=Path)
    a=p.parse_args()
    try: result=run(a.manifest,a.output,a.source_root)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as e: p.error(str(e))
    print(f"{sum(s['status']=='measured' for s in result['stones'])}/{len(result['stones'])} stones measured -> {a.output}")

if __name__=="__main__": main()
