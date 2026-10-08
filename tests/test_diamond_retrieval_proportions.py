"""Field-safe metadata extraction for retailer comparison tables.

Never treat words following 'cut', 'polish', 'girdle', or 'culet' in unrelated
HTML prose as a grade. Missing/ungraded values are absent, not fake grades.
"""
import unittest

from diamond_retrieval.retailers import (
    _normalized_proportion, _proportions,
    DiyonaListingProvider, QualityDiamondsListingProvider,
)
from tests.test_diamond_retrieval_retailers import (
    DIYONA_URL, QD_URL, FakeHttpClient, _fixture,
)
from tests.test_diyona_public_api import HTTP, ROW, PAGE


class ComparisonProportionsTests(unittest.TestCase):
    def test_real_qd_html_snapshot_preserves_real_reported_values(self):
        http = FakeHttpClient({
            QD_URL: (_fixture("quality-diamonds-detail.html"), "text/html")
        })
        result = QualityDiamondsListingProvider(http).fetch(QD_URL)
        p = result.metadata.reported_proportions
        self.assertEqual(p, {
            "table_percent": 60.0,
            "depth_percent": 60.6,
            "length_width_ratio": 1.42,
            "polish": "Excellent",
            "symmetry": "Excellent",
            "fluorescence": "None",
            "girdle": "Medium to Thick",
        })
        self.assertNotIn("cut", p)
        self.assertNotIn("culet", p)

    def test_flattened_text_does_not_invent_values_from_neighboring_labels(self):
        # Matches the bad published QD metadata:
        # cut='and', polish='ed', culet='Asscher,', girdle='Girdle:'
        noisy = (
            "Asscher, Cut and Polished diamond. "
            "Cut and polish enhanced. Culet Asscher, "
            "Girdle: Girdle: "
            "Polished finish. Table 64% Depth 64.6% Ratio 1.00 "
            "Symmetry Excellent Fluorescence None"
        )
        result = _proportions(noisy)
        self.assertEqual(result, {
            "table_percent": 64.0,
            "depth_percent": 64.6,
            "length_width_ratio": 1.0,
            "symmetry": "Excellent",
            "fluorescence": "None",
        })

    def test_explicit_valid_non_numeric_proportions(self):
        result = _proportions(
            "Cut Grade: Excellent Polish: EX Symmetry: Very Good "
            "Fluorescence: Faint Girdle: Very Thin to Slightly Thick "
            "Culet: Very Small Table: 60.0% Depth: 67.1% L/W Ratio: 1.01"
        )
        self.assertEqual(result, {
            "cut": "Excellent",
            "polish": "Excellent",
            "symmetry": "Very Good",
            "fluorescence": "Faint",
            "girdle": "Very Thin to Slightly Thick",
            "culet": "Very Small",
            "table_percent": 60.0,
            "depth_percent": 67.1,
            "length_width_ratio": 1.01,
        })

    def test_ungraded_and_missing_are_omitted_not_literal_values(self):
        p = _proportions(
            "Cut: Not Graded Polish: N/A Symmetry: - "
            "Fluorescence: N/A Girdle: Unknown Culet: -"
        )
        self.assertEqual(p, {})
        for key in ("cut", "polish", "symmetry", "fluorescence",
                    "girdle", "culet"):
            self.assertNotIn(key, p)

    def test_none_is_genuine_for_fluorescence_and_culet_not_cut_grade(self):
        self.assertEqual(_normalized_proportion("fluorescence", "NON"), "None")
        self.assertEqual(_normalized_proportion("fluorescence", "None"), "None")
        self.assertEqual(_normalized_proportion("culet", "None"), "None")
        self.assertIsNone(_normalized_proportion("cut", "None"))

    def test_bad_number_and_placeholder_rejected(self):
        for value in (None, "-", "--", "N/A", "not graded", "Unknown",
                      "Infinity", "-10", "101"):
            self.assertIsNone(_normalized_proportion("table_percent", value))
        self.assertEqual(_normalized_proportion("table_percent", "60%"), 60.0)
        self.assertEqual(_normalized_proportion("length_width_ratio", "1.01"), 1.01)

    def test_public_diyona_api_removes_dash_cut_and_normalizes_codes(self):
        row = {**ROW, "cut": "-", "polish": "EX", "symmetry": "EX",
               "fluorescence": "NON", "table_percent": 60.0}
        listing = DiyonaListingProvider(HTTP(rows=[row])).fetch(PAGE)
        p = listing.metadata.reported_proportions
        self.assertNotIn("cut", p)
        self.assertEqual(p["polish"], "Excellent")
        self.assertEqual(p["symmetry"], "Excellent")
        self.assertEqual(p["fluorescence"], "None")
        self.assertEqual(p["table_percent"], 60.0)

    def test_public_diyona_api_missing_grades_remain_absent(self):
        row = {**ROW, "cut": None, "polish": "N/A",
               "symmetry": "-", "fluorescence": "unknown"}
        listing = DiyonaListingProvider(HTTP(rows=[row])).fetch(PAGE)
        for key in ("cut", "polish", "symmetry", "fluorescence"):
            self.assertNotIn(key, listing.metadata.reported_proportions)

    def test_price_is_unmodified_and_remains_a_listed_price(self):
        qd = QualityDiamondsListingProvider(FakeHttpClient({
            QD_URL: (_fixture("quality-diamonds-detail.html"), "text/html")
        })).fetch(QD_URL).metadata
        self.assertEqual(str(qd.price), "1330.00")
        self.assertEqual(qd.currency, "GBP")
        diyona = DiyonaListingProvider(HTTP()).fetch(PAGE).metadata
        self.assertEqual(str(diyona.price), "749.77")
        self.assertEqual(diyona.currency, "USD")


if __name__ == "__main__":
    unittest.main()
