"""Regression tests for WDI country-year join behavior."""
import unittest
import pandas as pd
from cipdash.fetch_wb import _combine_frames, _merge_cached, tidy


class TestWorldBankMerging(unittest.TestCase):
    def test_duplicate_index_is_normalized_before_join(self):
        mva = pd.DataFrame(
            {"iso3": ["USA", "USA", "KOR"], "year": [2020, "2020", 2020], "value": [20.0, 21.0, 30.0]}
        )
        trade = pd.DataFrame(
            {"iso3": ["USA", "KOR"], "year": [2020, 2020], "value": [25.0, 40.0]}
        )
        frames = [tidy(mva, "mva_gdp"), tidy(trade, "trade_gdp")]
        result = _combine_frames(frames)
        self.assertEqual(len(result), 2)
        usa = result[result.iso3 == "USA"].iloc[0]
        self.assertEqual(usa.mva_gdp, 21.0)
        self.assertEqual(usa.trade_gdp, 25.0)

    def test_cache_fills_missing_refresh_values(self):
        new = pd.DataFrame({"iso3": ["USA"], "year": [2023], "gdppc_ppp": [100.0]})
        old = pd.DataFrame({"iso3": ["USA", "KOR"], "year": [2023, 2023], "gdppc_ppp": [95.0, 80.0], "mva_gdp": [10.0, 12.0]})
        result = _merge_cached(new, old)
        usa = result[result.iso3 == "USA"].iloc[0]
        kor = result[result.iso3 == "KOR"].iloc[0]
        self.assertEqual(usa.gdppc_ppp, 100.0)
        self.assertEqual(usa.mva_gdp, 10.0)
        self.assertEqual(kor.gdppc_ppp, 80.0)
        self.assertEqual(kor.mva_gdp, 12.0)


if __name__ == "__main__":
    unittest.main()
