"""Silhouette moments in camera coordinates, without inferring 3D geometry."""
import numpy as np


def measure(mask):
    y,x = np.nonzero(mask)
    if len(x) < 3:
        raise ValueError('Cannot measure empty/degenerate mask')
    points = np.column_stack([x,y]).astype(float)
    centre = points.mean(axis=0)
    covariance = np.cov(points-centre, rowvar=False, bias=True)
    values,vectors = np.linalg.eigh(covariance)
    values,vectors = values[::-1],vectors[:,::-1]
    ratio = float(values[0]/max(values[1],1e-12))
    major = vectors[:,0]
    angle = float((np.degrees(np.arctan2(major[1],major[0]))+90)%180-90)
    ambiguous = ratio < 1.08
    return dict(centroid_xy=centre.tolist(),bbox_xyxy=[int(x.min()),int(y.min()),int(x.max()),int(y.max())],
                width_px=int(np.ptp(x)+1),height_px=int(np.ptp(y)+1),area_px=int(len(x)),
                principal_axes_xy=vectors.T.tolist(),eigenvalues_px2=values.tolist(),
                eigenvalue_ratio=ratio,orientation_deg=None if ambiguous else angle,
                orientation_ambiguous=ambiguous,orientation_period_deg=180,
                principal_axis_lengths_px=(4*np.sqrt(values)).tolist(),
                corner_estimation='omitted: hull vertices are not validated Asscher corners')
