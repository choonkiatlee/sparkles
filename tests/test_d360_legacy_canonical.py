"""Exact no-scramble R23 D360 regression: source-backed order and failures.

The public R23 D360 player (PR #252) uses a canonical progressive mapping
if bootstrap has no scramble. Tests do not invent an arbitrary frame order.
"""
import base64
import hashlib
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from PIL import Image

from diamond_retrieval import ROTATION, EvidenceReference, HttpResponse, InvalidPayloadError
from diamond_retrieval.composition import default_config
from diamond_retrieval.motion import ProgressiveRotationProcessor, ordered_positions
from diamond_retrieval.motion_sources import (
    D360LegacyCanonicalRotationDownloader, D360RotationDownloader,
)
from diamond360.d360_source import PACK_COUNTS, PACK_START_SERIALS


def _jpeg(index, size):
    image = Image.new("RGB", size, (index % 256, (index*7) % 256, (index*13) % 256))
    image.putpixel((index % size[0], index % size[1]), (255, 255, 255))
    out = BytesIO()
    image.save(out, format="JPEG", quality=80)
    return out.getvalue()


class FakeHttp:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(url)
        body = self.responses.get(url)
        return HttpResponse(
            200 if body is not None else 404, url,
            {"Content-Type": "application/json" if url.endswith(".json") else "image/jpeg"},
            body if body is not None else b"missing",
        )


