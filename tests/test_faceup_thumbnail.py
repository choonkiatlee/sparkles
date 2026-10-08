"""Network-free integrity and cropping tests for #143."""
import copy
import hashlib
from io import BytesIO
import unittest
from PIL import Image, ImageDraw
from diamond_catalogue.faceup_thumbnail import (
    SourceFrame, source_frames, verified_image, assess_image,
    crop_color_original, encode_icon, choose_frame,
)

def synthetic_image():
    im = Image.new("RGB",(360,360),(230,231,229))
    draw=ImageDraw.Draw(im)
    # Dark-edged Asscher cut-corner silhouette on a stable vendor background.
    corners=[(95,45),(265,45),(315,95),(315,265),
             (265,315),(95,315),(45,265),(45,95)]
    draw.polygon(corners,fill=(110,130,135),outline=(65,70,74),width=6)
    # A bright table inside; must not be mistaken for the outside crop.
    draw.rectangle((135,135,225,225),fill=(234,240,244))
    return im

class ThumbnailTests(unittest.TestCase):
    def test_verifies_original_source_sha_before_any_transform(self):
        buf=BytesIO()
        synthetic_image().save(buf,format="PNG")
        data=buf.getvalue()
        source=SourceFrame(0,7,2,hashlib.sha256(data).hexdigest(),"https://example.test/frame.png")
        self.assertEqual(verified_image(data,source).size,(360,360))
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            verified_image(data+b"x",source)

    def test_outer_crop_keeps_full_outline_not_inner_bright_table(self):
        image=synthetic_image()
        cropped,bbox=crop_color_original(image)
        self.assertTrue(bbox[0] < 95 and bbox[1] < 95, bbox)
        self.assertTrue(bbox[2] > 265 and bbox[3] > 265, bbox)
        self.assertLess(max(cropped.size),360)
        icon=encode_icon(cropped)
        self.assertLess(len(icon),25000)
        self.assertEqual(Image.open(BytesIO(icon)).size,(128,128))

    def test_bad_source_and_short_cycle_do_not_claim_faceup(self):
        manifest={"evidence":[{"kind":"still","status":"success","payload_asset":{}}]}
        self.assertEqual(source_frames(manifest),[])
        frame={"source_index":0,"stored_position":0,"asset":{
            "sha256":"f"*64,"storage":{"url":"https://example.test/image.jpg"}}}
        manifest["evidence"]=[{"kind":"rotation","status":"success",
            "metadata":{"sequence_complete":True},"frames":[copy.deepcopy(frame) for _ in range(16)]}]
        self.assertEqual(len(source_frames(manifest,sample_count=16)),16)
        manifest["evidence"][0]["frames"][0]["asset"]["storage"]["url"]="file:///secrets"
        with self.assertRaisesRegex(ValueError,"public HTTPS"):
            source_frames(manifest,sample_count=16)

    def test_selector_requires_existing_pose_and_outer_gates(self):
        self.assertEqual(choose_frame([],sequence_complete=True)["status"],"unavailable")
        result=assess_image(synthetic_image(),position=0)
        self.assertIn(result["record"]["assessment"]["status"],
                      ("ok","review","rejected","failed"))
        self.assertIn(result["outer"]["status"],("candidate","rejected"))
