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
