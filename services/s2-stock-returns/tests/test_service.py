"""Tests use deterministic fixtures; no live Alpha Vantage API key or web traffic."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import time

import pytest
import requests

from stock_returns import (
    AlphaVantageClient, ServiceError, StockReturnsService,
    calculate_returns_from_prices, validate_request,
)

NOW = datetime(2026, 11, 10, 23, 30, tzinfo=timezone.utc)


def make_payload(prices):
    return {"Meta Data": {"2. Symbol": "IBM"}, "Time Series (Daily)": {
        day: {"4. close": str(price)} for day, price in prices.items()
    }}


class FakeAV:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_daily_data(self, symbol):
        self.calls.append(symbol)
        return self.payload


def service_for(prices, now=NOW):
    return StockReturnsService(client=FakeAV(make_payload(prices)), now=lambda: now)


def error_code(func):
    with pytest.raises(ServiceError) as exc:
        func()
    return exc.value.code


def test_returns_are_chronological_dated_later_day_and_percent():
    service = service_for({"2026-01-07": "121.00", "2026-01-05": "100.00",
                           "2026-01-06": "110.00"})
    result = service.run("ibm", "2026-01-05", "2026-01-07")
    assert result == {
        "service_id": "S2", "symbol": "IBM",
        "requested_start_date": "2026-01-05", "requested_end_date": "2026-01-07",
        "effective_start_date": "2026-01-05", "effective_end_date": "2026-01-07",
        "price_basis": "raw_close", "number_of_returns": 2,
        "returns": [{"date": "2026-01-06", "return_percent": 10.0},
                    {"date": "2026-01-07", "return_percent": 10.0}],
    }
    assert service.client.calls == ["IBM"]


def test_round_only_at_end_in_percentage_points():
    service = service_for({"2026-01-05": "100", "2026-01-06": "100.123456"})
    result = service.run("IBM", "2026-01-05", "2026-01-06")
    assert result["returns"] == [{"date": "2026-01-06", "return_percent": 0.1235}]


def test_negative_returns_and_valid_exact_zero():
    service = service_for({"2026-01-05": "100", "2026-01-06": "90", "2026-01-07": "90"})
    result = service.run("IBM", "2026-01-05", "2026-01-07")
    assert [x["return_percent"] for x in result["returns"]] == [-10.0, 0.0]


def test_weekend_not_missing():
    service = service_for({"2026-01-09": "100", "2026-01-12": "105"})
    result = service.run("IBM", "2026-01-09", "2026-01-12")
    assert result["returns"] == [{"date": "2026-01-12", "return_percent": 5.0}]


def test_exchange_holiday_not_missing():
    # NYSE Thanksgiving: Thu Nov 26 is closed, Fri Nov 27 is open (early close).
    service = service_for({"2026-11-25": "200", "2026-11-27": "210"},
                          now=datetime(2026, 11, 30, 23, tzinfo=timezone.utc))
    result = service.run("IBM", "2026-11-25", "2026-11-27")
    assert result["returns"] == [{"date": "2026-11-27", "return_percent": 5.0}]


def test_reject_missing_midweek_even_with_two_prices():
    service = service_for({"2026-01-05": "100", "2026-01-06": "105", "2026-01-08": "110"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-08")) == "INCOMPLETE_DATA"


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity", "abc", None])
def test_invalid_prices_rejected(bad):
    service = service_for({"2026-01-05": "100", "2026-01-06": bad})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-06")) == "INVALID_PRICE"


def test_two_nonadjacent_prices_have_no_usable_pair():
    service = service_for({"2026-01-05": "100", "2026-01-07": "110"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-07")) == "INSUFFICIENT_DATA"


def test_missing_fewer_than_two_prices():
    service = service_for({"2026-01-05": "100"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-06")) == "INSUFFICIENT_DATA"


def test_one_trading_session_is_insufficient_without_api_call():
    service = service_for({"2026-01-05": "100"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-05")) == "INSUFFICIENT_DATA"
    assert not service.client.calls


@pytest.mark.parametrize("symbol,start,end,expected", [
    (None, "2026-01-05", "2026-01-06", "MISSING_INPUT"),
    ("IBM", None, "2026-01-06", "MISSING_INPUT"),
    ("IBM", "2026-01-05", None, "MISSING_INPUT"),
    ("IBM", "2026/01/05", "2026-01-06", "INVALID_DATE"),
    ("IBM", "2026-02-30", "2026-03-06", "INVALID_DATE"),
    ("IBM", "2026-01-07", "2026-01-06", "INVALID_DATE_RANGE"),
    ("IBM", "2026-11-11", "2026-11-12", "FUTURE_DATE"),
    ("INVALID SYMBOL!", "2026-01-05", "2026-01-06", "INVALID_SYMBOL"),
])
def test_validation(symbol, start, end, expected):
    assert error_code(lambda: validate_request(symbol, start, end, date(2026, 11, 10))) == expected


def test_today_before_final_price_availability_is_excluded_from_effective_dates():
    # 2026-11-10 18:00 UTC is 1PM NY; Tuesday session is still open.
    now = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    prices = {"2026-11-06": "100", "2026-11-09": "110"}
    result = service_for(prices, now=now).run("IBM", "2026-11-06", "2026-11-10")
    assert result["requested_end_date"] == "2026-11-10"
    assert result["effective_end_date"] == "2026-11-09"
    assert result["number_of_returns"] == 1


def test_unrecognized_symbol_response():
    service = StockReturnsService(client=FakeAV({"Error Message": "Invalid API call. Please retry."}),
                                  now=lambda: NOW)
    assert error_code(lambda: service.run("XXXX", "2026-01-05", "2026-01-06")) == "UNKNOWN_SYMBOL"


def test_rate_limit_and_premium_response():
    for payload, expected in [
        ({"Note": "Our standard API rate limit is 25 requests per day."}, "UPSTREAM_RATE_LIMIT"),
        ({"Information": "This is a premium endpoint."}, "HISTORY_UNAVAILABLE"),
        ({}, "DATA_UNAVAILABLE"),
    ]:
        service = StockReturnsService(client=FakeAV(payload), now=lambda: NOW)
        assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-06")) == expected


def test_compact_incomplete_older_history_rejected():
    service = service_for({"2026-01-05": "100", "2026-01-06": "101"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-09")) == "INCOMPLETE_DATA"


class FakeResponse:
    def __init__(self, payload, code=200):
        self.payload = payload
        self.status_code = code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        next_step = next(self.steps)
        if isinstance(next_step, Exception):
            raise next_step
        return next_step


def test_alpha_vantage_params_and_retry_then_success():
    session = FakeSession([requests.Timeout(), FakeResponse(make_payload({"2026-01-05": "100"}))])
    client = AlphaVantageClient(api_key="TEST_KEY", session=session, outputsize="full")
    assert "Time Series (Daily)" in client.get_daily_data("IBM")
    assert len(session.calls) == 2
    assert session.calls[0][1]["params"] == {
        "function": "TIME_SERIES_DAILY", "symbol": "IBM",
        "outputsize": "full", "apikey": "TEST_KEY",
    }
    assert session.calls[0][0].startswith("https://")


def test_upstream_timeout_after_two_attempts_is_structured():
    client = AlphaVantageClient(api_key="TEST_KEY", session=FakeSession([requests.Timeout(), requests.Timeout()]))
    assert error_code(lambda: client.get_daily_data("IBM")) == "UPSTREAM_TIMEOUT"


def test_http_429_is_not_retried():
    session = FakeSession([FakeResponse({}, 429)])
    client = AlphaVantageClient(api_key="TEST_KEY", session=session)
    assert error_code(lambda: client.get_daily_data("IBM")) == "UPSTREAM_RATE_LIMIT"
    assert len(session.calls) == 1


def test_missing_api_key():
    client = AlphaVantageClient(api_key="", session=FakeSession([]))
    assert error_code(lambda: client.get_daily_data("IBM")) == "CONFIGURATION_ERROR"


def test_in_memory_300_prices_and_json_serialization_under_1_second():
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    days = [session.date() for session in cal.sessions_in_range("2025-05-01", "2026-09-30")][:300]
    prices = {d: Decimal(100) + Decimal(i) / Decimal(10) for i, d in enumerate(days)}
    durations = []
    for _ in range(100):
        t0 = time.perf_counter()
        result = calculate_returns_from_prices(prices, days, "IBM", days[0], days[-1])
        json.dumps(result)
        durations.append(time.perf_counter() - t0)
    assert len(result["returns"]) == 299
    assert sum(d < 1.0 for d in durations) >= 95


def test_service_recovers_after_transient_upstream_failure():
    class RecoveringAV:
        def __init__(self):
            self.calls = 0

        def get_daily_data(self, symbol):
            self.calls += 1
            if self.calls == 1:
                raise ServiceError("UPSTREAM_TIMEOUT", f"Alpha Vantage timed out for {symbol}.", 504)
            return make_payload({"2026-01-05": "100", "2026-01-06": "101"})

    service = StockReturnsService(client=RecoveringAV(), now=lambda: NOW)
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-06")) == "UPSTREAM_TIMEOUT"
    assert service.run("IBM", "2026-01-05", "2026-01-06")["number_of_returns"] == 1


def test_extreme_prices_return_structured_error_not_500():
    service = service_for({"2026-01-05": "1e-999999", "2026-01-06": "1e999999"})
    assert error_code(lambda: service.run("IBM", "2026-01-05", "2026-01-06")) == "INVALID_PRICE"
