"""Fetch Alpha Vantage daily closes and compare 2–5 stocks over common dates."""

import argparse
import json
import sys
from collections.abc import Mapping
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import date

import pandas_market_calendars as mcal

from s5_alpha_vantage import AlphaVantageClient
from s5_stock_comparison import StockComparisonError, _parse_date, compare_stocks


LOOKUP_TIMEOUT_SECONDS = 12


def _fetch_histories(symbols, client):
    # The default client makes independent requests, not a shared requests.Session.
    # Injected clients must support concurrent fetch_daily_closes calls.
    pool = ThreadPoolExecutor(max_workers=len(symbols))
    futures = {}
    try:
        futures = {symbol: pool.submit(client.fetch_daily_closes, symbol) for symbol in symbols}
        done, pending = wait(futures.values(), timeout=LOOKUP_TIMEOUT_SECONDS, return_when=FIRST_EXCEPTION)
        # Propagate a completed upstream error before reporting pending work.
        for future in futures.values():
            if future in done and future.exception() is not None:
                future.result()
        if pending:
            affected = next(symbol for symbol in symbols if futures[symbol] in pending)
            raise StockComparisonError(
                "UPSTREAM_TIMEOUT", f"Stock-data lookup deadline exceeded for {affected}.", affected
            )
        return {symbol: future.result() for symbol, future in futures.items()}
    finally:
        for future in futures.values():
            future.cancel()
        # Do not extend the caller's wait for other requests after an error.
        # Already-running HTTP calls finish under their own inactivity timeout.
        pool.shutdown(wait=False, cancel_futures=True)


def fetch_stock_comparison(
    symbols, start_date: str, end_date: str, *, exchange="NYSE", exchanges=None, client=None
) -> dict:
    """Retrieve and compare daily closes using independent exchange calendars.

    ``exchange`` is the default calendar for every stock. ``exchanges`` can
    override it per uppercase symbol, e.g. {"SHOP.TRT": "TSX"}. Exchange identity
    is explicit, never guessed from a symbol or from returned price dates.
    """
    if isinstance(symbols, (str, bytes)) or symbols is None:
        raise StockComparisonError("INVALID_INPUT", "Supply 2–5 distinct stock symbols.")
    try:
        symbols = list(symbols)
    except TypeError:
        raise StockComparisonError("INVALID_INPUT", "Supply 2–5 distinct stock symbols.") from None
    if not 2 <= len(symbols) <= 5 or any(not isinstance(s, str) or not s.strip() for s in symbols):
        raise StockComparisonError("INVALID_INPUT", "Supply 2–5 distinct stock symbols.")
    symbols = [symbol.strip().upper() for symbol in symbols]
    if len(set(symbols)) != len(symbols):
        raise StockComparisonError("INVALID_INPUT", "Stock symbols must be distinct.")
    start, end = _parse_date(start_date), _parse_date(end_date)
    if start > end or end > date.today():
        raise StockComparisonError("INVALID_INPUT", "Dates must be ordered and must not be in the future.")
    exchanges = {} if exchanges is None else exchanges
    if not isinstance(exchanges, Mapping) or any(symbol not in symbols for symbol in exchanges):
        raise StockComparisonError("INVALID_INPUT", "Exchange overrides must use requested uppercase symbols.")

    calendars, calendar_names, cached = {}, {}, {}
    for symbol in symbols:
        name = exchanges.get(symbol, exchange)
        if not isinstance(name, str) or not name:
            raise StockComparisonError("INVALID_INPUT", f"An exchange calendar is required for {symbol}.", symbol)
        if name not in cached:
            try:
                calendar = mcal.get_calendar(name)
                cached[name] = [day.date().isoformat() for day in calendar.valid_days(start_date=start, end_date=end)]
            except (RuntimeError, ValueError, KeyError, OverflowError):
                raise StockComparisonError("INVALID_INPUT", f"Invalid calendar or date range for {symbol}: {name}.", symbol) from None
        calendars[symbol] = cached[name]
        calendar_names[symbol] = name
        if not calendars[symbol]:
            raise StockComparisonError("INSUFFICIENT_DATA", f"No trading sessions for {symbol} in the requested interval.", symbol)
    common = set(calendars[symbols[0]])
    for symbol in symbols[1:]:
        common.intersection_update(calendars[symbol])
    if len(common) < 2:
        raise StockComparisonError("INSUFFICIENT_DATA", "At least two common trading dates are required for comparison.")

    client = client if client is not None else AlphaVantageClient()
    histories = _fetch_histories(symbols, client)
    for symbol in symbols:
        prices = histories[symbol]
        if client.outputsize == "compact" and min(prices) > calendars[symbol][0]:
            raise StockComparisonError(
                "INSUFFICIENT_DATA",
                f"Compact Alpha Vantage history does not cover the requested interval for {symbol}. "
                "Use a covered recent range or full history with an entitled key.", symbol,
            )
        histories[symbol] = {day: prices[day] for day in calendars[symbol] if day in prices}
    result = compare_stocks(symbols, start_date, end_date, histories, trading_dates=calendars)
    result["source"] = "Alpha Vantage"
    result["exchange_calendars"] = calendar_names
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare stocks using Alpha Vantage daily closes.")
    parser.add_argument("symbols", help="2–5 comma-separated stock symbols")
    parser.add_argument("start_date", help="YYYY-MM-DD")
    parser.add_argument("end_date", help="YYYY-MM-DD")
    parser.add_argument("--exchange", default="NYSE", help="Default exchange calendar (default: NYSE)")
    parser.add_argument("--symbol-exchange", action="append", default=[], metavar="SYMBOL=CALENDAR",
                        help="Per-symbol exchange override; may be repeated")
    args = parser.parse_args(argv)
    try:
        overrides = {}
        for item in args.symbol_exchange:
            symbol, separator, calendar = item.partition("=")
            symbol = symbol.strip().upper()
            if not separator or not symbol or not calendar.strip() or symbol in overrides:
                raise StockComparisonError("INVALID_INPUT", "Use distinct SYMBOL=CALENDAR exchange overrides.")
            overrides[symbol] = calendar.strip()
        result = fetch_stock_comparison(args.symbols.split(","), args.start_date, args.end_date,
                                        exchange=args.exchange, exchanges=overrides)
    except StockComparisonError as error:
        print(json.dumps(error.to_dict(), allow_nan=False), file=sys.stderr)
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
