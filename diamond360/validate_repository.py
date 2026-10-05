"""Reproduce QC on exact original frames already committed to Sparkles."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image
from .pipeline import run
from .geometry import measure
from .qc import contact_sheet

# These are exact saved archives, not supplier requests or inferred stone IDs.
DATASETS = {
    'IGI-LG756520111': ('pass2-motion-diagrams','Workshop'),
    'IGI-LG818659722': ('compact-evaluation-evidence','Diajewel'),
    'IGI-LG836619414': ('compact-evaluation-evidence','Diajewel'),
    'IGI-LG756580087': ('pass2-compact-evaluation-evidence','Diajewel'),
    'IGI-LG811638512': ('pass2-motion-evidence','Diajewel'),
}


def extract_bundle(archive,destination):
    """Read only flat original frames and their manifest; no extractall/path traversal."""
    destination.mkdir(parents=True,exist_ok=True);frames=destination/'frames';frames.mkdir(exist_ok=True)
    manifests=[];seen=set()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            p=Path(info.filename)
            if info.file_size>16_000_000:raise ValueError('Unexpected large bundle member')
            if p.parent==Path('frames') and p.suffix.lower() in {'.jpg','.jpeg','.png'}:
                if p.name in seen:raise ValueError('Duplicate frame member')
                seen.add(p.name);(frames/p.name).write_bytes(bundle.read(info))
            elif p.suffix=='.json':
                data=json.loads(bundle.read(info))
                if isinstance(data,dict) and ('frames' in data or 'selected_frames' in data):
                    manifests.append(data)
    if len(manifests)!=1 or not seen:raise ValueError('Expected original frames and one source manifest')
    path=destination/'manifest.json';path.write_text(json.dumps(manifests[0],indent=2)+'\n')
    return path,manifests[0]


def validate(repository,work,qc_dir=None):
    repository,work=Path(repository).resolve(),Path(work).resolve()
    if work.exists() and any(work.iterdir()):raise ValueError('Validation work directory must be fresh/empty')
    work.mkdir(parents=True,exist_ok=True)
    summary=dict(schema_version='1.0',scope='79 sparse archived originals; no full-rotation validation',sequences=[])
    registration_items=[]
    for key,(suffix,pipeline) in DATASETS.items():
        archive=repository/'resources'/key/'artifacts'/f'{key}-{suffix}.zip'
        source=work/'inputs'/key;manifest,m=extract_bundle(archive,source)
        if 'faceup_reading_order' in m:indices=m['faceup_reading_order']
        else:indices=m.get('reading_order',m.get('reading_order_zero_based'))[:12]
        out=work/'outputs'/key;r=run(source,out,manifest,diagnostic_indices=indices)
        counts=Counter(f['segmentation']['status'] for f in r['frames'] if 'segmentation' in f)
        centroid_errors=[]
        for f in r['frames']:
            assert hashlib.sha256((out/f['camera_original_path']).read_bytes()).hexdigest()==f['sha256']
            if 'registration' in f:
                mask=np.asarray(Image.open(out/f['registration']['mask_path']))>0
                centroid_errors.append(float(np.max(np.abs(np.array(measure(mask)['centroid_xy'])-127.5))))
        preservation={}
        if r['diagnostics']['status']=='complete':
            a=r['diagnostics']['spaces']['camera']['frame_mean_brightness']
            b=r['diagnostics']['spaces']['diamond']['frame_mean_brightness']
            preservation=dict(mean_brightness_max_abs_difference=float(np.max(np.abs(np.array(a)-b))),
                              mean_brightness_series_correlation=float(np.corrcoef(a,b)[0,1]))
            # Every registered pair, compressed only for the compact combined overview.
            sheet=Image.open(out/'registration.jpg');registration_items.append((key,sheet))
        record=dict(certificate=key,source_pipeline=pipeline,archive=str(archive.relative_to(repository)),
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    frames=r['frame_count'],valid=r['valid_count'],dimensions=r['dimensions'],segmentation=dict(counts),
                    diagnostic_status=r['diagnostics']['status'],diagnostic_indices=r['diagnostics']['accepted_indices'],
                    exclusions=r['diagnostics']['excluded'],max_raster_centroid_error_px=max(centroid_errors,default=None),
                    temporal_preservation=preservation,source_sha256_verified=True,
                    qc_paths=['segmentation.jpg','geometry.png']+(['registration.jpg','regions.jpg','temporal-camera.jpg','temporal-diamond.jpg'] if preservation else []))
        summary['sequences'].append(record)
        print(key,dict(counts),r['diagnostics']['status'])
    (work/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    if qc_dir:
        qc_dir=Path(qc_dir);qc_dir.mkdir(parents=True,exist_ok=True)
        (qc_dir/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
        contact_sheet(registration_items,qc_dir/'cross-registration.jpg',columns=3,cell_size=(500,1000))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',type=Path,default=Path('.'))
    parser.add_argument('--work-dir',type=Path,required=True,help='Fresh/empty directory for extracted and generated data')
    parser.add_argument('--qc-dir',type=Path,help='Optional compact validation summary/contact sheet destination')
    args=parser.parse_args()
    try:validate(args.repository,args.work_dir,args.qc_dir)
    except (OSError,ValueError) as error:parser.error(str(error))

if __name__=='__main__':main()
