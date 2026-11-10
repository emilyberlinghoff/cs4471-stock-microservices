"""S5 calculation core, independent of HTTP, retrieval, and other services."""

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from math import isfinite


class StockComparisonError(ValueError):
    """A calculation failure that an HTTP adapter can serialize."""

    def __init__(self, code: str, message: str, symbol: str | None = None):
        super().__init__(message)
        self.code = code
        self.symbol = symbol

    def to_dict(self) -> dict:
        error = {"code": self.code, "message": str(self)}
        if self.symbol is not None:
            error["symbol"] = self.symbol
        return {"error": error}


def _parse_date(value: str, *, code="INVALID_INPUT", symbol=None) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise StockComparisonError(
            code, f"Expected a YYYY-MM-DD date; received {value!r}.", symbol
        ) from None


def _price(value: object, symbol: str, session: date) -> Fraction:
    try:
        if isinstance(value, bool):
            raise ValueError
        price = Decimal(str(value))
        if not price.is_finite() or price <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        raise StockComparisonError(
            "INVALID_DATA", f"Invalid closing price for {symbol} on {session}.", symbol
        ) from None
    return Fraction(price)


def compare_stocks(
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
    closing_prices: Mapping[str, Mapping[str, object]],
    *,
    trading_dates: Mapping[str, Iterable[str]],
) -> dict:
    """Rank 2–5 stocks by percentage price change over common endpoints.

    Price and calendar mappings use uppercase symbols. Price histories map
    YYYY-MM-DD dates to unadjusted closing prices (numbers or decimal strings).
    Each calendar must independently enumerate every expected exchange session
    in the requested interval, excluding weekends and holidays. Do not derive
    calendars from returned price keys: that would hide truncated histories.

    All expected prices in the interval must be present and valid. The common
    endpoints are the earliest/latest sessions shared by every stock. Ranking
    uses exact rational changes; only returned percentages are rounded. Inputs
    are not mutated and no upstream requests or fallback data are used.
    """
    if isinstance(symbols, (str, bytes)) or symbols is None:
        raise StockComparisonError("INVALID_INPUT", "Supply 2–5 distinct stock symbols.")
    symbols = list(symbols)
    if not 2 <= len(symbols) <= 5 or any(
        not isinstance(symbol, str) or not symbol.strip() for symbol in symbols
    ):
        raise StockComparisonError("INVALID_INPUT", "Supply 2–5 distinct stock symbols.")
    symbols = [symbol.strip().upper() for symbol in symbols]
    if len(set(symbols)) != len(symbols):
        raise StockComparisonError("INVALID_INPUT", "Stock symbols must be distinct.")
    start, end = _parse_date(start_date), _parse_date(end_date)
    if start > end:
        raise StockComparisonError("INVALID_INPUT", "start_date must not be after end_date.")
    if end > date.today():
        raise StockComparisonError("INVALID_INPUT", "Requested dates must not be in the future.")

    histories = {}
    common_dates = None
    for symbol in symbols:
        prices = closing_prices.get(symbol)
        calendar = trading_dates.get(symbol)
        if not isinstance(prices, Mapping) or calendar is None:
            raise StockComparisonError(
                "INSUFFICIENT_DATA", f"Missing price history or trading calendar for {symbol}.", symbol
            )
        sessions = [_parse_date(day, code="INVALID_DATA", symbol=symbol) for day in calendar]
        if len(set(sessions)) != len(sessions):
            raise StockComparisonError(
                "INVALID_DATA", f"Duplicate trading-calendar dates for {symbol}.", symbol
            )
        expected = sorted(day for day in sessions if start <= day <= end)
        if not expected:
            raise StockComparisonError(
                "INSUFFICIENT_DATA", f"No trading sessions in the requested range for {symbol}.", symbol
            )
        history = {}
        for session in expected:
            key = session.isoformat()
            if key not in prices:
                raise StockComparisonError(
                    "INSUFFICIENT_DATA", f"Missing closing price for {symbol} on {session}.", symbol
                )
            history[session] = _price(prices[key], symbol, session)
        histories[symbol] = history
        common_dates = set(history) if common_dates is None else common_dates.intersection(history)

    if len(common_dates) < 2:
        raise StockComparisonError(
            "INSUFFICIENT_DATA", "At least two common trading dates are required for comparison."
        )
    first, last = min(common_dates), max(common_dates)
    changes = [
        (symbol, 100 * (histories[symbol][last] / histories[symbol][first] - 1))
        for symbol in symbols
    ]
    changes.sort(key=lambda item: (-item[1], item[0]))
    ranking = []
    for symbol, change in changes:
        try:
            rounded = float(round(change, 4))
            if not isfinite(rounded):
                raise OverflowError
        except OverflowError:
            raise StockComparisonError(
                "INVALID_DATA", f"Percentage change for {symbol} exceeds the JSON numeric range.", symbol
            ) from None
        ranking.append({"symbol": symbol, "percentage_change": rounded})
    return {
        "service_id": "S5",
        "start_date": start_date,
        "end_date": end_date,
        "effective_start_date": first.isoformat(),
        "effective_end_date": last.isoformat(),
        "price_basis": "unadjusted_daily_close",
        "ranking": ranking,
    }
