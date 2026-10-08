"""Regression for IGI PDFs labelled 'Shape and Cutting Style'.

Do not interpret the trailing 'ting Style' as a diamond shape. Unknown
shape strings produce no shape observation, preserving independent
identity checks for any other certificate fields.
"""
import unittest
from diamond_retrieval.processors import _pdf_fields


class PdfShapeLabelTests(unittest.TestCase):
    def test_historical_shorthand_keeps_real_shape(self):
        fields = _pdf_fields("SHAPE AND CUT ASSCHER\nMEASUREMENTS 7.20 x 7.10 x 5.05")
        self.assertEqual(fields["shape"], "ASSCHER")

    def test_full_cutting_style_heading_same_line(self):
        fields = _pdf_fields("Shape and Cutting Style: Asscher\nCarat Weight 2.69")
        self.assertEqual(fields["shape"], "ASSCHER")

    def test_full_cutting_style_heading_following_line(self):
        fields = _pdf_fields("Shape and Cutting Style\nAsscher\nCarat Weight 2.69")
        self.assertEqual(fields["shape"], "ASSCHER")

    def test_full_cutting_style_heading_no_value_cannot_be_shape(self):
        fields = _pdf_fields("Shape and Cutting Style\nMeasurements 7.20 x 7.10 x 5.05")
        self.assertNotIn("shape", fields)
        self.assertEqual(fields["dimensions"], (7.2, 7.1, 5.05))

    def test_partial_label_fragment_never_passes_shape_identity(self):
        fields = _pdf_fields("Shape and Cutting Style\nCarat Weight 2.69")
        self.assertNotIn("shape", fields)
        self.assertEqual(fields["carat"], 2.69)

    def test_unrecognized_shape_is_missing_not_automatically_equivalent(self):
        fields = _pdf_fields("Shape and Cutting Style\nUnknown Step Variety\nREPORT NUMBER LG816611062")
        self.assertNotIn("shape", fields)
        self.assertEqual(fields["report_number"], "LG816611062")

    def test_real_shape_conflict_remains_detectable(self):
        fields = _pdf_fields("Shape and Cutting Style\nROUND BRILLIANT\nREPORT NUMBER LG816611062")
        self.assertEqual(fields["shape"], "ROUND BRILLIANT")


if __name__ == "__main__":
    unittest.main()
