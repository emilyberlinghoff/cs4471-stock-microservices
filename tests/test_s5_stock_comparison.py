import copy
import json
import unittest
from datetime import date, timedelta
from decimal import Decimal

from s5_stock_comparison import StockComparisonError, compare_stocks


class StockComparisonTests(unittest.TestCase):
    def setUp(self):
        # Synthetic calendars with a weekend and an exchange holiday between endpoints.
        self.days = ["2025-01-17", "2025-01-21", "2025-01-22"]
        self.prices = {
            "AAA": dict(zip(self.days, [100, 105, 110])),
            "BBB": dict(zip(self.days, [200, 190, 180])),
        }
        self.calendars = {symbol: list(self.days) for symbol in self.prices}

    def calculate(self, symbols=("AAA", "BBB"), start=None, end=None):
        return compare_stocks(
            symbols, start or self.days[0], end or self.days[-1], self.prices,
            trading_dates=self.calendars,
        )

    def assert_error(self, code, symbol=None, **kwargs):
        with self.assertRaises(StockComparisonError) as caught:
            self.calculate(**kwargs)
        payload = caught.exception.to_dict()
        self.assertEqual(payload["error"]["code"], code)
        if symbol is not None:
            self.assertEqual(payload["error"]["symbol"], symbol)
        self.assertNotIn("ranking", payload)
        return payload

    def test_positive_negative_changes_and_metadata(self):
        result = self.calculate()
        self.assertEqual(result["ranking"], [
            {"symbol": "AAA", "percentage_change": 10.0},
            {"symbol": "BBB", "percentage_change": -10.0},
        ])
        self.assertEqual(result["service_id"], "S5")
        self.assertEqual(result["start_date"], self.days[0])
        self.assertEqual(result["end_date"], self.days[-1])
        self.assertEqual(result["effective_start_date"], self.days[0])
        self.assertEqual(result["effective_end_date"], self.days[-1])
        self.assertEqual(result["price_basis"], "unadjusted_daily_close")
        json.dumps(result, allow_nan=False)

    def test_different_exchange_calendars_use_common_endpoints(self):
        self.calendars["BBB"] = self.days[1:]
        self.prices["BBB"].pop(self.days[0])
        result = self.calculate()
        self.assertEqual(result["effective_start_date"], self.days[1])
        self.assertEqual(result["effective_end_date"], self.days[-1])
        self.assertEqual(result["ranking"][0]["percentage_change"], 4.7619)
        self.assertEqual(result["ranking"][1]["percentage_change"], -5.2632)

    def test_rank_by_unrounded_change_not_displayed_percentage(self):
        self.prices["AAA"][self.days[-1]] = "100.000011"
        self.prices["BBB"] = dict.fromkeys(self.days, "100")
        self.prices["BBB"][self.days[-1]] = "100.000012"
        ranking = self.calculate()["ranking"]
        self.assertEqual([row["symbol"] for row in ranking], ["BBB", "AAA"])
        self.assertEqual([row["percentage_change"] for row in ranking], [0.0, 0.0])

    def test_exact_ties_use_alphabetical_symbol_order(self):
        self.prices["BBB"][self.days[-1]] = 220
        ranking = self.calculate(symbols=["BBB", "AAA"])["ranking"]
        self.assertEqual([row["symbol"] for row in ranking], ["AAA", "BBB"])
        self.assertEqual([row["percentage_change"] for row in ranking], [10.0, 10.0])

    def test_no_change_is_valid_zero(self):
        self.prices["AAA"][self.days[-1]] = 100
        self.assertEqual(self.calculate()["ranking"][0]["percentage_change"], 0.0)

    def test_five_stocks_and_precision_against_decimal_reference(self):
        symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
        for i, symbol in enumerate(symbols):
            self.prices[symbol] = dict(zip(self.days, ["3.000019", "4.2", str(7 + i)]))
            self.calendars[symbol] = self.days
        ranking = self.calculate(symbols=symbols)["ranking"]
        self.assertEqual([row["symbol"] for row in ranking], list(reversed(symbols)))
        for row in ranking:
            history = self.prices[row["symbol"]]
            reference = 100 * (Decimal(history[self.days[-1]]) / Decimal(history[self.days[0]]) - 1)
            self.assertLessEqual(abs(Decimal(str(row["percentage_change"])) - reference), Decimal("0.0001"))

    def test_fewer_than_two_common_dates(self):
        self.calendars["BBB"] = [self.days[-1]]
        self.assert_error("INSUFFICIENT_DATA")
        self.calendars["BBB"] = ["2025-01-20"]
        self.prices["BBB"] = {"2025-01-20": 100}
        self.assert_error("INSUFFICIENT_DATA")

    def test_truncated_and_internally_missing_histories_rejected(self):
        for missing in self.days:
            with self.subTest(missing=missing):
                prices = self.prices["BBB"]
                value = prices.pop(missing)
                payload = self.assert_error("INSUFFICIENT_DATA", "BBB")
                self.assertIn(missing, payload["error"]["message"])
                prices[missing] = value

    def test_invalid_prices_reject_entire_ranking_including_interior_days(self):
        for value in (None, "bad", "NaN", "Infinity", "-Infinity", 0, -1, True):
            for day in self.days:
                with self.subTest(value=value, day=day):
                    self.prices["BBB"][day] = value
                    self.assert_error("INVALID_DATA", "BBB")
                    self.prices["BBB"][day] = 200

    def test_missing_stock_or_calendar_has_affected_symbol(self):
        history = self.prices.pop("BBB")
        self.assert_error("INSUFFICIENT_DATA", "BBB")
        self.prices["BBB"] = history
        self.calendars.pop("BBB")
        self.assert_error("INSUFFICIENT_DATA", "BBB")

    def test_weekends_holidays_and_out_of_range_prices_ignored(self):
        self.prices["AAA"]["2025-01-16"] = "bad"
        self.prices["BBB"]["2025-01-23"] = "bad"
        result = self.calculate(start="2025-01-16", end="2025-01-23")
        self.assertEqual(result["effective_start_date"], "2025-01-17")
        self.assertEqual(result["effective_end_date"], "2025-01-22")
        self.assertEqual(result["ranking"][0]["percentage_change"], 10.0)

    def test_unsorted_inputs_not_mutated_and_symbols_normalized(self):
        for symbol in self.prices:
            self.prices[symbol] = dict(reversed(list(self.prices[symbol].items())))
            self.calendars[symbol].reverse()
        before = copy.deepcopy((self.prices, self.calendars))
        self.assertEqual(self.calculate(symbols=[" bbb ", "aaa"]), self.calculate())
        self.assertEqual((self.prices, self.calendars), before)

    def test_invalid_symbol_counts_and_duplicates(self):
        for symbols in (None, "AAA", [], ["AAA"], ["AAA"] * 6,
                        ["AAA", " aaa "], ["AAA", ""], ["AAA", 4]):
            with self.subTest(symbols=symbols):
                self.assert_error("INVALID_INPUT", symbols=symbols)

    def test_invalid_requested_dates(self):
        for start, end in (("2025-1-17", self.days[-1]), ("2025-02-30", self.days[-1]),
                           (self.days[-1], self.days[0]),
                           (self.days[0], (date.today() + timedelta(days=1)).isoformat())):
            with self.subTest(start=start, end=end):
                self.assert_error("INVALID_INPUT", start=start, end=end)

    def test_invalid_duplicate_and_empty_calendars(self):
        for calendar in ([self.days[0], self.days[0]], ["bad-date"], []):
            with self.subTest(calendar=calendar):
                self.calendars["BBB"] = calendar
                self.assert_error("INVALID_DATA" if calendar else "INSUFFICIENT_DATA", "BBB")

    def test_unrepresentable_change_returns_error_not_infinite_json(self):
        self.prices["BBB"][self.days[0]] = "1e-400"
        self.assert_error("INVALID_DATA", "BBB")


if __name__ == "__main__":
    unittest.main()
