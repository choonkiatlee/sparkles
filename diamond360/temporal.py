"""Explicit subset selection and provenance for temporal diagnostics."""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from .ingestion import load_rgb
from .photometry import COEFFICIENTS
from .diagnostics import summarise
from .qc import diagnostic_sheet


def write_diagnostics(metadata,output,indices):
    if indices is None:
        return dict(status='not_requested',reason='Select an explicit comparable face-up subset')
    if len(indices)!=len(set(indices)):
        raise ValueError('Duplicate diagnostic indices')
    grouped={}
    for record in metadata['frames']:
        grouped.setdefault(record['source_index'],[]).append(record)
    ambiguous=[i for i in indices if len(grouped.get(i,[]))>1]
    if ambiguous:raise ValueError(f'Ambiguous selected source indices: {ambiguous}')
    available={i:rs[0] for i,rs in grouped.items()}
    if set(indices)-set(available):
        raise ValueError('Requested diagnostic indices missing from sequence')
    accepted=[];excluded=[];selected_hashes={}
    for i in indices:
        record=available[i]
        if 'registration' not in record:
            excluded.append(dict(source_index=i,reason='invalid_image_or_unaccepted_segmentation'))
        elif record.get('pixel_sha256',record['sha256']) in selected_hashes:
            excluded.append(dict(source_index=i,reason='duplicate_frame',
                                 duplicate_of_index=selected_hashes[record.get('pixel_sha256',record['sha256'])]))
        else:
            selected_hashes[record.get('pixel_sha256',record['sha256'])]=i
            accepted.append(record)
    status=dict(status='complete' if len(accepted)>=2 else 'insufficient_accepted_frames',
                requested_indices=indices,accepted_indices=[r['source_index'] for r in accepted],
                excluded=excluded,weighting='equal weight per supplied frame; no calibrated time/angle',
                relative_dark_definition='brightness < 0.65 * per-frame median on valid stone pixels',
                limitation='recorded-scene activity only; relative darkness is not leakage; no facet correspondence',
                spaces={})
    if len(accepted)<2:return status
    for space in ['diamond','camera']:
        if space=='camera' and len({(r['height'],r['width']) for r in accepted})!=1:
            status['spaces'][space]=dict(status='skipped',reason='mixed_camera_dimensions');continue
        def frames():
            for r in accepted:
                if space=='diamond':
                    with np.load(output/r['photometry_path']) as channels:
                        yield channels['encoded_brightness'],channels['valid_mask']
                else:
                    rgb=load_rgb(output/r['camera_original_path'])
                    mask=np.asarray(Image.open(output/r['segmentation']['mask_path']))>0
                    yield (rgb.astype(np.float32)/255)@COEFFICIENTS,ndi.binary_erosion(mask)
        result=summarise(frames())
        path=f'temporal-{space}.npz'
        np.savez_compressed(output/path,**{k:v for k,v in result.items() if isinstance(v,np.ndarray)})
        diagnostic_sheet(result,output/f'temporal-{space}.jpg')
        status['spaces'][space]={k:v for k,v in result.items() if not isinstance(v,np.ndarray)}
        status['spaces'][space].update(status='complete',path=path,qc_path=f'temporal-{space}.jpg')
    return status
