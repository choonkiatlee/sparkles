"""Compact labelled contact sheets; all images are derived QC."""
import math
import numpy as np
from PIL import Image, ImageDraw


def overlay(rgb, mask, boundary=None):
    rgb = np.asarray(rgb).copy()
    rgb[mask] = (.85*rgb[mask] + .15*np.array([20,220,60])).astype(np.uint8)
    if boundary is not None:
        rgb[boundary] = [255,40,40]
    return Image.fromarray(rgb)


def contact_sheet(items, destination, columns=4, cell_size=(240,240)):
    cw, ch = cell_size
    sheet = Image.new('RGB', (columns*cw, max(1,math.ceil(len(items)/columns))*ch), '#eeeeee')
    draw = ImageDraw.Draw(sheet)
    for i,(label,image) in enumerate(items):
        x,y = (i % columns)*cw, (i // columns)*ch
        thumb = image.copy(); thumb.thumbnail((cw-8,ch-32))
        sheet.paste(thumb, (x+(cw-thumb.width)//2,y+28+(ch-32-thumb.height)//2))
        draw.text((x+4,y+4),label,fill='black')
    sheet.save(destination)


def geometry_chart(records, destination):
    """Frame positions are categorical samples, not calibrated time/angle."""
    sheet = Image.new('RGB',(900,720),'white'); draw = ImageDraw.Draw(sheet)
    groups = [('Centroid x / y (camera px)', lambda g:g['centroid_xy']),
              ('Apparent width / height (px)',lambda g:[g['width_px'],g['height_px']]),
              ('PCA axis (degrees; gaps = ambiguous)',lambda g:[g['orientation_deg']])]
    draw.text((15,10),'Geometry vs supplied frame position; blue/red = first/second quantity',fill='black')
    for panel,(label,extract) in enumerate(groups):
        top=45+panel*210; left,right,bottom=65,865,top+155
        draw.text((15,top),label,fill='black')
        series=[extract(r['geometry']) if 'geometry' in r else [None,None] for r in records]
        values=[v for pair in series for v in pair if v is not None]
        if not values:
            draw.text((left,top+50),'No accepted geometry',fill='black');continue
        lo,hi=min(values),max(values);hi=max(hi,lo+1)
        draw.line((left,top+30,left,bottom,right,bottom),fill='grey')
        draw.text((5,top+30),f'{hi:.1f}',fill='black');draw.text((5,bottom-12),f'{lo:.1f}',fill='black')
        for channel,color in enumerate(['#155bb0','#c3392d']):
            previous=None
            for i,pair in enumerate(series):
                v=pair[channel] if channel<len(pair) else None
                if v is None:previous=None;continue
                point=(left+i*(right-left)/max(1,len(series)-1),bottom-(v-lo)/(hi-lo)*125)
                if previous:draw.line((previous,point),fill=color,width=2)
                draw.ellipse((point[0]-2,point[1]-2,point[0]+2,point[1]+2),fill=color);previous=point
        for i,r in enumerate(records):
            draw.text((left+i*(right-left)/max(1,len(records)-1)-8,bottom+8),str(r['source_index']),fill='black')
    sheet.save(destination)


def region_overlay(rgb, regions, names):
    colours=np.array([[230,80,60],[60,190,100],[60,120,235],[235,190,50],
                      [160,80,210],[30,210,210],[230,120,190],[130,170,70]])
    canvas=np.asarray(rgb).copy()
    for i,name in enumerate(names):
        m=regions[name];canvas[m]=(.65*canvas[m]+.35*colours[i]).astype(np.uint8)
    return Image.fromarray(canvas)


def map_image(values, maximum=1):
    values=np.asarray(values);valid=np.isfinite(values)
    scaled=np.nan_to_num(values/maximum,nan=0).clip(0,1)
    # Fixed blue -> cyan -> yellow ramp, grey = no support.
    rgb=np.stack([np.clip(2*scaled-.3,0,1),np.clip(1.8*scaled,0,1),1-scaled],axis=2)
    rgb=(rgb*255).astype(np.uint8);rgb[~valid]=[150,150,150]
    return Image.fromarray(rgb)


def diagnostic_sheet(summary,destination):
    groups=[('mean brightness 0..1','mean',1),('std 0..0.25 (display cap)','std',.25),
            ('relative dark fraction 0..1','relative_dark_fraction',1),
            ('support fraction 0..1','support_fraction',1)]
    contact_sheet([(label,map_image(summary[key],scale)) for label,key,scale in groups],
                  destination,columns=4)


def asscher_pose_overlay(rgb, assessment):
    """Overlay the fitted 2-D Asscher outline/axes for compact pose QC."""
    image = Image.fromarray(np.asarray(rgb, dtype=np.uint8).copy())
    outline = assessment.get("outline")
    if not outline:
        return image
    draw = ImageDraw.Draw(image)
    vertices = [tuple(point) for point in outline["vertices_xy"]]
    if vertices:
        draw.line(vertices + [vertices[0]], fill=(255, 55, 55), width=2)
    cx, cy = outline["centre_xy"]
    radius = max(2, int(round(outline["effective_diameter_px"] * 0.015)))
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=(255, 220, 40),
        width=2,
    )
    axis_half = outline["effective_diameter_px"] * 0.38
    for axis, colour in zip(
        outline["cardinal_axes_xy"],
        [(30, 180, 255), (80, 240, 110)],
    ):
        dx, dy = np.asarray(axis, float) * axis_half
        draw.line(
            (cx - dx, cy - dy, cx + dx, cy + dy),
            fill=colour,
            width=2,
        )
    return image
