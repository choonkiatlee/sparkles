"""Coarse image-aligned regions; no physical facet identity or windmill inference."""
import numpy as np

RADIAL = ['centre','inner','middle','outer']
QUADRANTS = ['quadrant_NE','quadrant_SE','quadrant_SW','quadrant_NW']
SECTORS = ['side_E','corner_SE','side_S','corner_SW','side_W','corner_NW','side_N','corner_NE']


def build(mask, target_extent=192):
    h,w=mask.shape
    if h != w or target_extent <= 0:
        raise ValueError('Regions require a square canonical canvas and positive extent')
    y,x=np.indices(mask.shape);cx,cy=(w-1)/2,(h-1)/2
    dx,dy=(x-cx)/(target_extent/2),(y-cy)/(target_extent/2)
    radius=np.maximum(abs(dx),abs(dy))
    ring=np.digitize(radius,[.20,.45,.70])
    result={name:mask&(ring==i) for i,name in enumerate(RADIAL)}
    quadrants=[(dx>=0)&(dy<0),(dx>=0)&(dy>=0),(dx<0)&(dy>=0),(dx<0)&(dy<0)]
    result.update({name:mask&q for name,q in zip(QUADRANTS,quadrants)})
    octant=(np.floor((np.arctan2(dy,dx)+np.pi/8)/(np.pi/4)).astype(int))%8
    result.update({name:mask&(octant==i) for i,name in enumerate(SECTORS)})
    return result


def boundary_strip_masks(mask, radius, width, guard=.01, sector_mask=None, target_extent=192):
    """Build guarded strips around one legacy coarse radial boundary."""
    mask = np.asarray(mask, bool)
    h, w = mask.shape
    if h != w or target_extent <= 0:
        raise ValueError('Regions require a square canonical canvas and positive extent')
    radius = float(radius)
    width = float(width)
    guard = float(guard)
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError('boundary radius must be finite and positive')
    if not np.isfinite(width) or width <= 0:
        raise ValueError('strip width must be finite and positive')
    if not np.isfinite(guard) or guard < 0:
        raise ValueError('strip guard must be finite and nonnegative')
    y, x = np.indices(mask.shape)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    dx, dy = (x - cx) / (target_extent / 2), (y - cy) / (target_extent / 2)
    r = np.maximum(abs(dx), abs(dy))
    support = mask.copy()
    if sector_mask is not None:
        sector_mask = np.asarray(sector_mask, bool)
        if sector_mask.shape != mask.shape:
            raise ValueError('sector mask must match the silhouette shape')
        support &= sector_mask
    inside = support & (r >= radius - guard - width) & (r < radius - guard)
    outside = support & (r > radius + guard) & (r <= radius + guard + width)
    return {'inside': inside, 'outside': outside}

def specification():
    return dict(radial_coordinate='max(abs(x-centre),abs(y-centre))/(target_extent/2)',
                radial_edges=[.20,.45,.70],centre_definition='canonical canvas centre',
                quadrants='image x-right/y-down axes, north=top',
                sectors='8 equal angular wedges, sides on image axes and corners on diagonals',
                clipping='all masks intersect per-frame silhouette; intensity summaries also require valid_mask',
                limitation='image-aligned coarse partitions, not material/facet correspondence; no windmill masks')
