"""Continuous scene measurements, separate from preprocessing and quality judgments."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from .regions import RADIAL


def validate_interval(indices, source_frame_count=None, wrap=False):
    if len(indices) < 2 or len(indices) != len(set(indices)) or any(type(i) is not int or i < 0 for i in indices):
        raise ValueError('Select at least two unique nonnegative source indices')
    if wrap and (type(source_frame_count) is not int or source_frame_count <= 0):
        raise ValueError('Wrap requires a known source frame count')
    if source_frame_count is not None and any(i >= source_frame_count for i in indices):
        raise ValueError('Source index exceeds source frame count')
    for a,b in zip(indices,indices[1:]):
        if b != a+1 and not (wrap and a == source_frame_count-1 and b == 0):
            raise ValueError('Continuous traces require consecutive source indices; sparse samples cannot supply runs')


def state_summary(states):
    """None breaks runs/adjacency; endpoint runs are censored, not loop-joined."""
    observed=[s for s in states if s is not None]
    longest={True:0,False:0}; previous=None; length=0; transitions=0; pairs=0
    for state in states:
        if state is None:
            previous=None;length=0;continue
        if previous is not None:
            pairs+=1;transitions+=int(state != previous)
        length=length+1 if state == previous else 1
        longest[state]=max(longest[state],length);previous=state
    return dict(observed_frames=len(observed),dark_occupancy=sum(observed)/len(observed) if observed else None,
                transitions=transitions,observed_adjacent_pairs=pairs,
                longest_dark_run_frames=longest[True],longest_bright_run_frames=longest[False],
                run_boundary='interval endpoints and gaps censor runs; no implicit loop closure')


def measure_regions(brightness, valid_masks, region_masks, observed=None):
    brightness=np.asarray(brightness);valid_masks=np.asarray(valid_masks,bool)
    if brightness.ndim != 3 or valid_masks.shape != brightness.shape:
        raise ValueError('Matching frame-height-width brightness and support required')
    observed=np.ones(len(brightness),bool) if observed is None else np.asarray(observed,bool)
    if observed.shape != (len(brightness),):raise ValueError('Observed flags must match frames')
    valid_masks=valid_masks & np.isfinite(brightness)
    common=np.all(valid_masks[observed],axis=0) if observed.any() else np.zeros(brightness.shape[1:],bool)
    global_medians=[float(np.median(b[common])) if ok and common.any() else None for b,ok in zip(brightness,observed)]
    result={}
    for name,region in region_masks.items():
        region=np.asarray(region,bool)
        if region.shape != common.shape:raise ValueError('Region shape differs from canvas')
        support=region & common;n=int(support.sum());nominal=int(region.sum())
        medians=[];dark=[];states=[];dynamic=[]
        for b,v,ok,g in zip(brightness,valid_masks,observed,global_medians):
            dynamic.append(float((v & region).sum()/nominal) if ok and nominal else None)
            if not ok or not n or g is None:
                medians.append(None);dark.append(None);states.append(None);continue
            median=float(np.median(b[support]));medians.append(median)
            dark.append(float(np.mean(b[support] < .65*g)));states.append(bool(median < .65*g))
        values=[v for v in medians if v is not None]
        pixel_stats = None
        if n:
            transitions=np.zeros(n,int);dark_run=np.zeros(n,int);bright_run=np.zeros(n,int)
            longest_dark=np.zeros(n,int);longest_bright=np.zeros(n,int);previous=None
            for frame,ok,g in zip(brightness,observed,global_medians):
                if not ok or g is None:
                    previous=None;dark_run[:]=0;bright_run[:]=0;continue
                state=frame[support] < .65*g
                if previous is not None:transitions += state != previous
                dark_run=np.where(state,dark_run+1,0);bright_run=np.where(~state,bright_run+1,0)
                longest_dark=np.maximum(longest_dark,dark_run);longest_bright=np.maximum(longest_bright,bright_run)
                previous=state
            pixel_stats=dict(fraction_with_transitions=float(np.mean(transitions>0)),
                transitions_median=float(np.median(transitions)),transitions_p90=float(np.quantile(transitions,.9)),
                max_transitions=int(transitions.max()),longest_dark_run_p90_frames=float(np.quantile(longest_dark,.9)),
                longest_dark_run_max_frames=int(longest_dark.max()),longest_bright_run_p90_frames=float(np.quantile(longest_bright,.9)),
                limitation='fixed image pixels, not physical facet tracking; endpoint runs censored')
        result[name]=dict(common_support_pixels=n,reference_region_pixels=nominal,
            common_support_fraction=n/nominal if nominal else None,per_frame_support_fraction=dynamic,
            median_brightness=medians,global_median_brightness=global_medians,
            relative_dark_pixel_fraction=dark,
            mean_relative_dark_pixel_fraction=float(np.mean([v for v in dark if v is not None])) if values else None,
            activation_amplitude_p90_p10=float(np.quantile(values,.9)-np.quantile(values,.1)) if values else None,
            median_brightness_range=[min(values),max(values)] if values else None,
            dark_states=states,states=state_summary(states),pixel_states=pixel_stats)
    return result


def plot_traces(result, destination):
    indices=result['requested_indices'];n=len(indices)
    im=Image.new('RGB',(1100,900),'white');d=ImageDraw.Draw(im)
    d.text((15,10),'Median encoded brightness (blue); relative-dark pixel fraction (red); fixed common support',fill='black')
    for j,name in enumerate(RADIAL):
        r=result['regions'][name];top=45+j*205;left,right,bottom=65,1070,top+145
        d.text((15,top),f'{name}: common support {r["common_support_pixels"]} pixels; amplitude {r["activation_amplitude_p90_p10"]}',fill='black')
        d.line((left,top+25,left,bottom,right,bottom),fill='grey')
        d.text((25,top+25),'1.0',fill='black');d.text((25,bottom-10),'0.0',fill='black')
        for key,color in [('median_brightness','#155bb0'),('relative_dark_pixel_fraction','#c3392d')]:
            previous=None
            for i,v in enumerate(r[key]):
                if v is None:previous=None;continue
                point=(left+i*(right-left)/(n-1),bottom-v*120)
                if previous:d.line((previous,point),fill=color,width=2)
                d.ellipse((point[0]-2,point[1]-2,point[0]+2,point[1]+2),fill=color);previous=point
        for i,state in enumerate(r['dark_states']):
            x=left+i*(right-left)/n
            d.rectangle((x,bottom+8,x+(right-left)/n,bottom+20),fill='#333333' if state is True else '#dddddd' if state is False else '#e39944')
        for i in range(0,n,max(1,n//10)):
            d.text((left+i*(right-left)/(n-1)-8,bottom+24),str(indices[i]),fill='black')
    d.text((15,880),'Source indices, unknown angles/timing. State strip: dark median < 0.65 x global median; grey = other; orange = excluded.',fill='black')
    im.save(destination)


def run(processed, output, indices, wrap=False):
    processed=Path(processed).resolve();output=Path(output).resolve()
    if processed == output or processed in output.parents or output in processed.parents:
        raise ValueError('Trace input/output must be disjoint')
    if output.exists() and any(output.iterdir()):raise ValueError('Choose a fresh trace output')
    sequence=processed/'sequence.json';metadata=json.loads(sequence.read_text())
    validate_interval(indices,metadata.get('source_frame_count'),wrap)
    lookup={}
    for r in metadata['frames']:lookup.setdefault(r['source_index'],[]).append(r)
    selected=[];exclusions=[];seen=set()
    for i in indices:
        records=lookup.get(i,[])
        if len(records)>1:raise ValueError('Ambiguous source index')
        r=records[0] if records else None
        digest=r.get('pixel_sha256',r['sha256']) if r else None
        reason='missing_frame' if r is None else 'unaccepted_outline' if 'registration' not in r else 'duplicate_frame' if digest in seen else None
        if reason:exclusions.append(dict(source_index=i,reason=reason));selected.append(None)
        else:seen.add(digest);selected.append(r)
    accepted=[r for r in selected if r]
    if not accepted:raise ValueError('No accepted frames in interval')
    with np.load(processed/accepted[0]['regions_path']) as masks:
        regions={name:masks[name].copy() for name in RADIAL}
    shape=regions['centre'].shape;b=[];v=[]
    for r in selected:
        if r:
            with np.load(processed/r['photometry_path']) as c:
                b.append(c['encoded_brightness'].copy());v.append(c['valid_mask'].copy())
        else:b.append(np.zeros(shape));v.append(np.zeros(shape,bool))
    measured=measure_regions(b,v,regions,[r is not None for r in selected])
    result=dict(schema_version='diamond360-region-traces/1',sequence_sha256=hashlib.sha256(sequence.read_bytes()).hexdigest(),
        requested_indices=indices,accepted_indices=[r['source_index'] for r in accepted],excluded=exclusions,wrap_explicit=wrap,
        brightness_definition=metadata['brightness_definition'],
        support_definition='intersection of valid support across accepted interval frames; fixed image-aligned radial regions',
        dark_definition='pixel/region median < 0.65 * per-frame global median on common support',
        units='frames/source steps, not seconds or degrees; equal observed-frame weights',
        limitation='recorded scene, pose and lighting changes; coarse regions are not facets; no quality score or leakage inference',regions=measured)
    output.mkdir(parents=True,exist_ok=True)
    (output/'traces.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (output/'traces.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['source_index','region','median_brightness','relative_dark_pixel_fraction','dark_state','per_frame_support_fraction'])
        for j,i in enumerate(indices):
            for name,r in measured.items():writer.writerow([i,name,r['median_brightness'][j],r['relative_dark_pixel_fraction'][j],r['dark_states'][j],r['per_frame_support_fraction'][j]])
    plot_traces(result,output/'traces.png')
    # Fixed support is auditable separately from intensity.
    common=np.all(np.asarray(v)[[r is not None for r in selected]],axis=0)
    Image.fromarray(common.astype(np.uint8)*255).save(output/'common-support.png')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('processed',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--indices',required=True,help='Ordered consecutive indices, including wrap if explicitly allowed');p.add_argument('--wrap',action='store_true')
    a=p.parse_args()
    try:r=run(a.processed,a.output,[int(i) for i in a.indices.split(',')],a.wrap)
    except (ValueError,OSError,KeyError) as e:p.error(str(e))
    print(f'{len(r["accepted_indices"])}/{len(r["requested_indices"])} observed frames -> {a.output}')

if __name__=='__main__':main()
