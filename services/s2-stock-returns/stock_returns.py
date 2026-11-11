"""Stock Returns (S2): get closing prices and calculate daily returns."""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP

import exchange_calendars
import requests


class ServiceError(Exception):
    """An error that the Flask app can send back as JSON."""

    def __init__(self, code, message, status):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_response(self):
        return {"error": {"code": self.code, "message": self.message}}


def validate_request(symbol, start_date, end_date, today):
    """Check the three request inputs and return cleaned-up values."""
    inputs = {"symbol": symbol, "start_date": start_date, "end_date": end_date}

    for name, value in inputs.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ServiceError("MISSING_INPUT", f"Missing required input: {name}.", 400)

    if not isinstance(symbol, str):
        raise ServiceError("INVALID_SYMBOL", "Invalid stock symbol.", 400)

    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", symbol):
        raise ServiceError("INVALID_SYMBOL", "Invalid stock symbol.", 400)

    dates = []
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ServiceError("INVALID_DATE", f"{name} must use YYYY-MM-DD.", 400)
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            raise ServiceError("INVALID_DATE", f"{name} is not a valid date.", 400)

    start, end = dates
    if start > end:
        raise ServiceError("INVALID_DATE_RANGE", "start_date cannot be after end_date.", 400)
    if start > today or end > today:
        raise ServiceError("FUTURE_DATE", "Dates cannot be in the future.", 400)

    return symbol, start, end


def check_alpha_vantage_error(data, symbol):
    """Alpha Vantage sometimes reports errors inside an HTTP 200 response."""
    for field in ("Note", "Information", "Error Message"):
        if field not in data:
            continue

        message = str(data[field]).lower()
        if any(word in message for word in
               ("limit", "frequency", "requests per", "calls per", "rate")):
            raise ServiceError("UPSTREAM_RATE_LIMIT", f"Alpha Vantage request limit reached for {symbol}.", 503)
        if any(word in message for word in ("premium", "subscription", "outputsize=full")):
            raise ServiceError("HISTORY_UNAVAILABLE", f"Full price history is unavailable for {symbol}.", 503)
        if field == "Error Message" and ("symbol" in message or "invalid api call" in message):
            raise ServiceError("UNKNOWN_SYMBOL", f"Unknown stock symbol: {symbol}.", 404)
        raise ServiceError("UPSTREAM_FAILURE", f"Alpha Vantage rejected the request for {symbol}.", 502)


class AlphaVantageClient:
    """Makes requests to Alpha Vantage. A fake session can be used in tests."""

    def __init__(self, api_key=None, outputsize=None, session=None, clock=None):
        self.api_key = api_key if api_key is not None else os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.outputsize = (outputsize or os.getenv("ALPHA_VANTAGE_OUTPUTSIZE", "compact")).lower()
        if self.outputsize not in ("compact", "full"):
            raise ValueError("ALPHA_VANTAGE_OUTPUTSIZE must be 'compact' or 'full'")
        self.session = session if session is not None else requests.Session()
        self.clock = clock if clock is not None else time.monotonic

    def get_daily_data(self, symbol):
        if not self.api_key or self.api_key == "your_key_here":
            raise ServiceError("CONFIGURATION_ERROR", "Alpha Vantage API key is not configured.", 503)

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": self.outputsize,
            "apikey": self.api_key,
        }
        deadline = self.clock() + 13

        # Try at most twice if Alpha Vantage times out or has a server problem.
        for attempt in range(2):
            remaining = deadline - self.clock()
            if remaining <= 0.4:
                raise ServiceError("UPSTREAM_TIMEOUT", f"Alpha Vantage timed out for {symbol}.", 504)

            try:
                response = self.session.get(
                    "https://www.alphavantage.co/query",
                    params=params,
                    timeout=(min(2, remaining), min(5, remaining)),
                    allow_redirects=False,
                )
            except requests.Timeout:
                if attempt == 0 and self.clock() < deadline - 0.5:
                    continue
                raise ServiceError("UPSTREAM_TIMEOUT", f"Alpha Vantage timed out for {symbol}.", 504)
            except requests.RequestException:
                if attempt == 0 and self.clock() < deadline - 0.5:
                    continue
                raise ServiceError("UPSTREAM_FAILURE", f"Could not connect to Alpha Vantage for {symbol}.", 502)

            if response.status_code == 429:
                raise ServiceError("UPSTREAM_RATE_LIMIT", f"Alpha Vantage request limit reached for {symbol}.", 503)
            if 500 <= response.status_code <= 599 and attempt == 0 and self.clock() < deadline - 0.5:
                continue
            if response.status_code != 200:
                raise ServiceError("UPSTREAM_FAILURE", f"Alpha Vantage returned HTTP {response.status_code} for {symbol}.", 502)

            try:
                data = response.json()
            except ValueError:
                raise ServiceError("UPSTREAM_FAILURE", f"Alpha Vantage returned invalid JSON for {symbol}.", 502)
            if not isinstance(data, dict):
                raise ServiceError("UPSTREAM_FAILURE", f"Invalid Alpha Vantage response for {symbol}.", 502)

            check_alpha_vantage_error(data, symbol)
            return data

        raise ServiceError("UPSTREAM_FAILURE", f"Alpha Vantage failed for {symbol}.", 502)


