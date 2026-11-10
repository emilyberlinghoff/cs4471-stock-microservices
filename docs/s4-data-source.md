# S4: Alpha Vantage integration

Implements Service Task List **row 33** (connect S4 to its stock data source),
building on row 32's calculation core. `s4_service.fetch_moving_averages` fetches
unadjusted daily closing prices from Alpha Vantage and passes the requested
sessions and up to 49 preceding sessions to `calculate_moving_averages`.

## Setup and use

From the repository root, use Python 3.10+ (verified with Python 3.11):

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-s4.txt
export ALPHA_VANTAGE_API_KEY='your-own-key'
export ALPHA_VANTAGE_OUTPUTSIZE=full
python s4_service.py MSFT 2025-01-02 2025-12-31 --exchange NYSE
```

Use your own key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key).
`.env.example` lists configuration names; `.env` files are ignored by Git and
are **not loaded automatically**. Export the variables in your shell or configure
them in your deployment environment. Never commit a real API key.

Alpha Vantage's [daily endpoint documentation](https://www.alphavantage.co/documentation/#daily)
specifies that `TIME_SERIES_DAILY` returns raw, unadjusted daily observations.
`outputsize=full` requires a premium key and provides historical data, as needed
for arbitrary date intervals or the project's one-year history. Free keys can
use `ALPHA_VANTAGE_OUTPUTSIZE=compact`, which returns only the newest 100 daily
observations. Select a recent interval whose warm-up is also covered. The
integration returns `INSUFFICIENT_DATA` if compact data starts after the first
required warm-up session. It does not silently retry premium requests or claim
to supply a year of history from 100 prices.

Choose the actual exchange calendar explicitly using `--exchange` or the Python
function's `exchange` parameter. The default `NYSE` suits the project's US-listed
examples; it does not automatically identify arbitrary international exchanges
from a ticker. Calendar names come from `pandas_market_calendars`.

The same integration is callable by the [HTTP API](s4-api.md) or Python code:

```python
from s4_service import fetch_moving_averages
from s4_moving_averages import MovingAverageError

try:
    result = fetch_moving_averages("MSFT", "2025-01-02", "2025-12-31", exchange="NYSE")
except MovingAverageError as error:
    result = error.to_dict()
```

## Data handling and results

- One HTTPS `TIME_SERIES_DAILY` request per lookup, using `4. close`. Decimal
  strings retain precision until the existing core rounds final averages.
- Independent [exchange calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html)
  supply expected trading sessions, excluding weekends, holidays, and scheduled
  exceptional closures. A one-year calendar lookback supplies the preceding
  sessions; only the latest 49 are passed to the core. Returned price keys are
  never used to infer the calendar.
- Missing, invalid, or non-positive prices remain gaps. Affected moving averages
  are `null` with an insufficient-data reason. Other valid windows remain usable.
  Full history for a newly listed stock may legitimately have fewer warm-up
  observations. No valid window anywhere produces an insufficient-data error.
- Results retain the core's `symbol`, `start_date`, `end_date`, `price_basis`,
  and chronological `moving_averages`, plus `source: "Alpha Vantage"` and
  `exchange_calendar`. The price basis is `unadjusted_daily_close`.
- No synthetic data, implicit zero values, or stale-success fallback is used.
  Each request fetches anew; shared storage/caching policy remains a separate
  project task.

## Failures and verification

`StockDataError` extends `MovingAverageError`. Its `to_dict()` includes an error
`code`, `message`, and affected `symbol`. Codes include `CONFIGURATION_ERROR`,
`RATE_LIMITED`, `UNKNOWN_SYMBOL`, `UNAVAILABLE_DATA`, `UPSTREAM_TIMEOUT`,
`UPSTREAM_ERROR`, and `INSUFFICIENT_DATA`. Basic request/calendar errors use
`INVALID_INPUT`. Source exceptions and raw provider messages are never included
in responses because they can expose credentials. HTTP redirects are rejected.

Each upstream call has a 10-second requests timeout and no automatic retries.
This bounds socket inactivity; it is not a hard 15-second end-to-end deadline
against a continuously streaming response. Hard HTTP deadlines and registry
lifecycle (row 35) remain separate tasks. HTTP status mappings and consumer
validation (row 34) are implemented in the [S4 HTTP API](s4-api.md).
The CLI prints successful JSON to stdout and errors to stderr, exiting with code
1 for service errors.

```sh
python -m unittest discover -s tests -v
```

The 30 calculation/source tests run offline, covering the core plus mocked HTTP-to-SMA
integration, real exchange-calendar holidays, missing/invalid prices, compact
coverage, provider control messages, non-success HTTP statuses, bad JSON,
credential-safe errors, timeouts, and successful recovery on the next request.
Another 15 tests verify the HTTP API, for 45 tests in total.
Authenticated live retrieval requires your own entitled key and has not been
verified in the development environment.
