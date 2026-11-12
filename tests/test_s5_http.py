import json
import unittest
from datetime import date, timedelta
from unittest.mock import Mock

from s5_app import create_app
from s5_service import fetch_stock_comparison
from s5_stock_comparison import StockComparisonError
from s5_validation import InputValidationError


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.histories = {
            "AAA": {"2025-01-17": "100", "2025-01-21": "105", "2025-01-22": "110"},
            "BBB": {"2025-01-17": "200", "2025-01-21": "190", "2025-01-22": "180"},
        }
        self.source = Mock(outputsize="full")
        self.source.fetch_daily_closes.side_effect = lambda symbol: self.histories[symbol]
        self.app = create_app(stock_client=self.source)
        self.app.testing = True
        self.client = self.app.test_client()
        self.inputs = {"symbols": [" aaa ", "bbb"], "start_date": "2025-01-17", "end_date": "2025-01-22"}

    def assert_error(self, response, status, code="INVALID_INPUT", field=None):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.mimetype, "application/json")
        payload = response.get_json()
        self.assertEqual(payload["error"]["code"], code)
        self.assertTrue(payload["error"]["message"])
        self.assertNotIn("ranking", payload)
        if field:
            self.assertEqual(payload["error"]["field"], field)
        return payload

    def test_get_and_post_normalize_and_compute_same_ranking(self):
        get = self.client.get("/comparison", query_string=dict(self.inputs, symbols=" aaa ,bbb"))
        post = self.client.post("/comparison", json=self.inputs)
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.get_json(), post.get_json())
        self.assertEqual(post.get_json()["ranking"], [{"symbol": "AAA", "percentage_change": 10.0},
                                                       {"symbol": "BBB", "percentage_change": -10.0}])

    def test_symbol_count_type_syntax_and_duplicates_before_lookup(self):
        for symbols in (None, "AAA,BBB", [], ["AAA"], ["AAA"] * 6, ["AAA", " aaa "],
                        ["AAA", 5], ["AAA", True], ["AAA", {}], ["AAA", ""],
                        ["AAA", "B B"], ["AAA", "B,CCC"], ["AAA", "x" * 65]):
            with self.subTest(symbols=symbols):
                self.assert_error(self.client.post("/comparison", json=dict(self.inputs, symbols=symbols)), 400, field="symbols")
        missing = dict(self.inputs)
        del missing["symbols"]
        self.assert_error(self.client.post("/comparison", json=missing), 400, field="symbols")
        self.source.fetch_daily_closes.assert_not_called()

    def test_get_requires_two_to_five_distinct_comma_separated_symbols(self):
        for symbols in ("AAA", "AAA,", "AAA,AAA", "AAA,,BBB", "AAA,BBB,CCC,DDD,EEE,FFF"):
            with self.subTest(symbols=symbols):
                self.assert_error(self.client.get("/comparison", query_string=dict(self.inputs, symbols=symbols)), 400, field="symbols")
        self.source.fetch_daily_closes.assert_not_called()

    def test_five_symbols_and_international_syntax(self):
        symbols = ["AAA", "BRK.B", "SHOP.TRT", "600104.SHH", "BRK-B"]
        for symbol in symbols[1:]:
            self.histories[symbol] = dict(self.histories["AAA"])
        response = self.client.post("/comparison", json=dict(self.inputs, symbols=symbols))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["ranking"]), 5)
        self.assertEqual(self.source.fetch_daily_closes.call_count, 5)

    def test_missing_wrong_type_invalid_and_future_dates(self):
        for field in ("start_date", "end_date"):
            for value in (None, "", 10, True, [], {}, "2025-1-17", "2025-02-30", "20250117",
                          "2025-01-17T00:00:00", (date.today() + timedelta(days=1)).isoformat()):
                with self.subTest(field=field, value=value):
                    self.assert_error(self.client.post("/comparison", json=dict(self.inputs, **{field: value})), 400, field=field)
            missing = dict(self.inputs)
            del missing[field]
            self.assert_error(self.client.post("/comparison", json=missing), 400, field=field)
        self.assert_error(self.client.post("/comparison", json=dict(self.inputs, end_date="2025-01-16")), 400, field="end_date")
        self.source.fetch_daily_closes.assert_not_called()

    def test_invalid_default_calendar(self):
        for exchange in (None, [], True, "", " " * 2, "unknown-calendar"):
            with self.subTest(exchange=exchange):
                self.assert_error(self.client.post("/comparison", json=dict(self.inputs, exchange=exchange)), 400, field="exchange")
        self.source.fetch_daily_closes.assert_not_called()

    def test_invalid_exchange_overrides(self):
        for exchanges in (None, [], "TSX", {"OTHER": "TSX"}, {"BBB": None}, {"BBB": []},
                          {"BBB": ""}, {"BBB": "unknown"}, {"BBB": "TSX", " bbb ": "NYSE"}):
            with self.subTest(exchanges=exchanges):
                self.assert_error(self.client.post("/comparison", json=dict(self.inputs, exchanges=exchanges)), 400, field="exchanges")
        self.source.fetch_daily_closes.assert_not_called()

    def test_mixed_exchange_override_normalized(self):
        self.histories["BBB"]["2025-01-20"] = "195"
        response = self.client.post("/comparison", json=dict(self.inputs, exchanges={" bbb ": " TSX "}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["exchange_calendars"]["BBB"], "TSX")
        self.assertEqual(response.get_json()["effective_start_date"], "2025-01-17")

    def test_duplicate_query_unknown_fields_mixed_inputs_and_get_body(self):
        query = [("symbols", "AAA,BBB"), ("symbols", "AAA,CCC"), ("start_date", "2025-01-17"), ("end_date", "2025-01-22")]
        self.assert_error(self.client.get("/comparison", query_string=query), 400, field="symbols")
        self.assert_error(self.client.post("/comparison", json=dict(self.inputs, typo="bad")), 400, field="typo")
        self.assert_error(self.client.get("/comparison", query_string={"symbols": "AAA,BBB", "exchanges": "{}"}), 400, field="exchanges")
        self.assert_error(self.client.post("/comparison?exchange=NYSE", json=self.inputs), 400, field="query")
        self.assert_error(self.client.get("/comparison", json=self.inputs), 400, field="body")
        self.source.fetch_daily_closes.assert_not_called()

    def test_json_errors_body_shape_and_size(self):
        for data in ("", "{bad"):
            self.assert_error(self.client.post("/comparison", data=data, content_type="application/json"), 400, "BAD_REQUEST")
        self.assert_error(self.client.post("/comparison", data="symbols=AAA,BBB"), 415, "UNSUPPORTED_MEDIA_TYPE")
        for data in (None, [], "text", True, 42):
            self.assert_error(self.client.post("/comparison", data=json.dumps(data), content_type="application/json"), 400, field="body")
        self.assert_error(self.client.post("/comparison", json={"symbols": "x" * 17000}), 413, "PAYLOAD_TOO_LARGE")
        self.source.fetch_daily_closes.assert_not_called()

    def test_source_errors_have_status_symbol_and_no_partial_ranking(self):
        for code, status in (("UNKNOWN_SYMBOL", 404), ("UNAVAILABLE_DATA", 404),
                             ("INSUFFICIENT_DATA", 422), ("RATE_LIMITED", 429),
                             ("INVALID_DATA", 502), ("UPSTREAM_ERROR", 502),
                             ("CONFIGURATION_ERROR", 503), ("UPSTREAM_TIMEOUT", 504)):
            with self.subTest(code=code):
                self.source.fetch_daily_closes.side_effect = StockComparisonError(code, "Data unavailable for BBB.", "BBB")
                payload = self.assert_error(self.client.post("/comparison", json=self.inputs), status, code)
                self.assertEqual(payload["error"]["symbol"], "BBB")

    def test_missing_price_and_invalid_price_abort_comparison(self):
        price = self.histories["BBB"].pop("2025-01-21")
        payload = self.assert_error(self.client.post("/comparison", json=self.inputs), 422, "INSUFFICIENT_DATA")
        self.assertEqual(payload["error"]["symbol"], "BBB")
        self.histories["BBB"]["2025-01-21"] = "NaN"
        self.assert_error(self.client.post("/comparison", json=self.inputs), 502, "INVALID_DATA")
        self.histories["BBB"]["2025-01-21"] = price
        self.assertEqual(self.client.post("/comparison", json=self.inputs).status_code, 200)

    def test_safe_unexpected_error_and_recovery(self):
        original = self.source.fetch_daily_closes.side_effect
        self.source.fetch_daily_closes.side_effect = RuntimeError("credential-secret in private URL")
        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            response = self.client.post("/comparison", json=self.inputs)
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertNotIn("credential-secret", response.get_data(as_text=True))
        self.assertNotIn("credential-secret", " ".join(logs.output))
        self.source.fetch_daily_closes.side_effect = original
        self.assertEqual(self.client.post("/comparison", json=self.inputs).status_code, 200)

    def test_framework_errors_health_and_options(self):
        self.assert_error(self.client.get("/missing"), 404, "NOT_FOUND")
        response = self.client.delete("/comparison")
        self.assert_error(response, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("POST", response.headers["Allow"])
        self.assertEqual(self.client.get("/health").get_json(), {"service_id": "S5", "status": "UP"})
        self.assertEqual(self.client.options("/comparison").status_code, 200)
        self.source.fetch_daily_closes.assert_not_called()

    def test_python_integration_shares_validation(self):
        with self.assertRaises(InputValidationError) as caught:
            fetch_stock_comparison(["AAA", "B B"], "2025-01-17", "2025-01-22", client=self.source)
        self.assertEqual(caught.exception.field, "symbols")
        self.source.fetch_daily_closes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
