"""Rebuild compact issue-15 QC from a complete preprocessing run (no fetching)."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from diamond360.region_traces import run, measure_regions
from diamond360.qc import contact_sheet,overlay,map_image
from diamond360.regions import RADIAL

p=argparse.ArgumentParser();p.add_argument('processed',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
source=a.processed;out=a.destination;out.mkdir(parents=True,exist_ok=True)
m=json.loads((source/'sequence.json').read_text());rs={r['source_index']:r for r in m['frames']}
core=list(range(248,256))+list(range(9));wide=list(range(240,256))+list(range(17));sparse=[240,244,248,250,252,254,0,2,4,8,12,16]
for name,ids in [('core',core),('wide',wide)]:run(source,out/name,ids,True)
contact_sheet([(str(i),Image.open(source/rs[i]['camera_original_path'])) for i in range(256)],out/'full-contact.jpg',columns=16,cell_size=(100,110))
qcids=sorted(set(range(0,256,16))|{248,252,255,4,8})
contact_sheet([(str(i)+' '+rs[i]['segmentation']['status'],overlay(np.asarray(Image.open(source/rs[i]['camera_original_path'])),np.asarray(Image.open(source/rs[i]['segmentation']['mask_path']))>0,np.asarray(Image.open(source/rs[i]['segmentation']['boundary_path']))>0)) for i in qcids],out/'segmentation-qc.jpg',columns=7,cell_size=(155,165))
contact_sheet([(str(i),Image.open(source/rs[i]['registration']['rgb_path'])) for i in core],out/'faceup-core.jpg',columns=6,cell_size=(180,190))
contact_sheet([(str(i)+' '+kind,Image.open(source/(rs[i]['camera_original_path'] if kind=='camera' else rs[i]['registration']['rgb_path']))) for i in [248,252,0,4,8,64,128,192] for kind in ['camera','registered']],out/'registration-qc.jpg',columns=4,cell_size=(200,210))
shutil.copyfile(source/'geometry.png',out/'geometry.png')
# Compare sparse/full on identical fixed support, regions and thresholds.
b=[];v=[]
for i in wide:
 with np.load(source/rs[i]['photometry_path']) as c:b.append(c['encoded_brightness']);v.append(c['valid_mask'])
b=np.asarray(b);v=np.asarray(v);common=np.all(v,axis=0)
with np.load(source/rs[wide[0]]['regions_path']) as r:regions={name:r[name] for name in RADIAL}
full=measure_regions(b,np.broadcast_to(common,v.shape),regions)
pos=[wide.index(i) for i in sparse]
sampled=measure_regions(b[pos],np.broadcast_to(common,b[pos].shape),regions)
comparison={'sparse_indices':sparse,'full_interval':wide,'method':'identical common support and per-frame threshold; sparse run/transition counts not valid source-step durations','regions':{name:{'full':full[name],'sparse':{k:val for k,val in sampled[name].items() if k not in ['states','pixel_states']}} for name in RADIAL}}
(out/'comparison.json').write_text(json.dumps(comparison,indent=2,allow_nan=False)+'\n')
# Pixel diagnostics for the primary interval, keeping fixed spatial support.
cp=[wide.index(i) for i in core];cb=b[cp];cv=v[cp];cm=np.all(cv,axis=0)
thresholds=.65*np.median(cb[:,cm],axis=1)
states=cb<thresholds[:,None,None]
transitions=np.sum(states[1:]!=states[:-1],axis=0)
runs=np.zeros(cm.shape,int);longest=np.zeros(cm.shape,int)
for state in states:
 runs=np.where(state,runs+1,0);longest=np.maximum(longest,runs)
occupancy=np.mean(states,axis=0)
arrays=[occupancy,transitions.astype(float),longest.astype(float)]
for arr in arrays:arr[~cm]=np.nan
np.savez_compressed(out/'pixel-activity-core.npz',source_indices=core,common_support=cm,relative_dark_fraction=arrays[0],transition_count=arrays[1],longest_dark_run_frames=arrays[2])
contact_sheet([('dark occupancy 0..1',map_image(arrays[0],1)),('transitions 0..16',map_image(arrays[1],16)),('longest dark run 0..17',map_image(arrays[2],17)),('fixed support (white)',Image.fromarray(cm.astype(np.uint8)*255))],out/'pixel-activity-core.jpg',columns=4,cell_size=(260,280))

# Old sparse method: varying per-frame support and threshold, aggregate pixel dark maps.
old=[]
for j in pos:
 threshold=.65*np.median(b[j][v[j]])
 old.append(b[j]<threshold)
old=np.asarray(old);valid=v[pos];oldmap=np.divide(np.sum(old&valid,axis=0),valid.sum(axis=0),out=np.full(common.shape,np.nan),where=valid.sum(axis=0)>0)
newmap=np.mean(b<(.65*np.median(b[:,common],axis=1))[:,None,None],axis=0);newmap[~common]=np.nan
contact_sheet([('sparse 12; changing support',map_image(oldmap)),('full 33; common support',map_image(newmap))],out/'occupancy-comparison.jpg',columns=2,cell_size=(320,330))
manifest=m['source_manifest'];(out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
report=dict(code_baseline='85093657d3b28714ddb233e8e91ebba129ea6a61',valid_images=m['valid_count'],accepted_outlines=sum('registration' in r for r in m['frames']),frame_count=m['frame_count'],byte_duplicates=[r['source_index'] for r in m['frames'] if 'duplicate_of' in r],pixel_duplicates=[r['source_index'] for r in m['frames'] if 'pixel_duplicate_of' in r],source_copies_verified=True,preprocessing_thresholds_changed=False,primary_interval=core,sensitivity_interval=wide)
for r in m['frames']:
 assert hashlib.sha256((source/r['camera_original_path']).read_bytes()).hexdigest()==r['sha256']
(out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({name:{'full_dark':full[name]['mean_relative_dark_pixel_fraction'],'sparse_dark':sampled[name]['mean_relative_dark_pixel_fraction'],'pixels':full[name]['pixel_states']} for name in RADIAL},indent=2))
