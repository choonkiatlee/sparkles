"""Background-aware textured silhouette; convex envelope is an approximation."""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull, QhullError


def segment(rgb, contrast_threshold=18.0, gradient_threshold=4.0):
    rgb = np.asarray(rgb)
    h, w = rgb.shape[:2]
    empty = np.zeros((h,w), bool)
    result = dict(status='failed', reasons=[], mask=empty, boundary=empty,
                  vertices_xy=[], method='border-background/textured-component/convex-envelope')
    if min(h,w) < 32:
        result['reasons'] = ['image_too_small']; return result
    border = np.concatenate([rgb[:3].reshape(-1,3), rgb[-3:].reshape(-1,3),
                             rgb[:, :3].reshape(-1,3), rgb[:, -3:].reshape(-1,3)])
    background = np.median(border, axis=0)
    noise = float(np.quantile(np.linalg.norm(border-background, axis=1), .75))
    threshold = max(contrast_threshold, noise*2)
    result.update(background_rgb=background.tolist(), border_spread=noise,
                  contrast_threshold=threshold, gradient_threshold=gradient_threshold,
                  border_outlier_fraction=float((np.linalg.norm(border-background,axis=1)>30).mean()))
    if noise > 30:
        result['reasons'] = ['nonuniform_or_contaminated_border']; return result
    smooth = ndi.gaussian_filter(rgb.astype(float), sigma=(.65,.65,0))
    gy, gx = np.gradient(smooth, axis=(0,1))
    gradient = np.sqrt((gx*gx + gy*gy).sum(axis=2))
    contrast = np.linalg.norm(smooth - background, axis=2)
    seeds = (contrast > threshold) & (gradient > gradient_threshold)
    connected = ndi.binary_closing(ndi.binary_dilation(seeds, iterations=2), iterations=2)
    labels, count = ndi.label(connected)
    if not count:
        result['reasons'] = ['no_silhouette']; return result
    sizes = np.bincount(labels.ravel()); sizes[0] = 0
    component = labels == sizes.argmax()
    y, x = np.nonzero(component)
    if len(x) < max(40, h*w*.0005):
        result['reasons'] = ['insufficient_foreground']; return result
    try:
        points = np.column_stack([x,y]); hull = ConvexHull(points)
        vertices = points[hull.vertices]
    except QhullError:
        result['reasons'] = ['degenerate_contour']; return result
    raster = Image.new('L', (w,h))
    ImageDraw.Draw(raster).polygon([tuple(p) for p in vertices], fill=255)
    mask = ndi.binary_erosion(np.asarray(raster) > 0, iterations=2)
    boundary = mask & ~ndi.binary_erosion(mask)
    fraction = float(mask.mean())
    reasons = []
    if result['border_outlier_fraction'] > .05:
        reasons.append('foreground_or_nonuniformity_on_border')
    if fraction < .01 or fraction > .85:
        reasons.append('implausible_area')
    if x.min() <= 3 or y.min() <= 3 or x.max() >= w-4 or y.max() >= h-4:
        reasons.append('outline_near_image_edge')
    if sizes.max() < sizes.sum()*.45:
        reasons.append('fragmented_foreground')
    by,bx = np.nonzero(boundary)
    boundary_points = np.column_stack([bx,by])
    vertices = boundary_points[ConvexHull(boundary_points).vertices]
    result.update(status='review' if reasons else 'ok', reasons=reasons,
                  mask=mask, boundary=boundary, vertices_xy=vertices.tolist(),
                  area_fraction=fraction, component_seed_pixels=int(sizes.max()))
    return result
