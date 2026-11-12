import copy
import io
import json
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

import requests

from s5_alpha_vantage import AlphaVantageClient
from s5_service import fetch_stock_comparison, main
from s5_stock_comparison import StockComparisonError


class DataSourceTests(unittest.TestCase):
    def setUp(self):
        self.days = ["2025-01-17", "2025-01-21", "2025-01-22"]
        self.prices = {
            "AAA": dict(zip(self.days, ["100", "105", "110"])),
            "BBB": dict(zip(self.days, ["200", "190", "180"])),
        }
        self.responses = {}
        for symbol, prices in self.prices.items():
            response = Mock(status_code=200)
            response.json.return_value = {
                "Meta Data": {"2. Symbol": symbol},
                "Time Series (Daily)": {day: {"4. close": price} for day, price in reversed(list(prices.items()))},
            }
            self.responses[symbol] = response
        self.http = Mock()
        self.http.get.side_effect = lambda url, **kwargs: self.responses[kwargs["params"]["symbol"]]
        self.client = AlphaVantageClient("unit-test-key", session=self.http)

    def fetch(self, symbols=("AAA", "BBB"), **kwargs):
        return fetch_stock_comparison(symbols, self.days[0], self.days[-1], client=self.client, **kwargs)

    def assert_error(self, code, symbol=None):
        with self.assertRaises(StockComparisonError) as caught:
            self.fetch()
        payload = caught.exception.to_dict()
        self.assertEqual(payload["error"]["code"], code)
        if symbol:
            self.assertEqual(payload["error"]["symbol"], symbol)
        self.assertNotIn("ranking", payload)
        self.assertNotIn("unit-test-key", json.dumps(payload))

    def test_end_to_end_daily_close_requests_and_ranking(self):
        result = self.fetch(symbols=[" bbb ", "aaa"])
        self.assertEqual(result["ranking"], [{"symbol": "AAA", "percentage_change": 10.0},
                                              {"symbol": "BBB", "percentage_change": -10.0}])
        self.assertEqual(result["effective_start_date"], self.days[0])
        self.assertEqual(result["effective_end_date"], self.days[-1])
        self.assertEqual(result["source"], "Alpha Vantage")
        self.assertEqual(result["price_basis"], "unadjusted_daily_close")
        self.assertEqual(result["exchange_calendars"], {"AAA": "NYSE", "BBB": "NYSE"})
        self.assertEqual(self.http.get.call_count, 2)
        for call in self.http.get.call_args_list:
            self.assertEqual(call.args[0], "https://www.alphavantage.co/query")
            self.assertEqual(call.kwargs["params"]["function"], "TIME_SERIES_DAILY")
            self.assertEqual(call.kwargs["params"]["apikey"], "unit-test-key")
            self.assertEqual(call.kwargs["params"]["outputsize"], "full")
            self.assertEqual(call.kwargs["timeout"], 10)
            self.assertFalse(call.kwargs["allow_redirects"])
        for response in self.responses.values():
            response.close.assert_called_once()
        json.dumps(result, allow_nan=False)

    def test_requests_are_concurrent(self):
        barrier = threading.Barrier(2)
        original = self.http.get.side_effect
        def get(url, **kwargs):
            barrier.wait(timeout=2)
            return original(url, **kwargs)
        self.http.get.side_effect = get
        self.assertEqual(len(self.fetch()["ranking"]), 2)

    def test_five_stocks_fetch_once_each(self):
        for symbol in ("CCC", "DDD", "EEE"):
            response = Mock(status_code=200)
            response.json.return_value = {"Time Series (Daily)": {day: {"4. close": "100"} for day in self.days}}
            self.responses[symbol] = response
        result = self.fetch(symbols=list(self.responses))
        self.assertEqual(len(result["ranking"]), 5)
        self.assertEqual(self.http.get.call_count, 5)

    def test_calendar_handles_weekends_and_holidays(self):
        result = fetch_stock_comparison(["AAA", "BBB"], "2025-01-18", "2025-01-22", client=self.client)
        self.assertEqual(result["effective_start_date"], "2025-01-21")
        self.assertEqual(result["effective_end_date"], "2025-01-22")

    def test_mixed_exchanges_use_actual_common_dates(self):
        # NYSE closes for Martin Luther King Day; TSX trades on Jan 20.
        self.responses["BBB"].json.return_value["Time Series (Daily)"]["2025-01-20"] = {"4. close": "195"}
        result = self.fetch(exchanges={"BBB": "TSX"})
        self.assertEqual(result["exchange_calendars"]["BBB"], "TSX")
        self.assertEqual(result["effective_start_date"], self.days[0])
        self.assertEqual(result["ranking"][0]["percentage_change"], 10.0)

    def test_truncated_or_missing_interior_history_identifies_symbol(self):
        series = self.responses["BBB"].json.return_value["Time Series (Daily)"]
        for missing in self.days:
            with self.subTest(day=missing):
                observation = series.pop(missing)
                self.assert_error("INSUFFICIENT_DATA", "BBB")
                series[missing] = observation

    def test_invalid_closes_abort_ranking(self):
        series = self.responses["BBB"].json.return_value["Time Series (Daily)"]
        for observation in ({"4. close": "NaN"}, {"4. close": 0}, {"4. close": -1}, {}, None):
            with self.subTest(observation=observation):
                series[self.days[1]] = observation
                self.assert_error("INVALID_DATA", "BBB")

    def test_compact_history_coverage(self):
        self.client.outputsize = "compact"
        self.assertEqual(len(self.fetch()["ranking"]), 2)
        del self.responses["BBB"].json.return_value["Time Series (Daily)"][self.days[0]]
        self.assert_error("INSUFFICIENT_DATA", "BBB")

    def test_one_unknown_stock_or_limit_aborts_whole_comparison(self):
        for payload, code in (({"Error Message": "invalid unit-test-key"}, "UNKNOWN_SYMBOL"),
                              ({"Note": "rate limit unit-test-key"}, "RATE_LIMITED"),
                              ({"Information": "25 requests per day"}, "RATE_LIMITED"),
                              ({"Information": "premium key required"}, "CONFIGURATION_ERROR")):
            with self.subTest(payload=payload):
                self.responses["BBB"].json.return_value = payload
                self.assert_error(code, "BBB")

    def test_http_error_statuses(self):
        for status, code in ((429, "RATE_LIMITED"), (500, "UPSTREAM_ERROR"),
                             (403, "UPSTREAM_ERROR"), (302, "UPSTREAM_ERROR")):
            with self.subTest(status=status):
                self.responses["BBB"].status_code = status
                self.assert_error(code, "BBB")

    def test_timeout_and_recovery(self):
        original = self.http.get.side_effect
        def get(url, **kwargs):
            if kwargs["params"]["symbol"] == "BBB":
                raise requests.exceptions.Timeout("url?apikey=unit-test-key")
            return original(url, **kwargs)
        self.http.get.side_effect = get
        self.assert_error("UPSTREAM_TIMEOUT", "BBB")
        self.http.get.side_effect = original
        self.assertEqual(len(self.fetch()["ranking"]), 2)

    def test_network_exception_redacts_credentials(self):
        self.http.get.side_effect = requests.exceptions.ConnectionError("url?apikey=unit-test-key")
        self.assert_error("UPSTREAM_ERROR")

    def test_shared_deadline_does_not_return_partial_ranking(self):
        release = threading.Event()
        original = self.http.get.side_effect
        def get(url, **kwargs):
            release.wait(timeout=2)
            return original(url, **kwargs)
        self.http.get.side_effect = get
        try:
            with patch("s5_service.LOOKUP_TIMEOUT_SECONDS", 0.01):
                self.assert_error("UPSTREAM_TIMEOUT")
        finally:
            release.set()

    def test_invalid_json_empty_series_or_wrong_symbol(self):
        response = self.responses["BBB"]
        response.json.side_effect = ValueError("unit-test-key")
        self.assert_error("UPSTREAM_ERROR", "BBB")
        response.json.side_effect = None
        for payload, code in (([], "UPSTREAM_ERROR"), ({}, "UNAVAILABLE_DATA"),
                              ({"Time Series (Daily)": {}}, "UNAVAILABLE_DATA"),
                              ({"Meta Data": {"2. Symbol": "OTHER"}}, "UPSTREAM_ERROR"),
                              ({"Time Series (Daily)": {"bad-date": {"4. close": "1"}}}, "UPSTREAM_ERROR")):
            with self.subTest(payload=payload):
                response.json.return_value = payload
                self.assert_error(code, "BBB")

    def test_source_precision_sorting_and_payload_immutability(self):
        payload = self.responses["AAA"].json.return_value
        payload["Time Series (Daily)"][self.days[0]]["4. close"] = "100.000019"
        before = copy.deepcopy(payload)
        prices = self.client.fetch_daily_closes("AAA")
        self.assertEqual(prices[self.days[0]], "100.000019")
        self.assertEqual(list(prices), self.days)
        self.assertEqual(payload, before)

    def test_missing_key_and_bad_outputsize_make_no_requests(self):
        for key, outputsize in (("", "full"), ("unit-test-key", "bad")):
            with self.subTest(outputsize=outputsize):
                self.client = AlphaVantageClient(key, outputsize=outputsize, session=self.http)
                self.assert_error("CONFIGURATION_ERROR")
        self.http.get.assert_not_called()

    def test_environment_configuration(self):
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "unit-test-key", "ALPHA_VANTAGE_OUTPUTSIZE": "compact"}):
            client = AlphaVantageClient(session=self.http)
        client.fetch_daily_closes("AAA")
        self.assertEqual(self.http.get.call_args.kwargs["params"]["outputsize"], "compact")

    def test_invalid_inputs_make_no_requests(self):
        for symbols, start, end, kwargs in (
            (["AAA"], self.days[0], self.days[-1], {}),
            (["AAA", " aaa "], self.days[0], self.days[-1], {}),
            (["AAA", "BBB"], "2025-1-17", self.days[-1], {}),
            (["AAA", "BBB"], self.days[-1], self.days[0], {}),
            (["AAA", "BBB"], self.days[0], "9999-01-01", {}),
            (["AAA", "BBB"], self.days[0], self.days[-1], {"exchange": "unknown"}),
            (["AAA", "BBB"], self.days[0], self.days[-1], {"exchanges": {"TYPO": "TSX"}}),
            (["AAA", "BBB"], "2025-01-18", "2025-01-20", {}),
            (["AAA", "BBB"], self.days[0], self.days[0], {}),
        ):
            with self.subTest(symbols=symbols, start=start, end=end, kwargs=kwargs):
                with self.assertRaises(StockComparisonError):
                    fetch_stock_comparison(symbols, start, end, client=self.client, **kwargs)
        self.http.get.assert_not_called()

    def test_cli_json_and_exit_status(self):
        with patch("s5_service.AlphaVantageClient", return_value=self.client):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["AAA,BBB", self.days[0], self.days[-1]]), 0)
            self.assertEqual(json.loads(output.getvalue())["service_id"], "S5")
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(main(["AAA,BBB", self.days[0], self.days[-1], "--symbol-exchange", "bad"]), 1)
            self.assertEqual(json.loads(errors.getvalue())["error"]["code"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
