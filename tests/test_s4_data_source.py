import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from unittest.mock import Mock, patch

import requests

from alpha_vantage import AlphaVantageClient, StockDataError
from s4_moving_averages import MovingAverageError
from s4_service import fetch_moving_averages, main, trading_sessions


class DataSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = trading_sessions(date(2025, 1, 2), date(2025, 2, 28), "NYSE")
        cls.start = "2025-01-02"
        cls.end = "2025-02-28"

    def setUp(self):
        self.payload = {
            "Meta Data": {"2. Symbol": "TEST"},
            "Time Series (Daily)": {
                day: {"4. close": str(index + 1), "5. volume": "1000"}
                for index, day in reversed(list(enumerate(self.days)))
            },
        }
        self.response = Mock(status_code=200)
        self.response.json.return_value = self.payload
        self.http = Mock()
        self.http.get.return_value = self.response
        self.client = AlphaVantageClient("unit-test-key", session=self.http)

    def fetch(self, **kwargs):
        return fetch_moving_averages(" test ", self.start, self.end, client=self.client, **kwargs)

    def assert_source_error(self, code):
        with self.assertRaises(StockDataError) as caught:
            self.fetch()
        payload = caught.exception.to_dict()
        self.assertEqual(payload["error"]["code"], code)
        self.assertEqual(payload["error"]["symbol"], "TEST")
        self.assertNotIn("unit-test-key", json.dumps(payload))
        self.assertNotIn("moving_averages", payload)

    def test_daily_close_request_and_end_to_end_calculations(self):
        result = self.fetch()
        self.http.get.assert_called_once_with(
            "https://www.alphavantage.co/query",
            params={"function": "TIME_SERIES_DAILY", "symbol": "TEST", "apikey": "unit-test-key",
                    "outputsize": "full", "datatype": "json"},
            timeout=10, allow_redirects=False,
        )
        first = result["moving_averages"][0]
        self.assertEqual(first["date"], self.start)
        self.assertEqual(first["sma_20"], 40.5)
        self.assertEqual(first["sma_50"], 25.5)
        self.assertEqual(result["source"], "Alpha Vantage")
        self.assertEqual(result["price_basis"], "unadjusted_daily_close")
        self.assertEqual(result["exchange_calendar"], "NYSE")
        self.response.close.assert_called_once()
        json.dumps(result, allow_nan=False)

    def test_calendar_has_49_warmup_sessions_and_excludes_holidays(self):
        self.assertEqual(len([day for day in self.days if day < self.start]), 49)
        self.assertNotIn("2024-12-25", self.days)
        self.assertNotIn("2025-01-01", self.days)
        self.assertNotIn("2025-01-09", self.days)  # Carter national day of mourning
        self.assertNotIn("2025-01-20", self.days)
        self.assertNotIn("2025-02-01", self.days)

    def test_prices_sorted_without_rounding_or_mutating_payload(self):
        self.payload["Time Series (Daily)"][self.start]["4. close"] = "50.000049"
        before = copy.deepcopy(self.payload)
        closes = self.client.fetch_daily_closes("TEST")
        self.assertEqual(list(closes), sorted(closes))
        self.assertEqual(closes[self.start], "50.000049")
        self.assertEqual(self.payload, before)

    def test_missing_price_is_not_hidden_by_inferred_calendar(self):
        del self.payload["Time Series (Daily)"][self.start]
        rows = self.fetch()["moving_averages"]
        self.assertEqual(rows[0]["date"], self.start)
        self.assertIsNone(rows[0]["sma_20"])
        self.assertIsNone(rows[0]["sma_50"])
        self.assertEqual(rows[0]["sma_20_reason"]["code"], "INSUFFICIENT_DATA")
        self.assertIsNotNone(rows[20]["sma_20"])

    def test_invalid_close_or_missing_close_breaks_only_affected_windows(self):
        for observation in ({"4. close": "NaN"}, {"4. close": 0}, {}, None):
            with self.subTest(observation=observation):
                self.payload["Time Series (Daily)"][self.days[0]] = observation
                first = self.fetch()["moving_averages"][0]
                self.assertEqual(first["sma_20"], 40.5)
                self.assertIsNone(first["sma_50"])

    def test_compact_coverage_rejected_including_missing_warmup(self):
        self.client.outputsize = "compact"
        del self.payload["Time Series (Daily)"][self.days[0]]
        self.assert_source_error("INSUFFICIENT_DATA")

    def test_compact_covered_range_succeeds(self):
        self.client.outputsize = "compact"
        self.assertEqual(self.fetch()["moving_averages"][0]["sma_50"], 25.5)

    def test_full_history_can_return_partial_windows_for_new_listing(self):
        series = self.payload["Time Series (Daily)"]
        self.payload["Time Series (Daily)"] = {day: value for day, value in series.items() if day >= self.start}
        rows = self.fetch()["moving_averages"]
        self.assertIsNone(rows[0]["sma_20"])
        self.assertIsNotNone(rows[19]["sma_20"])
        self.assertIsNone(rows[19]["sma_50"])

    def test_http_failures_do_not_fabricate_metrics(self):
        for status, code in ((429, "RATE_LIMITED"), (500, "UPSTREAM_ERROR"),
                             (403, "UPSTREAM_ERROR"), (302, "UPSTREAM_ERROR")):
            with self.subTest(status=status):
                self.response.status_code = status
                self.assert_source_error(code)

    def test_provider_control_messages_and_no_credential_echo(self):
        for payload, code in (
            ({"Note": "limit unit-test-key"}, "RATE_LIMITED"),
            ({"Information": "25 requests per day unit-test-key"}, "RATE_LIMITED"),
            ({"Information": "premium endpoint unit-test-key"}, "CONFIGURATION_ERROR"),
            ({"Information": "demo key unit-test-key"}, "CONFIGURATION_ERROR"),
            ({"Information": "service unavailable unit-test-key"}, "UPSTREAM_ERROR"),
            ({"Error Message": "Invalid API call unit-test-key"}, "UNKNOWN_SYMBOL"),
        ):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                self.assert_source_error(code)

    def test_timeout_and_network_failure_are_structured_and_single_attempt(self):
        for exception, code in ((requests.exceptions.Timeout("url?apikey=unit-test-key"), "UPSTREAM_TIMEOUT"),
                                (requests.exceptions.ConnectionError("unit-test-key"), "UPSTREAM_ERROR")):
            with self.subTest(exception=exception):
                self.http.get.reset_mock()
                self.http.get.side_effect = exception
                self.assert_source_error(code)
                self.http.get.assert_called_once()

    def test_recovery_on_next_request_after_timeout(self):
        self.http.get.side_effect = requests.exceptions.Timeout()
        self.assert_source_error("UPSTREAM_TIMEOUT")
        self.http.get.side_effect = None
        self.assertEqual(self.fetch()["moving_averages"][0]["sma_50"], 25.5)

    def test_invalid_json_and_payload_shapes(self):
        self.response.json.side_effect = ValueError("unit-test-key")
        self.assert_source_error("UPSTREAM_ERROR")
        self.response.json.side_effect = None
        for payload, code in (([], "UPSTREAM_ERROR"), ({}, "UNAVAILABLE_DATA"),
                              ({"Time Series (Daily)": {}}, "UNAVAILABLE_DATA")):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                self.assert_source_error(code)

    def test_bad_upstream_date_and_wrong_symbol(self):
        self.payload["Time Series (Daily)"]["not-a-date"] = {"4. close": "1"}
        self.assert_source_error("UPSTREAM_ERROR")
        del self.payload["Time Series (Daily)"]["not-a-date"]
        self.payload["Meta Data"]["2. Symbol"] = "OTHER"
        self.assert_source_error("UPSTREAM_ERROR")

    def test_no_usable_window_returns_symbol_specific_error(self):
        self.payload["Time Series (Daily)"] = {self.start: {"4. close": "50"}}
        self.assert_source_error("INSUFFICIENT_DATA")

    def test_configuration_errors_make_no_network_request(self):
        for key, outputsize in (("", "full"), ("   ", "full"), ("unit-test-key", "bad")):
            with self.subTest(key_present=bool(key.strip()), outputsize=outputsize):
                self.client = AlphaVantageClient(key, outputsize=outputsize, session=self.http)
                self.assert_source_error("CONFIGURATION_ERROR")
        self.http.get.assert_not_called()

    def test_environment_configuration(self):
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "unit-test-key", "ALPHA_VANTAGE_OUTPUTSIZE": "compact"}):
            client = AlphaVantageClient(session=self.http)
        client.fetch_daily_closes("TEST")
        self.assertEqual(self.http.get.call_args.kwargs["params"]["outputsize"], "compact")

    def test_bad_inputs_and_closed_interval_make_no_network_request(self):
        for symbol, start, end, exchange in (
            ("", self.start, self.end, "NYSE"),
            ("TEST", "2025-1-02", self.end, "NYSE"),
            ("TEST", self.end, self.start, "NYSE"),
            ("TEST", self.start, "9999-01-01", "NYSE"),
            ("TEST", self.start, self.end, "unknown-exchange"),
            ("TEST", "2025-01-18", "2025-01-20", "NYSE"),
        ):
            with self.subTest(symbol=symbol, start=start, end=end, exchange=exchange):
                with self.assertRaises(MovingAverageError):
                    fetch_moving_averages(symbol, start, end, exchange=exchange, client=self.client)
        self.http.get.assert_not_called()

    def test_cli_success_and_failure_exit_codes(self):
        with patch("s4_service.AlphaVantageClient", return_value=self.client):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["TEST", self.start, self.end]), 0)
            self.assertEqual(json.loads(output.getvalue())["service_id"], "S4")
            self.http.get.side_effect = requests.exceptions.Timeout()
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(["TEST", self.start, self.end]), 1)
            self.assertEqual(json.loads(error.getvalue())["error"]["code"], "UPSTREAM_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
