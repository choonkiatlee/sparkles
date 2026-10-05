"""Explicit photometry of recorded sRGB; no automatic frame-wise normalisation."""
import numpy as np

COEFFICIENTS = np.array([.2126,.7152,.0722],dtype=np.float32)


def represent(rgb, mask, valid_mask, gain=1.0):
    if not np.isfinite(gain) or not .9 <= gain <= 1.1:
        raise ValueError('Sequence-wide luminance gain must be finite and within 0.9..1.1')
    encoded=np.asarray(rgb,dtype=np.float32)/255
    linear=np.where(encoded<=.04045,encoded/12.92,((encoded+.055)/1.055)**2.4)
    luminance=linear@COEFFICIENTS
    return dict(encoded_brightness=encoded@COEFFICIENTS,linear_luminance=luminance,
                gain_luminance=luminance*gain,chroma_range=encoded.max(axis=2)-encoded.min(axis=2),
                mask=np.asarray(mask,dtype=bool),valid_mask=np.asarray(valid_mask,dtype=bool))


def specification(gain=1.0):
    return dict(assumed_colour_space='sRGB; no radiometric calibration or ICC conversion',
                encoded_brightness='0.2126 R + 0.7152 G + 0.0722 B of encoded RGB / 255',
                linear_luminance='sRGB inverse transfer, then same Rec.709 weights',
                chroma_range='max(encoded RGB)-min(encoded RGB); not a fire measure',
                gain=float(gain),gain_scope='one user-supplied constant for the whole sequence',
                gain_luminance='linear_luminance * gain; unclipped; raw channels retained',
                framewise_adjustments='none',mask_application='separate mask; array values retain background')
