"""Tests for normalising the official UNIDO table export."""
import gzip
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from cipdash.schema import normalise, read_any


class TestUNIDOTableExport(unittest.TestCase):
    def sample(self):
        return pd.DataFrame([
            {"Year": 2020, "Country": "Korea, Republic of", "CountryCode": "410", "VariableCode": "cip", "Value": 0.31, "ValueUSD": 0.31},
            {"Year": 2020, "Country": "Korea, Republic of", "CountryCode": "410", "VariableCode": "MVApc", "Value": 10, "ValueUSD": 100},
            {"Year": 2020, "Country": "Korea, Republic of", "CountryCode": "410", "VariableCode": "MXpc", "Value": 5, "ValueUSD": 50},
            {"Year": 2020, "Country": "Korea, Republic of", "CountryCode": "410", "VariableCode": "INDint_index", "Value": 0.7, "ValueUSD": 0.7},
            {"Year": 2020, "Country": "Korea, Republic of", "CountryCode": "410", "VariableCode": "cipRank", "Value": 4, "ValueUSD": 4},
        ])

    def test_long_export_pivots_and_maps_m49_codes(self):
        result = normalise(self.sample())
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row.iso3, "KOR")
        self.assertEqual(row.cip, 0.31)
        self.assertEqual(row.mvapc, 100)
        self.assertEqual(row.mxpc, 50)
        self.assertEqual(row.indint, 0.7)

    def test_gzip_csv_is_readable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data.csv.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                self.sample().to_csv(f, index=False)
            result = read_any(path)[0]
        self.assertEqual(len(result), 5)
        self.assertIn("VariableCode", result.columns)


if __name__ == "__main__":
    unittest.main()
