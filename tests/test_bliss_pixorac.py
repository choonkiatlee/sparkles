import base64
import unittest
from diamond_retrieval.resolvers import Loupe360CertificateResolver as Resolver
from diamond_retrieval.loupe360_proxy import validated_proxy_root
from diamond_retrieval.models import EvidenceReference, ProvenanceStep, ROTATION

VIEWER = 'https://diamond.blissvideos.com/?d=M-370-33'
ROOT = 'https://assets-images.pixorac.com/' + base64.b64encode(VIEWER.encode()).decode()

class BlissPixoracTests(unittest.TestCase):
    def test_standard_base64_preserves_embedded_slash(self):
        assert Resolver._unwrap_v360(ROOT) == VIEWER

    def test_certified_bliss_proxy_is_accepted(self):
        ref = EvidenceReference(identifier='bliss',kind=ROTATION,retrieval_key=ROOT,locator=ROOT,
            provenance=(ProvenanceStep('loupe360_exact_certificate', Resolver.endpoint),),
            metadata={'loupe360_proxy_exact_certificate':True,'report_number':'LG739556391','lab':'IGI','supplier_frame_count':256,'supplier_top_index':168})
        assert validated_proxy_root(ref) == ROOT

    def test_certified_bliss_recovers_full_proxy_sequence(self):
        from unittest.mock import patch
        from tests import test_loupe360_proxy_motion as helpers
        from diamond_retrieval import retrieve_reference_media
        http = helpers.FakeHttp(graphql=helpers.certificate(
            report='LG739556391', proxy_root=ROOT, top='168'))
        with patch.object(helpers, 'PROXY_ROOT', ROOT):
            result = retrieve_reference_media(
                'bliss-regression', lab='IGI', report_number='LG739556391', http_client=http)
        self.assertEqual(len(result.rotations), 1)
        self.assertEqual(len(result.rotations[0].frames), 256)
        self.assertEqual(result.rotations[0].face_up_hint, 168)

    def test_bliss_arbitrary_paths_are_rejected(self):
        for url in ['https://diamond.blissvideos.com/other?d=M-370-33','https://diamond.blissvideos.com/?d=../secret','https://diamond.blissvideos.com/?d=M-370-33&extra=1']:
            assert not Resolver._is_supported_rotation_url(url)

if __name__ == "__main__":
    unittest.main()
