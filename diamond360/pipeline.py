"""Stage orchestration. Failure records remain visible in sequence metadata."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .ingestion import ingest, load_rgb
from .segmentation import segment
from .qc import contact_sheet, overlay


def run(source, output, order_manifest=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Input and output must be disjoint directories')
    metadata = ingest(source, order_manifest)
    output.mkdir(parents=True, exist_ok=True)
    (output/'masks').mkdir(exist_ok=True)
    items = []
    for record in metadata['frames']:
        if record['status'] != 'valid': continue
        rgb = load_rgb(source/record['path'])
        result = segment(rgb)
        stem = f'{record["position"]:04d}'
        mask_path = f'masks/{stem}.png'
        Image.fromarray(result['mask'].astype(np.uint8)*255).save(output/mask_path)
        Image.fromarray(result['boundary'].astype(np.uint8)*255).save(output/'masks'/f'{stem}-boundary.png')
        record['segmentation'] = {k:v for k,v in result.items() if k not in ('mask','boundary')}
        record['segmentation']['mask_path'] = mask_path
        record['segmentation']['boundary_path'] = f'masks/{stem}-boundary.png'
        items.append((f'{record["source_index"]} {result["status"]}',overlay(rgb,result['mask'],result['boundary'])))
    contact_sheet(items,output/'segmentation.jpg')
    (output/'sequence.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    return metadata
