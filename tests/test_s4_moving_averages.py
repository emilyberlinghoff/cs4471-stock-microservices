import json
import unittest
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean

from s4_moving_averages import MovingAverageError, calculate_moving_averages


def sessions(count):
    """Synthetic exchange calendar, with New Year's Day excluded."""
    result = []
    day = date(2025, 1, 1)
    while len(result) < count:
        if day.weekday() < 5 and day != date(2025, 1, 1):
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


class MovingAverageTests(unittest.TestCase):
    def setUp(self):
        self.dates = sessions(100)
        self.prices = {day: str(i + 1) for i, day in enumerate(self.dates)}

    def calculate(self, start=49, end=49, prices=None, calendar=None):
        return calculate_moving_averages(
            " test ", self.dates[start], self.dates[end],
            self.prices if prices is None else prices,
            trading_dates=self.dates if calendar is None else calendar,
        )

    def test_exact_windows_include_current_day_and_warmup(self):
        result = self.calculate()
        self.assertEqual(result["symbol"], "TEST")
        row = result["moving_averages"][0]
        self.assertEqual(row["sma_20"], 40.5)
        self.assertEqual(row["sma_50"], 25.5)
        self.assertIsNone(row["sma_20_reason"])
        self.assertIsNone(row["sma_50_reason"])
        self.assertEqual(result["price_basis"], "unadjusted_daily_close")
        json.dumps(result, allow_nan=False)

    def test_shorter_window_survives_insufficient_longer_history(self):
        rows = self.calculate(18, 20)["moving_averages"]
        self.assertIsNone(rows[0]["sma_20"])
        self.assertEqual(rows[0]["sma_20_reason"]["code"], "INSUFFICIENT_DATA")
        self.assertEqual(rows[1]["sma_20"], 10.5)
        self.assertIsNone(rows[1]["sma_50"])
        self.assertEqual(rows[1]["sma_50_reason"]["code"], "INSUFFICIENT_DATA")

    def test_all_unavailable_is_structured_error(self):
        for prices in ({}, self.prices):
            with self.subTest(prices_empty=not prices):
                with self.assertRaises(MovingAverageError) as caught:
                    self.calculate(0, 18, prices=prices)
                self.assertEqual(caught.exception.to_dict()["error"]["code"], "INSUFFICIENT_DATA")

    def test_missing_price_breaks_window_until_it_rolls_out(self):
        prices = dict(self.prices)
        del prices[self.dates[30]]
        rows = self.calculate(49, 80, prices)["moving_averages"]
        self.assertIsNone(rows[0]["sma_20"])
        self.assertEqual(rows[1]["sma_20"], 41.5)
        self.assertIsNone(rows[1]["sma_50"])
        self.assertEqual(rows[-1]["sma_50"], 56.5)

    def test_invalid_prices_are_not_skipped_or_replaced_by_zero(self):
        for value in (None, "bad", "NaN", "Infinity", "-Infinity", 0, -2, True):
            with self.subTest(value=value):
                prices = dict(self.prices)
                prices[self.dates[30]] = value
                rows = self.calculate(49, 50, prices)["moving_averages"]
                self.assertIsNone(rows[0]["sma_20"])
                self.assertIsNone(rows[1]["sma_50"])
                self.assertEqual(rows[1]["sma_20"], 41.5)

    def test_weekends_and_holidays_are_not_missing_observations(self):
        self.assertEqual(self.dates[0], "2025-01-02")
        self.assertEqual(self.dates[2], "2025-01-06")
        self.assertEqual(self.calculate(19, 19)["moving_averages"][0]["sma_20"], 10.5)

    def test_unsorted_inputs_are_chronological_and_unchanged(self):
        prices = dict(reversed(list(self.prices.items())))
        before = dict(prices)
        rows = self.calculate(49, 51, prices, reversed(self.dates))["moving_averages"]
        self.assertEqual([row["date"] for row in rows], self.dates[49:52])
        self.assertEqual(prices, before)

    def test_future_prices_do_not_affect_current_results(self):
        prices = dict(self.prices)
        prices[self.dates[50]] = "999999999"
        self.assertEqual(self.calculate(), self.calculate(prices=prices))

    def test_rounds_only_final_average_against_independent_reference(self):
        prices = {day: str(Decimal(i + 1) / Decimal(7)) for i, day in enumerate(self.dates)}
        rows = self.calculate(49, 60, prices)["moving_averages"]
        for index, row in enumerate(rows, 49):
            for size in (20, 50):
                reference = mean(Decimal(prices[d]) for d in self.dates[index-size+1:index+1])
                self.assertLessEqual(abs(Decimal(str(row[f"sma_{size}"])) - reference), Decimal("0.0001"))
        # Rounding source observations first would incorrectly return 1.0000.
        prices = dict.fromkeys(self.dates, "1.000049")
        prices[self.dates[49]] = "1.000089"
        self.assertEqual(self.calculate(prices=prices)["moving_averages"][0]["sma_20"], 1.0001)

    def test_duplicate_sessions_rejected(self):
        with self.assertRaises(MovingAverageError) as caught:
            self.calculate(calendar=self.dates + [self.dates[0]])
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_basic_core_argument_errors(self):
        for symbol, start, end in (("", self.dates[0], self.dates[1]),
                                   ("TEST", "2025-1-02", self.dates[49]),
                                   ("TEST", self.dates[49], self.dates[0])):
            with self.subTest(symbol=symbol, start=start, end=end):
                with self.assertRaises(MovingAverageError) as caught:
                    calculate_moving_averages(symbol, start, end, self.prices, trading_dates=self.dates)
                self.assertEqual(caught.exception.code, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
