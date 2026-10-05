"""Translation/isotropic-scale alignment; no pose or facet correspondence claim."""
import numpy as np
from scipy import ndimage as ndi


def canonicalise(rgb, mask, geometry, size=256, target_extent=192):
    if size < 32 or not 8 <= target_extent <= size-8:
        raise ValueError('Target extent must fit within canvas with margins')
    cx,cy=geometry['centroid_xy']; scale=target_extent/max(geometry['width_px'],geometry['height_px'])
    centre=(size-1)/2
    forward=np.array([[scale,0,centre-scale*cx],[0,scale,centre-scale*cy],[0,0,1]],float)
    inverse=np.linalg.inv(forward)
    # SciPy uses (row,column) coordinates, metadata uses pixel-centre (x,y).
    matrix=inverse[:2,:2][::-1,::-1]; offset=inverse[:2,2][::-1]
    channels=[ndi.affine_transform(rgb[:,:,c].astype(float),matrix,offset,
              output_shape=(size,size),order=1,mode='constant',cval=0,prefilter=False) for c in range(3)]
    aligned=np.rint(np.stack(channels,axis=2)).clip(0,255).astype(np.uint8)
    aligned_mask=ndi.affine_transform(mask.astype(np.uint8),matrix,offset,
                 output_shape=(size,size),order=0,mode='constant',cval=0,prefilter=False)>0
    # Require all bilinear source neighbours inside the original silhouette.
    source_interior=ndi.binary_erosion(mask)
    support=ndi.affine_transform(source_interior.astype(float),matrix,offset,
            output_shape=(size,size),order=1,mode='constant',cval=0,prefilter=False)
    valid=(support>.999)&aligned_mask
    return dict(rgb=aligned,mask=aligned_mask,valid_mask=valid,
                camera_to_diamond=forward,diamond_to_camera=inverse,scale=float(scale),
                interpolation='RGB: bilinear, rounded uint8; silhouette: nearest; valid mask: source interior support',
                rotation_applied=False,size=size,target_extent=target_extent)