class R23LegacyCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.viewer = D360LegacyCanonicalRotationDownloader.VIEWER
        cls.root = D360LegacyCanonicalRotationDownloader.ROOT
        cls.frames = [_jpeg(i, (600, 600)) for i in range(256)]
        cls.still = _jpeg(257, (778, 778))
        cls.meta = json.dumps({"PROPERTIES": {"SHAPE": "EMERALD"}}).encode()
        cls.bootstrap = json.dumps({
            "width": "600", "height": "600", "quality": "4",
            "image": base64.b64encode(cls.frames[0]).decode(),
        }).encode()
        cls.source_responses = {
            cls.root + "/metadata.json": cls.meta,
            cls.root + "/0.json": cls.bootstrap,
            cls.root + "/still.jpg": cls.still,
        }
        index=0
        for number,count in enumerate(PACK_COUNTS,1):
            pack=[base64.b64encode(cls.frames[i]).decode()
                  for i in range(index,index+count)]
            index+=count
            cls.source_responses[cls.root + f"/{number}.json"] = json.dumps(pack).encode()
        assert index==256

    def reference(self, *, report="13534682", lab="GIA", url=None):
        return EvidenceReference(
            identifier="ps281114-r23:loupe-report:supplier-rotation",
            kind=ROTATION, retrieval_key=url or self.viewer,
            locator=url or self.viewer,
            metadata={"lab": lab, "report_number": report},
        )

    def downloader(self, responses=None):
        http=FakeHttp(self.source_responses if responses is None else responses)
        downloader=D360LegacyCanonicalRotationDownloader(http)
        return http, downloader

    def pinned(self):
        return patch.multiple(
            D360LegacyCanonicalRotationDownloader,
            BOOTSTRAP_SHA256=hashlib.sha256(self.bootstrap).hexdigest(),
            METADATA_SHA256=hashlib.sha256(self.meta).hexdigest(),
            PREVIEW_SHA256=hashlib.sha256(self.frames[0]).hexdigest(),
            STILL_SHA256=hashlib.sha256(self.still).hexdigest(),
        )

    def test_pinned_hashes_are_from_live_r23_audit_not_fixture(self):
        self.assertEqual(
            D360LegacyCanonicalRotationDownloader.BOOTSTRAP_SHA256,
            "c2a1eda06f5250c2e7ec4f698e45e2d041739aff9df881f0abb0c2ff8f34fd34",
        )
        self.assertEqual(
            D360LegacyCanonicalRotationDownloader.PREVIEW_SHA256,
            "39cd59e0a7d85450be189a233149871245f01d54af034a8cef0f3298dd417191",
        )

    def test_vendor_default_canonical_reconstructs_all_256_originals(self):
        http, dl = self.downloader()
        with self.pinned():
            raw=dl.download(self.reference())
            evidence=ProgressiveRotationProcessor().process(raw)[0]
        self.assertEqual(len(evidence.frames),256)
        self.assertEqual([f.source_index for f in evidence.frames],list(range(256)))
        self.assertEqual(len({f.sha256 for f in evidence.frames}),256)
        self.assertEqual(evidence.metadata["ordering"],
                         "vendor default canonical progressive order (no scramble)")
        self.assertFalse(evidence.metadata["vendor_scramble_present"])
        self.assertEqual(len(raw.source_responses),10)
        self.assertEqual(http.calls,[self.root+"/metadata.json",self.root+"/0.json",
            self.root+"/still.jpg"]+
            [self.root+f"/{i}.json" for i in range(1,8)])
        identity = [list(range(n)) for n in PACK_COUNTS]
        targets = ordered_positions(identity)
        self.assertEqual(tuple(targets[:8]),(0,64,128,192,32,96,160,224))
        for stored_serial in (0,1,2,3,4,10,37,129,255):
            target_index=targets[stored_serial]
            self.assertEqual(evidence.frames[target_index].payload,
                             self.frames[stored_serial])
        self.assertEqual(evidence.frames[0].payload,self.frames[0])

    def test_uniqueness_and_source_selection(self):
        http=FakeHttp({})
        ref=self.reference()
        supporting=[x for x in default_config(http).downloaders if x.supports(ref)]
        self.assertEqual(len(supporting),1)
        self.assertIsInstance(supporting[0],D360LegacyCanonicalRotationDownloader)
        self.assertFalse(D360RotationDownloader(http).supports(ref))
        ordinary=self.reference(url="https://d360.tech/view.html?d=ANOTHER-ITEM")
        self.assertFalse(D360LegacyCanonicalRotationDownloader(http).supports(ordinary))
        self.assertTrue(D360RotationDownloader(http).supports(ordinary))
        for bad in (
            self.viewer+"#extra",self.viewer+"&surl=https://evil.test",
            self.viewer.replace("https://","http://"),
            self.viewer.replace("d360.tech","d360.tech.evil.test"),
            self.viewer.replace("89-AY-8102","89-AY-8103"),
        ):
            self.assertFalse(D360LegacyCanonicalRotationDownloader(http).supports(
                self.reference(url=bad)))
        self.assertEqual(http.calls,[])

    def test_wrong_report_and_lab_rejected_without_network(self):
        for report,lab in (("OTHER","GIA"),("13534682","IGI")):
            http,dl=self.downloader()
            with self.assertRaises(InvalidPayloadError):
                dl.download(self.reference(report=report,lab=lab))
            self.assertEqual(http.calls,[])

    def test_missing_pack_fails_closed(self):
        truncated=dict(self.source_responses)
        del truncated[self.root+"/4.json"]
        http,dl=self.downloader(truncated)
        with self.pinned(),self.assertRaises(Exception):
            dl.download(self.reference())

    def test_malformed_pack_fails_closed(self):
        truncated=dict(self.source_responses)
        truncated[self.root+"/4.json"]=b"[]"
        _,dl=self.downloader(truncated)
        with self.pinned(),self.assertRaises(InvalidPayloadError):
            dl.download(self.reference())

    def test_changed_bootstrap_and_scramble_fails_closed(self):
        cases=(b"{}",json.dumps({
            "width":"600","height":"600","image":base64.b64encode(self.frames[0]).decode(),
            "scramble":"not an audited source",
        }).encode())
        for payload in cases:
            with self.subTest(payload=payload[:16]):
                responses=dict(self.source_responses)
                responses[self.root+"/0.json"]=payload
                _,dl=self.downloader(responses)
                with self.pinned(),self.assertRaises(InvalidPayloadError):
                    dl.download(self.reference())

    def test_wrong_still_and_first_source_frame_rejected(self):
        responses=dict(self.source_responses)
        responses[self.root+"/still.jpg"]=self.frames[1]
        _,dl=self.downloader(responses)
        with self.pinned(),self.assertRaises(InvalidPayloadError):
            dl.download(self.reference())
        responses=dict(self.source_responses)
        firstpack=json.loads(responses[self.root+"/1.json"])
        firstpack[0]=base64.b64encode(self.frames[1]).decode()
        responses[self.root+"/1.json"]=json.dumps(firstpack).encode()
        _,dl=self.downloader(responses)
        with self.pinned(),self.assertRaises(InvalidPayloadError):
            dl.download(self.reference())

    def test_duplicate_original_payload_refused(self):
        responses=dict(self.source_responses)
        second=json.loads(responses[self.root+"/2.json"])
        second[0]=base64.b64encode(self.frames[0]).decode()
        responses[self.root+"/2.json"]=json.dumps(second).encode()
        _,dl=self.downloader(responses)
        with self.pinned(),self.assertRaises(InvalidPayloadError):
            dl.download(self.reference())

    def test_canonical_mode_provenance_cannot_be_used_with_forged_scramble(self):
        _,dl=self.downloader()
        with self.pinned():
            raw=dl.download(self.reference())
        record=json.loads(raw.payload)
        record["scramble"][0]=[3,2,1,0]
        from diamond_retrieval.models import RawEvidence
        modified=RawEvidence(reference=raw.reference,
            payload=json.dumps(record).encode(),
            media_type=raw.media_type,format=raw.format)
        with self.assertRaises(InvalidPayloadError):
            ProgressiveRotationProcessor().process(modified)


if __name__=="__main__":
    unittest.main()
