"""Stage orchestration. Failure records remain visible in sequence metadata."""
import json
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from .ingestion import ingest, load_rgb
from .segmentation import segment
from .qc import contact_sheet, overlay, geometry_chart
from .geometry import measure
from .registration import canonicalise
from .photometry import represent, specification
from . import regions
from .qc import region_overlay
from .temporal import write_diagnostics


def run(source, output, order_manifest=None, gain=1.0, diagnostic_indices=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Input and output must be disjoint directories')
    specification(gain)
    # Validate gain even when every frame fails segmentation.
    represent(np.zeros((1,1,3),np.uint8),np.ones((1,1),bool),np.ones((1,1),bool),gain)
    metadata = ingest(source, order_manifest)
    metadata['photometry'] = specification(gain)
    metadata['regions'] = regions.specification()
    output.mkdir(parents=True, exist_ok=True)
    (output/'masks').mkdir(exist_ok=True)
    for folder in ['camera','diamond','photometry','regions']:
        (output/folder).mkdir(exist_ok=True)
    items,registered,region_items = [],[],[]
    for record in metadata['frames']:
        if record['status'] != 'valid': continue
        rgb = load_rgb(source/record['path'])
        camera_path = f'camera/{record["position"]:04d}{Path(record["name"]).suffix.lower()}'
        shutil.copyfile(source/record['path'],output/camera_path)
        record['camera_original_path'] = camera_path
        result = segment(rgb)
        stem = f'{record["position"]:04d}'
        mask_path = f'masks/{stem}.png'
        Image.fromarray(result['mask'].astype(np.uint8)*255).save(output/mask_path)
        Image.fromarray(result['boundary'].astype(np.uint8)*255).save(output/'masks'/f'{stem}-boundary.png')
        record['segmentation'] = {k:v for k,v in result.items() if k not in ('mask','boundary')}
        record['segmentation']['mask_path'] = mask_path
        record['segmentation']['boundary_path'] = f'masks/{stem}-boundary.png'
        if result['status'] == 'ok':
            record['geometry'] = measure(result['mask'])
            normal = canonicalise(rgb,result['mask'],record['geometry'])
            record['registration'] = {k:(v.tolist() if isinstance(v,np.ndarray) else v)
                                      for k,v in normal.items() if k not in ('rgb','mask','valid_mask')}
            paths={'rgb_path':f'diamond/{stem}.png','mask_path':f'diamond/{stem}-mask.png',
                   'valid_mask_path':f'diamond/{stem}-valid.png'}
            record['registration'].update(paths)
            Image.fromarray(normal['rgb']).save(output/paths['rgb_path'])
            for key,array in [('mask_path',normal['mask']),('valid_mask_path',normal['valid_mask'])]:
                Image.fromarray(array.astype(np.uint8)*255).save(output/paths[key])
            channels=represent(normal['rgb'],normal['mask'],normal['valid_mask'],gain)
            channel_path=f'photometry/{stem}.npz'
            np.savez_compressed(output/channel_path,**channels)
            record['photometry_path']=channel_path
            spatial=regions.build(normal['mask'],normal['target_extent'])
            region_path=f'regions/{stem}.npz'
            np.savez_compressed(output/region_path,**spatial)
            record['regions_path']=region_path
            for names,title in [(regions.RADIAL,'radial'),(regions.QUADRANTS,'quadrants'),(regions.SECTORS,'side/corner')]:
                region_items.append((str(record['source_index'])+' '+title,region_overlay(normal['rgb'],spatial,names)))
            label=str(record['source_index'])
            registered.extend([(label+' camera',Image.fromarray(rgb)),
                               (label+' normalised',Image.fromarray(normal['rgb']))])
        items.append((f'{record["source_index"]} {result["status"]}',overlay(rgb,result['mask'],result['boundary'])))
    contact_sheet(items,output/'segmentation.jpg')
    if region_items: contact_sheet(region_items,output/'regions.jpg',columns=3)
    if registered: contact_sheet(registered,output/'registration.jpg',columns=4)
    geometry_chart(metadata['frames'],output/'geometry.png')
    metadata['diagnostics'] = write_diagnostics(metadata,output,diagnostic_indices)
    (output/'sequence.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    return metadata
