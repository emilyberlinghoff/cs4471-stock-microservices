# S5: Alpha Vantage integration

Implements Service Task List **row 39**, connecting the S5 comparison core to
Alpha Vantage unadjusted daily closes. S5 runs independently of S4 and its PR.
The service-local adapter mirrors S4's source/error conventions; shared data
acquisition infrastructure remains a separate project task.

## Setup

From the repository root, use Python 3.10+ (verified with Python 3.11):

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-s5.txt
export ALPHA_VANTAGE_API_KEY='your-own-key'
export ALPHA_VANTAGE_OUTPUTSIZE=full
python s5_service.py MSFT,AAPL,GOOGL 2025-01-02 2025-12-31 --exchange NYSE
```

Use a key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key).
`.env.example` lists variable names. `.env` is ignored by Git and is not loaded
automatically; export the values or configure your deployment environment.
Never commit a real API key.

The [daily endpoint](https://www.alphavantage.co/documentation/#daily) returns
unadjusted observations. `full` history requires a premium key and supports the
project's one-year interval. Free keys support `ALPHA_VANTAGE_OUTPUTSIZE=compact`
for the latest 100 daily observations. Use a recent covered range with compact
mode. A truncated interval produces an error identifying the affected symbol,
not a ranking calculated over a silently shortened period. There is no retry
from full to compact and no synthetic fallback.

Each comparison uses 2–5 provider requests, one per distinct symbol, without
automatic retries or caching. These count against the key's quota. Requests
are made concurrently; quota responses fail the entire comparison explicitly.

## Python interface and calendars

```python
from s5_service import fetch_stock_comparison
from s5_stock_comparison import StockComparisonError

try:
    result = fetch_stock_comparison(
        ["MSFT", "SHOP.TRT"], "2025-01-02", "2025-12-31",
        exchange="NYSE", exchanges={"SHOP.TRT": "TSX"},
    )
except StockComparisonError as error:
    result = error.to_dict()
```

`exchange` is the default calendar, with optional per-symbol `exchanges`
overrides keyed by uppercase requested symbols. Set the actual exchange;
symbols do not automatically determine it. The CLI supports repeated overrides:

```sh
python s5_service.py MSFT,SHOP.TRT 2025-01-02 2025-12-31 \
  --exchange NYSE --symbol-exchange SHOP.TRT=TSX
```

Expected dates come from independent
[exchange calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html),
including exchange holidays and exceptional closures. Returned price keys are
never used to infer trading sessions. Every required session must have a finite,
positive close, including interior dates. Any invalid, missing, or unavailable
stock aborts the entire result. Stocks on different calendars use the earliest
and latest common sessions, with at least two common sessions required.

Prices retain source precision until the comparison core calculates changes.
Ranking uses unrounded changes, exact ties sort alphabetically, and returned
percentages round to four decimal places. Results retain the core's requested
dates, effective dates, `price_basis`, and `ranking`; integration adds
`source: "Alpha Vantage"` and an `exchange_calendars` mapping. See
[the core contract](s5-core.md) for result examples.

## Errors and timeouts

Errors use `StockComparisonError.to_dict()`: an `error` object containing
`code`, `message`, and the affected `symbol` where applicable. Upstream codes
include `CONFIGURATION_ERROR`, `RATE_LIMITED`, `UNKNOWN_SYMBOL`,
`UNAVAILABLE_DATA`, `UPSTREAM_ERROR`, and `UPSTREAM_TIMEOUT`. Core errors include
`INVALID_INPUT`, `INVALID_DATA`, and `INSUFFICIENT_DATA`. No error contains a
partial ranking, raw provider text, or request exception text that might expose
the API key. HTTP redirects are rejected.

All symbol lookups share a 12-second wait budget, rather than multiplying the
10-second per-call socket-inactivity timeout by the symbol count. Completed
errors are propagated without waiting for other symbols. Pending work is
cancelled where possible; already-running calls finish under their own socket
timeouts. A continuously streaming upstream response cannot be forcibly stopped
by thread cancellation, and CLI interpreter shutdown can wait for those workers.
The shared budget covers lookup waiting, not calendar generation or JSON output.
A hard process-level HTTP deadline remains part of deployment/HTTP integration.
Injected test clients must support concurrent calls.

The CLI prints successful JSON to stdout and errors to stderr, with exit code 1
for service errors. HTTP routes and consumer validation (row 40) are implemented;
see [the S5 HTTP API](s5-api.md). Registry lifecycle (row 41) remains separate.

## Verification

```sh
python -m unittest discover -s tests -v
```

The 35 core/source tests pass: 16 core tests and 19 integration tests. Coverage
includes mocked HTTP-to-ranking integration, five-stock retrieval, concurrency,
mixed exchange calendars, holidays, missing/interior/invalid observations,
compact coverage, provider and HTTP errors, credential redaction, timeouts,
recovery, and CLI exit behavior. An additional 15 HTTP tests bring the full suite
to 50 calculation/source/HTTP tests. Another 11 lifecycle tests bring the suite to 61. Authenticated live retrieval requires your own entitled key and is
not verified in this development environment. Cloud
performance has not been measured by these offline tests.
