"""S4 calculation core; independent of HTTP, data retrieval, and registration."""

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from math import isfinite


class MovingAverageError(ValueError):
    """An error that a future HTTP adapter can translate into a response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": str(self)}}


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise MovingAverageError(
            "INVALID_INPUT", f"Expected a YYYY-MM-DD date; received {value!r}."
        ) from None


def _price(value: object) -> Decimal | None:
    # Strings are accepted so a data adapter can preserve source precision.
    if isinstance(value, bool):
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price <= 0:
        return None
    # Results are JSON numbers, so require prices representable as finite floats.
    if not isfinite(float(price)):
        return None
    return price


def _average(window: list[Decimal | None], size: int) -> tuple[float | None, dict | None]:
    if len(window) < size:
        message = f"Need {size} consecutive trading-day prices; history is too short."
    elif any(price is None for price in window):
        message = f"The {size}-trading-day window contains a missing or invalid price."
    else:
        # No intermediate rounding; round only the completed arithmetic mean.
        with localcontext() as context:
            context.prec = 340
            average = sum(window, Decimal(0)) / Decimal(size)
            return float(round(average, 4)), None
    return None, {"code": "INSUFFICIENT_DATA", "message": message}


def calculate_moving_averages(
    symbol: str,
    start_date: str,
    end_date: str,
    closing_prices: Mapping[str, object],
    *,
    trading_dates: Iterable[str],
) -> dict:
    """Calculate trailing 20/50-day means for dates in the requested interval.

    ``closing_prices`` maps YYYY-MM-DD dates to unadjusted daily closing prices.
    ``trading_dates`` must enumerate the exchange's expected trading sessions,
    including up to 49 sessions before start_date and every session through
    end_date. It must come from a trusted exchange calendar, not be inferred
    from the returned price keys: an absent session's price breaks a window,
    whereas weekends and exchange holidays do not belong in the calendar.

    Missing/invalid prices occupy their session and never shorten a window.
    Inputs are neither mutated nor fetched. Results contain only requested
    sessions, in date order, with nulls and reasons for unavailable averages.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise MovingAverageError("INVALID_INPUT", "A non-empty stock symbol is required.")
    symbol = symbol.strip().upper()
    start, end = _parse_date(start_date), _parse_date(end_date)
    if start > end:
        raise MovingAverageError("INVALID_INPUT", "start_date must not be after end_date.")

    sessions = [_parse_date(value) for value in trading_dates]
    if len(set(sessions)) != len(sessions):
        raise MovingAverageError("INVALID_INPUT", "trading_dates contains duplicate sessions.")
    sessions.sort()
    # Retain only the warm-up observations that can affect the first result.
    preceding = [session for session in sessions if session < start][-49:]
    requested = [session for session in sessions if start <= session <= end]
    history: list[Decimal | None] = []
    results = []
    has_average = False
    for session in preceding + requested:
        history.append(_price(closing_prices.get(session.isoformat())))
        history = history[-50:]
        if session < start:
            continue
        sma_20, reason_20 = _average(history[-20:], 20)
        sma_50, reason_50 = _average(history, 50)
        has_average |= sma_20 is not None or sma_50 is not None
        results.append({
            "date": session.isoformat(),
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_20_reason": reason_20,
            "sma_50_reason": reason_50,
        })

    if not has_average:
        raise MovingAverageError(
            "INSUFFICIENT_DATA",
            f"No complete 20- or 50-trading-day window exists for {symbol} "
            f"between {start_date} and {end_date}.",
        )
    return {
        "service_id": "S4",
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "price_basis": "unadjusted_daily_close",
        "moving_averages": results,
    }
