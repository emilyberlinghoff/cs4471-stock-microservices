"""S5 input checks shared by the HTTP API, CLI, and Python integration."""

import re
from collections.abc import Mapping
from datetime import date

from s5_stock_comparison import StockComparisonError


class InputValidationError(StockComparisonError):
    def __init__(self, message, field, symbol=None):
        super().__init__("INVALID_INPUT", message, symbol)
        self.field = field

    def to_dict(self):
        payload = super().to_dict()
        payload["error"]["field"] = self.field
        return payload


def _calendar(value, field, symbol=None):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 64:
        raise InputValidationError("Provide a non-empty calendar name of at most 64 characters.", field, symbol)
    return value.strip()


def validate_inputs(symbols, start_date, end_date, exchange="NYSE", exchanges=None):
    if isinstance(symbols, (str, bytes, Mapping)) or symbols is None:
        raise InputValidationError("Provide 2–5 distinct stock symbols as a list.", "symbols")
    try:
        symbols = list(symbols)
    except TypeError:
        raise InputValidationError("Provide 2–5 distinct stock symbols as a list.", "symbols") from None
    if not 2 <= len(symbols) <= 5:
        raise InputValidationError("Provide 2–5 distinct stock symbols.", "symbols")
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_-]{0,63}", symbol.strip().upper(), flags=re.ASCII):
            raise InputValidationError("Each stock symbol must be a string of 1–64 ASCII ticker characters without spaces or commas.", "symbols")
        normalized.append(symbol.strip().upper())
    if len(set(normalized)) != len(normalized):
        raise InputValidationError("Stock symbols must be distinct after normalization.", "symbols")
    parsed = {}
    for field, value in (("start_date", start_date), ("end_date", end_date)):
        try:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError
            parsed[field] = date.fromisoformat(value)
        except ValueError:
            raise InputValidationError(f"{field} must be a valid YYYY-MM-DD date.", field) from None
        if parsed[field] > date.today():
            raise InputValidationError(f"{field} must not be later than the request date.", field)
    if parsed["start_date"] > parsed["end_date"]:
        raise InputValidationError("end_date must be on or after start_date.", "end_date")
    exchange = _calendar(exchange, "exchange")
    if exchanges is None:
        exchanges = {}
    if not isinstance(exchanges, Mapping):
        raise InputValidationError("exchanges must be an object mapping requested symbols to calendars.", "exchanges")
    overrides = {}
    for key, value in exchanges.items():
        if not isinstance(key, str) or key.strip().upper() not in normalized:
            raise InputValidationError("Exchange overrides must refer to requested symbols.", "exchanges")
        symbol = key.strip().upper()
        if symbol in overrides:
            raise InputValidationError("Exchange override symbols must be distinct after normalization.", "exchanges", symbol)
        overrides[symbol] = _calendar(value, "exchanges", symbol)
    return {"symbols": normalized, "start_date": start_date, "end_date": end_date,
            "exchange": exchange, "exchanges": overrides}
