"""Streaming, support-aware activity maps; never optical quality scores."""
import numpy as np


def summarise(frames, dark_ratio=.65):
    if not np.isfinite(dark_ratio) or not 0 < dark_ratio < 1:
        raise ValueError('Relative dark ratio must be within 0..1')
    count=0;shape=None;thresholds=[];frame_means=[]
    for brightness, mask in frames:
        brightness=np.asarray(brightness,dtype=np.float64)
        valid=np.asarray(mask,bool)&np.isfinite(brightness)
        if shape is None:
            shape=brightness.shape
            support=np.zeros(shape,np.uint32);total=np.zeros(shape);squares=np.zeros(shape);dark=np.zeros(shape)
        if brightness.shape != shape or valid.shape != shape:
            raise ValueError('Mixed dimensions in temporal map')
        pixels=brightness[valid]
        threshold=float(np.median(pixels)*dark_ratio) if len(pixels) else None
        thresholds.append(threshold);frame_means.append(float(pixels.mean()) if len(pixels) else None)
        values=np.where(valid,brightness,0)
        support+=valid;total+=values;squares+=values*values
        if threshold is not None:dark+=valid&(brightness<threshold)
        count+=1
    if not count:raise ValueError('No frames for diagnostics')
    mean=np.full(shape,np.nan);fraction=np.full(shape,np.nan)
    np.divide(total,support,out=mean,where=support>0)
    np.divide(dark,support,out=fraction,where=support>0)
    moment=np.zeros(shape);np.divide(squares,support,out=moment,where=support>0)
    std=np.sqrt(np.maximum(moment-mean**2,0));std[support<2]=np.nan
    return dict(mean=mean.astype(np.float32),std=std.astype(np.float32),
                relative_dark_fraction=fraction.astype(np.float32),support_count=support,
                support_fraction=(support/count).astype(np.float32),
                frame_count=count,relative_dark_ratio=dark_ratio,frame_dark_thresholds=thresholds,
                frame_mean_brightness=frame_means)