def read_closing_prices(data, symbol, trading_dates):
    """Read just the closing prices for the expected trading dates."""
    series = data.get("Time Series (Daily)")
    if series is None:
        raise ServiceError("DATA_UNAVAILABLE", f"No daily prices available for {symbol}.", 503)
    if not isinstance(series, dict):
        raise ServiceError("UPSTREAM_FAILURE", f"Invalid daily price data for {symbol}.", 502)

    prices = {}
    for day in trading_dates:
        day_text = day.isoformat()
        if day_text not in series:
            continue  # Missing dates are reported when calculating returns.

        row = series[day_text]
        if not isinstance(row, dict) or "4. close" not in row:
            raise ServiceError("INVALID_PRICE", f"Missing closing price for {symbol} on {day_text}.", 422)

        try:
            price = Decimal(str(row["4. close"]))
        except (InvalidOperation, TypeError, ValueError):
            raise ServiceError("INVALID_PRICE", f"Invalid closing price for {symbol} on {day_text}.", 422)

        if not price.is_finite() or price <= 0:
            raise ServiceError("INVALID_PRICE", f"Closing price must be positive for {symbol} on {day_text}.", 422)
        prices[day] = price

    return prices


def calculate_returns_from_prices(prices, trading_dates, symbol, start_date, end_date):
    """Calculate percentage returns between consecutive trading days."""
    pairs = list(zip(trading_dates, trading_dates[1:]))
    if not any(day1 in prices and day2 in prices for day1, day2 in pairs):
        raise ServiceError("INSUFFICIENT_DATA", f"Not enough consecutive prices for {symbol}.", 422)

    missing = [day.isoformat() for day in trading_dates if day not in prices]
    if missing:
        raise ServiceError("INCOMPLETE_DATA", f"Missing trading-day prices for {symbol}: {', '.join(missing[:5])}.", 422)

    returns = []
    for previous_day, current_day in pairs:
        try:
            # Convert to a percentage, then round to 4 decimal places.
            percentage = (prices[current_day] / prices[previous_day] - 1) * 100
            percentage = percentage.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except DecimalException:
            raise ServiceError("INVALID_PRICE", f"Could not calculate a valid return for {symbol}.", 422)

        returns.append({
            "date": current_day.isoformat(),
            "return_percent": float(percentage),
        })

    return {
        "service_id": "S2",
        "symbol": symbol,
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "effective_start_date": trading_dates[0].isoformat(),
        "effective_end_date": trading_dates[-1].isoformat(),
        "price_basis": "raw_close",
        "number_of_returns": len(returns),
        "returns": returns,
    }


class StockReturnsService:
    """Connects input checking, the trading calendar, API data, and calculations."""

    def __init__(self, client=None, calendar_name=None, now=None, availability_lag_minutes=None):
        self.client = client if client is not None else AlphaVantageClient()
        self.now = now if now is not None else lambda: datetime.now(timezone.utc)
        calendar_name = calendar_name or os.getenv("EXCHANGE_CALENDAR", "XNYS")
        if availability_lag_minutes is None:
            availability_lag_minutes = int(os.getenv("DATA_AVAILABILITY_LAG_MINUTES", "240"))
        if availability_lag_minutes < 0:
            raise ValueError("DATA_AVAILABILITY_LAG_MINUTES cannot be negative")
        self.availability_lag_minutes = availability_lag_minutes

        # Load the calendar once so requests do not need to rebuild it.
        year = self.now().year
        self.calendar = exchange_calendars.get_calendar(
            calendar_name, start="1970-01-01", end=f"{year + 3}-12-31"
        )

    def run(self, symbol, start_date, end_date):
        now = self.now()
        if now.tzinfo is None:
            raise RuntimeError("Current time must include a time zone")

        today = now.astimezone(self.calendar.tz).date()
        symbol, start, end = validate_request(symbol, start_date, end_date, today)

        if start < self.calendar.first_session.date() or end > self.calendar.last_session.date():
            raise ServiceError("CALENDAR_UNAVAILABLE", "Dates are outside the trading calendar.", 422)

        try:
            sessions = self.calendar.sessions_in_range(start.isoformat(), end.isoformat())
        except (ValueError, OverflowError):
            raise ServiceError("CALENDAR_UNAVAILABLE", "Dates are outside the trading calendar.", 422)

        # The latest market session is only usable after its close plus a delay.
        cutoff = now.astimezone(timezone.utc) - timedelta(minutes=self.availability_lag_minutes)
        trading_dates = [
            day.date() for day in sessions
            if self.calendar.session_close(day).to_pydatetime() <= cutoff
        ]
        if len(trading_dates) < 2:
            raise ServiceError("INSUFFICIENT_DATA", f"Not enough completed trading days for {symbol}.", 422)

        data = self.client.get_daily_data(symbol)
        if not isinstance(data, dict):
            raise ServiceError("UPSTREAM_FAILURE", f"Invalid Alpha Vantage response for {symbol}.", 502)
        check_alpha_vantage_error(data, symbol)
        prices = read_closing_prices(data, symbol, trading_dates)
        return calculate_returns_from_prices(prices, trading_dates, symbol, start, end)
