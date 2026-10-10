"""Pure-text parsing guards for R01's read-only IGI document audit."""
import unittest

from tools.audit_reference_r01_igi_pdf import extract_matches


class R01IgiTests(unittest.TestCase):
    def test_matching_fields(self):
        text = """
        IGI REPORT NUMBER LG566392177
        SHAPE AND CUT ASSCHER
        CARAT WEIGHT 1.97 Carat
        COLOR GRADE D
        CLARITY GRADE VS 1
        """
        self.assertTrue(all(extract_matches(text).values()))

    def test_missing_report_not_a_match(self):
        text = "ASSCHER 1.97 Carat COLOR GRADE D CLARITY GRADE VS1"
        self.assertFalse(extract_matches(text)["report_present"])

    def test_wrong_shape_not_a_match(self):
        text = "LG566392177 ROUND BRILLIANT 1.97 Carat COLOR GRADE D CLARITY GRADE VS1"
        self.assertFalse(extract_matches(text)["asscher_description_present"])

    def test_unlabelled_grade_tokens_do_not_match(self):
        text = "LG566392177 ASSCHER 1.97 Carat D VS1"
        fields = extract_matches(text)
        self.assertFalse(fields["color_d_label_present"])
        self.assertFalse(fields["clarity_vs1_label_present"])


if __name__ == "__main__":
    unittest.main()
