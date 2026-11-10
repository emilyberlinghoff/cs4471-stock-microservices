# S5 stock comparison core

Implements Service Task List **row 38**, Gantt task **5.05**, from
`02_Services_Requirements_and_Project_Plan.xlsx`. The module is independent of S4,
Flask, Alpha Vantage, and registry availability. Requires Python 3.10+ and no
third-party dependencies.

## Calculation contract

```python
from s5_stock_comparison import compare_stocks, StockComparisonError

prices = {
    "AAA": {"2025-01-17": "100", "2025-01-21": "110"},
    "BBB": {"2025-01-17": "200", "2025-01-21": "180"},
}
calendars = {symbol: ["2025-01-17", "2025-01-21"] for symbol in prices}
try:
    result = compare_stocks(
        ["AAA", "BBB"], "2025-01-17", "2025-01-21", prices,
        trading_dates=calendars,
    )
except StockComparisonError as error:
    result = error.to_dict()
```

These are synthetic fixtures, not market observations. The result is:

```json
{
  "service_id": "S5",
  "start_date": "2025-01-17",
  "end_date": "2025-01-21",
  "effective_start_date": "2025-01-17",
  "effective_end_date": "2025-01-21",
  "price_basis": "unadjusted_daily_close",
  "ranking": [
    {"symbol": "AAA", "percentage_change": 10.0},
    {"symbol": "BBB", "percentage_change": -10.0}
  ]
}
```

Supply 2–5 distinct symbols. Request symbols are stripped and uppercased; mapping
keys must already be uppercase. Histories contain unadjusted daily closing prices
in a consistent source price basis. Decimal strings preserve source precision.
The calculation is `100 * (end_close / start_close - 1)`; results express
percentage points, not decimal fractions. JSON numbers are rounded to four decimal
places without padding trailing zeroes.

Each symbol's calendar must come from an independent exchange calendar covering
the entire requested interval. Include all expected trading dates and exclude
weekends and exchange holidays. **Do not infer calendars from returned price keys**:
doing so would silently accept missing observations or a truncated upstream response.
Calendar completeness is the caller's responsibility; the core checks every
expected price against it. Calendars can differ between exchanges.

The core verifies finite positive prices on every expected session in the range,
including interior dates. It intersects the calendars and chooses the earliest
and latest common sessions. Fewer than two common sessions is an error. Data
outside the requested interval and entries outside expected sessions are not used.
Exact rational arithmetic preserves unrounded ordering, even when displayed
percentages round to the same value; exact ties use alphabetical symbol order.

Any unusable stock causes the entire comparison to fail, with no partial ranking
or substituted values. `StockComparisonError.to_dict()` returns an `error` object
containing `code`, `message`, and, for stock-specific failures, `symbol`.
Codes are `INVALID_INPUT`, `INVALID_DATA`, and `INSUFFICIENT_DATA`.
Full HTTP validation/status mapping and upstream error translation remain adapter
responsibilities.

## Verification and remaining integration

```sh
python3 -m unittest discover -s tests -v
```

Tests cover positive, negative, and zero changes; common endpoints; unrounded
ranking and exact ties; five-stock comparisons; missing, invalid, and truncated
data; weekends/holidays; input immutability; numerical precision; and structured
errors without partial rankings.

This implements the calculation portions of S5 FR3.2–FR6.2 with basic argument
checks. The Python function and result fields are a proposed internal contract
for the HTTP interface task. Alpha Vantage access and upstream errors (row 39)
are now implemented; see [data source setup and integration](s5-data-source.md).
The HTTP adapter and full validation (row 40), and registration/deregistration
(row 41) remain separate tasks. No cloud-performance or live-data claims are
made by the offline tests.
