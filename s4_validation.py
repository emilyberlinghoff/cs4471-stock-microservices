"""Shared S4 input validation for the Python integration, CLI, and HTTP API."""

import re
from datetime import date

from s4_moving_averages import MovingAverageError


class InputValidationError(MovingAverageError):
    def __init__(self, message: str, field: str, symbol=None):
        super().__init__("INVALID_INPUT", message)
        self.field = field
        self.symbol = symbol

    def to_dict(self):
        payload = super().to_dict()
        payload["error"]["field"] = self.field
        if self.symbol is not None:
            payload["error"]["symbol"] = self.symbol
        return payload


def validate_inputs(symbol, start_date, end_date, exchange="NYSE") -> dict:
    if not isinstance(symbol, str) or not symbol.strip():
        raise InputValidationError("Provide one non-empty stock symbol as a string.", "symbol")
    symbol = symbol.strip().upper()
    # Permit international numeric tickers, class/suffix dots, hyphens, and
    # index prefixes. Commas/whitespace cannot encode multiple stock symbols.
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_-]{0,63}", symbol, flags=re.ASCII):
        raise InputValidationError("Provide one stock symbol of at most 64 characters, without spaces or commas.", "symbol")
    parsed = {}
    for field, value in (("start_date", start_date), ("end_date", end_date)):
        try:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError
            parsed[field] = date.fromisoformat(value)
        except ValueError:
            raise InputValidationError(f"{field} must be a valid date in YYYY-MM-DD format.", field, symbol) from None
        if parsed[field] > date.today():
            raise InputValidationError(f"{field} must not be later than the request date.", field, symbol)
    if parsed["start_date"] > parsed["end_date"]:
        raise InputValidationError("end_date must be on or after start_date.", "end_date", symbol)
    if not isinstance(exchange, str) or not exchange.strip() or len(exchange.strip()) > 64:
        raise InputValidationError("exchange must be a non-empty calendar name of at most 64 characters.", "exchange", symbol)
    return {"symbol": symbol, "start_date": start_date, "end_date": end_date, "exchange": exchange.strip()}
