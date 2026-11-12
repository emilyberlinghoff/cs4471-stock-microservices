import unittest
from datetime import date, timedelta
from unittest.mock import Mock

from alpha_vantage import StockDataError
from s4_app import create_app
from s4_service import fetch_moving_averages, trading_sessions
from s4_validation import InputValidationError


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = trading_sessions(date(2025, 1, 2), date(2025, 1, 3), "NYSE")

    def setUp(self):
        self.source = Mock(outputsize="full")
        self.source.fetch_daily_closes.return_value = {day: str(i + 1) for i, day in enumerate(self.sessions)}
        self.app = create_app(stock_client=self.source)
        self.app.testing = True
        self.client = self.app.test_client()
        self.inputs = {"symbol": " msft ", "start_date": "2025-01-02", "end_date": "2025-01-03"}

    def assert_error(self, response, status, code, field=None):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.mimetype, "application/json")
        data = response.get_json()
        self.assertEqual(data["error"]["code"], code)
        self.assertTrue(data["error"]["message"])
        self.assertNotIn("moving_averages", data)
        if field:
            self.assertEqual(data["error"]["field"], field)
        return data

    def test_get_and_post_return_real_core_results(self):
        get = self.client.get("/moving-averages", query_string=self.inputs)
        post = self.client.post("/moving-averages", json=self.inputs)
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.get_json(), post.get_json())
        data = get.get_json()
        self.assertEqual(data["symbol"], "MSFT")
        self.assertEqual(data["moving_averages"][0]["sma_20"], 40.5)
        self.assertEqual(data["moving_averages"][0]["sma_50"], 25.5)
        self.source.fetch_daily_closes.assert_called_with("MSFT")

    def test_missing_and_wrong_type_fields_never_fetch(self):
        for field in ("symbol", "start_date", "end_date"):
            for value in (None, "", [], {}, True, 123):
                with self.subTest(field=field, value=value):
                    data = dict(self.inputs, **{field: value})
                    self.assert_error(self.client.post("/moving-averages", json=data), 400, "INVALID_INPUT", field)
            data = dict(self.inputs)
            del data[field]
            self.assert_error(self.client.get("/moving-averages", query_string=data), 400, "INVALID_INPUT", field)
        self.source.fetch_daily_closes.assert_not_called()

    def test_invalid_symbol_syntax(self):
        for symbol in ("MSFT,AAPL", "M SFT", "a" * 65, "<script>", "ééé", "MSFT/../../"):
            with self.subTest(symbol=symbol):
                self.assert_error(self.client.post("/moving-averages", json=dict(self.inputs, symbol=symbol)), 400, "INVALID_INPUT", "symbol")
        self.source.fetch_daily_closes.assert_not_called()

    def test_international_and_class_symbols_reach_provider(self):
        for symbol in ("BRK.B", "SHOP.TRT", "600104.SHH", "BRK-B", "^GSPC"):
            with self.subTest(symbol=symbol):
                response = self.client.post("/moving-averages", json=dict(self.inputs, symbol=symbol))
                self.assertEqual(response.status_code, 200)
                self.source.fetch_daily_closes.assert_called_with(symbol)

    def test_invalid_dates_and_order(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        for field, value in (("start_date", "2025-1-02"), ("start_date", "2025-02-30"),
                             ("end_date", "2025-01-03T00:00:00"), ("end_date", "20250103"),
                             ("end_date", "2025-01-01"), ("start_date", tomorrow), ("end_date", tomorrow)):
            with self.subTest(field=field, value=value):
                self.assert_error(self.client.post("/moving-averages", json=dict(self.inputs, **{field: value})), 400, "INVALID_INPUT", field)
        self.source.fetch_daily_closes.assert_not_called()

    def test_exchange_type_blank_and_unknown(self):
        for exchange in (None, [], True, "", " " * 3, "unknown-exchange"):
            with self.subTest(exchange=exchange):
                payload = self.assert_error(self.client.post("/moving-averages", json=dict(self.inputs, exchange=exchange)), 400, "INVALID_INPUT", "exchange")
                self.assertEqual(payload["error"]["symbol"], "MSFT")
        self.source.fetch_daily_closes.assert_not_called()

    def test_duplicate_query_unknown_fields_and_mixed_inputs(self):
        query = list(self.inputs.items()) + [("symbol", "AAPL")]
        self.assert_error(self.client.get("/moving-averages", query_string=query), 400, "INVALID_INPUT", "symbol")
        self.assert_error(self.client.post("/moving-averages", json=dict(self.inputs, typo="value")), 400, "INVALID_INPUT", "typo")
        self.assert_error(self.client.post("/moving-averages?symbol=OTHER", json=self.inputs), 400, "INVALID_INPUT", "query")
        self.assert_error(self.client.get("/moving-averages", query_string=self.inputs, json=self.inputs), 400, "INVALID_INPUT", "body")
        self.source.fetch_daily_closes.assert_not_called()

    def test_json_format_content_type_and_body_shape(self):
        self.assert_error(self.client.post("/moving-averages", data="{bad", content_type="application/json"), 400, "BAD_REQUEST")
        self.assert_error(self.client.post("/moving-averages", data="", content_type="application/json"), 400, "BAD_REQUEST")
        self.assert_error(self.client.post("/moving-averages", data=self.inputs), 415, "UNSUPPORTED_MEDIA_TYPE")
        for body in ([], None, 4, "text", True):
            import json
            self.assert_error(self.client.post("/moving-averages", data=json.dumps(body), content_type="application/json"), 400, "INVALID_INPUT", "body")
        self.source.fetch_daily_closes.assert_not_called()

    def test_body_size_limit(self):
        self.assert_error(self.client.post("/moving-averages", json={"symbol": "a" * 17000}), 413, "PAYLOAD_TOO_LARGE")
        self.source.fetch_daily_closes.assert_not_called()

    def test_service_error_status_mapping_and_symbol(self):
        for code, status in (("UNKNOWN_SYMBOL", 404), ("UNAVAILABLE_DATA", 404),
                             ("INSUFFICIENT_DATA", 422), ("RATE_LIMITED", 429),
                             ("INVALID_DATA", 502), ("UPSTREAM_ERROR", 502),
                             ("CONFIGURATION_ERROR", 503), ("UPSTREAM_TIMEOUT", 504)):
            with self.subTest(code=code):
                self.source.fetch_daily_closes.side_effect = StockDataError(code, "Stock data unavailable for MSFT.", "MSFT")
                payload = self.assert_error(self.client.post("/moving-averages", json=self.inputs), status, code)
                self.assertEqual(payload["error"]["symbol"], "MSFT")

    def test_unexpected_error_is_safe_and_next_request_recovers(self):
        self.source.fetch_daily_closes.side_effect = RuntimeError("secret-key at private URL")
        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            response = self.client.get("/moving-averages", query_string=self.inputs)
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertNotIn("secret-key", response.get_data(as_text=True))
        self.assertNotIn("secret-key", " ".join(logs.output))
        self.source.fetch_daily_closes.side_effect = None
        self.assertEqual(self.client.get("/moving-averages", query_string=self.inputs).status_code, 200)

    def test_partial_windows_remain_success_and_all_missing_is_422(self):
        prices = self.source.fetch_daily_closes.return_value
        del prices[self.sessions[0]]
        response = self.client.get("/moving-averages", query_string=self.inputs)
        self.assertEqual(response.status_code, 200)
        row = response.get_json()["moving_averages"][0]
        self.assertEqual(row["sma_20"], 40.5)
        self.assertIsNone(row["sma_50"])
        self.source.fetch_daily_closes.return_value = {}
        self.assert_error(self.client.get("/moving-averages", query_string=self.inputs), 422, "INSUFFICIENT_DATA")

    def test_framework_errors_preserve_status_and_allow_header(self):
        self.assert_error(self.client.get("/missing"), 404, "NOT_FOUND")
        response = self.client.delete("/moving-averages")
        self.assert_error(response, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("GET", response.headers["Allow"])
        self.assertIn("POST", response.headers["Allow"])
        self.source.fetch_daily_closes.assert_not_called()

    def test_health_and_options_do_not_fetch(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["service_id"], "S4")
        self.assertEqual(self.client.options("/moving-averages").status_code, 200)
        self.source.fetch_daily_closes.assert_not_called()

    def test_python_integration_uses_same_validation(self):
        for symbol, start, end, exchange, field in (
            (True, "2025-01-02", "2025-01-03", "NYSE", "symbol"),
            ("MSFT", None, "2025-01-03", "NYSE", "start_date"),
            ("MSFT", "2025-01-02", "2025-01-03", {}, "exchange"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(InputValidationError) as caught:
                    fetch_moving_averages(symbol, start, end, exchange=exchange, client=self.source)
                self.assertEqual(caught.exception.field, field)
        self.source.fetch_daily_closes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
