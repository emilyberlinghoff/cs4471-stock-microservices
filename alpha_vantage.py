"""Alpha Vantage daily-close adapter. Credentials are never returned in errors."""

import os
from collections.abc import Mapping
from datetime import date

import requests

from s4_moving_averages import MovingAverageError


class StockDataError(MovingAverageError):
    def __init__(self, code: str, message: str, symbol: str):
        super().__init__(code, message)
        self.symbol = symbol

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["error"]["symbol"] = self.symbol
        return result


class AlphaVantageClient:
    """One request per lookup, no retries or synthetic fallback observations.

    ``full`` supports historical intervals and requires a premium Alpha Vantage
    key. ``compact`` is configurable for recent intervals supported by free keys.
    """

    URL = "https://www.alphavantage.co/query"
    TIMEOUT_SECONDS = 10

    def __init__(self, api_key=None, *, outputsize=None, session=None):
        self._api_key = api_key if api_key is not None else os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.outputsize = outputsize if outputsize is not None else os.getenv(
            "ALPHA_VANTAGE_OUTPUTSIZE", "full"
        )
        self._session = session if session is not None else requests

    def fetch_daily_closes(self, symbol: str) -> dict[str, object]:
        if not isinstance(self._api_key, str) or not self._api_key.strip():
            raise StockDataError(
                "CONFIGURATION_ERROR", "Set ALPHA_VANTAGE_API_KEY before retrieving stock data.", symbol
            )
        if self.outputsize not in ("full", "compact"):
            raise StockDataError(
                "CONFIGURATION_ERROR", "ALPHA_VANTAGE_OUTPUTSIZE must be full or compact.", symbol
            )
        try:
            response = self._session.get(
                self.URL,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "apikey": self._api_key.strip(),
                    "outputsize": self.outputsize,
                    "datatype": "json",
                },
                timeout=self.TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise StockDataError("UPSTREAM_TIMEOUT", f"Alpha Vantage timed out for {symbol}.", symbol) from None
        except requests.exceptions.RequestException:
            # Request exception strings can include the full URL and API key.
            raise StockDataError("UPSTREAM_ERROR", f"Alpha Vantage request failed for {symbol}.", symbol) from None
        try:
            if response.status_code == 429:
                raise StockDataError("RATE_LIMITED", f"Alpha Vantage request limit reached for {symbol}.", symbol)
            if response.status_code != 200:
                raise StockDataError("UPSTREAM_ERROR", f"Alpha Vantage returned HTTP {response.status_code} for {symbol}.", symbol)
            try:
                payload = response.json()
            except ValueError:
                raise StockDataError("UPSTREAM_ERROR", f"Alpha Vantage returned invalid JSON for {symbol}.", symbol) from None
        finally:
            response.close()

        if not isinstance(payload, Mapping):
            raise StockDataError("UPSTREAM_ERROR", f"Unexpected Alpha Vantage response for {symbol}.", symbol)
        # Inspect control messages before time-series data. Never echo upstream
        # text: it can contain account details or credentials.
        if "Note" in payload:
            raise StockDataError("RATE_LIMITED", f"Alpha Vantage request limit reached for {symbol}.", symbol)
        if "Information" in payload:
            message = str(payload["Information"]).lower()
            if any(word in message for word in ("rate", "limit", "frequency", "requests per")):
                code, explanation = "RATE_LIMITED", "request limit reached"
            elif any(word in message for word in ("premium", "apikey", "api key", "demo")):
                code, explanation = "CONFIGURATION_ERROR", "key or endpoint entitlement is insufficient"
            else:
                code, explanation = "UPSTREAM_ERROR", "returned an informational error"
            raise StockDataError(code, f"Alpha Vantage {explanation} for {symbol}.", symbol)
        if "Error Message" in payload:
            raise StockDataError("UNKNOWN_SYMBOL", f"Alpha Vantage rejected stock symbol {symbol}.", symbol)

        metadata = payload.get("Meta Data")
        if isinstance(metadata, Mapping) and "2. Symbol" in metadata:
            if str(metadata["2. Symbol"]).upper() != symbol.upper():
                raise StockDataError("UPSTREAM_ERROR", f"Alpha Vantage returned a different symbol for {symbol}.", symbol)
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, Mapping) or not series:
            raise StockDataError("UNAVAILABLE_DATA", f"No daily closing prices available for {symbol}.", symbol)
        closes = {}
        for day, observation in series.items():
            try:
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError
            except (TypeError, ValueError):
                raise StockDataError("UPSTREAM_ERROR", f"Invalid daily observation date returned for {symbol}.", symbol) from None
            # Missing/malformed closes retain their trading session as invalid.
            # The core then reports incomplete windows instead of skipping gaps.
            closes[day] = observation.get("4. close") if isinstance(observation, Mapping) else None
        return dict(sorted(closes.items()))
