"""Agreement and fail-closed tests for two already-shipped #123 RGB adapters.

#171 and #172 have different archived JSON layouts; they must agree on the
semantic fact that every interior optical candidate is unverified physical
geometry, even when strong and repeated across frames.
"""
from copy import deepcopy
import unittest

from diamond360 import asscher_facet_provenance as facet
from diamond360 import asscher_optical_physical_provenance as optical
from tests.test_asscher_facet_provenance import fixtures


class CrossContractAgreementTests(unittest.TestCase):
    def test_both_archived_formats_agree_without_physical_promotion(self):
        lines,junctions=fixtures()
        original=(deepcopy(lines),deepcopy(junctions))
        a=facet.build_stone_record(lines,junctions)
        b=optical.adapt_stone(lines,junctions)
        self.assertEqual((lines,junctions),original)
        self.assertEqual(a["selected_source_indices"],b["selected_source_indices"])
        self.assertEqual(a["crown_face_identity"],b["face_identity"])
        self.assertEqual(
            a["physical_geometry"]["silhouette"]["vertices_image_plane_normalized"],
            b["physical_geometry"]["external_silhouette"]["vertices_topology_order"]
        )
        self.assertEqual(
            len(a["optical_appearance"]["segments"]),
            sum(len(row["line_segment_candidates"])
                for row in b["optical_appearance"]["frames"])
        )
        self.assertEqual(
            len(a["optical_appearance"]["junction_candidates"]),
            sum(len(row["junction_candidates"])
                for row in b["optical_appearance"]["frames"])
        )
        self.assertEqual(
            a["counts"]["physical_interior_boundaries_validated"],0
        )
        self.assertFalse(b["can_use_as_physical_facet_geometry"])
        a_inner={
            r["semantic_id"]:r for r in
            a["physical_geometry"]["interior_facet_boundaries"]
        }
        for name in optical.INTERIOR_BOUNDARIES:
            self.assertIsNone(a_inner[name]["vertices"])
            self.assertEqual(a_inner[name]["status"],"unavailable")
            self.assertEqual(b["physical_geometry"]["interior_boundaries"][name]["status"],"unavailable")
            with self.assertRaises(ValueError):
                facet.require_physical_support(a_inner[name])
            with self.assertRaises(ValueError):
                optical.require_physical_boundary(b,name)

    def test_editing_output_does_not_turn_optical_line_into_physical_facet(self):
        lines,junctions=fixtures()
        b=optical.adapt_stone(lines,junctions)
        for name in optical.INTERIOR_BOUNDARIES:
            forged=deepcopy(b)
            row=forged["physical_geometry"]["interior_boundaries"][name]
            row.update(
                status="ok",
                provenance_class="independently_validated_physical_junction",
                vertices_topology_order=[[.5,.5]]*8
            )
            with self.assertRaisesRegex(ValueError,"unavailable"):
                optical.require_physical_boundary(forged,name)

    def test_both_reject_asserted_physical_identity_from_rgb_diagnostics(self):
        for mutation in ("line","junction","inner"):
            lines,junctions=fixtures()
            if mutation=="line":
                lines["physical_facet_claim"]=True
            elif mutation=="junction":
                junctions["physical_facet_identity_verified"]=True
            else:
                junctions["frames"][1]["junction_evidence"][
                    "physical_facet_identity_verified"]=True
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    facet.build_stone_record(lines,junctions)
                with self.assertRaises(ValueError):
                    optical.adapt_stone(lines,junctions)


if __name__=="__main__":
    unittest.main()
