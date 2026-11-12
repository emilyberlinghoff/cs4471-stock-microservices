"""Retrieve Alpha Vantage history and feed S4's moving-average core.

Run ``python s4_service.py SYMBOL START_DATE END_DATE --exchange NYSE``.
HTTP routes are in s4_app.py. Registry lifecycle remains a separate task.
"""

import argparse
import json
import sys
from datetime import date, timedelta

import pandas_market_calendars as mcal

from alpha_vantage import AlphaVantageClient, StockDataError
from s4_moving_averages import MovingAverageError, _parse_date, calculate_moving_averages
from s4_validation import InputValidationError, validate_inputs


def trading_sessions(start: date, end: date, exchange: str) -> list[str]:
    """Return requested sessions and at most 49 preceding exchange sessions."""
    try:
        calendar = mcal.get_calendar(exchange)
    except (RuntimeError, ValueError, KeyError):
        raise InputValidationError("exchange must name a supported exchange calendar.", "exchange") from None
    # A full year supplies sufficient lookback for normal exchange schedules.
    # The returned list retains only the 49 sessions needed by the SMA core.
    try:
        lookback = max(date.min, start - timedelta(days=min(366, start.toordinal() - 1)))
        days = [day.date().isoformat() for day in calendar.valid_days(start_date=lookback, end_date=end)]
    except (ValueError, OverflowError):
        raise MovingAverageError("INVALID_INPUT", "Date range is unsupported by the exchange calendar.") from None
    prior = [day for day in days if day < start.isoformat()][-49:]
    return prior + [day for day in days if day >= start.isoformat()]


def fetch_moving_averages(
    symbol: str, start_date: str, end_date: str, *, exchange: str = "NYSE", client=None
) -> dict:
    """Fetch unadjusted closes, retain gaps, and calculate requested SMAs.

    Explicitly select the symbol's exchange calendar. NYSE is the default for
    the project's US-listed examples; no exchange is inferred from a ticker.
    """
    inputs = validate_inputs(symbol, start_date, end_date, exchange)
    symbol, exchange = inputs["symbol"], inputs["exchange"]
    start, end = _parse_date(start_date), _parse_date(end_date)
    try:
        sessions = trading_sessions(start, end, exchange)
    except InputValidationError as error:
        error.symbol = symbol
        raise
    requested = [day for day in sessions if day >= start_date]
    if not requested:
        raise StockDataError("INSUFFICIENT_DATA", f"No trading sessions in the requested interval for {symbol}.", symbol)

    client = client if client is not None else AlphaVantageClient()
    prices = client.fetch_daily_closes(symbol)
    # A compact response contains only the newest 100 observations. Refuse to
    # interpret a short response as a complete historical/warm-up dataset.
    if client.outputsize == "compact" and min(prices) > sessions[0]:
        raise StockDataError(
            "INSUFFICIENT_DATA",
            f"Compact Alpha Vantage history does not cover the requested interval and 49-session warm-up for {symbol}. "
            "Use a covered recent range or full history with an entitled key.",
            symbol,
        )
    selected = {day: prices[day] for day in sessions if day in prices}
    try:
        result = calculate_moving_averages(
            symbol, start_date, end_date, selected, trading_dates=sessions
        )
    except MovingAverageError as error:
        raise StockDataError(error.code, str(error), symbol) from None
    result["source"] = "Alpha Vantage"
    result["exchange_calendar"] = exchange
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Calculate S4 moving averages using Alpha Vantage daily closes.")
    parser.add_argument("symbol")
    parser.add_argument("start_date", help="YYYY-MM-DD")
    parser.add_argument("end_date", help="YYYY-MM-DD")
    parser.add_argument("--exchange", default="NYSE", help="pandas_market_calendars exchange name (default: NYSE)")
    args = parser.parse_args(argv)
    try:
        result = fetch_moving_averages(args.symbol, args.start_date, args.end_date, exchange=args.exchange)
    except MovingAverageError as error:
        print(json.dumps(error.to_dict(), allow_nan=False), file=sys.stderr)
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
