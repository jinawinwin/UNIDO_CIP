"""Regression tests for the UNIDO CIP API response normalizer."""
import unittest

from cipdash.fetch_unido import _extract_records


CODES = ["cip", "cipRank", "MVApc", "MXpc"]
LABELS = {"CIP score": "cip", "Manufacturing value added per capita": "MVApc"}


class TestExtractRecords(unittest.TestCase):
    def test_long_json_response(self):
        payload = {"data": [
            {"period": "2023", "variableCode": "cip", "value": 0.31},
            {"period": "2023", "variableCode": "cipRank", "value": 6},
            {"period": "2024", "variableCode": "cip", "value": 0.32},
        ]}
        rows = _extract_records(payload, "KOR", "Republic of Korea", CODES, LABELS)
        got = {(r["year"], r["variable"]): r["value"] for r in rows}
        self.assertEqual(got[(2023, "cip")], 0.31)
        self.assertEqual(got[(2023, "cipRank")], 6)
        self.assertEqual(got[(2024, "cip")], 0.32)

    def test_wide_year_to_variables_json(self):
        payload = {"2022": {"cip": 0.29, "MVApc": "12,345", "cipRank": 8}}
        rows = _extract_records(payload, "KOR", "Republic of Korea", CODES, LABELS)
        got = {(r["year"], r["variable"]): r["value"] for r in rows}
        self.assertEqual(got[(2022, "cip")], 0.29)
        self.assertEqual(got[(2022, "MVApc")], 12345)
        self.assertEqual(got[(2022, "cipRank")], 8)

    def test_variable_label_and_missing_values(self):
        payload = {"observations": [
            {"year": 2020, "variable": "CIP score", "value": "0.28"},
            {"year": 2020, "variable": "CIP score", "value": ".."},
            {"year": 2020, "variable": "Unknown metric", "value": 100},
        ]}
        rows = _extract_records(payload, "KOR", "Republic of Korea", CODES, LABELS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["variable"], "cip")
        self.assertEqual(rows[0]["value"], 0.28)


if __name__ == "__main__":
    unittest.main()
